import functools
import os
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

    def test_tabs_and_sections_without_channel_manager(self):
        import main
        w = main.MainWindow()
        settle(w.beat_panel)
        self.assertEqual([w.tabs.tabText(i) for i in range(w.tabs.count())], ["Beats", "Loop kits", "Manual"])
        self.assertEqual(w._current_section(), SECTION_BEATS)
        w._loop_kit_loaded = True  # evita la lectura de Dropbox
        w.tabs.setCurrentIndex(1)
        self.assertEqual(w._current_section(), SECTION_LOOP_KITS)
        self.assertFalse(hasattr(w, "btn_channels"))
        self.assertIsNone(w.tabs.cornerWidget())

    def test_reload_waits_for_running_task(self):
        import main
        w = main.MainWindow()
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
