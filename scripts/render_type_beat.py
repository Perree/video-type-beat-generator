"""Render a previously reserved Type Beats job; artifacts exist only during context."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.beat_assets import DropboxAssets
from core.beat_cloud import BeatCloud, DropboxTransport, decode_document
from core.beat_http import BeatError
from core.beat_video import render_reserved
from core.beat_settings import read_app, settings
from core.beat_seo_store import prepare_seo
from core.beat_notion import fetch_report, read_report_file
from datetime import datetime, timezone


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job-id', required=True)
    parser.add_argument('--track', required=True, help='JSON metadata from the Beats catalog')
    parser.add_argument('--genre', required=True)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--config', help='Local app_config.json; otherwise use the remote Beats config')
    reports = parser.add_mutually_exclusive_group()
    reports.add_argument('--seo-report', help='Local JSON export of the Notion report')
    reports.add_argument('--seo-notion', action='store_true', help='Read with BEAT_NOTION_* credentials')
    parser.add_argument('--seo-only', action='store_true', help='Prepare SEO without downloads or rendering')
    args = parser.parse_args()
    try:
        track = decode_document(Path(args.track).read_bytes())
        cloud = BeatCloud(DropboxTransport.from_env())
        config = settings(read_app(args.config)) if args.config else cloud.read('config')[0]
        state, _ = cloud.read('state')
        job = state['jobs'].get(args.job_id)
        if not job:
            raise BeatError('reserved_job_required')
        channel = next((row for row in config['channels'] if row['id'] == job['channel']), None)
        if channel is None:
            raise BeatError('channel_unconfigured')
        loader = (lambda: read_report_file(args.seo_report)) if args.seo_report else (
            fetch_report if args.seo_notion else None)
        seo = prepare_seo(cloud, args.job_id, track, channel, datetime.now(timezone.utc).isoformat(),
                          report_loader=loader, dry_run=args.dry_run)
        if args.seo_only:
            print(json.dumps({'dry_run': args.dry_run, 'uploads': False, 'seo': seo, 'ok': True}))
            return 0
        with render_reserved(cloud, args.job_id, track, channel, args.genre,
                             config.get('beatstars_profile_url'), DropboxAssets.from_env(),
                             dry_run=args.dry_run) as result:
            # Local preview only: never publish or copy artifacts out of temporaries.
            print(json.dumps({'dry_run': result['dry_run'], 'uploads': False,
                              'visual_mode': result['visual_mode'],
                              'seo_source': seo['source'], 'seo_sha256': seo['sha256'],
                              'seconds': result.get('seconds'), 'ok': True}))
    except Exception:
        print('type_beat_render_failed', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
