"""Phase 6 smokes: real phase contracts with fake external services."""
import copy
import io
import json
import sys
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
from core.beat_selection import TrackNotMatching
from core.beat_seo_store import prepare_seo
from core.beat_source import BeatStarsSource
from core.beat_state import BeatState
from core.beat_video import render_reserved
from core.beat_worker import main as worker_main
from core.beat_youtube import BeatYouTube
from core.beat_publish import journal

# Los fixtures compartidos viven en tests/; así corre también como tests.test_beat_daily.
sys.path.insert(0, str(Path(__file__).resolve().parent))
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

    def test_no_selection_matches_blocks_before_any_reservation_or_render(self):
        self.cloud.update('config', lambda config: config['channels'][0].update(
            selection_tags=['SENSITIVE-selection-tag']))
        # Existing quota and legacy jobs must also remain untouched.
        store = BeatState(self.cloud, lambda: NOW)
        owner = store.acquire()
        jobs = store.fill_buffer(CONFIG, [{'id': 'TK101'}], owner)
        store.release(owner)
        store.reserve_attempt(jobs[0]['id'], 'existing-attempt')
        before = self.cloud.read('state')
        with patch.object(BeatState, 'acquire') as acquire, \
             patch.object(BeatState, 'fill_buffer') as fill, \
             patch.object(BeatState, 'reserve_attempt') as reserve, \
             patch.object(self, 'renderer') as render, \
             patch('core.beat_daily.prepare_seo') as seo:
            summary = self.run_worker(report_loader=lambda: self.fail('SEO report loaded'))
        for call in (acquire, fill, reserve, render, seo):
            call.assert_not_called()
        self.assertEqual(summary['no_matching_tracks'], 1)
        self.assertEqual(summary['blocked'], 1)
        for key in ('planned', 'eligible', 'uploaded', 'failed', 'budget'):
            self.assertEqual(summary[key], 0)
        self.assertEqual(self.cloud.read('state'), before)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.hls.calls)
        self.assertFalse(self.receipts.exists())
        self.assertEqual(self.notifications, [summary])
        safe = message(dict(summary, selection_tags=['SENSITIVE-selection-tag'],
                            error='SENSITIVE-error', channel='SENSITIVE-channel'))
        self.assertIn('no_matching_tracks: 1', safe)
        self.assertNotIn('SENSITIVE', safe)

    def test_selection_no_matches_dry_run_is_read_only(self):
        self.cloud.update('config', lambda config: config['channels'][0].update(
            selection_tags=['missing']))
        before = self.cloud.read('state')
        summary = self.run_worker(dry_run=True)
        self.assertEqual(summary['no_matching_tracks'], 1)
        self.assertEqual(self.cloud.read('state'), before)
        self.assertEqual(self.notifications, [])
        self.assertEqual(self.calls, [])

    def test_selection_matching_subset_excludes_legacy_buffer_jobs(self):
        # Reserve the old full catalog, then narrow the channel's selection.
        self.cloud.update('state', lambda state: apply_plan(state, plan(
            CONFIG, state, [{'id': f'TK{number}'} for number in range(101, 115)], NOW)))
        self.cloud.update('config', lambda config: config['channels'][0].update(
            selection_tags=['  AMBIENT  ']))
        self.public.fixture['pages'][0]['profileTracks']['content'][0]['metadata']['tags'] = ['Ambient']
        summary = self.run_worker()
        self.assertEqual(summary['uploaded'], 1)
        self.assertEqual(summary['eligible'], 1)
        self.assertEqual(summary['blocked'], 13)
        self.assertEqual(summary['failed'], 0)
        state, _ = self.cloud.read('state')
        entries = list(state['attempts'][NOW.date().isoformat()].values())
        self.assertEqual(len(entries), 1)
        self.assertEqual(state['jobs'][entries[0]['job_id']]['track_id'], 'TK101')
        self.assertTrue(all(job['status'] == 'planned' for job in state['jobs'].values()
                            if job['track_id'] != 'TK101'))

    def test_selection_blocks_only_its_channel_and_leaves_quota_for_other_channel(self):
        second = dict(CONFIG['channels'][0], id='second', selection_tags=[' TRAP '])
        self.cloud.update('config', lambda config: (
            config['channels'][0].update(selection_tags=['missing']),
            config['channels'].append(second)))
        summary = self.run_worker()
        self.assertEqual(summary['no_matching_tracks'], 1)
        self.assertEqual(self.cloud.read('state')[0]['jobs'], {})
        other = run_daily(self.cloud, 'second', DropboxAssets(self.assets_client), self.upload,
                          self.receipts, source=self.source, renderer=self.renderer, clock=lambda: NOW)
        self.assertEqual(other['uploaded'], 6)
        self.assertEqual(other['no_matching_tracks'], 0)
        self.assertEqual(other['failed'], 0)
        state, _ = self.cloud.read('state')
        self.assertEqual({job['channel'] for job in state['jobs'].values()}, {'second'})
        self.assertEqual(len(state['attempts'][NOW.date().isoformat()]), 6)

    def test_empty_selection_tags_preserves_legacy_worker_behavior(self):
        self.cloud.update('config', lambda config: config['channels'][0].update(selection_tags=[]))
        summary = self.run_worker()
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(summary['no_matching_tracks'], 0)

    def test_selection_change_during_scan_blocks_before_reserving_jobs(self):
        scan = self.source.scan
        def change(*args):
            snapshot = scan(*args)
            self.cloud.update('config', lambda config: config['channels'][0].update(
                selection_tags=['missing']))
            return snapshot
        before = self.cloud.read('state')
        with patch.object(self.source, 'scan', side_effect=change), \
             patch.object(self, 'renderer') as renderer:
            summary = self.run_worker()
        renderer.assert_not_called()
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(summary['planned'], 0)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(self.cloud.read('state'), before)
        self.assertEqual(self.calls, [])

    def test_selection_change_during_seo_report_blocks_before_reserving_jobs(self):
        before = self.cloud.read('state')
        def report():
            self.cloud.update('config', lambda config: config['channels'][0].update(
                selection_tags=['missing']))
        with patch.object(self, 'renderer') as renderer:
            summary = self.run_worker(report_loader=report)
        renderer.assert_not_called()
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(summary['planned'], 0)
        self.assertEqual(self.cloud.read('state'), before)

    def test_selection_change_before_next_render_blocks_pending_jobs(self):
        original = self.renderer
        @contextmanager
        def change(*args, **kwargs):
            with original(*args, **kwargs) as media:
                yield media
            # The first insert already happened; later pending jobs must stop.
            self.cloud.update('config', lambda config: config['channels'][0].update(
                selection_tags=['missing']))
        with patch.object(self, 'renderer', side_effect=change) as renderer:
            summary = self.run_worker()
        self.assertEqual(summary['uploaded'], 1)
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(renderer.call_count, 1)
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(len(self.cloud.read('state')[0]['attempts'][NOW.date().isoformat()]), 1)

    def test_selection_change_during_buffer_acquire_cannot_reserve_jobs(self):
        acquire = BeatState.acquire
        def change(store, *args, **kwargs):
            owner = acquire(store, *args, **kwargs)
            self.cloud.update('config', lambda config: config['channels'][0].update(selection_tags=['missing']))
            return owner
        with patch.object(BeatState, 'acquire', change), patch.object(self, 'renderer') as renderer:
            summary = self.run_worker()
        renderer.assert_not_called()
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(summary['planned'], 0)
        state = self.cloud.read('state')[0]
        self.assertEqual(state['jobs'], {})
        self.assertEqual(state['attempts'], {})
        self.assertIsNone(state['lock'])

    def test_selection_change_during_job_seo_blocks_before_render(self):
        def change(*args, **kwargs):
            snapshot = prepare_seo(*args, **kwargs)
            self.cloud.update('config', lambda config: config['channels'][0].update(selection_tags=['missing']))
            return snapshot
        with patch('core.beat_daily.prepare_seo', side_effect=change), \
             patch.object(self, 'renderer') as renderer:
            summary = self.run_worker()
        renderer.assert_not_called()
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(self.cloud.read('state')[0]['attempts'], {})
        self.assertEqual(self.calls, [])

    def test_selection_change_during_render_or_lease_renewal_spends_no_attempt(self):
        original = self.renderer
        for phase in ('render', 'renew'):
            with self.subTest(phase=phase):
                self.cloud.update('config', lambda config: config['channels'][0].pop('selection_tags', None))
                @contextmanager
                def change(*args, **kwargs):
                    with original(*args, **kwargs) as media:
                        def changed():
                            self.cloud.update('config', lambda config: config['channels'][0].update(
                                selection_tags=['missing']))
                        if phase == 'render':
                            changed()
                        else:
                            fence = media['before_upload']
                            def renew():
                                fence()
                                changed()
                            media = dict(media, before_upload=renew)
                        yield media
                with patch.object(self, 'renderer', side_effect=change) as renderer:
                    summary = self.run_worker()
                self.assertEqual(summary['blocked'], 1)
                self.assertEqual(summary['failed'], 0)
                self.assertEqual(renderer.call_count, 1)
                self.assertEqual(self.calls, [])
                self.assertEqual(self.cloud.read('state')[0]['attempts'], {})
                self.assertFalse(list(self.receipts.glob('*.json')))

    def test_selection_change_after_intent_blocks_upload_and_keeps_ledger(self):
        def write(*args, **kwargs):
            row = journal(*args, **kwargs)
            if args[2] == 'unknown':
                self.cloud.update('config', lambda config: config['channels'][0].update(
                    selection_tags=['missing']))
            return row
        with patch('core.beat_publish.journal', side_effect=write):
            summary = self.run_worker()
        self.assertEqual(summary['blocked'], 1)
        self.assertEqual(summary['failed'], 0)
        self.assertEqual(self.calls, [])
        before = self.cloud.read('state')
        self.assertEqual(len(before[0]['attempts'][NOW.date().isoformat()]), 1)
        again = self.run_worker()
        self.assertEqual(again['no_matching_tracks'], 1)
        self.assertEqual(self.cloud.read('state'), before)
        self.assertEqual(self.calls, [])

    def test_other_channel_filter_changes_do_not_block_this_channel(self):
        self.cloud.update('config', lambda config: config['channels'].append(
            dict(config['channels'][0], id='other', selection_tags=['missing'])))
        scan = self.source.scan
        def change(*args):
            snapshot = scan(*args)
            self.cloud.update('config', lambda config: config['channels'][1].update(selection_tags=['trap']))
            return snapshot
        with patch.object(self.source, 'scan', side_effect=change):
            summary = self.run_worker()
        self.assertEqual(summary['uploaded'], 6)
        self.assertEqual(summary['blocked'], 0)
        self.assertEqual(summary['failed'], 0)

    def test_selection_old_job_direct_seo_and_render_are_blocked_before_writes(self):
        job = self.prepare_job()
        self.cloud.update('config', lambda config: config['channels'][0].update(selection_tags=['missing']))
        channel = self.cloud.read('config')[0]['channels'][0]
        track = self.source.scan(CONFIG['beatstars_profile_url']).tracks[0].payload()
        before = self.cloud.read('state')
        for dry_run in (False, True):
            with self.subTest(dry_run=dry_run):
                with self.assertRaises(TrackNotMatching):
                    prepare_seo(self.cloud, job['id'], track, channel, NOW.isoformat(), dry_run=dry_run)
                with patch.object(BeatState, 'acquire') as acquire:
                    with self.assertRaises(TrackNotMatching):
                        with self.renderer(self.cloud, job['id'], track, channel, 'trap',
                                           CONFIG['beatstars_profile_url'], DropboxAssets(self.assets_client),
                                           dry_run=dry_run):
                            self.fail('excluded job rendered')
                acquire.assert_not_called()
                self.assertEqual(self.cloud.read('state'), before)
                self.assertEqual(self.process.calls, [])
                self.assertEqual(self.hls.calls, [])
                self.assertEqual(self.assets_client.downloads, [])

    def test_selection_direct_publish_rejects_excluded_or_unknown_track_without_quota(self):
        job = self.prepare_job()
        self.cloud.update('config', lambda config: config['channels'][0].update(selection_tags=['ambient']))
        before = self.cloud.read('state')
        for track in ({'id': job['track_id'], 'tags': ['trap']},
                      {'id': 'TK999', 'tags': ['ambient']}, None):
            with self.subTest(track=track):
                with self.assertRaises(TrackNotMatching):
                    publish(self.cloud, job, {'video': 'fake', 'thumbnail': 'fake'},
                            {'track': track, 'selected': {'title': 'Fixture'}}, self.upload,
                            self.receipts, lambda: NOW)
                self.assertEqual(self.cloud.read('state'), before)
                self.assertEqual(self.calls, [])
                self.assertFalse(self.receipts.exists())

    def test_selection_direct_publish_rechecks_filter_after_intent(self):
        job = self.prepare_job()
        self.cloud.update('config', lambda config: config['channels'][0].update(selection_tags=['trap']))
        def write(*args, **kwargs):
            row = journal(*args, **kwargs)
            if args[2] == 'unknown':
                self.cloud.update('config', lambda config: config['channels'][0].update(selection_tags=['missing']))
            return row
        with patch('core.beat_publish.journal', side_effect=write):
            with self.assertRaises(TrackNotMatching):
                publish(self.cloud, job, {'video': 'fake', 'thumbnail': 'fake'},
                        {'track': {'id': job['track_id'], 'tags': ['trap']}, 'selected': {'title': 'Fixture'}},
                        self.upload, self.receipts, lambda: NOW)
        self.assertEqual(self.calls, [])
        self.assertEqual(len(self.cloud.read('state')[0]['attempts'][NOW.date().isoformat()]), 1)

    def test_selection_direct_publish_backoff_cannot_spend_quota_under_stale_filter(self):
        job = self.prepare_job()
        self.cloud.update('config', lambda config: config['channels'][0].update(selection_tags=['trap']))
        before = self.cloud.read('state')
        self.memory.faults.append(('write', Transient()))
        self.cloud.sleep = lambda _: self.cloud.update('config', lambda config:
            config['channels'][0].update(selection_tags=['missing']))
        with self.assertRaises(TrackNotMatching):
            publish(self.cloud, job, {'video': 'fake', 'thumbnail': 'fake'},
                    {'track': {'id': job['track_id'], 'tags': ['trap']}, 'selected': {'title': 'Fixture'}},
                    self.upload, self.receipts, lambda: NOW)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.cloud.read('state'), before)
        self.assertFalse(list(self.receipts.glob('*.json')))

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

    def test_upload_error_reason_reaches_telegram(self):
        from googleapiclient.errors import HttpError
        from types import SimpleNamespace as NS
        body = json.dumps({'error': {'message': 'SECRET',
                                     'errors': [{'reason': 'quotaExceeded'}]}}).encode()
        def quota(**kwargs):
            self.upload(**kwargs)
            raise HttpError(NS(status=403, reason='x'), body)
        summary = self.run_worker(uploader=quota)
        self.assertEqual(summary['unknown'], 6)
        self.assertEqual(summary['reasons'], {'youtube_quota': 6})
        text = message(self.notifications[0])
        self.assertIn('cuota diaria', text)
        self.assertNotIn('SECRET', text)

    def test_render_failure_reports_a_reason(self):
        self.process.fail = 'render'
        summary = self.run_worker()
        self.assertGreater(summary['failed'], 0)
        self.assertEqual(sum(summary['reasons'].values()), summary['failed'])
        self.assertIn('Motivos:', message(summary))

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
        self.assertEqual(alerts, [{'failed': 1, 'dry_run': False,
                                   'reasons': {'error_runtimeerror': 1}}])
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


MONDAY_TAKEN = [{'youtube_id': 'manual00001', 'title': 'manual', 'privacy': 'private',
                 'published_at': '2026-10-01T10:00:00Z',
                 # Lunes 12/10 15:00 en Buenos Aires: ocupa todo ese lunes.
                 'publish_at': '2026-10-12T18:00:00Z'}]
MONDAY = instant('2026-10-12T18:00:00-03:00').date()


class CalendarTests(unittest.TestCase):
    """Calendario de YouTube en el worker diario: lunes ocupado, slots lunes y jueves."""
    renderer = DailyTests.renderer
    upload = DailyTests.upload
    run_worker = DailyTests.run_worker

    def setUp(self):
        DailyTests.setUp(self)
        self.cloud.update('config', lambda config: config['channels'][0].update(
            slots=[{'weekday': 0, 'hour': 18, 'minute': 0}, {'weekday': 3, 'hour': 18, 'minute': 0}]))
        self.reads = []

    def calendar(self, *answers):
        """Lector falso: devuelve las respuestas en orden y repite la última."""
        def read(channel):
            self.reads.append(channel)
            answer = answers[min(len(self.reads), len(answers)) - 1]
            if isinstance(answer, Exception):
                raise answer
            return answer
        return read

    def preplan(self, channel='channel'):
        state, rev = self.cloud.read('state')
        config = self.cloud.read('config')[0]
        config = dict(config, channels=[ch for ch in config['channels'] if ch['id'] == channel])
        apply_plan(state, plan(config, state, [{'id': f'TK{n}'} for n in range(101, 115)], NOW))
        self.cloud.write('state', state, rev)
        return state

    def days(self, status=None, channel='channel'):
        state = self.cloud.read('state')[0]
        return sorted(instant(job['slot']).date() for job in state['jobs'].values()
                      if job['channel'] == channel and (status is None or job['status'] == status))

    def test_taken_monday_moves_new_job_to_thursday(self):
        summary = self.run_worker(calendar=self.calendar(MONDAY_TAKEN))
        self.assertEqual(self.reads[0], 'channel')
        self.assertNotIn(MONDAY, self.days())
        self.assertEqual(self.days()[0].isoformat(), '2026-10-15')
        self.assertEqual(summary['uploaded'], 3)
        self.assertEqual(summary['calendar_unavailable'], 0)
        self.assertTrue(all(instant(call['publish_at']).date() != MONDAY for call in self.calls))

    def test_planned_monday_job_cancelled_without_reserving_attempt(self):
        state = self.preplan()
        monday = next(job['id'] for job in state['jobs'].values()
                      if instant(job['slot']).date() == MONDAY)
        reserved = []
        original = BeatState.reserve_attempt
        def reserve(store, job_id, *args, **kwargs):
            reserved.append(job_id)
            return original(store, job_id, *args, **kwargs)
        with patch.object(BeatState, 'reserve_attempt', reserve):
            summary = self.run_worker(calendar=self.calendar(MONDAY_TAKEN))
        jobs = self.cloud.read('state')[0]['jobs']
        self.assertEqual(jobs[monday]['status'], 'cancelled')
        self.assertNotIn(monday, reserved)
        self.assertEqual(summary['uploaded'], 3)
        self.assertTrue(all(instant(call['publish_at']).date() != MONDAY for call in self.calls))

    def test_loader_failure_keeps_jobs_and_uploads_nothing(self):
        self.preplan()
        before = self.cloud.read('state')
        summary = self.run_worker(calendar=self.calendar(youtube.YouTubeError('SECRET')))
        self.assertEqual(summary['calendar_unavailable'], 1)
        self.assertEqual(summary['planned'], 0)
        self.assertEqual(self.cloud.read('state'), before)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.hls.calls)
        self.assertEqual(self.notifications, [summary])
        self.assertIn('calendar_unavailable: 1', message(summary))
        self.assertEqual(summary['reasons'], {'calendar_read_failed': 1})
        self.assertNotIn('SECRET', message(summary))

    def test_invalid_calendar_row_is_unavailable_too(self):
        bad = [dict(MONDAY_TAKEN[0], publish_at='basura')]
        summary = self.run_worker(calendar=self.calendar(bad))
        self.assertEqual(summary['calendar_unavailable'], 1)
        self.assertEqual(self.cloud.read('state')[0]['jobs'], {})
        self.assertEqual(self.calls, [])

    def test_second_read_blocks_upload_first_read_allowed(self):
        summary = self.run_worker(calendar=self.calendar([], MONDAY_TAKEN))
        state = self.cloud.read('state')[0]
        monday = [job for job in state['jobs'].values() if instant(job['slot']).date() == MONDAY]
        self.assertEqual([job['status'] for job in monday], ['cancelled'])
        attempted = {e['job_id'] for day in state['attempts'].values() for e in day.values()}
        self.assertNotIn(monday[0]['id'], attempted)
        self.assertEqual(summary['uploaded'], 3)
        self.assertEqual(summary['eligible'], 3)
        self.assertTrue(all(instant(call['publish_at']).date() != MONDAY for call in self.calls))

    def test_recheck_failure_stops_uploads(self):
        summary = self.run_worker(calendar=self.calendar([], youtube.YouTubeError('down')))
        self.assertEqual(summary['calendar_unavailable'], 1)
        self.assertGreater(summary['planned'], 0)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.cloud.read('state')[0]['attempts'], {})
        self.assertTrue(all(job['status'] == 'planned'
                            for job in self.cloud.read('state')[0]['jobs'].values()))

    def test_uploaded_and_attempted_jobs_are_never_cancelled(self):
        state = self.preplan()
        ordered = sorted(state['jobs'].values(), key=lambda job: job['slot'])
        uploaded, attempted = ordered[0], ordered[1]
        self.assertEqual(instant(uploaded['slot']).date(), MONDAY)
        self.cloud.update('state', lambda s: s['jobs'][uploaded['id']].update(
            status='uploaded', youtube_id='video000099', uploaded_at=NOW.isoformat(),
            publication_mode='scheduled'))
        BeatState(self.cloud, lambda: NOW).reserve_attempt(attempted['id'], 'lost-response')
        thursday = [dict(MONDAY_TAKEN[0], publish_at='2026-10-15T21:00:00Z')]
        self.run_worker(calendar=self.calendar(MONDAY_TAKEN + thursday))
        jobs = self.cloud.read('state')[0]['jobs']
        self.assertEqual(jobs[uploaded['id']]['status'], 'uploaded')
        # Un intento reservado pudo haber subido el video que ocupa ese jueves.
        self.assertEqual(jobs[attempted['id']]['status'], 'planned')

    def test_other_channel_jobs_untouched(self):
        self.cloud.update('config', lambda config: config['channels'].append(
            dict(config['channels'][0], id='second')))
        self.preplan('second')
        before = {k: v for k, v in self.cloud.read('state')[0]['jobs'].items()}
        self.run_worker(calendar=self.calendar(MONDAY_TAKEN))
        jobs = self.cloud.read('state')[0]['jobs']
        self.assertTrue(all(jobs[key] == job for key, job in before.items()))
        self.assertIn(MONDAY, self.days(channel='second'))
        self.assertEqual(set(self.reads), {'channel'})

    def test_dry_run_never_calls_loader(self):
        summary = self.run_worker(dry_run=True, calendar=lambda channel: self.fail('YouTube read'))
        self.assertGreater(summary['planned'], 0)
        self.assertEqual(summary['calendar_unavailable'], 0)

    def test_private_pilot_uses_free_day_without_publish_at(self):
        calls = []
        def uploader(**kwargs):
            calls.append(kwargs)
            return {'youtube_id': 'video000001', 'thumbnail_error': ''}
        self.preplan()
        summary = self.run_worker(uploader=uploader, private_pilot=True,
                                  calendar=self.calendar(MONDAY_TAKEN))
        self.assertEqual(summary['uploaded'], 1)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(calls[0]['publish_at'])
        state = self.cloud.read('state')[0]
        job = next(job for job in state['jobs'].values() if job['status'] == 'uploaded')
        self.assertNotEqual(instant(job['slot']).date(), MONDAY)

    def test_cli_passes_calendar_only_outside_dry_run(self):
        seen = []
        with patch.dict('os.environ', {'BEAT_CHANNEL_ID': 'channel'}, clear=True), \
             patch('core.beat_worker.DropboxTransport.from_env', return_value=self.memory), \
             patch('core.beat_worker.DropboxAssets.from_env', return_value=DropboxAssets(self.assets_client)), \
             patch('core.beat_worker.run_daily', side_effect=lambda *a, **kw: seen.append(kw) or {}), \
             patch('sys.stdout', io.StringIO()):
            worker_main(['--dry-run', '--receipts', str(self.receipts)])
        self.assertIsNone(seen[0]['calendar'])


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
