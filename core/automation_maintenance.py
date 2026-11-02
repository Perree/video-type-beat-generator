"""Explicit maintenance: Telegram probe and WyreGuitars calendar migration."""
import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import urllib.request
import urllib.error


def telegram_probe():
    token = os.environ['KIT_TELEGRAM_TOKEN'].strip()
    chat = os.environ['KIT_TELEGRAM_CHAT_ID'].strip()
    for method, body in [('getMe', {}), ('getChat', {'chat_id': chat}),
                         ('sendMessage', {'chat_id': chat, 'text':
                          'Type Beat Generator: avisos compartidos para todos los canales conectados. Prueba correcta.'})]:
        request = urllib.request.Request('https://api.telegram.org/bot' + token + '/' + method,
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            result = json.loads(exc.read(65536))
        print(json.dumps({'method': method, 'ok': result.get('ok'),
                          'error_code': result.get('error_code')}), flush=True)
        if not result.get('ok'):
            return 1
    return 0


def next_slots(now, count, occupied=()):
    local = now.astimezone(timezone(timedelta(hours=-3)))
    slots = []
    for offset in range(366):
        slot = (local + timedelta(days=offset)).replace(hour=10, minute=0, second=0, microsecond=0)
        if slot > local and slot.weekday() in (1, 3) and slot.date() not in occupied:
            slots.append(slot.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z'))
            if len(slots) == count:
                return slots
    if count:
        raise ValueError('calendar_no_free_slots')
    return []


def guitars(apply=False):
    from core import kit_channel, kit_cloud, kit_state, youtube
    import dropbox
    paths = kit_channel.paths('wyreguitars')
    dbx = dropbox.Dropbox(app_key=kit_cloud._plain_or_field(os.environ, 'KIT_DROPBOX_APP_KEY', 'app_key'),
        oauth2_refresh_token=kit_cloud._plain_or_field(os.environ, 'KIT_DROPBOX_REFRESH_TOKEN', 'refresh_token'),
        timeout=30)
    owner = kit_state.acquire_lock(db_path=paths.state, dbx=dbx)
    try:
        config, rev = kit_cloud.read_json_rev(paths.config, dbx=dbx)
        if config['kit_preview']['channel'] != 'WyreGuitars':
            raise ValueError('channel_mismatch')
        with TemporaryDirectory() as folder:
            channel = 'WyreGuitars'
            Path(youtube._token_path(channel, folder)).write_text(os.environ['KIT_YT_TOKEN_JSON'], encoding='utf-8')
            yt = youtube._service(youtube._load_credentials(channel, folder))
            rows = youtube.list_channel_calendar(channel, folder)
            state = kit_state.load(db_path=paths.state, dbx=dbx)
            known = {r.get('youtube_id') for r in state['runs']}
            now = datetime.now(timezone.utc)
            future = sorted([r for r in rows if r['youtube_id'] in known and r.get('publish_at')
                and datetime.fromisoformat(r['publish_at'].replace('Z', '+00:00')) > now],
                key=lambda r: (r['publish_at'], r['youtube_id']))
            tz = timezone(timedelta(hours=-3))
            occupied = {datetime.fromisoformat(r['publish_at'].replace('Z', '+00:00')).astimezone(tz).date()
                        for r in rows if r.get('publish_at') and r['youtube_id'] not in {x['youtube_id'] for x in future}}
            slots = next_slots(now, len(future), occupied)
            changes = [dict(video_id=r['youtube_id'], before=r['publish_at'], after=slot)
                       for r, slot in zip(future, slots)]
            print(json.dumps({'apply': apply, 'changes': changes}), flush=True)
            if not apply:
                return 0
            config['kit_preview']['slots'] = [dict(weekday=d, hour=10, minute=0) for d in (1, 3)]
            kit_cloud.write_json(paths.config, config, rev=rev, dbx=dbx)
            for change in changes:
                vid, slot = change['video_id'], change['after']
                item = yt.videos().list(part='status', id=vid).execute()['items'][0]
                status = item['status']
                if status.get('privacyStatus') != 'private' or not status.get('publishAt'):
                    raise ValueError('video_no_longer_scheduled')
                writable = {k: status[k] for k in ('privacyStatus', 'embeddable', 'license',
                    'publicStatsViewable', 'selfDeclaredMadeForKids', 'containsSyntheticMedia') if k in status}
                writable['publishAt'] = slot
                yt.videos().update(part='status', body={'id': vid, 'status': writable}).execute()
                def record(document):
                    for run in document['runs']:
                        if run.get('youtube_id') == vid:
                            run['publish_at'] = slot
                kit_state._mutate(record, paths.state, dbx)
                actual = yt.videos().list(part='status', id=vid).execute()['items'][0]['status']
                if actual.get('publishAt') != slot:
                    raise ValueError('schedule_verification_failed')
                print(json.dumps({'verified': vid, 'publish_at': slot}), flush=True)
    finally:
        kit_state.release_lock(owner, db_path=paths.state, dbx=dbx)
    return 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['telegram', 'guitars'])
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    try:
        return telegram_probe() if args.operation == 'telegram' else guitars(args.apply)
    except Exception as exc:
        detail = {'failed': type(exc).__name__}
        if hasattr(exc, 'resp'):
            detail['http_status'] = getattr(exc.resp, 'status', None)
            try:
                error = json.loads(exc.content).get('error', {})
                allowed = {'insufficientPermissions', 'forbidden', 'quotaExceeded',
                           'invalidPublishAt', 'videoNotFound', 'invalidVideoMetadata'}
                detail['api_reasons'] = [e['reason'] for e in error.get('errors', [])
                                         if e.get('reason') in allowed]
            except (ValueError, TypeError):
                pass
        print(json.dumps(detail), flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
