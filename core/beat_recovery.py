"""CAS reconciliation of known orphan IDs; never uploads or refunds attempts."""
import hashlib
import re
from core.beat_schema import instant


def reconcile(cloud, receipt, channel_id, uploaded_at, verified_video, *, apply=False):
    """verified_video must come from an authenticated videos.list, not the journal."""
    if (type(receipt) is not dict or set(receipt) != {'job_sha256', 'outcome', 'youtube_id'}
            or receipt['outcome'] not in ('orphan', 'uploaded')
            or type(receipt['job_sha256']) is not str
            or not re.fullmatch('[0-9a-f]{64}', receipt['job_sha256'])
            or type(receipt['youtube_id']) is not str
            or not re.fullmatch('[A-Za-z0-9_-]{11}', receipt['youtube_id'])):
        raise ValueError('recovery_receipt_invalid')
    uploaded_at = instant(uploaded_at).isoformat()
    config, rev = cloud.read('config')
    channel = next((ch for ch in config['channels'] if ch['id'] == channel_id), None)
    if rev is None or channel is None or channel['active']:
        raise ValueError('recovery_requires_paused_channel')
    expected = channel.get('youtube_channel_id')
    if (type(expected) is not str or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', expected)
            or type(verified_video) is not dict or verified_video.get('id') != receipt['youtube_id']
            or verified_video.get('snippet', {}).get('channelId') != expected
            or verified_video.get('status', {}).get('uploadStatus') not in ('uploaded', 'processed')):
        raise ValueError('recovery_video_unverified')

    def record(state):
        rows = [job for job in state['jobs'].values() if
                hashlib.sha256(job['id'].encode('utf-8')).hexdigest() == receipt['job_sha256']]
        if len(rows) != 1 or rows[0]['channel'] != channel_id:
            raise ValueError('recovery_job_unmatched')
        job = rows[0]
        attempts = [entry for day in state['attempts'].values() for entry in day.values()
                    if entry['job_id'] == job['id']]
        if not attempts or instant(uploaded_at) < min(instant(e['reserved_at']) for e in attempts):
            raise ValueError('recovery_attempt_unmatched')
        if any(j.get('youtube_id') == receipt['youtube_id'] and j['id'] != job['id']
               for j in state['jobs'].values()):
            raise ValueError('recovery_video_already_assigned')
        if job.get('youtube_id') not in (None, receipt['youtube_id']):
            raise ValueError('recovery_receipt_conflict')
        if job.get('youtube_id') is None:
            status = verified_video['status']
            mode = 'private_pilot' if status.get('privacyStatus') == 'private' and not status.get('publishAt') else 'scheduled'
            job.update(status='uploaded', youtube_id=receipt['youtube_id'],
                       uploaded_at=uploaded_at, publication_mode=mode)
        return {'job_sha256': receipt['job_sha256'], 'outcome': 'uploaded',
                'youtube_id': receipt['youtube_id'], 'dry_run': not apply}

    if apply:
        # Reread pause before every CAS attempt/retry, including lost responses.
        def guard(_):
            latest, latest_rev = cloud.read('config')
            current = next((ch for ch in latest['channels'] if ch['id'] == channel_id), None)
            if (latest_rev is None or current is None or current['active']
                    or current.get('youtube_channel_id') != expected):
                raise ValueError('recovery_requires_paused_channel')
        return cloud.update('state', record, guard=guard, require_existing=True)
    state, rev = cloud.read('state')
    if rev is None:
        raise ValueError('beat_state_missing')
    return record(state)
