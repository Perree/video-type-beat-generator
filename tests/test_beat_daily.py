"""Phase 6 smokes: real phase contracts with fake external services."""
import copy
import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core import youtube
from core.beat_actions import matrix, check_environment
from core.beat_assets import DropboxAssets
from core.beat_cloud import BeatCloud, CloudError, Transient
from core.beat_daily import run_daily
from core.beat_fakes import MemoryDropbox
from core.beat_http import Limits
from core.beat_notify import message
from core.beat_publish import publish
from core.beat_render import MediaTools
from core.beat_schema import instant, migrate
from core.beat_schedule import plan, apply_plan
from core.beat_source import BeatStarsSource
from core.beat_state import BeatState
from core.beat_video import render_reserved
from core.beat_worker import main as worker_main
from core.beat_youtube import BeatYouTube
from core.beat_publish import journal
from test_beat_sync import FakeTransport
from test_beat_video import AssetsClient, HLS, Resolver, Processes

NOW = instant('2026-10-12T12:00:00-03:00')
CONFIG = migrate({'beatstars_profile_url': 'https://www.beatstars.com/fixtureproducer',
    'channels': [{'id': 'channel', 'genres': ['trap'], 'tags': ['trap'],
                  'dropbox_images': {'trap': '/images/trap'},
                  'slots': [{'weekday': day, 'hour': 18, 'minute': 0} for day in range(7)]}]}, 'config')


class DailyTests(unittest.TestCase):
    def setUp(self):
        self.memory = MemoryDropbox()
        self.cloud = BeatCloud(self.memory, sleep=lambda _: None)
        self.cloud.write('config', CONFIG, None)
        self.cloud.write('state', migrate({}, 'state'), None)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.receipts = Path(self.temp.name) / 'receipts'
        self.public = FakeTransport()
        # Enough distinct beats for quota tests: Phase 7 forbids immediate repeats.
        for page_index, page in enumerate(self.public.fixture['pages']):
            data = page['profileTracks']
            template = data['content'][0]
            data['content'] = [copy.deepcopy(template) for _ in range(7)]
            data['totalElements'] = 14
            for index, track in enumerate(data['content']):
                number = 101 + page_index * 7 + index
                track.update(id=f'TK{number}', v2Id=number)
                track['seoMetadata']['slug'] = f'fixture-{number}'
                track['metadata']['tags'] = ['trap']
        self.source = BeatStarsSource(self.public, Limits(page_size=7))
        self.assets_client = AssetsClient()
        self.process = Processes()
        self.hls = HLS()
        self.calls, self.notifications = [], []

    @contextmanager
    def renderer(self, *args, **kwargs):
        with render_reserved(*args, **kwargs, resolver=Resolver(), http=self.hls,
                             tools=MediaTools('fakeffmpeg', 'fakeprobe', self.process)) as result:
            yield result

    def upload(self, **kwargs):
        state, _ = self.cloud.read('state')
        entries = [e for day in state['attempts'].values() for e in day.values()]
        self.assertGreater(len(entries), len(self.calls))
        self.assertTrue(Path(kwargs['video_path']).is_file())
        self.assertTrue(Path(kwargs['thumbnail']).is_file())
        self.assertEqual(kwargs['privacy'], 'private')
        self.assertGreater(instant(kwargs['publish_at']), NOW)
        self.calls.append(kwargs)
        return {'youtube_id': f'video{len(self.calls):06d}', 'thumbnail_error': ''}

    def run_worker(self, **kwargs):
        return run_daily(self.cloud, 'channel', DropboxAssets(self.assets_client),
                         kwargs.pop('uploader', self.upload), self.receipts,
                         source=self.source, renderer=self.renderer,
                         clock=lambda: NOW, notify=self.notifications.append, **kwargs)

    def test_end_to_end_quota_schedule_seo_cleanup_and_rerun(self):
        summary = self.run_worker()
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(len(self.calls), 6)
        state, _ = self.cloud.read('state')
        self.assertEqual(len(state['attempts'][NOW.date().isoformat()]), 6)
        self.assertTrue(all(j.get('seo_snapshot') for j in state['jobs'].values()
                            if j['status'] == 'uploaded'))
        self.assertTrue(all(not Path(call['video_path']).exists() for call in self.calls))
        self.assertEqual(len(self.public.calls), 3)
        self.assertTrue(self.hls.calls)
        self.assertEqual(len(self.notifications), 1)
        again = self.run_worker()
        self.assertEqual(again['uploaded'], 0)
        self.assertEqual(len(self.calls), 6)

    def test_real_youtube_upload_contract_with_fake_google_service(self):
        calls = []
        class Google:
            def videos(inner):
                return inner
            def insert(inner, **kwargs):
                # Insertion sees the durable global reservation already committed.
                state, _ = self.cloud.read('state')
                self.assertGreater(len(state['attempts'][NOW.date().isoformat()]), len(calls))
                calls.append(kwargs)
                return SimpleNamespace(next_chunk=lambda: (None, {'id': f'video{len(calls):06d}'}))
            def thumbnails(inner):
                return inner
            def set(inner, **kwargs):
                return SimpleNamespace(execute=lambda: {})
        with patch.object(youtube, '_service', return_value=Google()), \
             patch.object(youtube, '_load_credentials', return_value=object()):
            summary = self.run_worker(uploader=youtube.upload)
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['failed'], 0)
        self.assertTrue(all(call['media_body'].stream().closed for call in calls))
        self.assertEqual(calls[0]['body']['status']['privacyStatus'], 'private')
        self.assertIn('publishAt', calls[0]['body']['status'])

    def test_adapter_retains_id_before_thumbnail_timeout(self):
        inserts, thumbnails = [], []
        class Google:
            def videos(inner):
                return inner
            def insert(inner, **kwargs):
                inserts.append(kwargs)
                return SimpleNamespace(next_chunk=lambda: (None, {'id': f'video{len(inserts):06d}'}))
            def thumbnails(inner):
                return inner
            def set(inner, **kwargs):
                thumbnails.append(kwargs)
                state, _ = self.cloud.read('state')
                self.assertTrue(any(j.get('youtube_id') == kwargs['videoId'] and j['status'] == 'uploaded'
                                    for j in state['jobs'].values()))
                def timeout():
                    raise TimeoutError('SECRET')
                return SimpleNamespace(execute=timeout)
        client = BeatYouTube(self.temp.name)
        with patch.object(client, 'service', return_value=Google()):
            summary = run_daily(self.cloud, 'channel', DropboxAssets(self.assets_client), client.upload,
                self.receipts, source=self.source, renderer=self.renderer, clock=lambda: NOW,
                thumbnailer=client.thumbnail)
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['thumbnail_failed'], 6)
        self.assertEqual(summary['unknown'], 0)
        self.assertEqual(summary['failed'], 0)
        self.assertTrue(all(call['media_body'].stream().closed for call in inserts + thumbnails))
        self.assertEqual(len(inserts), 6)
        self.assertEqual(len(thumbnails), 6)
        rows = [json.loads(p.read_text()) for p in self.receipts.glob('*.json')]
        self.assertTrue(all(row['youtube_id'] and row['outcome'] == 'uploaded' for row in rows))
        self.assertNotIn('SECRET', message(summary))
        self.run_worker()
        self.assertEqual(self.calls, [])

    def test_thumbnail_callback_not_run_for_orphan(self):
        thumbnails = []
        def uploader(**kwargs):
            result = self.upload(**kwargs)
            self.memory.faults.append(('write', CloudError('SECRET')))
            return result
        summary = run_daily(self.cloud, 'channel', DropboxAssets(self.assets_client), uploader,
            self.receipts, source=self.source, renderer=self.renderer, clock=lambda: NOW,
            thumbnailer=lambda *args: thumbnails.append(args))
        self.assertEqual(summary['orphan'], 6)
        self.assertEqual(summary['unknown'], 0)
        self.assertEqual(thumbnails, [])

    def test_genre_folder_fallback_for_artist_tags(self):
        for page in self.public.fixture['pages']:
            for track in page['profileTracks']['content']:
                track['metadata']['tags'] = ['Drake']
        summary = self.run_worker()
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['failed'], 0)
        self.assertTrue(self.assets_client.downloads)

    def test_video_mode_does_not_require_genre(self):
        config, rev = self.cloud.read('config')
        channel = config['channels'][0]
        channel['genres'] = []
        channel['dropbox_images'] = {}
        channel['visual'] = {'mode': 'video', 'video_source': 'dropbox', 'videos_folder': '/video'}
        self.cloud.write('config', config, rev)
        self.assets_client.files['/video/one.mp4'] = b'fake video'
        summary = self.run_worker(dry_run=True)
        self.assertEqual(summary['failed'], 0)
        self.assertGreater(summary['eligible'], 0)
        self.assertEqual(self.process.calls, [])

    def test_local_images_do_not_require_genre(self):
        image = Path(self.temp.name) / 'fixture.png'
        image.write_bytes(self.assets_client.files['/images/trap/a.png'])
        config, rev = self.cloud.read('config')
        config['channels'][0].update(genres=[], dropbox_images={}, images_folder=self.temp.name)
        self.cloud.write('config', config, rev)
        summary = self.run_worker()
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['failed'], 0)

    def prepare_job(self):
        state, rev = self.cloud.read('state')
        apply_plan(state, plan(CONFIG, state, [{'id': 'TK101'}], NOW))
        self.cloud.write('state', state, rev)
        return next(iter(state['jobs'].values()))

    def test_midnight_during_reservation_backoff_rejects_stale_budget(self):
        job = self.prepare_job()
        clock_value = [instant('2026-10-11T23:59:59-03:00')]
        def sleep(_):
            clock_value[0] += timedelta(seconds=2)
        cloud = BeatCloud(self.memory, sleep=sleep)
        self.memory.faults.append(('write', Transient()))
        with self.assertRaisesRegex(ValueError, 'upload_reservation_day_changed'):
            BeatState(cloud, lambda: clock_value[0]).reserve_attempt(job['id'], 'midnight', exclusive=True)
        self.assertEqual(self.cloud.read('state')[0]['attempts'], {})

    def test_midnight_after_reservation_before_insert_never_calls_youtube(self):
        job = self.prepare_job()
        clock_value = [instant('2026-10-11T23:59:59-03:00')]
        calls = []
        def writing(*args, **kwargs):
            result = journal(*args, **kwargs)
            if args[2] == 'unknown':
                clock_value[0] += timedelta(seconds=2)
            return result
        with patch('core.beat_publish.journal', side_effect=writing):
            with self.assertRaisesRegex(ValueError, 'upload_reservation_day_changed'):
                publish(self.cloud, job, {'video': 'fake', 'thumbnail': 'fake'},
                    {'selected': {'title': 'Fixture'}}, lambda **kwargs: calls.append(kwargs),
                    self.receipts, lambda: clock_value[0])
        self.assertEqual(calls, [])
        state, _ = self.cloud.read('state')
        self.assertEqual(len(state['attempts']['2026-10-11']), 1)

    def test_dry_run_no_writes_downloads_process_uploads_receipts_or_telegram(self):
        before = copy.deepcopy(self.memory.files)
        summary = self.run_worker(dry_run=True)
        self.assertGreater(summary['planned'], 0)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(self.memory.files, before)
        self.assertEqual(self.assets_client.downloads, [])
        self.assertEqual(self.process.calls, [])
        self.assertEqual(self.hls.calls, [])
        self.assertEqual(self.calls, [])
        self.assertEqual(self.notifications, [])
        self.assertFalse(self.receipts.exists())

    def test_orphan_remote_failure_and_rerun_never_reuploads_job(self):
        def uploader(**kwargs):
            result = self.upload(**kwargs)
            self.memory.faults.append(('write', CloudError('SECRET https://private.invalid')))
            return result
        summary = self.run_worker(uploader=uploader)
        self.assertEqual(summary['orphan'], 6)
        rows = [json.loads(p.read_text()) for p in self.receipts.glob('*.json')]
        self.assertEqual(len(rows), 6)
        self.assertTrue(all(row['outcome'] == 'orphan' and row['youtube_id'] for row in rows))
        state, _ = self.cloud.read('state')
        attempted = {e['job_id'] for entries in state['attempts'].values() for e in entries.values()}
        old = {p.name: p.read_bytes() for p in self.receipts.glob('*.json')}
        # Same-day rerun preserves orphan receipts rather than overwriting them.
        with patch('core.beat_daily.BeatState', wraps=BeatState):
            run_daily(self.cloud, 'channel', DropboxAssets(self.assets_client), self.upload,
                self.receipts, source=self.source, renderer=self.renderer,
                clock=lambda: NOW + timedelta(hours=1))
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(old, {p.name: p.read_bytes() for p in self.receipts.glob('*.json')})
        self.assertEqual(len(attempted), 6)

    def test_unknown_response_permanently_blocks(self):
        def timeout(**kwargs):
            self.upload(**kwargs)
            raise RuntimeError('SECRET token URL')
        summary = self.run_worker(uploader=timeout)
        self.assertEqual(summary['unknown'], 6)
        self.run_worker()
        self.assertEqual(len(self.calls), 6)
        self.assertTrue(all(json.loads(p.read_text())['outcome'] == 'unknown'
                            for p in self.receipts.glob('*.json')))

    def test_render_failure_never_consumes_upload_budget(self):
        self.process.fail = 'render'
        summary = self.run_worker()
        self.assertGreater(summary['failed'], 0)
        self.assertEqual(self.cloud.read('state')[0]['attempts'], {})
        self.assertEqual(self.calls, [])

    def test_reservation_failure_never_calls_youtube(self):
        with patch.object(BeatState, 'reserve_attempt', side_effect=CloudError('SECRET')):
            summary = self.run_worker()
        self.assertGreater(summary['failed'], 0)
        self.assertEqual(self.calls, [])

    def test_reservation_lost_response_recovered_before_single_upload(self):
        original = BeatState.reserve_attempt
        def reserve(store, *args, **kwargs):
            self.memory.faults.append(('after_write', Transient()))
            return original(store, *args, **kwargs)
        with patch.object(BeatState, 'reserve_attempt', reserve):
            summary = self.run_worker()
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(len(self.calls), 6)

    def test_cloud_receipt_lost_response_remains_idempotent(self):
        def uploader(**kwargs):
            result = self.upload(**kwargs)
            self.memory.faults.append(('after_write', Transient()))
            return result
        summary = self.run_worker(uploader=uploader)
        self.assertEqual(summary['uploaded'], 6)
        self.run_worker()
        self.assertEqual(len(self.calls), 6)

    def test_pause_is_read_only(self):
        config, rev = self.cloud.read('config')
        config['channels'][0]['active'] = False
        self.cloud.write('config', config, rev)
        before = copy.deepcopy(self.memory.files)
        self.assertEqual(self.run_worker()['blocked'], 1)
        self.assertEqual(self.memory.files, before)
        self.assertEqual(self.public.calls, [])

    def test_global_budget_shared_across_channels(self):
        config, rev = self.cloud.read('config')
        second = copy.deepcopy(config['channels'][0])
        second['id'] = 'second'
        config['channels'].append(second)
        self.cloud.write('config', config, rev)
        self.run_worker()
        state, _ = self.cloud.read('state')
        self.assertEqual({job['channel'] for job in state['jobs'].values()}, {'channel'})
        summary = run_daily(self.cloud, 'second', DropboxAssets(self.assets_client), self.upload,
                            self.receipts, source=self.source, renderer=self.renderer, clock=lambda: NOW)
        self.assertEqual(summary['uploaded'], 0)
        self.assertGreater(summary['budget'], 0)
        self.assertEqual(len(self.calls), 6)

    def test_exclusive_reservation_race_only_one_winner(self):
        state, rev = self.cloud.read('state')
        apply_plan(state, plan(CONFIG, state, [{'id': 'TK101'}], NOW))
        self.cloud.write('state', state, rev)
        job_id = next(iter(state['jobs']))
        def reserve(index):
            try:
                return BeatState(self.cloud, lambda: NOW).reserve_attempt(job_id, str(index), exclusive=True)
            except ValueError:
                return None
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(len(self.cloud.read('state')[0]['attempts'][NOW.date().isoformat()]), 1)

    def test_concurrent_publish_calls_only_one_youtube_insert(self):
        state, rev = self.cloud.read('state')
        apply_plan(state, plan(CONFIG, state, [{'id': 'TK101'}], NOW))
        self.cloud.write('state', state, rev)
        job = next(iter(state['jobs'].values()))
        calls = []
        def uploader(**kwargs):
            calls.append(kwargs)
            return {'youtube_id': 'video000001'}
        def attempt(index):
            try:
                return publish(self.cloud, job, {'video': 'fake', 'thumbnail': 'fake'},
                    {'selected': {'title': 'Fixture', 'description': '', 'tags': []}},
                    uploader, self.receipts, lambda: NOW)
            except ValueError:
                return 'blocked'
        with ThreadPoolExecutor(max_workers=8) as pool:
            outcomes = list(pool.map(attempt, range(8)))
        self.assertEqual(len(calls), 1)
        self.assertEqual(outcomes.count('uploaded'), 1)
        row = json.loads(next(self.receipts.glob('*.json')).read_text())
        self.assertEqual(row['outcome'], 'uploaded')

    def test_unknown_jobs_block_even_on_day_with_new_budget(self):
        def timeout(**kwargs):
            self.upload(**kwargs)
            raise RuntimeError('SECRET')
        self.run_worker(uploader=timeout)
        old_slots = {call['publish_at'] for call in self.calls}
        self.calls.clear()
        run_daily(self.cloud, 'channel', DropboxAssets(self.assets_client), self.upload,
                  self.receipts, source=self.source, renderer=self.renderer,
                  clock=lambda: NOW + timedelta(days=1))
        self.assertTrue(all(call['publish_at'] not in old_slots for call in self.calls))

    def test_failed_local_journal_never_calls_youtube(self):
        with patch('core.beat_publish.journal', side_effect=OSError('SECRET')):
            summary = self.run_worker()
        self.assertGreater(summary['failed'], 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.cloud.read('state')[0]['attempts'], {})

    def test_thumbnail_failure_is_sanitized_alert_without_retry(self):
        def uploader(**kwargs):
            return dict(self.upload(**kwargs), thumbnail_error='SECRET https://private.invalid')
        summary = self.run_worker(uploader=uploader)
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['thumbnail_failed'], 6)
        self.assertNotIn('SECRET', message(summary))
        self.run_worker()
        self.assertEqual(len(self.calls), 6)

    def test_cli_dry_run_bootstrap_and_no_token_or_telegram_required(self):
        output = io.StringIO()
        with patch.dict('os.environ', {'BEAT_CHANNEL_ID': 'channel'}, clear=True), \
             patch('core.beat_worker.DropboxTransport.from_env', return_value=self.memory), \
             patch('core.beat_worker.DropboxAssets.from_env', return_value=DropboxAssets(self.assets_client)), \
             patch('core.beat_worker.run_daily', wraps=lambda *args, **kw:
                   self.run_worker(dry_run=kw['dry_run'])), \
             patch('sys.stdout', output):
            result = worker_main(['--dry-run', '--receipts', str(self.receipts)])
        self.assertEqual(result, 0)
        self.assertTrue(json.loads(output.getvalue())['dry_run'])
        self.assertFalse(self.receipts.exists())

    def test_cli_bootstrap_exception_cannot_expose_secrets(self):
        output = io.StringIO()
        with patch.dict('os.environ', {'BEAT_CHANNEL_ID': 'channel'}, clear=True), \
             patch('core.beat_worker.DropboxTransport.from_env', side_effect=RuntimeError('SECRET')), \
             patch('sys.stdout', output):
            self.assertEqual(worker_main(['--dry-run']), 1)
        self.assertNotIn('SECRET', output.getvalue())

    def test_cli_cloud_bootstrap_failure_sends_sanitized_alert(self):
        output, alerts = io.StringIO(), []
        with patch.dict('os.environ', {'BEAT_CHANNEL_ID': 'channel',
                'BEAT_TELEGRAM_TOKEN': '123:abc', 'BEAT_TELEGRAM_CHAT_ID': '456'}, clear=True), \
             patch('core.beat_worker.Telegram', return_value=alerts.append), \
             patch('core.beat_worker.DropboxTransport.from_env', side_effect=RuntimeError('SECRET')), \
             patch('sys.stdout', output):
            self.assertEqual(worker_main([]), 1)
        self.assertEqual(alerts, [{'failed': 1, 'dry_run': False}])
        self.assertNotIn('SECRET', output.getvalue())

    def test_notification_failure_cannot_cause_repeat_upload(self):
        def fail(summary):
            raise RuntimeError('SECRET')
        summary = run_daily(self.cloud, 'channel', DropboxAssets(self.assets_client), self.upload,
                            self.receipts, source=self.source, renderer=self.renderer,
                            clock=lambda: NOW, notify=fail)
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['failed'], 1)
        self.run_worker()
        self.assertEqual(len(self.calls), 6)

    def test_telegram_never_includes_external_strings(self):
        text = message({'failed': 3, 'error': 'SECRET', 'channel': 'private',
                        'unknown': 'https://private.invalid', 'orphan': 1})
        self.assertNotIn('SECRET', text)
        self.assertNotIn('private', text)
        self.assertIn('orphan: 1', text)


class ActionsTests(unittest.TestCase):
    def test_matrix_injection_rejected(self):
        for raw in ('[]', '["a","a"]', '["$(secret)"]', '["../master"]', '[1]', '{}'):
            with self.assertRaises(ValueError):
                matrix(raw)
        self.assertEqual(matrix('["one","two"]'), [{'channel': 'one'}, {'channel': 'two'}])

    def test_environment_master_only_and_fail_closed(self):
        def check(policy, rules, ref='refs/heads/master'):
            class Opener:
                def open(inner, req, **kwargs):
                    data = {'deployment_branch_policy': policy} if '/deployment-branch-policies' not in req.full_url else rules
                    return Response(data)
            return check_environment({'GITHUB_REF': ref, 'BEAT_SLUG': 'one',
                'GITHUB_REPOSITORY': 'Perree/video-type-beat-generator',
                'GITHUB_EVENT_NAME': 'schedule'}, Opener())
        policy = {'protected_branches': False, 'custom_branch_policies': True}
        rules = {'total_count': 1, 'branch_policies': [{'name': 'master', 'type': 'branch'}]}
        check(policy, rules)
        for changed in (None, {'protected_branches': True, 'custom_branch_policies': False}):
            with self.assertRaises(ValueError):
                check(changed, rules)
        for name, kind in (('*', 'branch'), ('master', 'tag'), ('main', 'branch'), ('master', None)):
            with self.assertRaises(ValueError):
                check(policy, {'total_count': 1, 'branch_policies': [{'name': name, 'type': kind}]})
        with self.assertRaises(ValueError):
            check(policy, rules, 'refs/heads/feature')


class Response:
    status = 200
    def __init__(self, data):
        self.data = data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass
    def read(self, size):
        return json.dumps(self.data).encode()
