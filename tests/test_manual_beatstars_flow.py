"""Desktop download → edited title → real video → archive → reuse, with fake HTTP."""
import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from core import channel_profile as cp, manual_render as mr
from core.ffmpeg_util import get_media_duration, resolve_tool
from core.local_view import LocalView
from core.manual_beatstars import ManualBeatStars
from core.manual_beatstars_files import read_metadata
from core.manual_beatstars_media import ManualMediaTools
from core.manual_beatstars_store import HistoryStore, LINK, SIDECAR
from core.manual_panel import BeatDropTable
from test_manual_beatstars import HLS, PROFILE, Resolver, Source, track
from test_manual_beatstars_dialog import APP, initial_preferences, pump_until
from test_manual_beatstars_files import TITLE, URL, write_package


class ManualFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.local = self.root / 'local'
        cp.create(str(self.local), 'Canal')
        cp.create(str(self.local), 'Otro')
        cp.save(str(self.local), 'Canal', dict(cp.load(str(self.local), 'Canal'),
            titulo='{artist} - {name}', artistas=['Juice WRLD'],
            descripcion='Buy: {beatstars_url}\n{name} | {bpm} BPM', tags=['{name} type beat', 'trap']))
        self.profile_path = self.local / 'canales/Canal/perfil.json'
        self.profile_before = self.profile_path.read_bytes()
        Image.new('RGB', (640, 360), (25, 40, 80)).save(self.local / 'canales/Canal/fondos/bg.png')
        self.settings_path = str(self.root / 'config/manual.json')
        self.view = LocalView(settings_path=self.settings_path, local_root=str(self.local), legacy_root=str(self.root))
        self.view.reload_channels(select='Canal')
        self.view.settings['output_folder'] = str(self.root / 'videos')
        self.view.settings['output_folder_custom'] = True
        prefs = initial_preferences({}, self.root / 'absent.json')
        prefs.update(profile_url=PROFILE, quantity=1)
        self.view.settings['beatstars'] = prefs

    def tearDown(self):
        self.view.shutdown()
        pump_until(lambda: self.view.worker is None and self.view.beatstars_dialog is None, seconds=30)
        self.view.deleteLater()
        APP.processEvents()
        self.tmp.cleanup()

    def test_title_preview_uses_original_metadata_and_invalid_sidecar_stays_editable(self):
        audio = self.local / 'entrada/Canal/TK101 - truncated (2).m4a'
        write_package(audio)
        self.view.scan_inbox()
        self.assertEqual(self.view.titles(), ['Juice WRLD - Night'])
        self.view.table.item(0, BeatDropTable.COL_TITLE).setText('A mano')
        self.assertEqual(self.view.titles(), ['A mano'])
        self.view.reset_titles()
        self.assertEqual(self.view.titles(), ['Juice WRLD - Night'])
        Path(str(audio) + SIDECAR).write_text('{bad')
        self.view.scan_inbox()  # An invalid sidecar is reported by render, never crashes Qt.
        self.assertEqual(self.view.table.rowCount(), 1)
        self.assertIsNotNone(self.view.auto_title(str(audio)))

    @unittest.skipUnless(resolve_tool('ffmpeg') and resolve_tool('ffprobe'), 'requires FFmpeg')
    def test_download_video_edited_title_archive_collision_and_global_history(self):
        segment = self.root / 'preview.ts'
        subprocess.run([resolve_tool('ffmpeg'), '-nostdin', '-v', 'error', '-y',
                        '-f', 'lavfi', '-i', 'sine=duration=2', '-c:a', 'aac', '-f', 'mpegts', str(segment)],
                       check=True, timeout=30, capture_output=True)
        history_path = self.root / 'config/beatstars_history.json'
        source = Source([track(101, title=TITLE), track(102, title='Second beat')])
        http = HLS(segment.read_bytes())
        def factory(cancelled):
            return ManualBeatStars(HistoryStore(history_path), source, Resolver(), http,
                                   ManualMediaTools(cancelled=cancelled), cancelled)
        self.view._beatstars_service_factory = factory
        self.view.open_beatstars()
        dialog = self.view.beatstars_dialog
        dialog.search()
        pump_until(lambda: dialog.task is None)
        self.assertEqual(dialog.selected_ids(), ['TK101'])
        dialog.download()
        pump_until(lambda: dialog.task is None, seconds=30)
        self.assertEqual(dialog.last_batch.errors, [])
        self.assertEqual(len(self.view.beats), 1)
        self.assertEqual(self.view.generated, 0)
        audio = Path(self.view.beats[0])
        metadata = read_metadata(audio, verify=True)
        self.assertEqual(self.view.titles(), ['Juice WRLD - Night'])
        dialog.reject()

        # An orphan sidecar reserves the original basename, even without an audio.
        done = audio.parent / 'hechos'
        done.mkdir()
        orphan = Path(str(done / audio.name) + LINK)
        orphan.write_text('existing unrelated link')
        self.view.table.item(0, BeatDropTable.COL_TITLE).setText('Mi título final')
        render_tools = mr.Tools(cache=False)
        with patch.object(mr, 'Tools', return_value=render_tools):
            self.view.start()
            pump_until(lambda: self.view.worker is None, seconds=60)
        self.assertEqual(self.view.generated, 1)
        self.assertEqual(self.view.beats, [])
        moved = done / f'{audio.stem} (2).m4a'
        self.assertEqual(read_metadata(moved, verify=True), metadata)
        self.assertEqual(Path(str(moved) + LINK).read_text().strip(), URL)
        self.assertEqual(orphan.read_text(), 'existing unrelated link')
        for suffix in ('', SIDECAR, LINK):
            self.assertFalse(Path(str(audio) + suffix).exists())

        videos = list((self.root / 'videos').rglob('*.mp4'))
        self.assertEqual(len(videos), 1)
        video = videos[0]
        self.assertEqual(video.stem, 'Mi título final')
        self.assertAlmostEqual(get_media_duration(str(video)), 2, delta=.3)
        with Image.open(video.parent / 'Mi título final - miniatura.jpg') as image:
            self.assertEqual(image.size, (1280, 720))
        text = video.with_suffix('.txt').read_text(encoding='utf-8')
        self.assertTrue(text.startswith('TÍTULO\nMi título final\n'))
        self.assertIn('Buy: ' + URL, text)
        self.assertIn('Night | 140 BPM', text)
        self.assertIn('Night type beat', text)
        self.assertIn('\nBEATSTARS\n' + URL + '\n', text)
        self.assertNotIn('TK101', text)
        self.assertNotIn('truncated', text)
        self.assertEqual(len(list(video.parent.iterdir())), 3)
        with next((self.root / 'videos').rglob('pendientes.csv')).open(encoding='utf-8-sig', newline='') as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[1][:2], ['Canal', 'Mi título final'])
        self.assertEqual(self.profile_path.read_bytes(), self.profile_before)

        # Reusing an archived file parses the source title and sends the same URL to render.
        self.view.add_paths([str(moved)])
        self.assertEqual(self.view.titles(), ['Juice WRLD - Night'])
        with patch.object(mr, 'render_beat', return_value=dict(title='reuse', folder=str(self.root))) as render, \
                patch.object(mr, 'add_pending'):
            outputs, errors = mr.run_batch([str(moved)], 'Canal', str(self.local), str(self.root / 'reuse'), tools=object())
        self.assertEqual(errors, [])
        self.assertEqual(len(outputs), 1)
        self.assertEqual(render.call_args.kwargs['beatstars_url'], URL)
        self.assertEqual(render.call_args.args[3], 'Juice WRLD - Night')

        # A fresh dialog/service for another local channel excludes the downloaded track.
        self.view.clear_beats()
        self.view.reload_channels(select='Otro')
        self.view.open_beatstars()
        dialog = self.view.beatstars_dialog
        dialog.search()
        pump_until(lambda: dialog.task is None)
        self.assertEqual(dialog.selected_ids(), ['TK102'])
        self.assertEqual(dialog.table.rowCount(), 1)
        self.assertEqual(len(json.loads(history_path.read_text())['downloads']), 1)
        self.assertEqual(len(list((self.root / 'videos').rglob('*.mp4'))), 1)


if __name__ == '__main__':
    unittest.main()
