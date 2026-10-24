"""Anonymous bounded HLS acquisition. FFmpeg never receives a remote playlist."""
import math
import time
import urllib.request
from urllib.parse import urljoin
from pathlib import PurePosixPath
from core.beat_http import BeatError, check_url, _NoRedirect, check_cancelled

MEDIA_HOSTS = frozenset({'content.beatstars.com'})
# BeatStars serves the public manifests as octet-stream; magic is still mandatory.
PLAYLIST_TYPES = frozenset({'application/vnd.apple.mpegurl', 'application/x-mpegurl',
                           'audio/mpegurl', 'application/octet-stream'})
SEGMENT_TYPES = frozenset({'video/mp2t', 'audio/aac', 'audio/aacp', 'application/octet-stream'})
MAX_AUDIO = 80 * 1024 * 1024


def duration(value):
    if (isinstance(value, bool) or not isinstance(value, (float, int))
            or not math.isfinite(value) or not 1 <= value <= 900):
        raise BeatError('duration_rejected')
    return float(value)


def dropbox_path(value):
    if (not isinstance(value, str) or not value.startswith('/') or len(value) > 1000
            or '\\' in value or any(ord(c) < 32 for c in value)
            or any(p in ('', '.', '..') for p in value[1:].split('/'))):
        raise BeatError('dropbox_path_rejected')
    return value


def audio_type(data):
    # Only standalone MP3/WAV, ADTS AAC or MPEG-TS; never playlists/HTML.
    if data.startswith(b'RIFF') and data[8:12] == b'WAVE':
        return 'wav'
    if data.startswith(b'ID3'):
        return 'mp3'
    if len(data) > 2 and data[0] == 255 and data[1] & 224 == 224:
        return 'aac' if data[1] & 6 == 0 else 'mp3'
    if len(data) >= 377 and all(data[i] == 0x47 for i in (0, 188, 376)):
        return 'mpegts'
    raise BeatError('audio_type_rejected')


class MediaHTTP:
    def __init__(self, cancelled=lambda: False):
        self.cancelled = cancelled
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    def get(self, url, types, limit, deadline):
        check_cancelled(self.cancelled)
        check_url(url, MEDIA_HOSTS)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BeatError('download_timeout')
        req = urllib.request.Request(url, headers={'Accept-Encoding': 'identity', 'User-Agent': 'TypeBeatPreview/1'})
        try:
            with self.opener.open(req, timeout=min(10, remaining)) as response:
                check_url(response.geturl(), MEDIA_HOSTS)
                if response.geturl() != url or response.status != 200:
                    raise BeatError('redirect_rejected')
                if (response.headers.get_content_type() not in types
                        or response.headers.get('Content-Encoding', 'identity') != 'identity'):
                    raise BeatError('media_type_rejected')
                length = response.headers.get('Content-Length')
                if length and (len(length) > 10 or not length.isdecimal() or int(length) > limit):
                    raise BeatError('download_limit')
                data = bytearray()
                while True:
                    check_cancelled(self.cancelled)
                    if time.monotonic() >= deadline:
                        raise BeatError('download_timeout')
                    chunk = response.read1(min(65536, limit + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > limit:
                        raise BeatError('download_limit')
                if not data or (length and int(length) != len(data)):
                    raise BeatError('download_incomplete')
                check_cancelled(self.cancelled)
                return bytes(data)
        except BeatError:
            raise
        except Exception:
            raise BeatError('media_request_failed') from None


def download_hls(url, target, http=None, cancelled=lambda: False):
    http = http or MediaHTTP(cancelled)
    deadline = time.monotonic() + 180
    seen = set()
    for depth in range(3):
        check_cancelled(cancelled)
        check_url(url, MEDIA_HOSTS)
        if url in seen:
            raise BeatError('playlist_cycle')
        seen.add(url)
        data = http.get(url, PLAYLIST_TYPES, 256 * 1024, deadline)
        check_cancelled(cancelled)
        try:
            lines = [line.strip() for line in data.decode('utf-8-sig').splitlines() if line.strip()]
        except UnicodeError:
            raise BeatError('playlist_rejected') from None
        if not lines or lines[0] != '#EXTM3U':
            raise BeatError('playlist_rejected')
        if any(line.startswith(('#EXT-X-KEY', '#EXT-X-SESSION-KEY', '#EXT-X-MAP',
                                '#EXT-X-BYTERANGE', '#EXT-X-MEDIA:', '#EXT-X-PART')) for line in lines):
            raise BeatError('unsupported_hls')
        variants = [i for i, line in enumerate(lines) if line.startswith('#EXT-X-STREAM-INF:')]
        if variants:
            if depth == 2 or len(variants) > 20:
                raise BeatError('playlist_limit')
            i = variants[0] + 1
            if i >= len(lines) or lines[i].startswith('#'):
                raise BeatError('playlist_rejected')
            url = urljoin(url, lines[i])
            continue
        if '#EXT-X-ENDLIST' not in lines:
            raise BeatError('live_hls_rejected')
        segments, total, pending = [], 0.0, None
        for line in lines[1:]:
            if line.startswith('#EXTINF:'):
                if pending is not None:
                    raise BeatError('playlist_rejected')
                try:
                    pending = float(line[8:].split(',')[0])
                except ValueError:
                    raise BeatError('playlist_rejected') from None
                if not math.isfinite(pending) or not 0 < pending <= 60:
                    raise BeatError('duration_rejected')
            elif not line.startswith('#'):
                if pending is None:
                    raise BeatError('playlist_rejected')
                segment = urljoin(url, line)
                check_url(segment, MEDIA_HOSTS)
                segments.append(segment)
                total += pending
                pending = None
        if not segments or len(segments) > 500 or pending is not None:
            raise BeatError('playlist_limit')
        duration(total)
        size = 0
        with target.open('wb') as stream:
            for segment in segments:
                check_cancelled(cancelled)
                payload = http.get(segment, SEGMENT_TYPES, min(8 * 1024 * 1024, MAX_AUDIO - size), deadline)
                check_cancelled(cancelled)
                audio_type(payload)
                size += len(payload)
                if size > MAX_AUDIO:
                    raise BeatError('download_limit')
                stream.write(payload)
        return total
    raise BeatError('playlist_limit')


def acquire_audio(track, state, profile_url, target, resolver, dropbox, http=None):
    try:
        url, expected = resolver.resolve(track, profile_url)
        if expected is not None:
            duration(expected)
        total = download_hls(url, target, http)
        if expected is not None and abs(total - expected) > max(3, expected * .03):
            raise BeatError('duration_mismatch')
        return total, 'hls'
    except BeatError as exc:
        # Security rejections never silently redirect to a different source.
        if str(exc) not in {'preview_unavailable', 'preview_resolution_failed',
                            'media_request_failed', 'request_failed', 'http_error'}:
            raise
        association = state.get('audio_associations', {}).get(track['id'])
        if not isinstance(association, dict) or association.get('track_id') != track['id']:
            raise BeatError('explicit_audio_association_required') from None
        path = dropbox_path(association.get('path'))
        if PurePosixPath(path).suffix.lower() not in ('.mp3', '.wav'):
            raise BeatError('audio_type_rejected')
        dropbox.download(path, target, MAX_AUDIO)
        if not 0 < target.stat().st_size <= MAX_AUDIO:
            raise BeatError('download_limit')
        with target.open('rb') as stream:
            audio_type(stream.read(512))
        return duration(association.get('duration')), 'dropbox'
