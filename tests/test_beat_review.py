"""Confirmed phase-eight audit regressions, without network or public uploads."""
import copy
import io
import logging
import unittest
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import test_beat_daily as fixtures
from core.beat_actions import check_context, bind_channel, TRUSTED_REPOSITORY
from core.beat_cloud import BeatCloud, CloudError, Transient
from core.beat_google import service
from core.beat_http import BeatError
from core.beat_logs import quiet_dependencies
from core.beat_publish import journal
from core.beat_schema import migrate
from core.beat_youtube import BeatYouTube


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.case = fixtures.DailyTests()
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)

    def test_prebound_logging_handler_cannot_emit_secret(self):
        output = io.StringIO()
        logger = logging.getLogger('googleapiclient.http')
        handler = logging.StreamHandler(output)
        logger.addHandler(handler)
        previous = logging.root.manager.disable
        try:
            with quiet_dependencies():
                logger.warning('FIXTURE_SECRET')
                print('FIXTURE_SECRET')
                raise ValueError('fixture')
        except ValueError:
            pass
        finally:
            logger.removeHandler(handler)
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(logging.root.manager.disable, previous)

    def test_forks_other_refs_and_untrusted_events_rejected(self):
        env = {'GITHUB_REPOSITORY': TRUSTED_REPOSITORY, 'GITHUB_REF': 'refs/heads/master',
               'GITHUB_EVENT_NAME': 'schedule'}
        check_context(env)
        for key, value in [('GITHUB_REPOSITORY', 'fork/video-type-beat-generator'),
                           ('GITHUB_REF', 'refs/heads/feature'), ('GITHUB_EVENT_NAME', 'pull_request_target')]:
            with self.assertRaisesRegex(ValueError, 'untrusted_actions_context'):
                check_context(dict(env, **{key: value}))

    def test_environment_channel_binding_and_duplicate_slugs(self):
        bind_channel({'actions_slug': 'one'}, 'one')
        for channel in ({}, {'actions_slug': 'other'}):
            with self.assertRaisesRegex(ValueError, 'environment_channel_mismatch'):
                bind_channel(channel, 'one')
        config = copy.deepcopy(fixtures.CONFIG)
        config['channels'][0]['actions_slug'] = 'one'
        config['channels'].append(dict(config['channels'][0], id='other'))
        with self.assertRaisesRegex(ValueError, 'invalid_actions_slug'):
            migrate(config, 'config')

    def test_worker_crossed_environment_aborts_before_render(self):
        from core.beat_worker import main
        config, rev = self.case.cloud.read('config')
        config['channels'][0]['actions_slug'] = 'other'
        self.case.cloud.write('config', config, rev)
        env = {'GITHUB_ACTIONS': 'true', 'GITHUB_REPOSITORY': TRUSTED_REPOSITORY,
               'GITHUB_REF': 'refs/heads/master', 'GITHUB_EVENT_NAME': 'workflow_dispatch',
               'BEAT_SLUG': 'one', 'BEAT_CHANNEL_ID': 'channel'}
        with patch.dict('os.environ', env, clear=True), \
             patch('core.beat_worker.DropboxTransport.from_env', return_value=self.case.memory), \
             patch('core.beat_worker.DropboxAssets.from_env'), \
             patch('core.beat_worker.run_daily') as daily, patch('sys.stdout', io.StringIO()):
            self.assertEqual(main(['--dry-run']), 1)
        daily.assert_not_called()

    def test_lost_lease_before_upload_spends_no_attempt(self):
        original = self.case.renderer
        @contextmanager
        def renderer(*args, **kwargs):
            with original(*args, **kwargs) as media:
                self.case.cloud.update('state', lambda state: state.update(lock=None))
                yield media
        with patch.object(self.case, 'renderer', renderer):
            summary = self.case.run_worker(private_pilot=True)
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(self.case.calls, [])
        self.assertEqual(self.case.cloud.read('state')[0]['attempts'], {})

    def test_lost_lease_after_intent_retains_barrier_without_insert(self):
        def writing(*args, **kwargs):
            row = journal(*args, **kwargs)
            if args[2] == 'unknown':
                self.case.cloud.update('state', lambda state: state.update(lock=None))
            return row
        with patch('core.beat_publish.journal', side_effect=writing):
            summary = self.case.run_worker(private_pilot=True)
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(self.case.calls, [])
        state = self.case.cloud.read('state')[0]
        attempts = [entry for rows in state['attempts'].values() for entry in rows.values()]
        self.assertEqual(len(attempts), 1)
        summary = self.case.run_worker()
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(len(self.case.calls), 5)
        self.assertNotIn('youtube_id', self.case.cloud.read('state')[0]['jobs'][attempts[0]['job_id']])

    def test_destination_changed_during_render_blocks_upload(self):
        config, rev = self.case.cloud.read('config')
        config['channels'][0]['youtube_channel_id'] = 'UC' + 'a'*22
        self.case.cloud.write('config', config, rev)
        original = self.case.renderer
        @contextmanager
        def renderer(*args, **kwargs):
            with original(*args, **kwargs) as media:
                config, rev = self.case.cloud.read('config')
                config['channels'][0]['youtube_channel_id'] = 'UC' + 'b'*22
                self.case.cloud.write('config', config, rev)
                yield media
        with patch.object(self.case, 'renderer', renderer):
            summary = self.case.run_worker(private_pilot=True)
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(self.case.calls, [])
        self.assertEqual(self.case.cloud.read('state')[0]['attempts'], {})

    def test_destination_changed_after_owner_verification_blocks_catalog_and_upload(self):
        config, rev = self.case.cloud.read('config')
        config['channels'][0]['youtube_channel_id'] = 'UC' + 'b'*22
        self.case.cloud.write('config', config, rev)
        summary = self.case.run_worker(expected_owner='UC'+'a'*22)
        self.assertEqual(summary['failed'], 1)
        self.assertEqual(self.case.calls, [])
        self.assertEqual(self.case.public.calls, [])
        self.assertEqual(self.case.cloud.read('state')[0]['attempts'], {})

    def test_final_local_receipt_failure_keeps_uploaded_and_thumbnail(self):
        thumbnails = []
        def writing(*args, **kwargs):
            if args[2] == 'uploaded':
                raise OSError('disk fixture')
            return journal(*args, **kwargs)
        with patch('core.beat_publish.journal', side_effect=writing):
            summary = self.case.run_worker(thumbnailer=lambda *a: thumbnails.append(a))
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(len(thumbnails), 6)
        self.assertEqual(len(self.case.calls), 6)
        self.case.run_worker()
        self.assertEqual(len(self.case.calls), 6)

    def test_unbounded_and_invalid_backoff_fail_without_sleep(self):
        for delay in (1000000, float('nan'), float('inf'), -1, '30'):
            sleeps = []
            with self.assertRaisesRegex(CloudError, 'retry_delay_exceeds_budget'):
                BeatCloud(None, sleep=sleeps.append)._retry(lambda: (_ for _ in ()).throw(Transient(delay)))
            self.assertEqual(sleeps, [])

    def test_allowed_retry_after_is_respected(self):
        calls, sleeps = [], []
        def operation():
            calls.append(1)
            if len(calls) == 1:
                raise Transient(30)
            return True
        self.assertTrue(BeatCloud(None, sleep=sleeps.append)._retry(operation))
        self.assertEqual(sleeps, [30])

    def test_google_transport_fixed_hosts_deadline_proxy_redirects(self):
        now = [0]
        with patch('google.oauth2.credentials.Credentials.from_authorized_user_file', return_value=object()), \
             patch('googleapiclient.discovery.build', side_effect=lambda *a, **kw: kw['http']):
            authorized = service('fixture', clock=lambda: now[0], seconds=1800)
        http = authorized.http
        self.assertIsNone(http.proxy_info)
        self.assertFalse(http.follow_redirects)
        self.assertNotIn(308, http.redirect_codes)
        with patch('httplib2.Http.request', return_value=(SimpleNamespace(status=200), b'{}')) as request:
            http.request('https://www.googleapis.com/youtube/v3/channels')
            self.assertEqual(http.timeout, 30)
            for url in ('https://evil.invalid/upload', 'http://www.googleapis.com/upload'):
                with self.assertRaises(BeatError):
                    http.request(url)
            self.assertEqual(request.call_count, 1)
            now[0] = 1800
            with self.assertRaises(TimeoutError):
                http.request('https://www.googleapis.com/upload')
            self.assertEqual(request.call_count, 1)
        now[0] = 0
        with patch('httplib2.Http.request', return_value=(SimpleNamespace(status=302), b'')):
            with self.assertRaisesRegex(ValueError, 'youtube_redirect_rejected'):
                http.request('https://www.googleapis.com/upload')

    def test_stalled_upload_deadline_closes_media_without_second_insert(self):
        path = Path(self.case.temp.name) / 'video.mp4'
        path.write_bytes(b'fixture')
        media = []
        client = BeatYouTube(self.case.temp.name)
        class Google:
            def videos(inner): return inner
            def insert(inner, **kwargs):
                media.append(kwargs['media_body'])
                return SimpleNamespace(next_chunk=lambda: (None, None))
        with patch.object(client, 'service', return_value=Google()), \
             patch('core.beat_youtube.time.monotonic', side_effect=[0, 0, 1800]):
            with self.assertRaises(TimeoutError):
                client.upload(channel='channel', video_path=str(path), title='fixture')
        self.assertEqual(len(media), 1)
        self.assertTrue(media[0].stream().closed)

    def test_google_server_error_retries_same_request_with_finite_backoff(self):
        from googleapiclient.errors import HttpError
        import httplib2
        path = Path(self.case.temp.name) / 'video.mp4'
        path.write_bytes(b'fixture')
        inserts, chunks = [], []
        client = BeatYouTube(self.case.temp.name)
        class Google:
            def videos(inner): return inner
            def insert(inner, **kwargs):
                inserts.append(kwargs)
                def chunk():
                    chunks.append(1)
                    raise HttpError(httplib2.Response({'status': '503'}), b'{}')
                return SimpleNamespace(next_chunk=chunk)
        with patch.object(client, 'service', return_value=Google()), \
             patch('core.beat_youtube.time.sleep') as sleep:
            with self.assertRaises(HttpError):
                client.upload(channel='channel', video_path=str(path), title='fixture')
        self.assertEqual(len(inserts), 1)
        self.assertEqual(len(chunks), 6)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [1, 2, 4, 8, 16])
        self.assertTrue(inserts[0]['media_body'].stream().closed)
