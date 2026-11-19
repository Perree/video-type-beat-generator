"""Short silent normalized clips, concat sequence and a beat-length loop."""
import hashlib
import json
import math
import random
from decimal import Decimal
from core.beat_download import audio_type, duration
from core.beat_http import BeatError
from core.beat_visual import fetch, MAX_VIDEO_BYTES
from core.beat_film_overlay import filters
from core.beat_title_overlay import create_title, overlay_chain, overlay_inputs

FPS = 30


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
            'format=duration:stream=codec_type,codec_name,width,height,avg_frame_rate,duration',
            '-of', 'json', str(path)], 30, True))
        streams = [row for row in info['streams'] if row['codec_type'] == 'video']
        if len(streams) != 1:
            raise BeatError('video_stream_rejected')
        video = streams[0]
        seconds = float(info['format']['duration'])
        # Downloads may have longer audio, or video starting after timestamp zero.
        # Normalization resets video timestamps, so cuts must fit its own duration.
        video_seconds = video.get('duration')
        if video_seconds not in (None, 'N/A'):
            video_seconds = float(video_seconds)
            if not math.isfinite(video_seconds) or video_seconds <= 0:
                raise BeatError('video_incompatible')
            seconds = min(seconds, video_seconds)
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


def section_plan(starts, body, clip_min, clip_max, cap=None):
    """Whole-frame clip lengths for ``body`` seconds that cut exactly at each part start.

    ``starts`` are part starts in montage time; each gap is split evenly into clips of
    about the middle length, never longer than ``cap`` (the longest usable source)."""
    total = math.ceil(body * FPS)
    points = sorted({round(t * FPS) for t in starts if 0 < round(t * FPS) < total})
    longest = math.floor(min(clip_max, cap or clip_max) * FPS)
    if longest < 1:
        raise BeatError('video_too_short')
    target = (clip_min + clip_max) / 2 * FPS
    lengths, previous = [], 0
    for point in points + [total]:
        gap = point - previous
        pieces = max(1, math.ceil(gap / longest), round(gap / target))
        base, extra = divmod(gap, pieces)
        lengths += [base + (index < extra) for index in range(pieces)]
        previous = point
    return lengths


def _cut(source, demuxer, start, frames, spec, root, clip, tools):
    length = frames / FPS
    extra_inputs, filtering = filters(spec, root)
    tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-xerror', '-y',
        '-protocol_whitelist', 'file', '-f', demuxer, '-i', str(source),
        *extra_inputs, '-ss', str(start), '-t', str(length), '-an', '-sn', '-dn',
        *filtering, '-frames:v', str(frames), '-c:v', 'libx264',
        '-preset', 'fast', '-map_metadata', '-1', str(clip)], 180)
    if not clip.is_file() or not clip.stat().st_size:
        raise BeatError('video_decode_failed')
    verify_output(clip, length, tools, silent=True)


def _sources(rows, spec, root, dropbox, tools, checkpoint):
    """Download + probe up to 12 resources inside the byte budget; yields usable ones."""
    total_bytes = 0
    for index, row in enumerate(rows[:12]):
        checkpoint()
        if total_bytes + row['size'] > 512 * 1024 * 1024:
            continue
        source = root / f'source-{index}.bin'
        total_bytes += row['size']
        fetch(row, source, MAX_VIDEO_BYTES, dropbox)
        try:
            available, demuxer = video_info(source, tools)
            usable = available - 2 * spec.get('source_trim_seconds', 0)
            if usable < spec['clip_min_seconds']:
                raise BeatError('video_too_short')
            yield index, {'path': source, 'available': available, 'demuxer': demuxer,
                          'usable': usable, 'resource': row['path']}
        except BeatError as exc:
            if str(exc) in {'media_tool_missing', 'media_process_failed'}:
                raise
            yield index, None


def _random_clips(rows, spec, root, dropbox, tools, rng, checkpoint):
    """One random-length cut per source; the sequence loops over the beat."""
    clips, skipped = [], 0
    margin = spec.get('source_trim_seconds', 0)
    for index, row in _sources(rows, spec, root, dropbox, tools, checkpoint):
        if row is None:
            skipped += 1
            continue
        clip = root / f'clip-{index}.mp4'
        try:
            # Whole frames avoid concat boundary gaps from fractional clip lengths.
            minimum = math.ceil(spec['clip_min_seconds'] * FPS)
            maximum = math.floor(min(row['usable'], spec['clip_max_seconds']) * FPS)
            if maximum < minimum:
                raise BeatError('video_too_short')
            frames = rng.randint(minimum, maximum)
            length = frames / FPS
            start = rng.uniform(margin, max(margin, row['available'] - margin - length))
            _cut(row['path'], row['demuxer'], start, frames, spec, root, clip, tools)
            clips.append({'path': clip, 'seconds': length, 'resource': row['resource']})
        except BeatError as exc:
            if str(exc) in {'media_tool_missing', 'media_process_failed'}:
                raise
            skipped += 1
    return clips, skipped


def _section_clips(rows, spec, root, dropbox, tools, rng, checkpoint, starts, body):
    """Clips covering the whole beat that change exactly where each part starts."""
    sources, skipped = [], 0
    for _, row in _sources(rows, spec, root, dropbox, tools, checkpoint):
        if row is None:
            skipped += 1
        else:
            sources.append(row)
    if not sources:
        return [], skipped
    margin = spec.get('source_trim_seconds', 0)
    plan = section_plan(starts, body, spec['clip_min_seconds'], spec['clip_max_seconds'],
                        max(row['usable'] for row in sources))
    clips, turn, last = [], 0, None
    for index, frames in enumerate(plan):
        checkpoint()
        clip, length = root / f'clip-{index}.mp4', frames / FPS
        tries = len(sources)
        while tries and sources:
            tries -= 1
            row = sources[turn % len(sources)]
            turn += 1
            # Rotate sources so consecutive clips (and every part start) change picture.
            if row['usable'] < length or (row is last and len(sources) > 1):
                continue
            start = rng.uniform(margin, max(margin, row['available'] - margin - length))
            try:
                _cut(row['path'], row['demuxer'], start, frames, spec, root, clip, tools)
            except BeatError as exc:
                if str(exc) in {'media_tool_missing', 'media_process_failed'}:
                    raise
                sources.remove(row)
                skipped += 1
                tries = len(sources)
                continue
            clips.append({'path': clip, 'seconds': length, 'resource': row['resource']})
            last = row
            break
        if len(clips) != index + 1:
            return [], skipped
    return clips, skipped


def render_montage(audio, output, seconds, rows, spec, root, dropbox, tools, job_id,
                   checkpoint=lambda: None, intro=None, title=None, sections=None):
    """``intro={'path', 'seconds'}`` va antes del montaje; el audio arranca en 0 sobre ella
    y la duración total sigue siendo ``seconds``. Con ``spec['title_overlay']`` y ``title``,
    el nombre del beat va arriba todo el video (después de la intro). Con ``sections``
    (``[{'start', 'label'}]`` en segundos del audio) cada parte arranca con un clip nuevo;
    sin secciones, largos al azar en bucle como siempre."""
    duration(seconds)
    if intro and seconds - intro['seconds'] < 1:
        intro = None  # beat demasiado corto: sin intro antes que un montaje vacío
    rng = random.Random(int.from_bytes(hashlib.sha256(job_id.encode()).digest()[:8], 'big'))
    rows = list({row['path']: row for row in rows}.values())
    rng.shuffle(rows)
    lead = intro['seconds'] if intro else 0
    if sections:
        clips, skipped = _section_clips(rows, spec, root, dropbox, tools, rng, checkpoint,
                                        [row['start'] - lead for row in sections], seconds - lead)
    else:
        clips, skipped = _random_clips(rows, spec, root, dropbox, tools, rng, checkpoint)
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
    layer = []
    if spec.get('title_overlay') and title:
        layer = overlay_inputs(create_title(title, spec['title_overlay'], root / 'title.png'))
    common = ['-r', '30', '-af', f'atrim=duration={seconds},asetpts=PTS-STARTPTS', '-c:v', 'libx264',
              '-preset', 'fast', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart']
    if intro:
        body = seconds - intro['seconds']
        graph = (f'[1:v:0]trim=duration={body},setpts=PTS-STARTPTS[m];'
                 '[0:v:0][m]concat=n=2:v=1:a=0,setsar=1,fps=30,format=yuv420p')
        graph += ('[pre];' + overlay_chain('pre', 3, intro['seconds'], seconds)) if layer else '[v]'
        tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-y',
            '-protocol_whitelist', 'file', '-f', 'mov', '-i', str(intro['path']),
            '-stream_loop', '-1', '-protocol_whitelist', 'file', '-f', 'mov', '-i', str(sequence),
            '-protocol_whitelist', 'file', '-f', demuxer, '-i', str(audio), *layer,
            '-filter_complex', graph, '-map', '[v]', '-map', '2:a:0', '-t', str(seconds),
            *common, str(output)], 1200)
    else:
        body = seconds
        video = (['-filter_complex', overlay_chain('0:v:0', 2, 0, seconds), '-map', '[v]'] if layer
                 else ['-map', '0:v:0'])
        tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-y', '-stream_loop', '-1',
            '-protocol_whitelist', 'file', '-f', 'mov', '-i', str(sequence),
            '-protocol_whitelist', 'file', '-f', demuxer, '-i', str(audio), *layer,
            *video, '-map', '1:a:0', '-t', str(seconds), *common, str(output)], 1200)
    if not output.is_file() or not output.stat().st_size:
        raise BeatError('render_output_missing')
    verify_output(output, seconds, tools)
    return {'clips': loop_plan(clips, body), 'skipped_videos': skipped, 'first_clip': clips[0]['path'],
            'intro_seconds': intro['seconds'] if intro else 0}


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
