import os
import subprocess
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from core import channel_profile as cp
from core.ffmpeg_util import resolve_tool
from core.guide_panel import DONE, INFO, TODO, GuidePanel, GuideStep
from core.manual_panel import BeatDropTable


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


class LocalViewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = self.tmp.name
        self.local = os.path.join(base, "local")
        cp.create(self.local, "Canal")
        touch(os.path.join(self.local, "canales", "Canal", "fondos", "a.jpg"))
        cp.create(self.local, "Otro")
        self.drop = os.path.join(base, "drop")
        touch(os.path.join(self.drop, "one.mp3"))
        touch(os.path.join(self.drop, "more", "two.wav"))
        from core.local_view import LocalView
        self.view = LocalView(settings_path=os.path.join(base, "config", "manual_mode.json"),
                              local_root=self.local, legacy_root=os.path.join(base, "legacy"))
        self.view.reload_channels(select="Canal")

    def tearDown(self):
        self.view.deleteLater()
        app.processEvents()
        self.tmp.cleanup()

    def test_three_steps_enable_generate(self):
        v = self.view
        self.assertFalse(v.btn_generate.isEnabled())
        v.add_paths([self.drop])
        self.assertEqual(v.table.rowCount(), 2)
        self.assertTrue(v.btn_generate.isEnabled())
        self.assertEqual(v.btn_generate.text(), "Generar 2 videos")
        self.assertIn("1 imágenes", v.summary_label.text())

    def test_channel_without_backgrounds_explains_and_blocks(self):
        v = self.view
        v.reload_channels(select="Otro")
        v.add_paths([self.drop])
        self.assertFalse(v.btn_generate.isEnabled())
        self.assertIn("Faltan", v.summary_label.text())
        self.assertIn("fondos", v.status.text())

    def test_inbox_beats_show_up_with_marker_and_others_are_announced(self):
        touch(os.path.join(self.local, "entrada", "Canal", "inbox.mp3"))
        touch(os.path.join(self.local, "entrada", "Otro", "x.mp3"))
        v = self.view
        v.scan_inbox()
        self.assertEqual(v.table.rowCount(), 1)
        self.assertTrue(v.table.item(0, BeatDropTable.COL_BEAT).text().startswith("📥"))
        self.assertIn("1 de la carpeta de entrada", v.count_label.text())
        self.assertFalse(v.others.isHidden())
        self.assertIn("Otro (1)", v.others_label.text())

    def test_titles_editable_for_this_batch_and_reset(self):
        v = self.view
        v.add_paths([self.drop])
        v.table.item(0, BeatDropTable.COL_TITLE).setText("A mano")
        self.assertEqual(v.job()["titles"], {v.beats[0]: "A mano"})
        self.assertFalse(v.btn_reset.isHidden())
        v.reset_titles()
        self.assertEqual(v.title_overrides, {})
        self.assertTrue(v.btn_reset.isHidden())

    def test_remove_and_job(self):
        v = self.view
        v.add_paths([self.drop])
        v.table.selectRow(0)
        v.remove_selected()
        self.assertEqual(len(v.beats), 1)
        job = v.job()
        self.assertEqual((job["mode"], job["channel"], job["root"]), ("channel", "Canal", self.local))

    def test_guide_tracks_progress(self):
        v = self.view
        title, intro, steps = v.guide()
        states = [s.state() for s in steps]
        self.assertEqual(states[:3], [DONE, DONE, DONE])  # canales, canal elegido, fondos
        self.assertEqual(states[4], TODO)  # sumar beats
        v.add_paths([self.drop])
        self.assertEqual(steps[4].state(), DONE)
        self.assertEqual(steps[3].state(), INFO)

    @unittest.skipUnless(resolve_tool("ffmpeg") and resolve_tool("ffprobe"), "requiere FFmpeg")
    def test_generate_moves_inbox_beat_to_done(self):
        from PIL import Image
        Image.new("RGB", (640, 360), (10, 10, 80)).save(os.path.join(self.local, "canales", "Canal", "fondos", "a.jpg"))
        beat = os.path.join(self.local, "entrada", "Canal", "Night.mp3")
        os.makedirs(os.path.dirname(beat), exist_ok=True)
        subprocess.run([resolve_tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=2", beat],
                       check=True)
        v = self.view
        v.settings["output_folder"] = os.path.join(self.tmp.name, "out")
        v.scan_inbox()
        v.start()
        deadline = time.monotonic() + 120
        while v.worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.05)
        app.processEvents()
        self.assertIn("✓ 1 videos listos", v.status.text())
        self.assertTrue(os.path.exists(os.path.join(self.local, "entrada", "Canal", "hechos", "Night.mp3")))
        self.assertEqual(v.beats, [])
        self.assertEqual(v.guide()[2][5].state(), DONE)


class GuidePanelTests(unittest.TestCase):
    def test_steps_states_progress_and_action(self):
        flag = {"done": False, "clicked": 0}
        panel = GuidePanel()
        panel.set_guide("T", "intro", [
            GuideStep("a", done=lambda: True),
            GuideStep("b", done=lambda: flag["done"], action=lambda: flag.update(clicked=flag["clicked"] + 1)),
            GuideStep("info")])
        self.assertEqual(panel.states(), [DONE, TODO, INFO])
        self.assertEqual(panel.progress.text(), "1 de 2 pasos listos")
        panel.steps[1].action()
        self.assertEqual(flag["clicked"], 1)
        flag["done"] = True
        panel.refresh()
        self.assertIn("todo listo", panel.progress.text())

    def test_broken_check_never_crashes(self):
        step = GuideStep("x", done=lambda: 1 / 0)
        self.assertEqual(step.state(), TODO)


class ProfileEditorTests(unittest.TestCase):
    def test_presets_custom_and_more_options(self):
        with tempfile.TemporaryDirectory() as root:
            cp.create(root, "C")
            from core.profile_editor import TITLE_STYLES, ProfileEditor
            dialog = ProfileEditor(root, "C")
            self.assertEqual(dialog.style_combo.currentData(), cp.DEFAULT_TITLE)
            self.assertTrue(dialog.title_edit.isHidden())  # estilo listo: no hay plantilla a la vista
            self.assertTrue(dialog.more.isHidden())
            dialog.style_combo.setCurrentIndex(2)
            self.assertEqual(dialog.title_edit.text(), TITLE_STYLES[2][1])
            dialog.style_combo.setCurrentIndex(dialog.style_combo.count() - 1)  # Personalizado…
            self.assertFalse(dialog.title_edit.isHidden())
            dialog.title_edit.setText("{name} | Mío")
            dialog.artists_edit.setText("Juice WRLD")
            dialog.btn_more.setChecked(True)
            self.assertFalse(dialog.more.isHidden())
            self.assertTrue(dialog._save())
            saved = cp.load(root, "C")
            self.assertEqual((saved["titulo"], saved["artistas"]), ("{name} | Mío", ["Juice WRLD"]))
            reopened = ProfileEditor(root, "C")
            self.assertEqual(reopened.style_combo.currentData(), None)  # plantilla propia = Personalizado
            dialog.deleteLater()
            reopened.deleteLater()


class HomeScreenTests(unittest.TestCase):
    def test_two_choices_and_guide(self):
        from core.home_screen import HomeScreen
        home = HomeScreen()
        hits = []
        home.local_requested.connect(lambda: hits.append("local"))
        home.cloud_requested.connect(lambda: hits.append("cloud"))
        home.btn_local.click()
        home.btn_cloud.click()
        self.assertEqual(hits, ["local", "cloud"])
        title, intro, steps = home.guide()
        steps[0].action()
        self.assertEqual(hits[-1], "local")
        home.deleteLater()


if __name__ == "__main__":
    unittest.main()
