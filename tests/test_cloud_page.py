import functools
import json
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QRadioButton

app = QApplication.instance() or QApplication([])

from core import cloud_login
from core.beat_fakes import MemoryDropbox
from core.beat_panel import BeatPanel
from core.cloud_page import KITS, TAB_ADVANCED, TAB_CHANNEL, TAB_SEO


def settle(panel):
    deadline = time.monotonic() + 3
    while panel.task is not None and time.monotonic() < deadline:
        app.processEvents()
    app.processEvents()


def items(**oks):
    ids = ('slug', 'youtube', 'dropbox', 'gh', 'notion')
    return [{'id': i, 'ok': oks.get(i, False), 'label': i} for i in ids]


class CloudPageTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch("main.BeatPanel", functools.partial(BeatPanel, cloud_provider=MemoryDropbox))
        patcher.start()
        self.addCleanup(patcher.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.settings = os.path.join(tmp.name, "mm.json")
        with open(self.settings, "w", encoding="utf-8") as f:
            json.dump({"guide_seen": True, "local_root": tmp.name}, f)
        self.state = {}
        p1 = mock.patch("core.cloud_page.status.readiness_beats", lambda c, s: items(**self.state))
        p2 = mock.patch("core.cloud_page.cloud_login.dropbox_status",
                        lambda: cloud_login.OK if self.state.get("pc") else cloud_login.MISSING)
        for p in (p1, p2):
            p.start()
            self.addCleanup(p.stop)
        import main
        self.w = main.MainWindow(settings_path=self.settings)
        settle(self.w.beat_panel)
        self.cloud = self.w.cloud_page

    def tearDown(self):
        self.w.assistant.shutdown()
        self.w.deleteLater()
        app.processEvents()

    def test_advanced_hidden_by_default_and_persisted(self):
        inner = self.w.beat_panel.tabs
        self.assertFalse(inner.isTabVisible(TAB_SEO))
        self.assertFalse(inner.isTabVisible(TAB_ADVANCED))
        self.assertFalse(self.w.loop_kit_panel.tabs.isTabVisible(TAB_SEO))
        self.cloud.advanced.setChecked(True)
        self.assertTrue(inner.isTabVisible(TAB_SEO))
        with open(self.settings, encoding="utf-8") as f:
            self.assertTrue(json.load(f)["cloud_advanced"])
        self.cloud.advanced.setChecked(False)
        inner.setCurrentIndex(0)
        self.cloud.open_tab(TAB_SEO)  # pedir una pestaña avanzada la muestra
        self.assertTrue(self.cloud.advanced.isChecked())
        self.assertEqual(inner.currentIndex(), TAB_SEO)

    def test_connections_tab_scrolls(self):
        from PyQt5.QtWidgets import QScrollArea
        self.assertIsInstance(self.w.beat_panel.tabs.widget(0), QScrollArea)

    def test_guide_ticks_from_real_readiness(self):
        title, intro, steps = self.cloud.guide()
        self.assertEqual([s.state() for s in steps[:5]], ["todo"] * 5)
        self.state.update(pc=True, gh=True, youtube=True)
        self.assertEqual([s.state() for s in steps[:5]], ["done", "done", "todo", "done", "todo"])

    def test_cloud_assistant_walks_with_lights_and_banner(self):
        self.w.open_assistant()
        wizard = self.w.assistant.start_cloud()
        self.assertEqual(wizard.flow_title.text(), "Automatizar un canal en la nube")
        wizard.btn_next.click()  # Beats
        self.assertEqual(wizard.index, 1)
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("falta", wizard.hint.text())
        self.state.update(pc=True, gh=True)
        wizard.update_state()
        self.assertIn("●", wizard.pages[1].widget.findChildren(type(wizard.hint))[-1].text())
        wizard.btn_next.click()
        self.assertEqual(wizard.index, 2)
        self.assertFalse(wizard.btn_next.isEnabled())
        # «Abrir Canal» lleva a la pestaña con el aviso para volver
        button = [b for b in wizard.pages[2].widget.findChildren(type(wizard.btn_next)) if "Canal" in b.text()][0]
        button.click()
        self.assertIs(self.w.shell.current(), self.cloud)
        self.assertFalse(self.cloud.banner.isHidden())
        self.assertEqual(self.w.beat_panel.tabs.currentIndex(), TAB_CHANNEL)
        self.state.update(slug=True)
        self.cloud.banner.findChildren(type(wizard.btn_next))[0].click()  # Volver al asistente
        self.assertIs(self.w.shell.current(), self.w.assistant)
        self.assertIs(self.w.assistant.wizard, wizard)  # no se reinició
        self.assertTrue(wizard.btn_next.isEnabled())
        wizard.btn_next.click()
        self.assertEqual(wizard.index, 3)
        self.assertFalse(wizard.btn_next.isEnabled())
        self.state.update(youtube=True, dropbox=True)
        wizard.update_state()
        wizard.btn_next.click()
        self.assertEqual(wizard.btn_next.text(), "Terminar")

    def test_kits_choice_switches_tab(self):
        self.w._loop_kit_loaded = True  # evita leer Dropbox real
        wizard = self.w.assistant.start_cloud()
        kits = [r for r in wizard.pages[0].widget.findChildren(QRadioButton) if "Loop" in r.text()][0]
        kits.setChecked(True)
        wizard.btn_next.click()
        self.assertEqual(self.cloud.kind(), KITS)


if __name__ == "__main__":
    unittest.main()
