"""Channel-local publication history and strict repeat barriers."""
from datetime import timedelta
import hashlib
from core.beat_schema import instant

REST = timedelta(days=180)


def image_digest(path):
    from PIL import Image, ImageOps
    with Image.open(path) as source:
        picture = ImageOps.exif_transpose(source).convert('RGB')
        value = hashlib.sha256(repr(picture.size).encode())
        value.update(picture.tobytes())
        return value.hexdigest()


def previous_publication(state, job):
    rows = [row for row in state['jobs'].values()
            if row['id'] != job['id'] and row['channel'] == job['channel']
            and row['track_id'] == job['track_id'] and row['status'] == 'uploaded']
    return max(rows, key=publication_time, default=None)


def publication_time(job):
    # Scheduled uploads may be inserted days before their public release.
    return max(instant(job['slot']), instant(job.get('uploaded_at', job['slot'])))


def repeat_ready(history, tid, at, attempted_ids=()):
    # Una subida perdida (``lost``) ya se verificó fuera de YouTube: no bloquea el beat.
    rows = [row for row in history if row['track_id'] == tid and not row.get('lost')
            and (row['status'] != 'cancelled' or row['id'] in attempted_ids)]
    # Failed/planned reservations (including ambiguous inserts) must resolve first.
    return all(row['status'] == 'uploaded' and instant(at) >= publication_time(row) + REST
               for row in rows)


def publication_visual(state, previous):
    visual = previous.get('visual_snapshot')
    if visual is None:
        # Compatibility with Phase 4 Dropbox history.
        visual = next((row for genres in state.get('image_rotation', {}).values()
                       for rows in genres.values() for row in rows
                       if row['job_id'] == previous['id']), None)
    if visual is None:
        raise ValueError('previous_image_unknown')
    return visual


def changed_image(catalog, state, job):
    previous = previous_publication(state, job)
    if previous is None:
        return catalog
    visual = publication_visual(state, previous)
    rows = [row for row in catalog if row['path'].casefold() != visual['path'].casefold()]
    if not rows:
        raise ValueError('repeat_image_exhausted')
    return rows


def check_repeat(state, job, at):
    history = [row for row in state['jobs'].values()
               if row['channel'] == job['channel'] and row['id'] != job['id']]
    attempted_ids = {entry['job_id'] for entries in state.get('attempts', {}).values()
                     for entry in entries.values()}
    if not repeat_ready(history, job['track_id'], at, attempted_ids):
        raise ValueError('repeat_not_ready')
    previous = previous_publication(state, job)
    if previous is not None:
        current = state['jobs'][job['id']]
        visual = publication_visual(state, previous)
        if (not current.get('visual_snapshot')
                or current['visual_snapshot']['path'].casefold() == visual['path'].casefold()):
            raise ValueError('repeat_image_unchanged')
        if (visual.get('sha256') and
                current['visual_snapshot'].get('sha256') == visual['sha256']):
            raise ValueError('repeat_image_unchanged')
        if (not previous.get('seo_snapshot') or not current.get('seo_snapshot')
                or (current['seo_snapshot']['selected']['title'], current['seo_snapshot']['selected']['tags'])
                == (previous['seo_snapshot']['selected']['title'], previous['seo_snapshot']['selected']['tags'])):
            raise ValueError('repeat_seo_unchanged')
