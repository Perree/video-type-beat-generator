"""Phase 4 adversarial smokes: fake HLS, official Dropbox-shaped client and processes."""
import io
import json
import tempfile
import time
import unittest
from datetime import timedelta
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image

from core.beat_assets import DropboxAssets, select_image
from core.beat_cloud import BeatCloud, Transient
from core.beat_download import download_hls, acquire_audio, MediaHTTP, MEDIA_HOSTS
from core.beat_fakes import MemoryDropbox
from core.beat_http import BeatError, check_url, _NoRedirect
from core.beat_preview import PreviewResolver
from core.beat_queries import PROFILE_QUERY
from core.beat_render import MediaTools, compose
from core.beat_schema import identity, migrate, instant
from core.beat_video import render_reserved
from core.beat_seo_store import prepare_seo
from core.beat_publish import publish

URL = 'https://content.beatstars.com/fixture/index.m3u8'
TS = (b'G' + b'\x00' * 187) * 3
PLAYLIST = b'#EXTM3U\n#EXTINF:2,\npart.ts\n#EXT-X-ENDLIST\n'


class HLS:
    def __init__(self, playlist=PLAYLIST):
        self.playlist, self.calls = playlist, []

    def get(self, url, types, limit, deadline):
        check_url(url, MEDIA_HOSTS)
        self.calls.append(url)
        data = self.playlist if url.endswith('.m3u8') else TS
        if len(data) > limit:
            raise BeatError('download_limit')
        return data


class Resolver:
    def __init__(self, error=None):
        self.error = error

    def resolve(self, *args):
        if self.error:
            raise BeatError(self.error)
        return URL, 2


class Response:
    def __init__(self, data):
        self.data, self.closed = data, False

    def iter_content(self, size):
        for offset in range(0, len(self.data), size):
            yield self.data[offset:offset + size]

    def close(self):
        self.closed = True


class AssetsClient:
    def __init__(self):
        stream = io.BytesIO()
        Image.new('RGB', (640, 360), 'blue').save(stream, 'PNG')
        self.files = {'/images/trap/a.png': stream.getvalue(),
                      '/images/trap/b.png': stream.getvalue(), '/audio/track.mp3': b'ID3' + TS}
        self.downloads, self.responses = [], []

    def files_list_folder(self, folder, **kw):
        return SimpleNamespace(entries=[self.files_get_metadata(p) for p in sorted(self.files)
            if p.startswith(folder + '/')], has_more=False)

    def files_get_metadata(self, path):
        return SimpleNamespace(size=len(self.files[path]), rev='rev1', path_lower=path)

    def files_download(self, path, rev):
        self.downloads.append(path)
        response = Response(self.files[path])
        self.responses.append(response)
        return self.files_get_metadata(path), response


class Processes:
    def __init__(self, fail=None, seconds=2, streams=None):
        self.calls, self.fail, self.seconds, self.streams = [], fail, seconds, streams

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if cmd[0] == 'fakeprobe':
            payload = {'format': {'duration': str(self.seconds)},
                       'streams': self.streams or [{'codec_type': 'audio'}]}
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode())
        kind = 'decode' if '-xerror' in cmd else 'render'
        if kind == self.fail:
            return SimpleNamespace(returncode=1, stdout=b'')
        if kind == 'render':
            Path(cmd[-1]).write_bytes(b'fake mp4')
        return SimpleNamespace(returncode=0, stdout=b'')


def fixture():
    memory = MemoryDropbox()
    cloud = BeatCloud(memory, sleep=lambda _: None)
    tid, cid = 'TK101', 'channel'
    key = identity(tid, cid, 1, '2026-10-12T18:00:00-03:00')
    state = migrate({}, 'state')
    state['jobs'][key] = {'id': key, 'track_id': tid, 'channel': cid, 'cycle': 1,
                          'slot': '2026-10-12T18:00:00-03:00', 'status': 'planned'}
    cloud.write('state', state, None)
    track = {'id': tid, 'title': "Fixture | text: ' [safe]", 'preview_ref': {
        'provider': 'beatstars', 'track_id': tid, 'v2_id': '101'}}
    channel = {'id': cid, 'genres': ['trap'], 'dropbox_images': {'trap': '/images/trap'}}
    return cloud, key, track, channel


class VideoTests(unittest.TestCase):
    def run_video(self, **kwargs):
        cloud, key, track, channel = fixture()
        client, process = AssetsClient(), Processes()
        context = render_reserved(cloud, key, track, channel, 'trap', 'https://www.beatstars.com/fixture',
            DropboxAssets(client), resolver=Resolver(), http=HLS(),
            tools=MediaTools('fakeffmpeg', 'fakeprobe', process), **kwargs)
        return cloud, client, process, context

    def test_hls_render_and_cleanup_even_caller_failure(self):
        cloud, client, process, context = self.run_video()
        with self.assertRaisesRegex(RuntimeError, 'consumer'):
            with context as result:
                root = result['video'].parent
                self.assertTrue(result['video'].exists())
                with Image.open(result['thumbnail']) as image:
                    self.assertEqual(image.size, (1280, 720))
                self.assertEqual(result['audio_source'], 'hls')
                self.assertFalse(result['uploads'])
                raise RuntimeError('consumer')
        self.assertFalse(root.exists())
        self.assertEqual(len(process.calls), 3)
        self.assertTrue(all('https://' not in ' '.join(cmd) for cmd in process.calls))
        self.assertTrue(all(response.closed for response in client.responses))
        state, _ = cloud.read('state')
        self.assertIsNone(state['lock'])
        self.assertEqual(state['attempts'], {})
        self.assertEqual(len(state['image_rotation']['channel']['trap']), 1)
        visual = next(iter(state['jobs'].values()))['visual_snapshot']
        self.assertEqual(visual['path'], '/images/trap/a.png')
        self.assertEqual(len(visual['sha256']), 64)

    def test_visual_snapshot_persisted_after_lost_write_response(self):
        cloud, client, process, context = self.run_video()
        original = cloud.transport.write
        pending = [True]
        def losing(path, payload, rev):
            document = json.loads(payload)
            if pending and any(job.get('visual_snapshot') for job in document.get('jobs', {}).values()):
                pending.pop()
                cloud.transport.faults.append(('after_write', Transient()))
            return original(path, payload, rev)
        cloud.transport.write = losing
        with context as media:
            self.assertTrue(media['video'].exists())
        self.assertEqual(pending, [])
        state, _ = cloud.read('state')
        self.assertTrue(next(iter(state['jobs'].values()))['visual_snapshot']['sha256'])
        self.assertEqual(len(state['image_rotation']['channel']['trap']), 1)

    def test_full_repeat_after_180_days_changes_image_and_seo(self):
        cloud, key, track, channel = fixture()
        track['tags'] = ['trap', 'drill']
        channel['tags'] = ['trap', 'drill']
        remote_channel = dict(channel, slots=[{'weekday': 0, 'hour': 18, 'minute': 0}])
        cloud.write('config', migrate({'channels': [remote_channel]}, 'config'), None)
        old_slot = instant('2026-10-12T18:00:00-03:00')
        assets = AssetsClient()
        def rendering(job_id):
            return render_reserved(cloud, job_id, track, channel, 'trap',
                'https://www.beatstars.com/fixture', DropboxAssets(assets),
                resolver=Resolver(), http=HLS(), tools=MediaTools('fakeffmpeg', 'fakeprobe', Processes()))
        prepare_seo(cloud, key, track, channel, old_slot.isoformat())
        with rendering(key):
            pass
        cloud.update('state', lambda state: state['jobs'][key].update(status='uploaded'))
        state, _ = cloud.read('state')
        old = state['jobs'][key]
        new_slot = old_slot + timedelta(days=181)
        new_key = identity(track['id'], channel['id'], 2, new_slot)
        new = dict(id=new_key, track_id=track['id'], channel=channel['id'], cycle=2,
                   slot=new_slot.isoformat(), status='planned')
        cloud.update('state', lambda state: state['jobs'].update({new_key: new}))
        stream = io.BytesIO()
        Image.new('RGB', (640, 360), 'red').save(stream, 'PNG')
        assets.files['/images/trap/b.png'] = stream.getvalue()
        now = new_slot - timedelta(hours=1)
        seo = prepare_seo(cloud, new_key, track, channel, now.isoformat())
        with tempfile.TemporaryDirectory() as receipts, rendering(new_key) as media:
            outcome = publish(cloud, new, media, seo,
                lambda **_: {'youtube_id': 'video000001'}, receipts, lambda: now)
        self.assertEqual(outcome, 'uploaded')
        state, _ = cloud.read('state')
        current = state['jobs'][new_key]
        self.assertNotEqual(current['visual_snapshot']['sha256'], old['visual_snapshot']['sha256'])
        self.assertNotEqual(current['seo_snapshot']['selected']['tags'], old['seo_snapshot']['selected']['tags'])

    def test_dry_run_read_only(self):
        cloud, client, process, context = self.run_video(dry_run=True)
        before, rev = cloud.read('state')
        with context as result:
            self.assertTrue(result['dry_run'])
        self.assertEqual(cloud.read('state'), (before, rev))
        self.assertEqual(client.downloads, [])
        self.assertEqual(process.calls, [])

    def test_failed_decode_or_render_cleanup_no_rotation(self):
        for failure in ('decode', 'render'):
            cloud, key, track, channel = fixture()
            process = Processes(fail=failure)
            with self.assertRaises(BeatError):
                with render_reserved(cloud, key, track, channel, 'trap', 'https://www.beatstars.com/fixture',
                    DropboxAssets(AssetsClient()), resolver=Resolver(), http=HLS(),
                    tools=MediaTools('fakeffmpeg', 'fakeprobe', process)):
                    self.fail('must not yield')
            root = Path(next(cmd[cmd.index('-i') + 1] for cmd in process.calls if '-i' in cmd)).parent
            self.assertFalse(root.exists())
            state, _ = cloud.read('state')
            self.assertNotIn('image_rotation', state)
            self.assertIsNone(state['lock'])

    def test_dropbox_only_explicit_association(self):
        cloud, key, track, channel = fixture()
        state, _ = cloud.read('state')
        assets = DropboxAssets(AssetsClient())
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audio.bin'
            with self.assertRaisesRegex(BeatError, 'explicit_audio_association_required'):
                acquire_audio(track, state, '', path, Resolver('preview_unavailable'), assets)
            state['audio_associations'] = {'TK101': {'track_id': 'TK101', 'path': '/audio/track.mp3', 'duration': 2}}
            self.assertEqual(acquire_audio(track, state, '', path, Resolver('preview_unavailable'), assets), (2, 'dropbox'))
            with self.assertRaisesRegex(BeatError, 'url_rejected'):
                acquire_audio(track, state, '', path, Resolver('url_rejected'), assets)
            state['audio_associations']['TK101']['track_id'] = 'TK999'
            with self.assertRaises(BeatError):
                acquire_audio(track, state, '', path, Resolver('preview_unavailable'), assets)

    def test_fallback_pipeline_and_cleanup(self):
        cloud, key, track, channel = fixture()
        cloud.update('state', lambda state: state.update(audio_associations={
            'TK101': {'track_id': 'TK101', 'path': '/audio/track.mp3', 'duration': 2}}))
        client, process = AssetsClient(), Processes()
        with render_reserved(cloud, key, track, channel, 'trap', 'https://beatstars.com/fixture',
            DropboxAssets(client), resolver=Resolver('preview_unavailable'), http=HLS(),
            tools=MediaTools('fakeffmpeg', 'fakeprobe', process)) as result:
            root = result['video'].parent
            self.assertEqual(result['audio_source'], 'dropbox')
        self.assertFalse(root.exists())
        self.assertEqual(client.downloads, ['/audio/track.mp3', '/images/trap/a.png'])

    def test_missing_reservation_has_no_downloads(self):
        cloud, key, track, channel = fixture()
        client = AssetsClient()
        with self.assertRaisesRegex(BeatError, 'reserved_job_required'):
            with render_reserved(cloud, 'missing', track, channel, 'trap', '', DropboxAssets(client)):
                self.fail('must not yield')
        self.assertEqual(client.downloads, [])
        self.assertIsNone(cloud.read('state')[0]['lock'])

    def test_master_playlist_and_resource_bounds(self):
        class Master(HLS):
            def get(self, url, types, limit, deadline):
                if url == URL:
                    return b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=128000\nchild.m3u8\n'
                return super().get(url, types, limit, deadline)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audio'
            self.assertEqual(download_hls(URL, path, Master()), 2)
            self.assertEqual(path.read_bytes(), TS)
            with self.assertRaises(BeatError):
                download_hls(URL, path, HLS(b'#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nindex.m3u8\n'))
            with patch('core.beat_download.MAX_AUDIO', 1):
                with self.assertRaisesRegex(BeatError, 'download_limit'):
                    download_hls(URL, path, HLS())
            playlist = b'#EXTM3U\n' + b'#EXTINF:2,\npart.ts\n' * 501 + b'#EXT-X-ENDLIST\n'
            with self.assertRaises(BeatError):
                download_hls(URL, path, HLS(playlist))

    def test_security_failure_does_not_use_fallback(self):
        cloud, key, track, channel = fixture()
        state, _ = cloud.read('state')
        state['audio_associations'] = {'TK101': {'track_id': 'TK101', 'path': '/audio/track.mp3', 'duration': 2}}
        client = AssetsClient()
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(BeatError, 'url_rejected'):
                acquire_audio(track, state, '', Path(folder) / 'audio', Resolver(),
                              DropboxAssets(client), HLS(PLAYLIST.replace(b'part.ts', b'http://localhost/a')))
        self.assertEqual(client.downloads, [])

    def test_state_rejects_invalid_association_and_rotation(self):
        cloud, key, track, channel = fixture()
        state, _ = cloud.read('state')
        state['audio_associations'] = {'TK101': {'track_id': 'TK101', 'path': '/audio/../a.mp3', 'duration': 2}}
        with self.assertRaises(ValueError):
            migrate(state, 'state')
        del state['audio_associations']
        state['image_rotation'] = {'channel': {'trap': [{'job_id': 'missing', 'path': '/images/a.png', 'rev': 'r'}]}}
        with self.assertRaises(ValueError):
            migrate(state, 'state')

    def test_rotation_isolated_and_stable_for_retry(self):
        cloud, key, track, channel = fixture()
        state, _ = cloud.read('state')
        job = state['jobs'][key]
        assets = DropboxAssets(AssetsClient())
        first = select_image(channel, 'trap', state, job, assets)
        state['image_rotation'] = {'channel': {'trap': [{'job_id': key, 'path': first['path'], 'rev': 'rev1'}]}}
        self.assertEqual(select_image(channel, 'trap', state, job, assets), first)
        next_job = dict(job, id='next')
        self.assertNotEqual(select_image(channel, 'trap', state, next_job, assets), first)
        other = dict(channel, id='other')
        self.assertEqual(select_image(other, 'trap', state, dict(next_job, channel='other'), assets), first)
        state['image_rotation']['channel']['trap'].append({'job_id': 'second', 'path': '/images/trap/b.png', 'rev': 'rev1'})
        self.assertEqual(select_image(channel, 'trap', state, next_job, assets), first)

    def test_hosts_and_hls_rejections_before_download(self):
        bad_urls = ['http://content.beatstars.com/a', 'https://content.beatstars.com.evil.test/a',
                    'https://127.0.0.1/a', 'file:///a', 'https://user@content.beatstars.com/a',
                    'https://content.beatstars.com:444/a', 'https://content.beatstars.com/a#b']
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audio'
            for url in bad_urls:
                http = HLS()
                with self.assertRaises(BeatError):
                    download_hls(url, path, http)
                self.assertEqual(http.calls, [])
            bad_lists = [PLAYLIST.replace(b'part.ts', b'https://localhost/a'),
                         PLAYLIST.replace(b'part.ts', b'file:///etc/passwd'),
                         PLAYLIST.replace(b'#EXT-X-ENDLIST', b''),
                         PLAYLIST.replace(b'#EXTINF:2,', b'#EXTINF:nan,'),
                         PLAYLIST.replace(b'#EXTINF:2,', b'#EXTINF:9999,'),
                         b'<html>error</html>',
                         b'#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="x"\n' + PLAYLIST[8:],
                         b'#EXTM3U\n#EXT-X-MAP:URI="x"\n' + PLAYLIST[8:]]
            for playlist in bad_lists:
                with self.assertRaises(BeatError):
                    download_hls(URL, path, HLS(playlist))

    def test_probe_duration_and_streams(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'audio'
            path.write_bytes(TS)
            for seconds in (float('nan'), 0, 901, 30):
                proc = Processes(seconds=seconds)
                with self.assertRaises(BeatError):
                    MediaTools('fakeffmpeg', 'fakeprobe', proc).verify_audio(path, 2)
                self.assertEqual(len(proc.calls), 1)
            proc = Processes(streams=[{'codec_type': 'video'}])
            with self.assertRaises(BeatError):
                MediaTools('fakeffmpeg', 'fakeprobe', proc).verify_audio(path, 2)

    def test_resolver_owner_and_track_identity(self):
        cloud, key, track, channel = fixture()
        class Query:
            def query(self, query, variables, deadline):
                if query == PROFILE_QUERY:
                    return {'profileByUsername': {'username': 'fixture', 'memberId': 'MR1'}}
                return {'profileTracks': {'number': 0, 'last': True, 'content': [{
                    'id': 'TK101', 'profile': {'memberId': 'MR1'}, 'bundle': {'hls': {'url': URL, 'duration': 2}}}]}}
        self.assertEqual(PreviewResolver(Query()).resolve(track, 'https://beatstars.com/fixture'), (URL, 2))
        track['preview_ref']['track_id'] = 'TK999'
        with self.assertRaises(BeatError):
            PreviewResolver(Query()).resolve(track, 'https://beatstars.com/fixture')

    def test_asset_revision_size_and_close(self):
        client = AssetsClient()
        assets = DropboxAssets(client)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image'
            with self.assertRaisesRegex(BeatError, 'asset_changed'):
                assets.download('/images/trap/a.png', path, 100000, rev='stale')
            with self.assertRaisesRegex(BeatError, 'download_limit'):
                assets.download('/images/trap/a.png', path, 1)
            self.assertEqual(client.downloads, [])
            assets.download('/images/trap/a.png', path, 100000, rev='rev1')
            self.assertTrue(client.responses[-1].closed)

    def test_image_decode_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'bad').write_bytes(b'<html>wrong type</html>')
            with self.assertRaises(BeatError):
                compose(root / 'bad', 'title', root / 'frame', root / 'thumb')

    def test_bad_image_pipeline_cleans_downloads_and_keeps_rotation(self):
        cloud, key, track, channel = fixture()
        client = AssetsClient()
        client.files['/images/trap/a.png'] = b'<html>bad image</html>'
        targets = []
        assets = DropboxAssets(client)
        original = assets.download
        def download(path, target, *args, **kwargs):
            targets.append(target)
            return original(path, target, *args, **kwargs)
        assets.download = download
        with self.assertRaisesRegex(BeatError, 'image_decode_failed'):
            with render_reserved(cloud, key, track, channel, 'trap', 'https://beatstars.com/fixture',
                assets, resolver=Resolver(), http=HLS(),
                tools=MediaTools('fakeffmpeg', 'fakeprobe', Processes())):
                self.fail('must not yield')
        self.assertTrue(targets)
        self.assertTrue(all(not target.parent.exists() for target in targets))
        self.assertNotIn('image_rotation', cloud.read('state')[0])
        self.assertIsNone(cloud.read('state')[0]['lock'])

    def test_subprocess_deadline_is_sanitized(self):
        def run(*args, **kwargs):
            raise TimeoutError('private file and secret')
        with self.assertRaisesRegex(BeatError, '^media_process_failed$'):
            MediaTools('fakeffmpeg', 'fakeprobe', run)._call(['fakeffmpeg'], 1)

    def test_unlock_error_does_not_mask_render_error(self):
        cloud, key, track, channel = fixture()
        process = Processes(fail='render')
        with patch('core.beat_video.BeatState.release', side_effect=RuntimeError('unlock failed')):
            with self.assertRaisesRegex(BeatError, '^media_validation_failed$'):
                with render_reserved(cloud, key, track, channel, 'trap', '', DropboxAssets(AssetsClient()),
                    resolver=Resolver(), http=HLS(), tools=MediaTools('fakeffmpeg', 'fakeprobe', process)):
                    self.fail('must not yield')
        self.assertFalse(Path(process.calls[-1][-1]).parent.exists())


class HTTPTests(unittest.TestCase):
    def test_type_length_redirect_and_timeout(self):
        class HTTPResponse(io.BytesIO):
            status = 200
            def __init__(self, data, mime, length=None, final=URL):
                super().__init__(data)
                self.headers = Message()
                self.headers['Content-Type'] = mime
                if length:
                    self.headers['Content-Length'] = length
                self.final = final
            def geturl(self):
                return self.final
        for response in [HTTPResponse(b'x', 'text/html'),
                         HTTPResponse(b'xx', 'audio/aac', '999'),
                         HTTPResponse(b'xx', 'audio/aac', '3'),
                         HTTPResponse(b'xx', 'audio/aac', final='https://evil.test/a'),
                         HTTPResponse(b'xxx', 'audio/aac')]:
            http = MediaHTTP()
            http.opener = SimpleNamespace(open=lambda *a, **kw: response)
            with self.assertRaises(BeatError):
                http.get(URL, {'audio/aac'}, 2, time.monotonic() + 10)
            self.assertTrue(response.closed)
        with self.assertRaises(BeatError):
            MediaHTTP().get(URL, {'audio/aac'}, 2, time.monotonic() - 1)
        with self.assertRaisesRegex(BeatError, 'redirect_rejected'):
            _NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.test')


if __name__ == '__main__':
    unittest.main()


class PlainThumbnailTests(unittest.TestCase):
    def test_plain_compose_keeps_artwork_without_caption_banner(self):
        from PIL import Image
        from core.beat_render import compose
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new('RGB', (1920, 1080), (200, 10, 10)).save(root / 'art.png')
            compose(root / 'art.png', 'Some Title', root / 'f.png', root / 't.jpg', plain=True)
            thumb = Image.open(root / 't.jpg')
            self.assertEqual(thumb.size, (1280, 720))
            red, _, _ = thumb.getpixel((100, 700))
            self.assertGreater(red, 150)
            compose(root / 'art.png', 'Some Title', root / 'f.png', root / 't2.jpg')
            self.assertLess(Image.open(root / 't2.jpg').getpixel((100, 700))[0], 60)
