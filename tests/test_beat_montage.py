"""Visual correction: fixed image, normalized silent montage, resources and cleanup."""
from decimal import Decimal
import json
import os
import subprocess
import tempfile
import unittest
import wave
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path
from types import SimpleNamespace
from PIL import Image
from core.beat_assets import DropboxAssets
from core.beat_http import BeatError
from core.beat_montage import render_montage, loop_plan, section_plan, video_info, verify_output
from core.beat_render import MediaTools
from core.beat_video import render_reserved
from core.beat_visual import options, video_catalog
from core.beat_title_overlay import create_title, title_options
from core.beat_state import BeatState
from core.ffmpeg_util import resolve_tool
from test_beat_video import fixture, AssetsClient, HLS, Resolver, Processes, TS

MP4 = b'\x00\x00\x00\x18ftypisom' + b'fake video'


class MontageProcesses(Processes):
    def __init__(self, incompatible=None, fail_decode=None, output_seconds=2):
        super().__init__()
        self.incompatible = incompatible
        self.fail_decode = fail_decode
        self.output_seconds = output_seconds

    def __call__(self, cmd, **kwargs):
        self.calls.append(cmd)
        if cmd[0] == 'fakeprobe':
            path = Path(cmd[-1])
            if path.name == 'audio.bin':
                streams, seconds = [{'codec_type': 'audio'}], 2
            else:
                video = {'codec_type': 'video', 'codec_name': 'h264', 'width': 1920,
                         'height': 1080, 'avg_frame_rate': '30/1'}
                if self.incompatible:
                    video.update(self.incompatible)
                streams = [video, {'codec_type': 'audio', 'codec_name': 'aac'}]
                seconds = self.output_seconds if path.name == 'video.mp4' else 10
                if path.name.startswith('clip-'):
                    streams, seconds = [video], .5
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                'format': {'duration': str(seconds)}, 'streams': streams}).encode())
        if '-xerror' in cmd and self.fail_decode and cmd[-1].endswith('.mp4'):
            return SimpleNamespace(returncode=1, stdout=b'')
        if cmd[-1] != '-':
            if '-c:v' in cmd and cmd[cmd.index('-c:v') + 1] == 'png':
                Image.new('RGB', (1920, 1080), 'red').save(cmd[-1], 'PNG')
            else:
                Path(cmd[-1]).write_bytes(MP4)
        return SimpleNamespace(returncode=0, stdout=b'')


class MontageTests(unittest.TestCase):
    def test_source_cuts_use_video_duration_when_audio_is_longer(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source.mp4'
            source.write_bytes(MP4)
            process = MontageProcesses(incompatible={'duration': '6.6'})
            seconds, demuxer = video_info(source, MediaTools('fakeffmpeg', 'fakeprobe', process))
            self.assertEqual(seconds, 6.6)
            self.assertEqual(demuxer, 'mov')
            for bad in ('NaN', '-1', 'Infinity'):
                with self.assertRaises(BeatError):
                    video_info(source, MediaTools('fakeffmpeg', 'fakeprobe',
                        MontageProcesses(incompatible={'duration': bad})))

    def setup_resources(self, root):
        (root / 'a.mp4').write_bytes(MP4)
        (root / 'b.webm').write_bytes(b'\x1aE\xdf\xa3' + b'fake')
        return options({'visual': {'mode': 'video', 'videos_folder': str(root),
                                  'clip_min_seconds': .5, 'clip_max_seconds': .5}})

    def test_static_image_has_no_motion_and_keeps_frame(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio, frame = root / 'audio.bin', root / 'frame.png'
            audio.write_bytes(TS)
            Image.new('RGB', (1920, 1080), 'blue').save(frame)
            before = frame.read_bytes()
            process = Processes()
            MediaTools('fakeffmpeg', 'fakeprobe', process).render(audio, frame, root / 'out.mp4', 2.375)
            command = process.calls[-1]
            self.assertEqual(command[command.index('-vf') + 1], 'format=yuv420p')
            self.assertEqual(command[command.index('-loop') + 1], '1')
            self.assertEqual(command[command.index('-t') + 1], '2.375')
            self.assertFalse(any(word in ' '.join(command) for word in ('zoompan', 'fade', 'overlay')))
            self.assertEqual(frame.read_bytes(), before)
            self.assertEqual(options({})['mode'], 'image')

    def test_exact_loop_timeline_and_no_consecutive_duplicates(self):
        clips = [{'resource': 'a', 'seconds': .5}, {'resource': 'b', 'seconds': .5}]
        sequence = loop_plan(clips, 2.375)
        self.assertEqual(sum(Decimal(str(row['seconds'])) for row in sequence), Decimal('2.375'))
        self.assertEqual(sequence[-1]['seconds'], .375)
        self.assertTrue(all(a['resource'] != b['resource'] for a, b in zip(sequence, sequence[1:])))
        self.assertEqual(len(loop_plan(clips[:1], 2)), 4)

    def test_section_plan_cuts_exactly_at_each_part_start(self):
        # 60 s beat, parts at 0 / 14.5 / 38 (chorus): cuts land on those frames.
        plan = section_plan([0, 14.5, 38], 60, 3, 6)
        edges = [sum(plan[:i]) for i in range(len(plan) + 1)]
        self.assertEqual(edges[-1], 60 * 30)
        self.assertIn(round(14.5 * 30), edges)
        self.assertIn(38 * 30, edges)
        self.assertTrue(all(3 * 30 <= frames <= 6 * 30 for frames in plan))
        # Short sources cap the clip length; a part shorter than the minimum stays one clip.
        self.assertTrue(all(frames <= 60 for frames in section_plan([0, 30], 60, 1, 6, cap=2)))
        self.assertEqual(section_plan([0, 1, 20], 20, 3, 6)[0], 30)
        # Starts outside the montage (before the intro ends, after the end) are ignored.
        self.assertEqual(sum(section_plan([-4, 0, 70], 60, 3, 6)), 1800)
        with self.assertRaises(BeatError):
            section_plan([0], 10, .5, .5, cap=.01)

    def test_sections_switch_clip_at_each_part_and_cover_the_beat(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources = root / 'resources'
            resources.mkdir()
            spec = self.setup_resources(resources)
            audio = root / 'audio.bin'
            audio.write_bytes(TS)
            process = MontageProcesses(output_seconds=3)
            result = render_montage(audio, root / 'video.mp4', 3,
                video_catalog(spec, None), spec, root, None,
                MediaTools('fakeffmpeg', 'fakeprobe', process), 'job',
                sections=[{'start': 0, 'label': 'Intro'}, {'start': 1.5, 'label': 'Chorus'}])
            cuts = [cmd for cmd in process.calls if '-xerror' in cmd]
            self.assertEqual(len(cuts), 6)  # 3 s of .5 s clips, not 2 looped ones
            self.assertEqual({cmd[cmd.index('-frames:v') + 1] for cmd in cuts}, {'15'})
            resources_used = [row['resource'] for row in result['clips']]
            self.assertEqual(len(resources_used), 6)
            self.assertTrue(all(a != b for a, b in zip(resources_used, resources_used[1:])))
            manifest = (root / 'clips.txt').read_text().splitlines()
            self.assertEqual(len(manifest), 6)
            self.assertEqual(sum(Decimal(str(row['seconds'])) for row in result['clips']), Decimal('3'))

    def test_sections_shift_by_the_intro(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources = root / 'resources'
            resources.mkdir()
            spec = self.setup_resources(resources)
            audio, intro = root / 'audio.bin', root / 'intro.mp4'
            audio.write_bytes(TS)
            intro.write_bytes(MP4)
            with patch('core.beat_montage.section_plan', wraps=section_plan) as planner:
                render_montage(audio, root / 'video.mp4', 3, video_catalog(spec, None), spec, root, None,
                    MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses(output_seconds=3)), 'job',
                    intro={'path': intro, 'seconds': 1},
                    sections=[{'start': 0, 'label': 'Intro'}, {'start': 2, 'label': 'Chorus'}])
            starts, body = planner.call_args[0][:2]
            self.assertEqual((starts, body), ([-1, 1], 2))

    def test_section_cuts_option_is_boolean(self):
        self.assertFalse(options({'visual': {}}).get('section_cuts', False))
        self.assertTrue(options({'visual': {'section_cuts': True}})['section_cuts'])
        with self.assertRaises(ValueError):
            options({'visual': {'section_cuts': 'yes'}})

    def test_normalize_strip_source_audio_concat_and_loop(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources = root / 'resources'
            resources.mkdir()
            spec = self.setup_resources(resources)
            audio = root / 'audio.bin'
            audio.write_bytes(TS)
            process = MontageProcesses(output_seconds=2.375)
            result = render_montage(audio, root / 'video.mp4', 2.375,
                video_catalog(spec, None), spec, root, None,
                MediaTools('fakeffmpeg', 'fakeprobe', process), 'job')
            normalized = [cmd for cmd in process.calls if '-vf' in cmd]
            self.assertEqual(len(normalized), 2)
            for cmd in normalized:
                self.assertIn('-an', cmd)
                self.assertEqual(cmd[cmd.index('-map') + 1], '0:v:0')
                self.assertEqual(cmd[cmd.index('-c:v') + 1], 'libx264')
                self.assertIn('fps=30', cmd[cmd.index('-vf') + 1])
                self.assertIn('scale=1920:1080', cmd[cmd.index('-vf') + 1])
            final = next(cmd for cmd in process.calls if '-stream_loop' in cmd)
            self.assertEqual(final[final.index('-stream_loop') + 1], '-1')
            self.assertEqual(final[final.index('-t') + 1], '2.375')
            maps = [final[i + 1] for i, value in enumerate(final) if value == '-map']
            self.assertEqual(maps, ['0:v:0', '1:a:0'])
            self.assertIn('atrim=duration=2.375', final[final.index('-af') + 1])
            self.assertTrue((root / 'clips.txt').is_file())
            self.assertEqual(sum(Decimal(str(row['seconds'])) for row in result['clips']), Decimal('2.375'))

    def test_source_trim_avoids_both_ends_and_rejects_too_short_sources(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'audio.bin'
            audio.write_bytes(TS)
            spec = options({'visual': {'source_trim_seconds': 15,
                                      'clip_min_seconds': .5, 'clip_max_seconds': .5}})
            row = {'path': '/video.mp4', 'size': len(MP4)}
            process = MontageProcesses(output_seconds=2.375)
            def fixture(row, target, *args):
                target.write_bytes(MP4)
            with patch('core.beat_montage.fetch', side_effect=fixture), \
                 patch('core.beat_montage.video_info', return_value=(60, 'mov')):
                render_montage(audio, root / 'video.mp4', 2.375, [row], spec, root,
                               None, MediaTools('fakeffmpeg', 'fakeprobe', process), 'job')
            command = next(cmd for cmd in process.calls if '-vf' in cmd)
            self.assertGreaterEqual(float(command[command.index('-ss') + 1]), 15)
            self.assertLessEqual(float(command[command.index('-ss') + 1]) + .5, 45)
            with patch('core.beat_montage.fetch', side_effect=fixture), \
                 patch('core.beat_montage.video_info', return_value=(30, 'mov')):
                with self.assertRaisesRegex(BeatError, 'no_compatible_videos'):
                    render_montage(audio, root / 'short.mp4', 2.375, [row], spec, root,
                                   None, MediaTools('fakeffmpeg', 'fakeprobe', process), 'job')
        for margin in (-1, True, float('nan'), 61):
            with self.assertRaisesRegex(ValueError, 'invalid_source_trim'):
                options({'visual': {'source_trim_seconds': margin}})

    def test_empty_damaged_incompatible_and_decode_errors(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            spec = options({'visual': {'mode': 'video', 'videos_folder': str(root)}})
            with self.assertRaisesRegex(BeatError, 'video_catalog_empty'):
                video_catalog(spec, None)
            source = root / 'bad.mp4'
            source.write_bytes(b'<html>not video</html>')
            tools = MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses())
            with self.assertRaisesRegex(BeatError, 'video_type_rejected'):
                video_info(source, tools)
            self.assertEqual(tools.run.calls, [])
            source.write_bytes(MP4)
            for invalid in ({'codec_name': 'unknown'}, {'width': 10000}, {'avg_frame_rate': '0/0'}):
                with self.assertRaises(BeatError):
                    video_info(source, MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses(incompatible=invalid)))
            audio = root / 'audio.bin'
            audio.write_bytes(TS)
            with self.assertRaisesRegex(BeatError, 'no_compatible_videos'):
                render_montage(audio, root / 'video.mp4', 2, video_catalog(spec, None), spec,
                    root, None, MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses(fail_decode=True)), 'job')

    def test_bad_output_duration_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(BeatError, 'montage_output_rejected'):
                verify_output(Path(folder) / 'video.mp4', 2,
                    MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses(output_seconds=5)))

    def test_dropbox_pipeline_custom_thumbnail_and_cleanup(self):
        cloud, key, track, channel = fixture()
        channel['visual'] = dict(mode='video', video_source='dropbox', videos_folder='/videos',
                                 clip_min_seconds=.5, clip_max_seconds=.5,
                                 thumbnail_source='dropbox', thumbnail_path='/images/trap/b.png')
        client = AssetsClient()
        client.files.update({'/videos/a.mp4': MP4, '/videos/b.mp4': MP4})
        process = MontageProcesses()
        with render_reserved(cloud, key, track, channel, 'trap', 'https://beatstars.com/fixture',
            DropboxAssets(client), resolver=Resolver(), http=HLS(),
            tools=MediaTools('fakeffmpeg', 'fakeprobe', process)) as result:
            root = result['video'].parent
            self.assertEqual(result['visual_mode'], 'video')
            self.assertEqual(result['skipped_videos'], 0)
            self.assertTrue(result['thumbnail'].is_file())
        self.assertFalse(root.exists())
        self.assertIn('/images/trap/b.png', client.downloads)
        self.assertNotIn('/images/trap/a.png', client.downloads)
        self.assertNotIn('image_rotation', cloud.read('state')[0])
        self.assertTrue(all(response.closed for response in client.responses))

    def test_video_mode_rotates_dropbox_image_folder_as_thumbnail(self):
        cloud, key, track, channel = fixture()
        channel['visual'] = dict(mode='video', video_source='dropbox', videos_folder='/videos',
                                 clip_min_seconds=.5, clip_max_seconds=.5)
        self.assertIn('trap', channel['dropbox_images'])
        client = AssetsClient()
        client.files.update({'/videos/a.mp4': MP4})
        with render_reserved(cloud, key, track, channel, 'trap', 'https://beatstars.com/fixture',
            DropboxAssets(client), resolver=Resolver(), http=HLS(),
            tools=MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses())) as result:
            self.assertEqual(result['visual_mode'], 'video')
            self.assertTrue(result['thumbnail'].is_file())
        self.assertTrue(any(path.startswith('/images/trap/') for path in client.downloads))
        self.assertTrue(cloud.read('state')[0]['image_rotation'][channel['id']]['trap'])

    def test_local_pipeline_auto_thumbnail_and_dry_run(self):
        cloud, key, track, channel = fixture()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            channel['visual'] = self.setup_resources(root)
            assets, process = DropboxAssets(AssetsClient()), MontageProcesses()
            before = cloud.read('state')
            with render_reserved(cloud, key, track, channel, 'trap', '', assets, dry_run=True) as result:
                self.assertEqual(result['video_resources'], 2)
            self.assertEqual(cloud.read('state'), before)
            with render_reserved(cloud, key, track, channel, 'trap', '', assets,
                resolver=Resolver(), http=HLS(), tools=MediaTools('fakeffmpeg', 'fakeprobe', process)) as result:
                temporary = result['video'].parent
                self.assertTrue(result['thumbnail'].exists())
            self.assertFalse(temporary.exists())
            self.assertTrue((root / 'a.mp4').exists())

    def test_bad_resources_skipped_and_all_bad_pipeline_cleanup(self):
        cloud, key, track, channel = fixture()
        channel['visual'] = dict(mode='video', video_source='dropbox', videos_folder='/videos',
                                 clip_min_seconds=.5, clip_max_seconds=.5)
        client = AssetsClient()
        client.files.update({'/videos/bad.mp4': b'bad', '/videos/good.mp4': MP4})
        with render_reserved(cloud, key, track, channel, 'trap', '', DropboxAssets(client),
            resolver=Resolver(), http=HLS(), tools=MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses())) as result:
            self.assertEqual(result['skipped_videos'], 1)
        client.files['/videos/good.mp4'] = b'bad'
        targets = []
        assets = DropboxAssets(client)
        original = assets.download
        def download(path, target, *args, **kw):
            targets.append(target)
            original(path, target, *args, **kw)
        assets.download = download
        with self.assertRaisesRegex(BeatError, 'no_compatible_videos'):
            with render_reserved(cloud, key, track, channel, 'trap', '', assets,
                resolver=Resolver(), http=HLS(), tools=MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses())):
                self.fail('must not yield')
        self.assertTrue(all(not path.parent.exists() for path in targets))
        self.assertIsNone(cloud.read('state')[0]['lock'])

    def test_options_reject_invalid_bounds(self):
        for raw in ({'mode': 'zoom'}, {'clip_min_seconds': 10, 'clip_max_seconds': 2},
                    {'clip_min_seconds': float('nan')}, {'clip_max_seconds': True},
                    {'clip_min_seconds': .51, 'clip_max_seconds': .52}):
            with self.assertRaises(ValueError):
                options({'visual': raw})

    def test_grade_and_title_overlay_validation(self):
        self.assertNotIn('title_overlay', options({}))
        self.assertEqual(options({'visual': {'grade': 'dark'}})['grade'], 'dark')
        self.assertEqual(options({'visual': {'title_overlay': {'font': 'great_vibes'}}})['title_overlay'],
                         {'font': 'great_vibes', 'size': 96, 'y': 60})
        for value in ('bright', 1, [], None):
            with self.assertRaisesRegex(ValueError, 'invalid_grade'):
                options({'visual': {'grade': value}})
        for raw in ({}, {'size': 90}, {'font': 'comic_sans'}, {'font': 'great_vibes', 'size': 20},
                    {'font': 'great_vibes', 'size': 96.0}, {'font': 'great_vibes', 'size': True},
                    {'font': 'great_vibes', 'y': 900}, {'font': 'great_vibes', 'y': 'top'}, {'font': 'great_vibes', 'color': 'red'}, 'great_vibes'):
            with self.assertRaisesRegex(ValueError, 'invalid_title_overlay'):
                options({'visual': {'title_overlay': raw}})

    def test_title_png_is_centered_on_top_and_shrinks_long_names(self):
        with tempfile.TemporaryDirectory() as folder:
            spec = title_options({'font': 'dancing_script', 'size': 110, 'y': 60})
            path = create_title('  Powers  ', spec, Path(folder) / 't.png')
            with Image.open(path) as image:
                self.assertEqual((image.mode, image.size), ('RGBA', (1920, 1080)))
                left, top, right, bottom = image.getchannel('A').getbbox()
                self.assertLess(abs((left + right) / 2 - 960), 20)
                self.assertLess(top, 80)
                self.assertLess(bottom, 260)
                self.assertEqual(image.getpixel((960, 700))[3], 0)
            create_title('Very Long Beat Name ' * 6, spec, path)
            with Image.open(path) as image:
                left, _, right, _ = image.getchannel('A').getbbox()
                self.assertLessEqual(right - left, 1700 + 40)  # sombra difuminada incluida
            with self.assertRaises(ValueError):
                create_title('   ', spec, path)
            create_title('Powers', title_options({'font': 'great_vibes', 'size': 120, 'y': 'center'}), path)
            with Image.open(path) as image:
                left, top, right, bottom = image.getchannel('A').getbbox()
                self.assertLess(abs((left + right) / 2 - 960), 20)
                self.assertLess(abs((top + bottom) / 2 - 540), 20)

    def test_grade_and_title_reach_ffmpeg_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources = root / 'resources'
            resources.mkdir()
            spec = self.setup_resources(resources)
            spec.update(grade='dark', title_overlay=title_options({'font': 'great_vibes'}))
            audio = root / 'audio.bin'
            audio.write_bytes(TS)
            process = MontageProcesses(output_seconds=2.375)
            tools = MediaTools('fakeffmpeg', 'fakeprobe', process)
            render_montage(audio, root / 'video.mp4', 2.375, video_catalog(spec, None), spec, root,
                           None, tools, 'job', title='Powers')
            for cmd in (cmd for cmd in process.calls if '-vf' in cmd):
                graph = cmd[cmd.index('-vf') + 1]
                self.assertIn('eq=', graph)
                self.assertIn('vignette', graph)
                self.assertIn('noise=', graph)
            final = next(cmd for cmd in process.calls if '-stream_loop' in cmd)
            self.assertTrue((root / 'title.png').is_file())
            self.assertEqual(final[final.index('-loop') + 1], '1')
            self.assertEqual(final[final.index('-loop') + 11], str(root / 'title.png'))
            graph = final[final.index('-filter_complex') + 1]
            self.assertIn('[2:v:0]format=rgba,fade=t=in:st=0:d=1:alpha=1', graph)
            self.assertIn('fade=t=out:st=1.375', graph)
            self.assertIn('[0:v:0][title]overlay=0:0', graph)
            maps = [final[i + 1] for i, value in enumerate(final) if value == '-map']
            self.assertEqual(maps, ['[v]', '1:a:0'])
            # Con intro: el título arranca cuando termina la intro y es la cuarta entrada.
            process.calls.clear()
            intro = root / 'intro.mp4'
            intro.write_bytes(MP4)
            render_montage(audio, root / 'video.mp4', 2.375, video_catalog(spec, None), spec, root,
                           None, tools, 'job', intro={'path': intro, 'seconds': 1}, title='Powers')
            final = next(cmd for cmd in process.calls if '-filter_complex' in cmd and str(intro) in cmd)
            graph = final[final.index('-filter_complex') + 1]
            self.assertIn('format=yuv420p[pre];[3:v:0]format=rgba,fade=t=in:st=1:d=1', graph)
            self.assertTrue(graph.endswith('[v]'))
            # Sin title_overlay o sin nombre, la pasada final queda como antes.
            for title, overlay in (('Powers', None), (None, spec['title_overlay'])):
                process.calls.clear()
                plain = dict(spec, title_overlay=overlay)
                render_montage(audio, root / 'video.mp4', 2.375, video_catalog(plain, None), plain, root,
                               None, tools, 'job', title=title)
                final = next(cmd for cmd in process.calls if '-stream_loop' in cmd)
                self.assertNotIn('-loop', final)
                self.assertNotIn('-filter_complex', final)

    def test_lease_renewal_keeps_long_montage_fenced(self):
        cloud, key, track, channel = fixture()
        channel['visual'] = dict(mode='video', video_source='dropbox', videos_folder='/videos',
                                 clip_min_seconds=.5, clip_max_seconds=.5)
        client = AssetsClient()
        client.files.update({f'/videos/{name}.mp4': MP4 for name in 'abcd'})
        now = [datetime(2026, 10, 12, tzinfo=timezone.utc)]
        store = BeatState(cloud, clock=lambda: now[0])
        assets = DropboxAssets(client)
        original = assets.download
        def download(path, target, *args, **kw):
            now[0] += timedelta(seconds=1000)
            return original(path, target, *args, **kw)
        assets.download = download
        with patch('core.beat_video.BeatState', return_value=store):
            with render_reserved(cloud, key, track, channel, 'trap', '', assets,
                resolver=Resolver(), http=HLS(), tools=MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses())) as result:
                self.assertTrue(result['video'].is_file())
        self.assertIsNone(cloud.read('state')[0]['lock'])
        self.assertEqual(len([p for p in client.downloads if p.startswith('/videos/')]), 4)

    def test_byte_budget_skips_large_resource_and_tries_smaller(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio = root / 'audio.bin'
            audio.write_bytes(TS)
            rows = [{'path': f'/{i}.mp4', 'size': size} for i, size in enumerate((100, 100, 100, 100, 140, 10))]
            class RNG:
                def shuffle(self, rows):
                    pass
                def randint(self, low, high):
                    return low
                def uniform(self, low, high):
                    return low
            def fetch_fixture(row, target, *args):
                target.write_bytes(MP4)
            # Scale metadata to MiB; fixture downloads stay tiny.
            for row in rows:
                row['size'] *= 1024 * 1024
            with patch('core.beat_montage.random.Random', return_value=RNG()), \
                 patch('core.beat_montage.fetch', side_effect=fetch_fixture):
                result = render_montage(audio, root / 'video.mp4', 2, rows,
                    options({'visual': {'clip_min_seconds': .5, 'clip_max_seconds': .5}}),
                    root, None, MediaTools('fakeffmpeg', 'fakeprobe', MontageProcesses()), 'job')
            self.assertTrue((root / 'clip-5.mp4').exists())
            self.assertFalse((root / 'source-4.bin').exists())

    @unittest.skipUnless(os.environ.get('BEAT_REAL_FFMPEG_SMOKE') == '1' and resolve_tool('ffmpeg'),
                         'Set BEAT_REAL_FFMPEG_SMOKE=1 to run the real FFmpeg check')
    def test_real_ffmpeg_image_frames_are_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            audio, frame, output = root / 'audio.wav', root / 'frame.png', root / 'video.mp4'
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, 48000, 0, 'NONE', ''))
                stream.writeframes(b'\x00\x00' * 48000)
            Image.new('RGB', (1920, 1080), 'blue').save(frame)
            MediaTools().render(audio, frame, output, 1)
            result = subprocess.run([resolve_tool('ffmpeg'), '-nostdin', '-v', 'error',
                '-i', str(output), '-map', '0:v:0', '-an', '-f', 'framemd5', '-'],
                capture_output=True, timeout=30, check=True)
            hashes = [line.split(',')[-1].strip() for line in result.stdout.decode().splitlines()
                      if line and not line.startswith('#')]
            self.assertEqual(len(hashes), 30)
            self.assertEqual(len(set(hashes)), 1)

    @unittest.skipUnless(os.environ.get('BEAT_REAL_FFMPEG_SMOKE') == '1' and resolve_tool('ffmpeg'),
                         'Set BEAT_REAL_FFMPEG_SMOKE=1 to run the real FFmpeg check')
    def test_real_ffmpeg_montage_loops_and_removes_source_audio(self):
        ffmpeg = resolve_tool('ffmpeg')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources = root / 'resources'
            resources.mkdir()
            for name, color, rate in (('a', 'blue', 24), ('b', 'red', 60)):
                subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y',
                    '-f', 'lavfi', '-i', f'color=c={color}:s=320x180:r={rate}:d=1',
                    '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=1',
                    '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(resources / f'{name}.mp4')],
                    capture_output=True, timeout=30, check=True)
            audio, output = root / 'audio.wav', root / 'video.mp4'
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, 48000, 0, 'NONE', ''))
                stream.writeframes(b'\x00\x00' * 72000)

            def run(command, **kwargs):
                # ffprobe is absent on this machine: deterministic metadata for
                # our generated fixtures, with every FFmpeg command executed.
                if command[0] == 'fixtureprobe':
                    path = Path(command[-1])
                    normalized = path.name.startswith('clip-')
                    seconds = .5 if normalized else (1.5 if path == output else 1)
                    streams = [{'codec_type': 'video', 'codec_name': 'h264', 'width': 1920,
                                'height': 1080, 'avg_frame_rate': '30/1'}]
                    if not normalized:
                        streams.append({'codec_type': 'audio', 'codec_name': 'aac'})
                    return SimpleNamespace(returncode=0, stdout=json.dumps({
                        'format': {'duration': str(seconds)}, 'streams': streams}).encode())
                return subprocess.run(command, **kwargs)

            spec = options({'visual': {'mode': 'video', 'videos_folder': str(resources),
                                      'clip_min_seconds': .5, 'clip_max_seconds': .5}})
            montage = render_montage(audio, output, 1.5, video_catalog(spec, None), spec,
                root, None, MediaTools(ffmpeg, 'fixtureprobe', run), 'real-fixture')
            result = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(output),
                '-map', '0:v:0', '-an', '-f', 'framemd5', '-'], capture_output=True, timeout=30, check=True)
            hashes = [line.split(',')[-1].strip() for line in result.stdout.decode().splitlines()
                      if line and not line.startswith('#')]
            self.assertEqual(len(hashes), 45)  # exactly 1.5 s at 30 FPS
            self.assertEqual(hashes[0], hashes[30])
            self.assertNotEqual(hashes[0], hashes[15])
            for clip in {row['path'] for row in montage['clips']}:
                result = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(clip),
                    '-map', '0:a:0', '-f', 'null', '-'], capture_output=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)  # silent normalized clips
            result = subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-i', str(output),
                '-map', '0:a:0', '-f', 's16le', '-'], capture_output=True, timeout=30, check=True)
            self.assertTrue(result.stdout)
            self.assertFalse(any(result.stdout))  # only the silent beat, no source sine


    @unittest.skipUnless(os.environ.get('BEAT_REAL_FFMPEG_SMOKE') == '1' and resolve_tool('ffmpeg')
                         and resolve_tool('ffprobe'), 'Set BEAT_REAL_FFMPEG_SMOKE=1 to run the real FFmpeg check')
    def test_real_ffmpeg_grade_and_title_fade_in(self):
        ffmpeg = resolve_tool('ffmpeg')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            resources = root / 'resources'
            resources.mkdir()
            for name, color in (('a', 'gray'), ('b', 'silver')):
                subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                    '-i', f'color=c={color}:s=640x360:r=30:d=2', '-c:v', 'libx264', str(resources / f'{name}.mp4')],
                    capture_output=True, timeout=30, check=True)
            audio, output = root / 'audio.wav', root / 'video.mp4'
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, 48000, 0, 'NONE', ''))
                stream.writeframes(bytes(2 * 48000 * 3))
            spec = options({'visual': {'mode': 'video', 'videos_folder': str(resources), 'grade': 'dark',
                                      'clip_min_seconds': 1, 'clip_max_seconds': 1,
                                      'title_overlay': {'font': 'great_vibes', 'size': 140, 'y': 40}}})
            render_montage(audio, output, 3, video_catalog(spec, None), spec, root, None,
                           MediaTools(), 'real-title', title='Powers')
            verify_output(output, 3, MediaTools())

            def frame(second):
                target = root / f'f{second}.png'
                subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-ss', str(second), '-i', str(output),
                    '-frames:v', '1', str(target)], capture_output=True, timeout=30, check=True)
                with Image.open(target) as image:
                    return image.convert('L')
            start, middle = frame(0), frame(1.5)
            title_box, corner, center = (660, 30, 1260, 230), (0, 0, 200, 200), (860, 600, 1060, 800)
            self.assertLess(max(start.crop(title_box).get_flattened_data()), 200)  # fundido: aun sin titulo
            self.assertGreater(max(middle.crop(title_box).get_flattened_data()), 235)  # titulo blanco
            # Grade oscuro con vineta: la esquina queda mas oscura que el centro.
            self.assertLess(sum(middle.crop(corner).get_flattened_data()), sum(middle.crop(center).get_flattened_data()))


if __name__ == '__main__':
    unittest.main()
