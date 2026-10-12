"""Per-channel visual options and bounded local/Dropbox resource acquisition."""
import math
from pathlib import Path
from core.beat_assets import IMAGE_SUFFIXES, select_image
from core.beat_download import dropbox_path
from core.beat_http import BeatError
from core.beat_rotation import changed_image

VIDEO_SUFFIXES = {'.mp4', '.mov', '.mkv', '.webm'}
MAX_VIDEO_BYTES = 150 * 1024 * 1024


def options(channel):
    raw = channel.get('visual', {})
    if not isinstance(raw, dict):
        raise ValueError('invalid_visual_options')
    result = dict(mode='image', video_source='local', videos_folder='',
                  clip_min_seconds=3, clip_max_seconds=6,
                  thumbnail_source='auto', thumbnail_path='')
    result.update(raw)
    if (result['mode'] not in ('image', 'video')
            or result['video_source'] not in ('local', 'dropbox')
            or result['thumbnail_source'] not in ('auto', 'local', 'dropbox')):
        raise ValueError('invalid_visual_mode')
    for key in ('videos_folder', 'thumbnail_path'):
        if not isinstance(result[key], str) or len(result[key]) > 1000 or any(ord(c) < 32 for c in result[key]):
            raise ValueError('invalid_visual_path')
    for key in ('clip_min_seconds', 'clip_max_seconds'):
        value = result[key]
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value) or not .5 <= value <= 30):
            raise ValueError('invalid_clip_duration')
    if result['clip_min_seconds'] > result['clip_max_seconds']:
        raise ValueError('invalid_clip_duration')
    if math.ceil(result['clip_min_seconds'] * 30) > math.floor(result['clip_max_seconds'] * 30):
        raise ValueError('El rango de fragmentos debe contener al menos un cuadro a 30 FPS.')
    if result['video_source'] == 'dropbox' and result['videos_folder']:
        dropbox_path(result['videos_folder'])
    if result['thumbnail_source'] == 'dropbox' and result['thumbnail_path']:
        dropbox_path(result['thumbnail_path'])
    return result


def local_catalog(folder, suffixes, limit):
    root = Path(folder)
    if not folder or not root.is_dir():
        raise BeatError('resource_folder_missing')
    result = []
    for index, path in enumerate(root.iterdir()):
        if index >= 5000:
            raise BeatError('resource_catalog_limit')
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        size = path.stat().st_size
        if 0 < size <= limit:
            result.append({'path': str(path.resolve()), 'size': size, 'source': 'local'})
    return sorted(result, key=lambda row: row['path'])


def video_catalog(spec, dropbox):
    if spec['video_source'] == 'local':
        rows = local_catalog(spec['videos_folder'], VIDEO_SUFFIXES, MAX_VIDEO_BYTES)
    else:
        rows = [dict(row, source='dropbox') for row in dropbox.list_videos(spec['videos_folder'])]
    if not rows:
        raise BeatError('video_catalog_empty')
    return rows


def fetch(row, target, limit, dropbox):
    if row.get('source', 'dropbox') == 'dropbox':
        dropbox.download(row['path'], target, limit, rev=row.get('rev'))
        return
    source = Path(row['path'])
    if source.is_symlink():
        raise BeatError('local_resource_changed')
    size = 0
    with source.open('rb') as incoming, target.open('wb') as outgoing:
        while True:
            chunk = incoming.read(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise BeatError('download_limit')
            outgoing.write(chunk)
    if size != row['size']:
        raise BeatError('local_resource_changed')


def image_resource(channel, genre, state, job, dropbox):
    # Preserve the existing Dropbox catalog when configured for this genre.
    if genre in channel.get('dropbox_images', {}):
        return select_image(channel, genre, state, job, dropbox)
    if channel.get('images_folder'):
        rows = local_catalog(channel['images_folder'], IMAGE_SUFFIXES, 20 * 1024 * 1024)
        if not rows:
            raise BeatError('image_catalog_empty')
        reserved = job.get('visual_snapshot')
        if reserved:
            selected = next((row for row in rows if row['path'] == reserved['path']), None)
            if selected is None:
                raise BeatError('reserved_image_missing')
            return selected
        rows = changed_image(rows, state, job)
        return rows[(job['cycle'] - 1) % len(rows)]
    return select_image(channel, genre, state, job, dropbox)


def thumbnail_resource(spec):
    if spec['thumbnail_source'] == 'auto':
        return None
    path = spec['thumbnail_path']
    if not path:
        raise BeatError('thumbnail_required')
    if spec['thumbnail_source'] == 'dropbox':
        dropbox_path(path)
        return {'path': path, 'source': 'dropbox'}
    local = Path(path)
    if not local.is_file() or local.is_symlink() or not 0 < local.stat().st_size <= 20 * 1024 * 1024:
        raise BeatError('thumbnail_rejected')
    return {'path': str(local.resolve()), 'size': local.stat().st_size, 'source': 'local'}
