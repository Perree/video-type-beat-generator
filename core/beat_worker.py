"""Cloud bootstrap and CLI; only fixed summaries reach the Actions log."""
import argparse
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from core import youtube
from core.beat_assets import DropboxAssets
from core.beat_cloud import BeatCloud, DropboxTransport, decode_document
from core.beat_daily import run_daily
from core.beat_share import ShareLinks
from core.beat_notion import fetch_report
from core.beat_notify import Telegram
from core.beat_reasons import note
from core.beat_youtube import BeatYouTube
from core.beat_logs import quiet_dependencies
from core.beat_actions import check_context, bind_channel


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--private-pilot', action='store_true',
                        help='Try one job; private video without publishAt')
    parser.add_argument('--seed', type=int, default=0)
    parser.add_argument('--receipts', default='exported_videos/type_beats/receipts')
    args = parser.parse_args(argv)
    summary = {'failed': 1, 'dry_run': args.dry_run}
    # Suppress dependency output, including HTTP errors containing URLs/tokens.
    with quiet_dependencies():
        notifier = None
        try:
            actions = os.environ.get('GITHUB_ACTIONS') == 'true'
            slug = os.environ.get('BEAT_SLUG')
            if actions:
                check_context()
            notifier = None if args.dry_run else Telegram(os.environ['BEAT_TELEGRAM_TOKEN'],
                                                         os.environ['BEAT_TELEGRAM_CHAT_ID'])
            channel = os.environ['BEAT_CHANNEL_ID']
            transport = DropboxTransport.from_env()
            assets = DropboxAssets.from_env()
            notion_env = {key: os.environ.get(key) for key in ('BEAT_NOTION_TOKEN', 'BEAT_NOTION_PAGE_ID')}
            loader = (lambda: fetch_report(notion_env)) if notion_env['BEAT_NOTION_TOKEN'] else None
            token = os.environ.get('BEAT_YT_TOKEN_JSON')
            # Remove Beats credentials before any child process is launched.
            for key in list(os.environ):
                if key.startswith('BEAT_'):
                    os.environ.pop(key)
            with TemporaryDirectory(prefix='beat-oauth-') as folder:
                os.chmod(folder, 0o700)
                if not args.dry_run:
                    payload = decode_document(token)
                    if not isinstance(payload, dict):
                        raise ValueError('youtube_token_invalid')
                    path = Path(youtube._token_path(channel, folder))
                    path.write_text(json.dumps(payload), encoding='utf-8')
                    os.chmod(path, 0o600)
                client = BeatYouTube(folder)
                cloud = BeatCloud(transport)
                expected_owner = None
                if actions or not args.dry_run:
                    config, config_rev = cloud.read('config')
                    if config_rev is None:
                        raise ValueError('beat_config_missing')
                    spec = next(ch for ch in config['channels'] if ch['id'] == channel)
                    if actions:
                        bind_channel(spec, slug)
                    if not args.dry_run:
                        expected_owner = spec.get('youtube_channel_id')
                        client.check_owner(channel, expected_owner)
                summary = run_daily(cloud, channel, assets, client.upload,
                    args.receipts, dry_run=args.dry_run, report_loader=loader,
                    notify=notifier, thumbnailer=client.thumbnail, seed=args.seed,
                    private_pilot=args.private_pilot, expected_owner=expected_owner,
                    share_links=ShareLinks(),
                    # El token solo existe fuera del dry-run; el dry-run no lee YouTube.
                    calendar=None if args.dry_run else client.calendar)
        except Exception as exc:
            # Bootstrap failures are also a sanitized alert when Telegram exists.
            note(summary, exc)
            if notifier is not None:
                try:
                    notifier(summary)
                except Exception:
                    pass
    print(json.dumps(summary, sort_keys=True))
    return 1 if any(summary.get(k, 0) for k in ('failed', 'orphan', 'unknown', 'expired',
                                                  'calendar_unavailable')) else 0
