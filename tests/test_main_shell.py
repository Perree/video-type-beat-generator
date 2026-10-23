import functools
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from core.beat_fakes import MemoryDropbox
from core.beat_panel import BeatPanel
from core.sections import SECTION_BEATS, SECTION_LOOP_KITS


def settle(panel):
    deadline = time.monotonic() + 3
    while panel.task is not None and time.monotonic() < deadline:  # lectura inicial
        app.processEvents()
    app.processEvents()


class MainShellTests(unittest.TestCase):
    def setUp(self):
        # Sin Dropbox real: el panel de Beats lee de un doble en memoria vacío.
        patcher = mock.patch("main.BeatPanel", functools.partial(BeatPanel, cloud_provider=MemoryDropbox))
        patcher.start()
        self.addCleanup(patcher.stop)
        # Preferencias en una carpeta temporal: no tocar config/manual_mode.json real.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.settings = os.path.join(tmp.name, "manual_mode.json")

    def test_home_first_then_local_and_cloud(self):
        import main
        w = main.MainWindow(settings_path=self.settings)
        settle(w.beat_panel)
        self.assertIs(w.shell.current(), w.home)
        self.assertTrue(w.shell.btn_back.isHidden())
        w.home.btn_local.click()
        self.assertIs(w.shell.current(), w.local_view)
        self.assertFalse(w.shell.btn_back.isHidden())
        self.assertEqual(w.shell.guide.title.text(), "Crear videos en esta PC")
        w.shell.btn_back.click()
        self.assertIs(w.shell.current(), w.home)
        w.home.btn_cloud.click()
        self.assertIs(w.shell.current(), w.cloud_page)
        self.assertEqual([w.tabs.tabText(i) for i in range(w.tabs.count())], ["Beats", "Loop kits"])
        self.assertEqual(w._current_section(), SECTION_BEATS)
        w._loop_kit_loaded = True  # evita la lectura de Dropbox
        w.tabs.setCurrentIndex(1)
        self.assertEqual(w._current_section(), SECTION_LOOP_KITS)
        self.assertFalse(hasattr(w, "btn_channels"))

    def test_guide_toggle_and_first_run(self):
        import main
        w = main.MainWindow(settings_path=self.settings)
        settle(w.beat_panel)
        shell = w.shell
        shell.btn_guide.setChecked(True)
        self.assertFalse(shell.guide.isHidden())
        shell.guide._close()
        self.assertFalse(shell.btn_guide.isChecked())
        self.assertTrue(shell.guide.isHidden())

    def test_reload_waits_for_running_task(self):
        import main
        w = main.MainWindow(settings_path=self.settings)
        panel = w.beat_panel
        settle(panel)
        panel.task = object()
        with mock.patch.object(panel, "reload") as reload:
            panel.request_reload()
            reload.assert_not_called()
            self.assertTrue(panel._reload_pending)
            panel.task = None
            panel.request_reload()
            reload.assert_called_once()


if __name__ == "__main__":
    unittest.main()
