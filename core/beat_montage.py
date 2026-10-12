"""Short silent normalized clips, concat sequence and a beat-length loop."""
import hashlib
import json
import math
import random
from decimal import Decimal
from core.beat_download import audio_type, duration
from core.beat_http import BeatError
from core.beat_visual import fetch, MAX_VIDEO_BYTES

FPS = 30
NORMALIZE = 'scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,fps=30,format=yuv420p,setpts=PTS-STARTPTS'


def video_info(path, tools):
    with path.open('rb') as stream:
        header = stream.read(16)
    if len(header) >= 8 and header[4:8] in (b'ftyp', b'moov', b'mdat', b'wide', b'free'):
        demuxer = 'mov'
    elif header.startswith(b'\x1aE\xdf\xa3'):
        demuxer = 'matroska'
    else:
        raise BeatError('video_type_rejected')
    try:
        info = json.loads(tools._call([tools.ffprobe, '-v', 'error', '-protocol_whitelist', 'file',
            '-f', demuxer, '-show_entries',
            'format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate',
            '-of', 'json', str(path)], 30, True))
        streams = [row for row in info['streams'] if row['codec_type'] == 'video']
        if len(streams) != 1:
            raise BeatError('video_stream_rejected')
        video = streams[0]
        seconds = float(info['format']['duration'])
        rate = video['avg_frame_rate'].split('/')
        fps = int(rate[0]) / int(rate[1])
        if (video['codec_name'] not in {'h264', 'hevc', 'vp8', 'vp9', 'av1', 'mpeg4', 'prores', 'mjpeg'}
                or not math.isfinite(seconds) or not .5 <= seconds <= 3600
                or not 1 <= fps <= 120 or not 16 <= video['width'] <= 7680
                or not 16 <= video['height'] <= 4320):
            raise BeatError('video_incompatible')
        return seconds, demuxer
    except BeatError:
        raise
    except Exception:
        raise BeatError('video_probe_failed') from None


def loop_plan(clips, seconds):
    """Exact timeline, including the truncated final clip; stable loop boundary."""
    duration(seconds)
    if not clips:
        raise BeatError('video_catalog_empty')
    remaining = Decimal(str(seconds))
    result, index = [], 0
    while remaining > 0:
        clip = clips[index % len(clips)]
        available = Decimal(str(clip['seconds']))
        if available <= 0:
            raise BeatError('invalid_clip_duration')
        take = min(available, remaining)
        result.append(dict(clip, seconds=float(take)))
        remaining -= take
        index += 1
    return result


def render_montage(audio, output, seconds, rows, spec, root, dropbox, tools, job_id, checkpoint=lambda: None):
    duration(seconds)
    rng = random.Random(int.from_bytes(hashlib.sha256(job_id.encode()).digest()[:8], 'big'))
    rows = list({row['path']: row for row in rows}.values())
    rng.shuffle(rows)
    clips, skipped, total_bytes = [], 0, 0
    for index, row in enumerate(rows[:12]):
        checkpoint()
        if total_bytes + row['size'] > 512 * 1024 * 1024:
            continue
        source, clip = root / f'source-{index}.bin', root / f'clip-{index}.mp4'
        total_bytes += row['size']
        fetch(row, source, MAX_VIDEO_BYTES, dropbox)
        try:
            available, demuxer = video_info(source, tools)
            if available < spec['clip_min_seconds']:
                raise BeatError('video_too_short')
            # Whole frames avoid concat boundary gaps from fractional clip lengths.
            minimum = math.ceil(spec['clip_min_seconds'] * FPS)
            maximum = math.floor(min(available, spec['clip_max_seconds']) * FPS)
            if maximum < minimum:
                raise BeatError('video_too_short')
            frames = rng.randint(minimum, maximum)
            length = frames / FPS
            start = rng.uniform(0, max(0, available - length))
            tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-y',
                '-protocol_whitelist', 'file', '-f', demuxer, '-i', str(source),
                '-ss', str(start), '-t', str(length), '-map', '0:v:0', '-an', '-sn', '-dn',
                '-vf', NORMALIZE, '-frames:v', str(frames), '-c:v', 'libx264',
                '-preset', 'fast', '-map_metadata', '-1', str(clip)], 180)
            if not clip.is_file() or not clip.stat().st_size:
                raise BeatError('video_decode_failed')
            verify_output(clip, length, tools, silent=True)
            clips.append({'path': clip, 'seconds': length, 'resource': row['path']})
        except BeatError as exc:
            if str(exc) in {'media_tool_missing', 'media_process_failed'}:
                raise
            skipped += 1
    if not clips:
        raise BeatError('no_compatible_videos')
    # Unique resources appear once in a cycle, so its end/start cannot repeat
    # consecutively when at least two valid resources exist.
    manifest, sequence = root / 'clips.txt', root / 'sequence.mp4'
    checkpoint()
    manifest.write_text(''.join(f"file '{clip['path'].name}'\n" for clip in clips), encoding='ascii')
    tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'concat', '-safe', '1',
        '-protocol_whitelist', 'file', '-i', str(manifest), '-map', '0:v:0', '-an',
        '-c:v', 'copy', str(sequence)], 180)
    with audio.open('rb') as stream:
        demuxer = audio_type(stream.read(512))
    checkpoint()
    tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-y', '-stream_loop', '-1',
        '-protocol_whitelist', 'file', '-f', 'mov', '-i', str(sequence),
        '-protocol_whitelist', 'file', '-f', demuxer, '-i', str(audio),
        '-map', '0:v:0', '-map', '1:a:0', '-t', str(seconds), '-r', '30',
        '-af', f'atrim=duration={seconds},asetpts=PTS-STARTPTS', '-c:v', 'libx264',
        '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart',
        str(output)], 1200)
    if not output.is_file() or not output.stat().st_size:
        raise BeatError('render_output_missing')
    verify_output(output, seconds, tools)
    return {'clips': loop_plan(clips, seconds), 'skipped_videos': skipped, 'first_clip': clips[0]['path']}


def verify_output(output, seconds, tools, silent=False):
    try:
        info = json.loads(tools._call([tools.ffprobe, '-v', 'error', '-protocol_whitelist', 'file',
            '-f', 'mov', '-show_entries',
            'format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate',
            '-of', 'json', str(output)], 30, True))
        streams = info['streams']
        video = next(row for row in streams if row['codec_type'] == 'video')
        actual = float(info['format']['duration'])
        if (len(streams) != (1 if silent else 2)
                or sum(row['codec_type'] == 'audio' for row in streams) != (0 if silent else 1)
                or video['codec_name'] != 'h264' or video['width'] != 1920 or video['height'] != 1080
                or video['avg_frame_rate'] != '30/1'
                or not math.isfinite(actual) or abs(actual - seconds) > 1 / FPS + .001):
            raise BeatError('montage_output_rejected')
    except BeatError:
        raise
    except Exception:
        raise BeatError('montage_output_rejected') from None


def thumbnail_frame(clip, frame, tools):
    tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-y', '-protocol_whitelist', 'file',
        '-f', 'mov', '-i', str(clip), '-map', '0:v:0', '-an', '-frames:v', '1',
        '-c:v', 'png', '-f', 'image2', str(frame)], 30)
