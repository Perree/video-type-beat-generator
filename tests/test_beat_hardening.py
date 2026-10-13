"""Unattended operation failures, reproduced with offline service fixtures."""
import copy
import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
import unittest
from contextlib import contextmanager
from datetime import timedelta
from unittest.mock import patch

import test_beat_daily as daily_fixtures
from core.beat_publish import journal, publish
from core.beat_schema import instant
from core.beat_cloud import BeatCloud, CloudError, Missing, Transient, DropboxTransport
from core.beat_recovery import reconcile
from core.beat_state import BeatState, BudgetExhausted
from core.beat_youtube import BeatYouTube
from core import youtube


class HardeningTests(unittest.TestCase):
    def setUp(self):
        self.case = daily_fixtures.DailyTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_missing_remote_state_never_recreates_budget(self):
        case = self.case
        del case.memory.files['/type-beats/state.json']
        before = copy.deepcopy(case.memory.files)
        summary = case.run_worker()
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(case.memory.files, before)
        self.assertEqual(case.calls, [])
        self.assertEqual(case.public.calls, [])

    def test_pause_during_render_prevents_insert_and_budget_charge(self):
        case = self.case
        original = case.renderer
        @contextmanager
        def renderer(*args, **kwargs):
            with original(*args, **kwargs) as media:
                config, rev = case.cloud.read('config')
                config['channels'][0]['active'] = False
                case.cloud.write('config', config, rev)
                yield media
        with patch.object(case, 'renderer', renderer):
            summary = case.run_worker()
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(case.calls, [])
        self.assertEqual(case.cloud.read('state')[0]['attempts'], {})

    def test_slot_expiring_after_journal_never_calls_youtube(self):
        case = self.case
        job = case.prepare_job()
        now = [instant(job['slot']) - timedelta(seconds=1)]
        calls = []
        def writing(*args, **kwargs):
            row = journal(*args, **kwargs)
            if args[2] == 'unknown':
                now[0] += timedelta(seconds=2)
            return row
        with patch('core.beat_publish.journal', side_effect=writing):
            with self.assertRaisesRegex(ValueError, 'publication_slot_expired'):
                publish(case.cloud, job, {'video': 'fake', 'thumbnail': 'fake'},
                        {'selected': {'title': 'Fixture'}}, lambda **kw: calls.append(kw),
                        case.receipts, lambda: now[0])
        self.assertEqual(calls, [])

    def test_pause_after_intent_retains_attempt_without_insert(self):
        case = self.case
        job = case.prepare_job()
        calls = []
        def writing(*args, **kwargs):
            row = journal(*args, **kwargs)
            if args[2] == 'unknown':
                config, rev = case.cloud.read('config')
                config['channels'][0]['active'] = False
                case.cloud.write('config', config, rev)
            return row
        with patch('core.beat_publish.journal', side_effect=writing):
            with self.assertRaisesRegex(ValueError, 'channel_paused'):
                publish(case.cloud, job, {'video': 'fake', 'thumbnail': 'fake'},
                        {'selected': {'title': 'Fixture'}}, lambda **kw: calls.append(kw),
                        case.receipts, lambda: daily_fixtures.NOW)
        self.assertEqual(calls, [])
        self.assertEqual(sum(len(rows) for rows in case.cloud.read('state')[0]['attempts'].values()), 1)

    def test_deleted_state_before_lease_never_initializes_it(self):
        case = self.case
        del case.memory.files['/type-beats/state.json']
        with self.assertRaises(Missing):
            BeatState(case.cloud).acquire(require_existing=True)
        self.assertNotIn('/type-beats/state.json', case.memory.files)

    def test_release_after_state_loss_never_recreates_empty_ledger(self):
        case = self.case
        store = BeatState(case.cloud)
        owner = store.acquire(require_existing=True)
        del case.memory.files['/type-beats/state.json']
        with self.assertRaises(Missing):
            store.release(owner)
        self.assertNotIn('/type-beats/state.json', case.memory.files)

    def test_midnight_during_final_config_read_rejects_previous_day_budget(self):
        case = self.case
        job = case.prepare_job()
        now = [instant('2026-10-11T23:59:59-03:00')]
        calls, config_reads = [], []
        original = case.cloud.read
        def reading(kind):
            value = original(kind)
            if kind == 'config':
                config_reads.append(kind)
                if len(config_reads) == 2:
                    now[0] += timedelta(seconds=2)
            return value
        with patch.object(case.cloud, 'read', side_effect=reading):
            with self.assertRaisesRegex(ValueError, 'upload_reservation_day_changed'):
                publish(case.cloud, job, {'video': 'fake', 'thumbnail': 'fake'},
                        {'selected': {'title': 'Fixture'}}, lambda **kw: calls.append(kw),
                        case.receipts, lambda: now[0])
        self.assertEqual(calls, [])
        self.assertEqual(len(case.cloud.read('state')[0]['attempts']['2026-10-11']), 1)

    def test_private_pilot_one_insert_without_publish_at(self):
        calls = []
        class Google:
            def videos(inner):
                return inner
            def insert(inner, **kwargs):
                calls.append({'body': kwargs['body']})
                return SimpleNamespace(next_chunk=lambda: (None, {'id': 'video000001'}))
        client = BeatYouTube(self.case.temp.name)
        with patch.object(client, 'service', return_value=Google()):
            summary = self.case.run_worker(uploader=client.upload, private_pilot=True)
        self.assertEqual(summary['uploaded'], 1)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['body']['status']['privacyStatus'], 'private')
        self.assertNotIn('publishAt', calls[0]['body']['status'])
        state, _ = self.case.cloud.read('state')
        self.assertEqual(next(j for j in state['jobs'].values() if j['status'] == 'uploaded')['publication_mode'], 'private_pilot')

    def test_private_pilot_unknown_response_does_not_try_second_job(self):
        calls = []
        def timeout(**kwargs):
            calls.append(kwargs)
            raise TimeoutError('SECRET')
        summary = self.case.run_worker(uploader=timeout, private_pilot=True)
        self.assertEqual(summary['unknown'], 1)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0]['publish_at'])

    def test_distinct_jobs_racing_cannot_exceed_global_six_attempts(self):
        self.case.run_worker(dry_run=True)
        owner = BeatState(self.case.cloud, lambda: daily_fixtures.NOW).acquire()
        store = BeatState(self.case.cloud, lambda: daily_fixtures.NOW)
        jobs = store.fill_buffer(daily_fixtures.CONFIG, [{'id': 'TK'+str(i)} for i in range(14)], owner)
        store.release(owner)
        def reserve(index):
            try:
                store.reserve_attempt(jobs[index]['id'], str(index), exclusive=True)
                return True
            except BudgetExhausted:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertEqual(sum(pool.map(reserve, range(8))), 6)

    def test_wrong_youtube_account_rejected(self):
        expected = 'UC' + 'a' * 22
        client = BeatYouTube(self.case.temp.name)
        service = SimpleNamespace(channels=lambda: SimpleNamespace(list=lambda **kw:
                  SimpleNamespace(execute=lambda: {'items': [{'id': 'UC' + 'b' * 22}]})))
        with patch.object(client, 'service', return_value=service):
            with self.assertRaisesRegex(ValueError, 'youtube_owner_mismatch'):
                client.check_owner('channel', expected)
            with self.assertRaisesRegex(ValueError, 'youtube_owner_unconfigured'):
                client.check_owner('channel', None)
        service = SimpleNamespace(channels=lambda: SimpleNamespace(list=lambda **kw:
                  SimpleNamespace(execute=lambda: {'items': [{'id': expected}]})))
        with patch.object(client, 'service', return_value=service):
            client.check_owner('channel', expected)

    def test_shared_upload_closes_video_on_chunk_and_insert_creation_failure(self):
        path = Path(self.case.temp.name) / 'video.mp4'
        path.write_bytes(b'fixture')
        for fail_insert in (False, True):
            media = []
            class Google:
                def videos(inner):
                    return inner
                def insert(inner, **kwargs):
                    media.append(kwargs['media_body'])
                    if fail_insert:
                        raise OSError('fixture')
                    def timeout():
                        raise TimeoutError('fixture')
                    return SimpleNamespace(next_chunk=timeout)
            with patch.object(youtube, '_service', return_value=Google()), \
                 patch.object(youtube, '_load_credentials', return_value=object()):
                with self.assertRaises(OSError):
                    youtube.upload('channel', str(path), 'Fixture')
            self.assertEqual(len(media), 1)
            self.assertTrue(media[0].stream().closed)

    def test_shared_thumbnail_timeout_closes_both_files(self):
        root = Path(self.case.temp.name)
        video, thumbnail = root / 'video.mp4', root / 'thumbnail.jpg'
        video.write_bytes(b'fixture')
        thumbnail.write_bytes(b'fixture')
        media = []
        class Google:
            def videos(inner):
                return inner
            def insert(inner, **kwargs):
                media.append(kwargs['media_body'])
                return SimpleNamespace(next_chunk=lambda: (None, {'id': 'video000001'}))
            def thumbnails(inner):
                return inner
            def set(inner, **kwargs):
                media.append(kwargs['media_body'])
                def timeout():
                    raise TimeoutError('fixture')
                return SimpleNamespace(execute=timeout)
        with patch.object(youtube, '_service', return_value=Google()), \
             patch.object(youtube, '_load_credentials', return_value=object()):
            with self.assertRaises(TimeoutError):
                youtube.upload('channel', str(video), 'Fixture', thumbnail=str(thumbnail))
        self.assertEqual(len(media), 2)
        self.assertTrue(all(row.stream().closed for row in media))

    def recovery_fixture(self):
        case = self.case
        job = case.prepare_job()
        BeatState(case.cloud, lambda: daily_fixtures.NOW).reserve_attempt(job['id'], 'intent', exclusive=True)
        config, rev = case.cloud.read('config')
        config['channels'][0].update(active=False, youtube_channel_id='UC'+'a'*22)
        case.cloud.write('config', config, rev)
        receipt = {'job_sha256': hashlib.sha256(job['id'].encode()).hexdigest(),
                   'outcome': 'orphan', 'youtube_id': 'video000001'}
        video = {'id': 'video000001', 'snippet': {'channelId': 'UC'+'a'*22},
                 'status': {'uploadStatus': 'processed', 'privacyStatus': 'private'}}
        return job, receipt, video

    def test_recovery_dry_run_and_lost_response_are_idempotent(self):
        job, receipt, video = self.recovery_fixture()
        case = self.case
        before = copy.deepcopy(case.memory.files)
        result = reconcile(case.cloud, receipt, 'channel', daily_fixtures.NOW, video)
        self.assertTrue(result['dry_run'])
        self.assertEqual(case.memory.files, before)
        case.memory.faults.append(('after_write', Transient()))
        reconcile(case.cloud, receipt, 'channel', daily_fixtures.NOW, video, apply=True)
        state, rev = case.cloud.read('state')
        self.assertEqual(state['jobs'][job['id']]['youtube_id'], 'video000001')
        self.assertEqual(len(state['attempts'][daily_fixtures.NOW.date().isoformat()]), 1)
        reconcile(case.cloud, receipt, 'channel', daily_fixtures.NOW + timedelta(minutes=1), video, apply=True)
        self.assertEqual(case.cloud.read('state')[1], rev)
        self.assertEqual(case.calls, [])

    def test_recovery_rejects_unknown_wrong_channel_and_conflicts(self):
        job, receipt, video = self.recovery_fixture()
        case = self.case
        before = copy.deepcopy(case.memory.files)
        for row, remote in ((dict(receipt, outcome='unknown', youtube_id=None), video),
                            (receipt, dict(video, snippet={'channelId': 'UC'+'b'*22})),
                            (dict(receipt, job_sha256='0'*64), video)):
            with self.assertRaises(ValueError):
                reconcile(case.cloud, row, 'channel', daily_fixtures.NOW, remote, apply=True)
            self.assertEqual(case.memory.files, before)
        state, rev = case.cloud.read('state')
        state['attempts'] = {}
        case.cloud.write('state', state, rev)
        with self.assertRaisesRegex(ValueError, 'recovery_attempt_unmatched'):
            reconcile(case.cloud, receipt, 'channel', daily_fixtures.NOW, video, apply=True)

    def test_recovery_refuses_active_channel(self):
        _, receipt, video = self.recovery_fixture()
        config, rev = self.case.cloud.read('config')
        config['channels'][0]['active'] = True
        self.case.cloud.write('config', config, rev)
        with self.assertRaisesRegex(ValueError, 'recovery_requires_paused_channel'):
            reconcile(self.case.cloud, receipt, 'channel', daily_fixtures.NOW, video, apply=True)

    def test_recovery_cannot_overwrite_existing_video_id(self):
        job, receipt, video = self.recovery_fixture()
        case = self.case
        case.cloud.update('state', lambda state: state['jobs'][job['id']].update(
            status='uploaded', youtube_id='video000002', uploaded_at=daily_fixtures.NOW.isoformat()))
        before = copy.deepcopy(case.memory.files)
        with self.assertRaisesRegex(ValueError, 'recovery_receipt_conflict'):
            reconcile(case.cloud, receipt, 'channel', daily_fixtures.NOW, video, apply=True)
        self.assertEqual(case.memory.files, before)

    def test_recovery_pause_guard_survives_write_retry(self):
        _, receipt, video = self.recovery_fixture()
        case = self.case
        def unpause(_):
            config, rev = case.cloud.read('config')
            config['channels'][0]['active'] = True
            case.cloud.write('config', config, rev)
        cloud = BeatCloud(case.memory, sleep=unpause)
        before = case.cloud.read('state')
        case.memory.faults.append(('write', Transient()))
        with self.assertRaisesRegex(ValueError, 'recovery_requires_paused_channel'):
            reconcile(cloud, receipt, 'channel', daily_fixtures.NOW, video, apply=True)
        self.assertEqual(case.cloud.read('state'), before)

    def test_recovery_cli_uses_remote_verification_and_dry_run_by_default(self):
        from core.beat_recover_cli import main
        _, receipt, video = self.recovery_fixture()
        case = self.case
        target = Path(case.temp.name) / 'orphan.json'
        target.write_text(json.dumps(receipt))
        requests = []
        service = SimpleNamespace(videos=lambda: SimpleNamespace(list=lambda **kwargs:
            (requests.append(kwargs) or SimpleNamespace(execute=lambda: {'items': [video]}))))
        output = io.StringIO()
        before = copy.deepcopy(case.memory.files)
        with patch('core.beat_recover_cli.DropboxTransport.from_env', return_value=case.memory), \
             patch.object(BeatYouTube, 'check_owner') as owner, \
             patch.object(BeatYouTube, 'service', return_value=service), patch('sys.stdout', output):
            code = main(['--receipt', str(target), '--channel', 'channel',
                         '--uploaded-at', daily_fixtures.NOW.isoformat()])
        self.assertEqual(code, 0)
        owner.assert_called_once_with('channel', 'UC'+'a'*22)
        self.assertEqual(requests, [{'part': 'snippet,status', 'id': 'video000001'}])
        self.assertTrue(json.loads(output.getvalue())['dry_run'])
        self.assertEqual(case.memory.files, before)

    def test_dropbox_state_session_does_not_use_environment_proxies(self):
        import dropbox
        with patch.dict('os.environ', {'BEAT_DROPBOX_APP_KEY': 'key', 'BEAT_DROPBOX_REFRESH_TOKEN': 'token'}, clear=True):
            with patch.object(dropbox, 'Dropbox') as constructor:
                DropboxTransport.from_env()
        session = constructor.call_args.kwargs['session']
        self.assertFalse(session.trust_env)

    def test_cloud_document_limit_rejects_before_reading_body(self):
        response = SimpleNamespace(close=lambda: closed.append(True),
                                   iter_content=lambda _: self.fail('oversize body must not be read'))
        closed = []
        transport = DropboxTransport(SimpleNamespace(files_download=lambda _: (
                    SimpleNamespace(size=8*1024*1024+1, rev='rev'), response)))
        with self.assertRaises(CloudError):
            transport.read('/type-beats/state.json')
        self.assertEqual(closed, [True])

    def test_recovery_cli_failure_sanitized(self):
        from core.beat_recover_cli import main
        output = io.StringIO()
        with patch('core.beat_recover_cli.Path.open', side_effect=OSError('SECRET')), patch('sys.stdout', output):
            code = main(['--receipt', 'fake', '--channel', 'channel', '--uploaded-at', daily_fixtures.NOW.isoformat()])
        self.assertEqual(code, 1)
        self.assertNotIn('SECRET', output.getvalue())
        self.assertEqual(json.loads(output.getvalue())['outcome'], 'recovery_failed')


if __name__ == '__main__':
    unittest.main()
