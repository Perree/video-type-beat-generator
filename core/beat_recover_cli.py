"""Operator recovery: verify an existing video, preview reconciliation, opt in to CAS."""
import argparse
import json
from pathlib import Path
from core.beat_cloud import BeatCloud, DropboxTransport, decode_document
from core.beat_recovery import reconcile
from core.beat_youtube import BeatYouTube
from core.beat_logs import quiet_dependencies


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', required=True)
    parser.add_argument('--channel', required=True)
    parser.add_argument('--uploaded-at', required=True, help='Verified insertion timestamp with offset')
    parser.add_argument('--tokens-dir', default='tokens')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    result = {'outcome': 'recovery_failed'}
    with quiet_dependencies():
        try:
            with Path(args.receipt).open('rb') as stream:
                payload = stream.read(4097)
            if len(payload) > 4096:
                raise ValueError('recovery_receipt_invalid')
            receipt = decode_document(payload)
            cloud = BeatCloud(DropboxTransport.from_env())
            config, _ = cloud.read('config')
            channel = next(ch for ch in config['channels'] if ch['id'] == args.channel)
            if channel['active']:
                raise ValueError('recovery_requires_paused_channel')
            client = BeatYouTube(args.tokens_dir)
            client.check_owner(args.channel, channel.get('youtube_channel_id'))
            service = client.service(args.channel)
            rows = service.videos().list(part='snippet,status', id=receipt['youtube_id']).execute()['items']
            if len(rows) != 1:
                raise ValueError('recovery_video_unverified')
            result = reconcile(cloud, receipt, args.channel, args.uploaded_at, rows[0], apply=args.apply)
        except Exception:
            pass
    print(json.dumps(result, sort_keys=True))
    return 1 if result['outcome'] == 'recovery_failed' else 0
