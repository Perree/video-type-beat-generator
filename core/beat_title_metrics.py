"""Best-effort public counters at day 7/28; never infer CTR or a winning title."""
from copy import deepcopy
from datetime import datetime, timezone
from core.beat_seo_report import moment

WINDOWS = (7, 28)


def collect(cloud, channel, reader, now=None):
    now = now or datetime.now(timezone.utc).isoformat()
    instant = moment(now)
    config, _ = cloud.read('config')
    spec = next(c for c in config['channels'] if c['id'] == channel)
    if spec.get('seo', {}).get('title_mode') != 'rnb_test_v1':
        return 0
    state, _ = cloud.read('state')
    jobs = [job for job in state['jobs'].values() if job['channel'] == channel
            and job['status'] == 'uploaded' and job.get('youtube_id')
            and job.get('seo_snapshot', {}).get('experiment')
            and any(str(day) not in job.get('title_metrics', {})
                    and (instant - moment(job['slot'])).total_seconds() >= day * 86400
                    for day in WINDOWS)]
    additions = []
    for start in range(0, len(jobs), 50):
        batch = jobs[start:start + 50]
        rows = reader(channel, [job['youtube_id'] for job in batch])
        for job in batch:
            row = rows.get(job['youtube_id'])
            if not row or row.get('privacy') != 'public' or row.get('channel_id') != spec.get('youtube_channel_id'):
                continue
            if row.get('title') != job['seo_snapshot']['selected']['title']:
                continue  # An externally edited title is not the assigned experiment.
            age = (instant - moment(row['published_at'])).total_seconds() / 86400
            for day in WINDOWS:
                if age < day or str(day) in job.get('title_metrics', {}):
                    continue
                # If the first run is late, do not invent historical day-7 values.
                sample = {'observed_at': now, 'published_at': row['published_at'],
                          'age_days': round(age, 4), 'late': age >= day + 1,
                          'source': 'youtube_data_v3',
                          'title': row['title'], 'experiment': deepcopy(job['seo_snapshot']['experiment']),
                          'impressions': None, 'ctr': None, 'watch_time_minutes': None,
                          'search_views': None}
                for key in ('views', 'likes', 'comments'):
                    value = row.get(key)
                    if value is not None and (type(value) is not int or not 0 <= value <= 10**15):
                        raise ValueError('title_metric_invalid')
                    sample[key] = value
                additions.append((job, str(day), sample))
    if not additions:
        return 0

    def record(document):
        count = 0
        for original, window, sample in additions:
            current = document['jobs'].get(original['id'])
            if (not current or current.get('youtube_id') != original['youtube_id']
                    or current.get('seo_snapshot') != original['seo_snapshot']):
                continue
            samples = current.setdefault('title_metrics', {})
            if window not in samples:
                samples[window] = sample
                count += 1
        return count
    return cloud.update('state', record, require_existing=True)
