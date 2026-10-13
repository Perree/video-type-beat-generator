"""At-most-once uploads: cloud intent first, fsynced receipt, then cloud result."""
import hashlib
import json
import os
import re
from pathlib import Path
from uuid import uuid4
from core.beat_state import BeatState
from core.beat_schema import instant
from core.beat_guard import active_channel, future_slot
from core.beat_selection import require_track


def journal(folder, job_id, outcome, youtube_id=None):
    """Only a digest and validated ID leave the runner; no metadata or errors."""
    root = Path(folder)
    root.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(job_id.encode('utf-8')).hexdigest()
    row = {'job_sha256': key, 'outcome': outcome, 'youtube_id': youtube_id}
    target = root / (key + '.json')
    temporary = root / (key + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(row, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, target)
    return row


def publish(cloud, job, media, seo, uploader, receipts, clock, *, thumbnailer=None,
            private_pilot=False, expected_owner=None, selection_track=None):
    store = BeatState(cloud, clock)
    track = selection_track if selection_track is not None else seo.get('track')
    require_track(active_channel(cloud, job['channel'], expected_owner), track, job['track_id'])
    fence = media.get('before_upload')
    if fence is not None:
        fence()
    # Check journal writability BEFORE spending budget or calling YouTube.
    probe = journal(receipts, uuid4().hex, 'prepared')
    (Path(receipts) / (probe['job_sha256'] + '.json')).unlink()
    future_slot(job, clock)
    def selection_guard():
        guard = media.get('selection_guard')
        if guard is not None:
            guard()
        require_track(active_channel(cloud, job['channel'], expected_owner), track, job['track_id'])
    attempt = store.reserve_attempt(job['id'], uuid4().hex, exclusive=True,
                                    before_commit=selection_guard)
    journal(receipts, job['id'], 'unknown')
    require_track(active_channel(cloud, job['channel'], expected_owner), track, job['track_id'])
    if fence is not None:
        fence()
    future_slot(job, clock)
    # The fresh config read can itself cross midnight. Check AFTER that I/O.
    if instant(attempt['reserved_at']).date() != instant(clock()).date():
        raise ValueError('upload_reservation_day_changed')
    try:
        result = uploader(channel=job['channel'], video_path=str(media['video']),
                          thumbnail=str(media['thumbnail']), **seo['selected'],
                          privacy='private', publish_at=None if private_pilot else job['slot'])
    except Exception:
        # Even a timeout could hide a successful insert. Never retry this job.
        return 'unknown'
    video_id = result.get('youtube_id') if isinstance(result, dict) else None
    if not isinstance(video_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        return 'unknown'
    # Treat every known ID as an orphan until Dropbox acknowledges the receipt.
    # If this local write fails, cloud intent still prevents another upload.
    try:
        journal(receipts, job['id'], 'orphan', video_id)
    except Exception:
        # Try the cloud receipt even when local storage fails.
        pass

    uploaded_at = clock().isoformat()
    def record(state):
        current = state['jobs'][job['id']]
        existing = current.get('youtube_id')
        if existing is not None and existing != video_id:
            raise ValueError('upload_receipt_conflict')
        current.update(status='uploaded', youtube_id=video_id,
                       uploaded_at=uploaded_at,
                       publication_mode='private_pilot' if private_pilot else 'scheduled')
    try:
        cloud.update('state', record)
    except Exception:
        return 'orphan'
    try:
        journal(receipts, job['id'], 'uploaded', video_id)
    except Exception:
        # The cloud receipt is authoritative; keep the orphan journal if present.
        pass
    if thumbnailer is not None:
        try:
            thumbnailer(job['channel'], video_id, media['thumbnail'])
        except Exception:
            return 'thumbnail_failed'
    return 'thumbnail_failed' if result.get('thumbnail_error') else 'uploaded'
