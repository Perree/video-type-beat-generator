"""Manual acquisition: fixtures only, plus a short real FFmpeg media round-trip."""
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from core.beat_download import download_hls
from core.beat_http import BeatError
from core.beat_source import BeatStarsSource, Snapshot, Track
from core.ffmpeg_util import resolve_tool
from core.manual_beatstars import ManualBeatStars, filter_tags
from core.manual_beatstars_media import CancellableRun
from core.manual_beatstars_store import HistoryError, HistoryStore, LINK, SIDECAR, digest

PROFILE = 'https://www.beatstars.com/fixtureproducer'
URL = 'https://content.beatstars.com/fixture/index.m3u8'
PLAYLIST = b'#EXTM3U\n#EXTINF:2,\npart.ts\n#EXT-X-ENDLIST\n'
TS = (b'G' + b'\x00' * 187) * 3


def track(number=101, title='Same title', tags=('trap', 'Dark')):
    tid = f'TK{number}'
    return Track(tid, title, f'https://www.beatstars.com/beat/fixture-{number}', tags, 2,
                 {'provider': 'beatstars', 'track_id': tid, 'v2_id': str(number)})


class Source:
    def __init__(self, tracks=None, member='MR100'):
        self.tracks = (track(), track(102)) if tracks is None else tracks
        self.member = member
        self.calls = 0

    def scan(self, url):
        self.calls += 1
        return Snapshot(self.member, 'fixtureproducer', self.tracks)


class Resolver:
    def __init__(self):
        self.calls = []
        self.fail = set()

    def resolve(self, item, profile):
        self.calls.append(item['id'])
        if item['id'] in self.fail:
            raise BeatError('preview_unavailable')
        return URL + '?secret=transient', 2


class HLS:
    def __init__(self, segment=TS):
        self.segment, self.calls = segment, []

    def get(self, url, types, limit, deadline):
        self.calls.append(url)
        data = PLAYLIST if 'index.m3u8' in url else self.segment
        if len(data) > limit:
            raise BeatError('download_limit')
        return data


class Tools:
    def __init__(self):
        self.calls = 0
        self.fail = False
        self.after_prepare = lambda: None

    def prepare(self, source, target, expected):
        self.calls += 1
        target.write_bytes(b'fixture m4a')
        self.after_prepare()
        if self.fail:
            raise BeatError('audio_probe_failed')


class ManualBeatStarsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dest = self.root / 'entrada/Canal'
        self.store = HistoryStore(self.root / 'config/history.json')
        self.source, self.resolver, self.http, self.tools = Source(), Resolver(), HLS(), Tools()
        self.cancel = False
        self.service = self.new_service()

    def new_service(self, source=None):
        return ManualBeatStars(HistoryStore(self.store.path), source or self.source, self.resolver,
                               self.http, self.tools, lambda: self.cancel)

    def download(self, ids=('TK101',), destination=None, **kwargs):
        search = self.service.search(PROFILE, include_downloaded=True)
        return self.service.download(search, ids, destination or self.dest, **kwargs)

    def test_filter_exact_any_all_empty_and_order(self):
        tracks = [track(101), track(102, tags=('trap',)), track(103, tags=('darkness',))]
        self.assertEqual([t.id for t in filter_tags(tracks, ' DARK , trap')], ['TK101', 'TK102'])
        self.assertEqual([t.id for t in filter_tags(tracks, ['dark', 'TRAP'], 'all')], ['TK101'])
        self.assertEqual(list(filter_tags(tracks, ' , ')), tracks)
        for tags, mode in (([], 'unknown'), (['x' * 101], 'any'), (123, 'any')):
            with self.assertRaises(ValueError):
                list(filter_tags(tracks, tags, mode))

    def test_package_history_and_restart_global_across_channels(self):
        result = self.download()
        audio = result.downloads[0]
        self.assertEqual(audio.suffix, '.m4a')
        metadata = json.loads(Path(str(audio) + SIDECAR).read_text(encoding='utf-8'))
        self.assertEqual(metadata['sha256'], digest(audio))
        self.assertEqual(metadata['track_id'], 'TK101')
        self.assertEqual(Path(str(audio) + LINK).read_text(), track().url + '\n')
        self.assertNotIn('secret', self.store.path.read_text())
        self.assertNotIn('preview_ref', self.store.path.read_text())
        search = self.new_service().search(PROFILE)
        self.assertEqual([c.track.id for c in search.candidates], ['TK102'])
        included = self.new_service().search(PROFILE, include_downloaded=True)
        self.assertTrue(included.candidates[0].downloaded)
        skipped = self.service.download(included, ['TK101'], self.root / 'entrada/Otro')
        self.assertEqual(skipped.skipped, ['TK101'])
        self.assertEqual(len(self.resolver.calls), 1)

    def test_id_dedupe_survives_title_and_username_changes(self):
        self.download()
        self.source.tracks = [track(title='Renamed')]
        self.assertEqual(self.new_service().search(PROFILE + '/tracks').candidates, ())

    def test_same_titles_distinct_ids_and_repeat_without_overwrite(self):
        first = self.download(('TK101', 'TK102'))
        self.assertEqual(len(first.downloads), 2)
        self.assertNotEqual(*first.downloads)
        repeated = self.download(include_downloaded=True)
        self.assertNotEqual(first.downloads[0], repeated.downloads[0])
        self.assertTrue(first.downloads[0].exists())

    def test_profile_ids_are_isolated(self):
        self.download()
        search = self.new_service(Source(member='MR200')).search(PROFILE)
        self.assertFalse(search.candidates[0].downloaded)

    def test_partial_failure_continues_and_only_success_is_registered(self):
        self.resolver.fail.add('TK101')
        result = self.download(('TK101', 'TK102'))
        self.assertEqual(result.errors, [('TK101', 'preview_unavailable')])
        self.assertEqual(len(result.downloads), 1)
        self.assertEqual(list(self.store.load()['downloads']), ['MR100:TK102'])

    def test_media_failure_cleans_staging_and_leaves_no_success(self):
        self.tools.fail = True
        result = self.download()
        self.assertEqual(result.errors, [('TK101', 'audio_probe_failed')])
        self.assertEqual(list(self.dest.iterdir()), [])
        self.assertFalse(self.store.load()['downloads'])

    def test_duration_mismatch_never_converts(self):
        self.source.tracks = [Track(**dict(track().__dict__, duration=80))]
        result = self.download()
        self.assertEqual(result.errors, [('TK101', 'duration_mismatch')])
        self.assertEqual(self.tools.calls, 0)

    def test_cancel_before_start_and_after_media_cleans_files(self):
        search = self.service.search(PROFILE)
        self.cancel = True
        result = self.service.download(search, ['TK101'], self.dest)
        self.assertTrue(result.cancelled)
        self.assertFalse(self.resolver.calls)
        self.cancel = False
        self.tools.after_prepare = lambda: setattr(self, 'cancel', True)
        result = self.download()
        self.assertTrue(result.cancelled)
        self.assertEqual(list(self.dest.iterdir()), [])
        self.assertFalse(self.store.load()['downloads'])

    def test_cancel_after_first_success_retains_that_package(self):
        search = self.service.search(PROFILE)
        def progress(done, total, tid):
            if done == 1:
                self.cancel = True
        result = self.service.download(search, ['TK101', 'TK102'], self.dest, progress=progress)
        self.assertTrue(result.cancelled)
        self.assertEqual(len(result.downloads), 1)
        self.assertEqual(list(self.store.load()['downloads']), ['MR100:TK101'])

    def test_corrupt_history_blocks_search_and_download_without_network(self):
        search = self.service.search(PROFILE)
        self.source.calls = 0
        self.store.path.write_text('{broken', encoding='utf-8')
        with self.assertRaisesRegex(HistoryError, 'history_unreadable'):
            self.service.search(PROFILE)
        with self.assertRaisesRegex(HistoryError, 'history_unreadable'):
            self.service.download(search, ['TK101'], self.dest)
        self.assertEqual(self.source.calls, 0)
        self.assertFalse(self.resolver.calls)
        self.assertEqual(self.store.path.read_text(), '{broken')

    def test_structurally_invalid_history_is_never_treated_as_empty(self):
        with self.store.locked():
            pass
        for invalid in ([], {'version': True, 'downloads': {}},
                        {'version': 2, 'downloads': {}},
                        {'version': 1, 'downloads': {'MR100:TK101': {}}},
                        {'version': 1, 'downloads': {}, 'pending': []}):
            self.store.path.write_text(json.dumps(invalid), encoding='utf-8')
            with self.assertRaises(HistoryError):
                self.service.search(PROFILE)
        self.assertFalse(self.source.calls)

    def test_os_lock_rejects_concurrent_store_and_releases(self):
        with self.store.locked():
            with self.assertRaisesRegex(HistoryError, 'history_busy'):
                with HistoryStore(self.store.path).locked():
                    self.fail('lock acquired concurrently')
        with HistoryStore(self.store.path).locked():
            pass

    def test_recording_failure_stops_batch_and_next_search_recovers_package(self):
        # Each track has two durable writes: publication intent, then completed history.
        original = self.service.store.save
        calls = []
        def save(state):
            calls.append(1)
            if len(calls) == 2:
                raise HistoryError('history_write_failed')
            return original(state)
        with patch.object(self.service.store, 'save', side_effect=save):
            with self.assertRaisesRegex(HistoryError, 'history_write_failed') as error:
                self.download(('TK101', 'TK102'))
        self.assertEqual(error.exception.result.downloads, [])
        self.assertEqual(self.resolver.calls, ['TK101'])
        self.assertIsNotNone(self.store.load()['pending'])
        self.assertEqual([c.track.id for c in self.new_service().search(PROFILE).candidates], ['TK102'])
        self.assertIsNone(self.store.load()['pending'])

    def test_crash_mid_publication_rolls_back_on_restart(self):
        from core.manual_beatstars import _publish
        count = []
        def crashing(source, target):
            count.append(1)
            if len(count) == 2:
                raise KeyboardInterrupt()
            _publish(source, target)
        with patch('core.manual_beatstars._publish', side_effect=crashing):
            with self.assertRaises(KeyboardInterrupt):
                self.download()
        self.assertIsNotNone(self.store.load()['pending'])
        self.new_service().search(PROFILE)
        self.assertEqual(list(self.dest.iterdir()), [])
        self.assertFalse(self.store.load()['downloads'])

    def test_recovery_refuses_modified_files(self):
        original = self.service.store.save
        def fail_completion(state):
            if state['pending'] is None:
                raise HistoryError('history_write_failed')
            return original(state)
        with patch.object(self.service.store, 'save', side_effect=fail_completion):
            with self.assertRaises(HistoryError):
                self.download()
        audio = Path(self.store.load()['pending']['audio'])
        audio.write_bytes(b'changed by another program')
        with self.assertRaisesRegex(HistoryError, 'package_recovery_conflict'):
            self.new_service().search(PROFILE)
        self.assertEqual(audio.read_bytes(), b'changed by another program')

    def test_failed_publication_cleans_only_its_files_and_retries_next_track(self):
        from core.manual_beatstars import _publish
        count = []
        def collision(source, target):
            count.append(1)
            if len(count) == 2:
                raise OSError('disk error')
            _publish(source, target)
        with patch('core.manual_beatstars._publish', side_effect=collision):
            result = self.download(('TK101', 'TK102'))
        self.assertEqual(result.errors, [('TK101', 'local_write_failed')])
        self.assertEqual(len(result.downloads), 1)
        self.assertFalse(any('TK101' in f.name for f in self.dest.iterdir()))
        self.assertIsNone(self.store.load()['pending'])

    def test_rollback_failure_stops_batch_and_is_recoverable(self):
        from core.manual_beatstars import _publish
        count = []
        def failing(source, target):
            count.append(1)
            if len(count) == 2:
                raise OSError('publication failure')
            _publish(source, target)
        unlink = Path.unlink
        def deny_sidecar(path, *args, **kwargs):
            if str(path).endswith(SIDECAR):
                raise PermissionError('busy sidecar')
            return unlink(path, *args, **kwargs)
        with patch('core.manual_beatstars._publish', side_effect=failing), \
                patch.object(Path, 'unlink', deny_sidecar):
            with self.assertRaisesRegex(HistoryError, 'package_rollback_failed'):
                self.download(('TK101', 'TK102'))
        self.assertEqual(self.resolver.calls, ['TK101'])
        self.new_service().search(PROFILE)
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_external_publication_collision_is_not_overwritten_or_deleted(self):
        from core.manual_beatstars import _publish
        external = []
        def collision(source, target):
            if str(target).endswith(LINK):
                target.write_text('external file', encoding='utf-8')
                external.append(target)
            _publish(source, target)
        with patch('core.manual_beatstars._publish', side_effect=collision):
            result = self.download()
        self.assertEqual(result.errors, [('TK101', 'local_write_failed')])
        self.assertEqual(external[0].read_text(), 'external file')
        self.assertFalse(self.store.load()['downloads'])

    def test_atomic_history_write_failure_preserves_old_json(self):
        self.download()
        before = self.store.path.read_bytes()
        with patch('core.manual_beatstars_store.os.replace', side_effect=OSError('disk error')):
            with self.assertRaisesRegex(HistoryError, 'history_write_failed'):
                self.download(('TK102',))
        self.assertEqual(self.store.path.read_bytes(), before)
        self.assertFalse(any(p.suffix == '.tmp' for p in self.store.path.parent.iterdir()))
        self.assertFalse(any('TK102' in f.name for f in self.dest.iterdir()))

    def test_hls_cancel_between_segments_does_not_fetch_next(self):
        http = HLS()
        original = http.get
        def get(*args):
            data = original(*args)
            if len(http.calls) == 2:
                self.cancel = True
            return data
        http.get = get
        with self.assertRaisesRegex(BeatError, 'cancelled'):
            download_hls(URL, self.root / 'preview.part', http, lambda: self.cancel)
        self.assertEqual(len(http.calls), 2)

    def test_scan_cancel_after_profile_does_not_request_tracks(self):
        calls = []
        class Transport:
            def query(inner, *args):
                calls.append(1)
                self.cancel = True
                return {'profileByUsername': {'memberId': 'MR100', 'username': 'fixtureproducer'}}
        with self.assertRaisesRegex(BeatError, 'cancelled'):
            BeatStarsSource(Transport(), cancelled=lambda: self.cancel).scan(PROFILE)
        self.assertEqual(len(calls), 1)

    def test_invalid_selection_and_filters_fail_before_download(self):
        search = self.service.search(PROFILE)
        for ids in ([], ['TK101'] * 2, ['TK999'], ['TK101'] * 101):
            with self.assertRaises(ValueError):
                self.service.download(search, ids, self.dest)
        self.source.calls = 0
        with self.assertRaises(ValueError):
            self.service.search(PROFILE, match='invalid')
        self.assertFalse(self.source.calls)
        self.assertFalse(self.resolver.calls)

    @unittest.skipUnless(resolve_tool('ffmpeg') and resolve_tool('ffprobe'), 'requires FFmpeg')
    def test_real_hls_aac_to_valid_m4a_without_reencoding(self):
        segment = self.root / 'fixture.ts'
        subprocess.run([resolve_tool('ffmpeg'), '-nostdin', '-v', 'error', '-y',
                        '-f', 'lavfi', '-i', 'sine=duration=2', '-c:a', 'aac', '-f', 'mpegts', str(segment)],
                       check=True, timeout=30, capture_output=True)
        from core.manual_beatstars_media import ManualMediaTools
        media = ManualMediaTools()
        self.service.tools = media
        self.service.http = HLS(segment.read_bytes())
        with patch.object(media.tools, '_call', wraps=media.tools._call) as calls:
            result = self.download()
        self.assertEqual(result.errors, [])
        audio = result.downloads[0]
        self.assertTrue(any('-c:a' in c.args[0] and 'copy' in c.args[0] for c in calls.call_args_list))
        self.assertAlmostEqual(media.verify(audio, 2), 2, delta=.1)
        self.assertFalse(any('https://' in ' '.join(map(str, c.args[0])) for c in calls.call_args_list))

    def test_cancellable_subprocess_is_stopped_promptly(self):
        started = time.monotonic()
        runner = CancellableRun(lambda: time.monotonic() - started > .2)
        with self.assertRaisesRegex(BeatError, 'cancelled'):
            runner([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=40,
                   stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.assertLess(time.monotonic() - started, 5)

    def test_subprocess_deadline_stops_process(self):
        with self.assertRaisesRegex(BeatError, 'media_timeout'):
            CancellableRun()([sys.executable, '-c', 'import time; time.sleep(30)'], timeout=.2,
                             stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    @unittest.skipUnless(resolve_tool('ffmpeg') and resolve_tool('ffprobe'), 'requires FFmpeg')
    def test_real_non_aac_preview_is_transcoded_and_verified(self):
        from core.manual_beatstars_media import ManualMediaTools
        source, target = self.root / 'source.wav', self.root / 'target.m4a'
        subprocess.run([resolve_tool('ffmpeg'), '-nostdin', '-v', 'error', '-y',
                        '-f', 'lavfi', '-i', 'sine=duration=2', str(source)],
                       check=True, timeout=30, capture_output=True)
        media = ManualMediaTools()
        with patch.object(media.tools, '_call', wraps=media.tools._call) as calls:
            media.prepare(source, target, 2)
        self.assertTrue(any('-c:a' in c.args[0] and '192k' in c.args[0] for c in calls.call_args_list))
        self.assertAlmostEqual(media.verify(target, 2), 2, delta=.1)


if __name__ == '__main__':
    unittest.main()
