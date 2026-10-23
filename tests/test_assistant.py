import os
import subprocess
import tempfile
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QComboBox, QLineEdit, QRadioButton

app = QApplication.instance() or QApplication([])

from core import channel_profile as cp
from core.ffmpeg_util import resolve_tool
from core.manual_panel import BeatDropTable
from core.wizard import Wizard, WizardPage


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


def wait_until(predicate, seconds=120):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.05)
    app.processEvents()


class WizardTests(unittest.TestCase):
    def test_next_enabled_only_when_ready_and_blocker_shown(self):
        flag = {"ok": False}
        done = []
        wizard = Wizard("T", [WizardPage("A", "a", ready=lambda: flag["ok"], blocker=lambda: "falta algo"),
                              WizardPage("B", "b", next_text="Terminar")])
        wizard.finished.connect(lambda: done.append(True))
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("falta algo", wizard.hint.text())
        self.assertTrue(wizard.btn_back.isHidden())
        flag["ok"] = True
        wizard.update_state()
        wizard.btn_next.click()
        self.assertEqual(wizard.index, 1)
        self.assertEqual(wizard.btn_next.text(), "Terminar")
        self.assertIn("Paso 2 de 2", wizard.dots.text())
        wizard.btn_next.click()
        self.assertEqual(done, [True])
        wizard.deleteLater()

    def test_on_next_false_stays(self):
        wizard = Wizard("T", [WizardPage("A", "a", on_next=lambda: False), WizardPage("B", "b")])
        wizard.btn_next.click()
        self.assertEqual(wizard.index, 0)
        wizard.advance()
        self.assertEqual(wizard.index, 1)
        wizard.deleteLater()


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = self.tmp.name
        self.local = os.path.join(base, "local")
        cp.create(self.local, "ConFondos")
        from PIL import Image
        Image.new("RGB", (640, 360), (20, 20, 90)).save(os.path.join(self.local, "canales", "ConFondos", "fondos", "a.png"))
        cp.create(self.local, "SinFondos")
        from core.local_view import LocalView
        from core.assistant import AssistantView
        self.view = LocalView(settings_path=os.path.join(base, "mm.json"), local_root=self.local,
                              legacy_root=os.path.join(base, "legacy"))
        self.view.settings["output_folder"] = os.path.join(base, "out")
        self.assistant = AssistantView(self.view)

    def tearDown(self):
        self.assistant.shutdown()
        self.assistant.deleteLater()
        self.view.deleteLater()
        app.processEvents()
        self.tmp.cleanup()

    def test_one_channel_blocks_until_backgrounds_and_beats(self):
        wizard = self.assistant.start_one("SinFondos")
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("no tiene fondos", wizard.hint.text())
        combo = wizard.pages[0].widget.findChild(QComboBox)
        combo.setCurrentText("ConFondos")
        wizard.update_state()
        self.assertTrue(wizard.btn_next.isEnabled())
        wizard.btn_next.click()
        self.assertEqual(wizard.index, 1)
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("al menos un beat", wizard.hint.text())
        drop = wizard.pages[1].widget.findChild(BeatDropTable)
        drop.paths_dropped.emit([touch(os.path.join(self.tmp.name, "b", "Night 140bpm.mp3"))])
        wizard.update_state()
        self.assertTrue(wizard.btn_next.isEnabled())
        wizard.btn_next.click()
        titles = wizard.pages[2].widget.findChild(BeatDropTable)
        self.assertEqual(titles.item(0, BeatDropTable.COL_TITLE).text(), '[FREE] "Night"')
        wizard.btn_next.click()
        self.assertEqual(wizard.btn_next.text(), "🎬 Generar 1 videos")

    @unittest.skipUnless(resolve_tool("ffmpeg") and resolve_tool("ffprobe"), "requiere FFmpeg")
    def test_one_channel_end_to_end_with_inbox(self):
        beat = os.path.join(self.local, "entrada", "ConFondos", "Night.mp3")
        subprocess.run([resolve_tool("ffmpeg"), "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=2", beat],
                       check=True)
        wizard = self.assistant.start_one("ConFondos")
        wizard.btn_next.click()  # canal
        self.assertIn("📥", wizard.pages[1].widget.findChild(BeatDropTable).item(0, 0).text())
        wizard.btn_next.click()  # beats
        wizard.btn_next.click()  # títulos
        wizard.btn_next.click()  # generar
        self.assertFalse(wizard.btn_next.isEnabled())  # ocupado
        wait_until(lambda: wizard.index == 4)
        self.assertEqual(wizard.index, 4)
        self.assertTrue(wizard.btn_back.isHidden())
        self.assertTrue(os.path.exists(os.path.join(self.local, "entrada", "ConFondos", "hechos", "Night.mp3")))

    def test_new_channel_flow(self):
        wizard = self.assistant.start_new()
        name = wizard.pages[0].widget.findChild(QLineEdit)
        name.setText("ConFondos")
        wizard.update_state()
        self.assertIn("ya existe", wizard.hint.text())
        name.setText("a/b")
        wizard.update_state()
        self.assertFalse(wizard.btn_next.isEnabled())
        name.setText("Nuevo Canal")
        wizard.update_state()
        wizard.btn_next.click()
        base = wizard.pages[1].widget.findChild(QComboBox)
        base.setCurrentIndex(base.findData("ConFondos"))
        wizard.btn_next.click()
        video = [r for r in wizard.pages[2].widget.findChildren(QRadioButton) if "Video" in r.text()][0]
        video.setChecked(True)
        wizard.btn_next.click()
        self.assertEqual(wizard.btn_next.text(), "Crear canal →")
        with unittest.mock.patch.object(self.view, "open_folder"):
            wizard.btn_next.click()  # crea el canal y abre la carpeta de fondos
        self.assertIn("Nuevo Canal", cp.list_channels(self.local))
        self.assertEqual(cp.load(self.local, "Nuevo Canal")["fondo"], cp.MODE_VIDEO)
        self.assertFalse(wizard.btn_next.isEnabled())
        touch(os.path.join(self.local, "canales", "Nuevo Canal", "fondos", "clip.mp4"))
        wizard.update_state()
        self.assertTrue(wizard.btn_next.isEnabled())
        wizard.btn_next.click()
        self.assertEqual(wizard.btn_next.text(), "🎬 Hacer videos para este canal")
        wizard.btn_next.click()  # pasa al camino «un canal» con el canal nuevo
        new_wizard = self.assistant.wizard
        self.assertIsNot(new_wizard, wizard)
        self.assertEqual(new_wizard.pages[0].widget.findChild(QComboBox).currentText(), "Nuevo Canal")

    def test_many_channels_needs_inbox(self):
        wizard = self.assistant.start_many()
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("carpeta de entrada", wizard.hint.text())
        touch(os.path.join(self.local, "entrada", "ConFondos", "uno.mp3"))
        touch(os.path.join(self.local, "entrada", "SinFondos", "dos.mp3"))
        wizard.pages[0].on_enter()  # «Volver a revisar»
        wizard.update_state()
        self.assertTrue(wizard.btn_next.isEnabled())
        wizard.btn_next.click()
        self.assertEqual(wizard.stack.currentWidget().layout().itemAt(0).widget().rowCount(), 2)

    def test_cloud_goal_and_exit(self):
        hits = []
        self.assistant.cloud_requested.connect(lambda: hits.append(1))
        self.assistant.btn_cloud.click()
        self.assertEqual(hits, [1])
        wizard = self.assistant.start_one()
        wizard.btn_cancel.click()
        self.assertIs(self.assistant.stack.currentWidget(), self.assistant.goals)


import unittest.mock  # noqa: E402

if __name__ == "__main__":
    unittest.main()
