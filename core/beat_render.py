"""Local-only media verification and horizontal render with text baked by Pillow."""
import json
import os
import subprocess
import warnings
from core.beat_http import BeatError
from core.beat_download import duration, MAX_AUDIO, audio_type
from core.ffmpeg_util import resolve_tool


class MediaTools:
    def __init__(self, ffmpeg=None, ffprobe=None, run=subprocess.run):
        self.ffmpeg = ffmpeg or resolve_tool('ffmpeg')
        self.ffprobe = ffprobe or resolve_tool('ffprobe')
        self.run = run

    def _call(self, command, timeout, capture=False):
        if not command[0]:
            raise BeatError('media_tool_missing')
        # Credentials do not reach subprocesses; stdout/stderr stay out of logs.
        env = {k: v for k, v in os.environ.items() if not any(
            word in k.upper() for word in ('TOKEN', 'SECRET', 'KEY', 'PASSWORD'))}
        try:
            result = self.run(command, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, timeout=timeout, env=env)
            if result.returncode:
                raise BeatError('media_validation_failed')
            return result.stdout if capture else None
        except BeatError:
            raise
        except Exception:
            raise BeatError('media_process_failed') from None

    def verify_audio(self, path, expected):
        if not 0 < path.stat().st_size <= MAX_AUDIO:
            raise BeatError('download_limit')
        with path.open('rb') as stream:
            demuxer = audio_type(stream.read(512))
        try:
            data = json.loads(self._call([self.ffprobe, '-v', 'error', '-protocol_whitelist', 'file',
                '-f', demuxer, '-show_entries', 'format=duration:stream=codec_type,codec_name',
                '-of', 'json', str(path)], 30, True))
            streams = data['streams']
            if len(streams) != 1 or streams[0]['codec_type'] != 'audio':
                raise BeatError('audio_stream_rejected')
            seconds = duration(float(data['format']['duration']))
            if abs(seconds - duration(expected)) > max(3, expected * .03):
                raise BeatError('duration_mismatch')
        except BeatError:
            raise
        except Exception:
            raise BeatError('audio_probe_failed') from None
        self._call([self.ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-protocol_whitelist', 'file',
                    '-f', demuxer, '-i', str(path), '-map', '0:a:0', '-f', 'null', '-'], 180)
        return seconds

    def render(self, audio, frame, output, seconds):
        duration(seconds)
        with audio.open('rb') as stream:
            demuxer = audio_type(stream.read(512))
        self._call([self.ffmpeg, '-nostdin', '-v', 'error', '-y', '-loop', '1',
                    '-framerate', '30',
                    '-protocol_whitelist', 'file', '-i', str(frame),
                    '-protocol_whitelist', 'file', '-f', demuxer, '-i', str(audio),
                    '-map', '0:v:0', '-map', '1:a:0', '-vf', 'format=yuv420p',
                    '-t', str(seconds), '-c:v', 'libx264', '-preset', 'fast',
                    '-c:a', 'aac', '-movflags', '+faststart', str(output)], 1200)
        if not output.is_file() or output.stat().st_size == 0:
            raise BeatError('render_output_missing')


def compose(image, title, frame, thumbnail):
    from PIL import Image, ImageOps, ImageDraw, ImageFont
    if not isinstance(title, str) or not title.strip() or len(title) > 500:
        raise BeatError('title_rejected')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(image) as source:
                if (source.format not in {'JPEG', 'PNG', 'WEBP'} or source.width * source.height > 25_000_000
                        or source.width < 320 or source.height < 180 or getattr(source, 'n_frames', 1) != 1):
                    raise BeatError('image_rejected')
                source.load()
                picture = ImageOps.fit(ImageOps.exif_transpose(source).convert('RGB'), (1920, 1080))
                picture.info.clear()
        draw = ImageDraw.Draw(picture)
        draw.rectangle((0, 780, 1920, 1080), fill=(15, 15, 20))
        # A bundled/system font may be supplied later; Pillow's default is portable.
        try:
            font = ImageFont.truetype('DejaVuSans.ttf', 58)
        except OSError:
            try:
                font = ImageFont.load_default(size=58)
            except TypeError:
                font = ImageFont.load_default()
        words, lines, line = title.split(), [], ''
        for word in words:
            trial = (line + ' ' + word).strip()
            if draw.textlength(trial, font=font) > 1740:
                if line:
                    lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
        visible = lines[:3]
        for i, value in enumerate(visible):
            while value and draw.textlength(value, font=font) > 1740:
                value = value[:-1]
            visible[i] = value
        if len(lines) > 3:
            value = visible[-1]
            while value and draw.textlength(value + '...', font=font) > 1740:
                value = value[:-1]
            visible[-1] = value + '...'
        text = '\n'.join(visible)
        draw.multiline_text((90, 815), text, font=font, fill='white', spacing=12)
        picture.save(frame, 'PNG')
        picture.resize((1280, 720)).save(thumbnail, 'JPEG', quality=90)
    except BeatError:
        raise
    except Exception:
        raise BeatError('image_decode_failed') from None
