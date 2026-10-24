"""Cancellable local media validation and preview conversion, without remote FFmpeg I/O."""
import json
import subprocess
import time
from pathlib import Path

from core.beat_download import MAX_AUDIO, audio_type, duration
from core.beat_http import BeatError, check_cancelled
from core.beat_render import MediaTools


class CancellableRun:
    def __init__(self, cancelled=lambda: False):
        self.cancelled = cancelled

    def __call__(self, command, timeout, **kwargs):
        check_cancelled(self.cancelled)
        deadline = time.monotonic() + timeout
        with subprocess.Popen(command, **kwargs) as process:
            try:
                while True:
                    check_cancelled(self.cancelled)
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise BeatError('media_timeout')
                    try:
                        stdout, stderr = process.communicate(timeout=min(.1, remaining))
                        check_cancelled(self.cancelled)
                        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
                    except subprocess.TimeoutExpired:
                        continue
            finally:
                if process.poll() is None:
                    process.kill()
                    process.communicate()


class ManualMediaTools:
    def __init__(self, cancelled=lambda: False, ffmpeg=None, ffprobe=None, run=None):
        self.cancelled = cancelled
        self.tools = MediaTools(ffmpeg, ffprobe, run or CancellableRun(cancelled))

    def _probe(self, audio, demuxer=None):
        args = [self.tools.ffprobe, '-v', 'error', '-protocol_whitelist', 'file']
        if demuxer:
            args += ['-f', demuxer]
        args += ['-show_entries', 'format=duration:stream=codec_type,codec_name', '-of', 'json', str(audio)]
        try:
            data = json.loads(self.tools._call(args, 30, True))
            streams = data['streams']
            if len(streams) != 1 or streams[0]['codec_type'] != 'audio':
                raise BeatError('audio_stream_rejected')
            return streams[0]['codec_name'], duration(float(data['format']['duration']))
        except BeatError:
            raise
        except (ValueError, KeyError, TypeError):
            raise BeatError('audio_probe_failed') from None

    def prepare(self, source, target, expected):
        check_cancelled(self.cancelled)
        self.tools.verify_audio(source, expected)
        with Path(source).open('rb') as stream:
            demuxer = audio_type(stream.read(512))
        codec, _ = self._probe(source, demuxer)
        # AAC is already suitable for MP4; other preview codecs are converted once.
        encoding = ['-c:a', 'copy'] if codec == 'aac' else ['-c:a', 'aac', '-b:a', '192k']
        self.tools._call([self.tools.ffmpeg, '-nostdin', '-v', 'error', '-y',
                          '-protocol_whitelist', 'file', '-f', demuxer, '-i', str(source),
                          '-map', '0:a:0', *encoding, '-movflags', '+faststart',
                          '-f', 'ipod', str(target)], 180)
        self.verify(target, expected)

    def verify(self, audio, expected):
        check_cancelled(self.cancelled)
        if not 0 < Path(audio).stat().st_size <= MAX_AUDIO:
            raise BeatError('download_limit')
        codec, seconds = self._probe(audio)
        if codec != 'aac' or abs(seconds - duration(expected)) > max(3, expected * .03):
            raise BeatError('converted_audio_rejected')
        self.tools._call([self.tools.ffmpeg, '-nostdin', '-v', 'error', '-xerror',
                          '-protocol_whitelist', 'file', '-i', str(audio),
                          '-map', '0:a:0', '-f', 'null', '-'], 180)
        check_cancelled(self.cancelled)
        return seconds
