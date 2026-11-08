"""Read-only comparison of uploaded metadata with the channel's current SEO profile."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from core.beat_seo import build_snapshot


def compare(cloud, channel, service):
    state, _ = cloud.read('state')
    jobs = [j for j in state['jobs'].values()
            if j.get('channel') == channel['id'] and j.get('youtube_id')]
    records = []
    for start in range(0, len(jobs), 50):
        batch = jobs[start:start + 50]
        rows = service.videos().list(part='snippet,status',
            id=','.join(j['youtube_id'] for j in batch)).execute()['items']
        by_id = {row['id']: row for row in rows}
        for job in batch:
            row = by_id.get(job['youtube_id'])
            if not row or row['snippet']['channelId'] != channel['youtube_channel_id']:
                raise ValueError('metadata_video_owner_mismatch')
            snapshot, _ = build_snapshot(job, job['seo_snapshot']['track'], channel,
                                          datetime.now(timezone.utc).isoformat())
            wanted = snapshot['selected']
            snippet = row['snippet']
            differences = []
            if snippet['title'] != wanted['title']:
                differences.append('title')
            # YouTube returns tags in a different order from videos.update.
            if set(snippet.get('tags', [])) != set(wanted['tags']):
                differences.append('tags')
            if job.get('publication_mode') == 'scheduled':
                slot = datetime.fromisoformat(job['slot'])
                if slot > datetime.now(timezone.utc):
                    published = row['status'].get('publishAt', '')
                    if (not published or datetime.fromisoformat(published.replace('Z', '+00:00')) != slot
                            or row['status'].get('privacyStatus') != 'private'):
                        differences.append('schedule')
            records.append(dict(youtube_id=job['youtube_id'], differences=differences,
                                expected_title=wanted['title'], expected_tags=wanted['tags'],
                                actual=row))
    return records


def main():
    from core.beat_actions import check_context, bind_channel
    from core.beat_cloud import BeatCloud, DropboxTransport, decode_document
    from core.beat_google import service
    from core.beat_logs import quiet_dependencies
    with quiet_dependencies():
        check_context()
        cloud = BeatCloud(DropboxTransport.from_env())
        config, _ = cloud.read('config')
        channel = next(c for c in config['channels'] if c['id'] == os.environ['BEAT_CHANNEL_ID'])
        bind_channel(channel, os.environ['BEAT_SLUG'])
        token = decode_document(os.environ['BEAT_YT_TOKEN_JSON'])
        with TemporaryDirectory(prefix='metadata-read-') as folder:
            path = Path(folder) / 'token.json'
            path.write_text(json.dumps(token), encoding='utf8')
            os.chmod(path, 0o600)
            yt = service(str(path))
            mine = yt.channels().list(part='id', mine=True).execute()['items']
            if len(mine) != 1 or mine[0]['id'] != channel['youtube_channel_id']:
                raise ValueError('metadata_channel_owner_mismatch')
            records = compare(cloud, channel, yt)
    out = Path('exported_videos/type_beats/receipts/metadata-verification.json')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records), encoding='utf8')
    failed = sum(bool(r['differences']) for r in records)
    print(json.dumps(dict(verified=len(records), failed=failed,
                          differences=[dict(id=r['youtube_id'], fields=r['differences'])
                                       for r in records if r['differences']])))
    return bool(failed)


if __name__ == '__main__':
    raise SystemExit(main())
