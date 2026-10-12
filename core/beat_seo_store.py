"""Immutable per-reservation SEO, committed through the existing Dropbox CAS."""
from copy import deepcopy
from core.beat_seo import build_snapshot, validate_snapshot
from core.beat_video import reserved_job
from core.beat_seo_report import validate_report, moment, fields
from core.beat_rotation import previous_publication


def _cache_date(row, channel, now):
    try:
        fields(row, ('manual_hash', 'report'))
        validate_report(row['report'], channel, now, max_age_days=30)
        return moment(row['report']['generated_at']).timestamp()
    except Exception:
        return float('-inf')


def prepare_seo(cloud, job_id, track, channel, now, *, report_loader=None, dry_run=False):
    state, _ = cloud.read('state')
    _, job = reserved_job(state, job_id, track, channel)
    publication = previous_publication(state, job)
    if publication is not None and not publication.get('seo_snapshot'):
        raise ValueError('previous_seo_unknown')
    previous_selected = publication['seo_snapshot']['selected'] if publication else None
    if 'seo_snapshot' in job:
        snapshot = validate_snapshot(job['seo_snapshot'], job)
        if previous_selected and (snapshot['selected']['title'], snapshot['selected']['tags']) == (
                previous_selected['title'], previous_selected['tags']):
            raise ValueError('repeat_seo_unchanged')
        return snapshot
    payload = None
    if report_loader is not None:
        try:
            payload = report_loader()
        except Exception:
            pass
    caches = state.get('seo_last_good', {})
    cached = caches.get(channel['id']) if type(caches) is dict and len(caches) <= 100 else None
    snapshot, cache = build_snapshot(job, track, channel, now, payload, cached,
                                     previous_selected=previous_selected)
    if dry_run:
        return snapshot

    def record(document):
        _, current = reserved_job(document, job_id, track, channel)
        if previous_publication(document, current) != publication:
            raise ValueError('seo_history_changed')
        if 'seo_snapshot' in current:
            result = validate_snapshot(current['seo_snapshot'], current)
            if previous_selected and (result['selected']['title'], result['selected']['tags']) == (
                    previous_selected['title'], previous_selected['tags']):
                raise ValueError('repeat_seo_unchanged')
            return result
        if current != job:
            raise ValueError('seo_reservation_changed')
        document['jobs'][job_id]['seo_snapshot'] = deepcopy(snapshot)
        if cache is not None:
            caches = document.get('seo_last_good')
            if type(caches) is not dict or len(caches) > 100:
                caches = document['seo_last_good'] = {}
            if channel['id'] not in caches and len(caches) >= 100:
                # Removed channels must not permanently exhaust cache capacity.
                # Prefer invalid/expired entries, otherwise evict the oldest report.
                oldest = min(caches, key=lambda cid: (_cache_date(caches[cid], cid, now), cid))
                del caches[oldest]
            previous = caches.get(channel['id'])
            # A late writer must not roll a newer valid cache backwards.
            try:
                validate_report(previous['report'], channel['id'], now, max_age_days=30)
                newer = (previous['manual_hash'] == cache['manual_hash'] and
                         moment(previous['report']['generated_at']) > moment(cache['report']['generated_at']))
            except Exception:
                newer = False
            if not newer:
                caches[channel['id']] = deepcopy(cache)
        return deepcopy(snapshot)

    return cloud.update('state', record)
