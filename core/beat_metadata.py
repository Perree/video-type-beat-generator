"""Explicit metadata refresh for paused Beats reservations; never clears upload attempts."""
from copy import deepcopy
from core.beat_seo import manual_profile


def refresh_pending_seo(state, channel):
    if state.get('lock') is not None:
        raise ValueError('render_in_progress')
    _, profile = manual_profile(channel)
    attempted = {row['job_id'] for day in state['attempts'].values() for row in day.values()}
    changed = []
    for key, job in state['jobs'].items():
        if (job['channel'] != channel['id'] or job['status'] not in ('planned', 'failed')
                or job.get('youtube_id') or key in attempted):
            continue
        snapshot = job.get('seo_snapshot')
        if not snapshot or snapshot['manual'] == profile:
            continue
        history = job.setdefault('seo_snapshot_history', [])
        if not isinstance(history, list):
            raise ValueError('invalid_seo_snapshot_history')
        history.append(deepcopy(snapshot))
        del job['seo_snapshot']
        changed.append(key)
    return changed
