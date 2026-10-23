import json
import os
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QComboBox, QMessageBox

app = QApplication.instance() or QApplication([])

from core import cloud_registry
from core.beat_fakes import MemoryDropbox
from core.beat_panel import BeatPanel
from core.my_channels import BeatCard, KitCard, MyChannelsView, ScheduleDialog, schedule_text

CONFIG_PATH = "/type-beats/config.json"


def pump(until, timeout=5):
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return until()


def seed(memory, with_registry=True):
    if with_registry:
        rows = [dict(slug=s, tipo="beats", clave=s, nombre=s, activo=True) for s in ("beat-a", "beat-b")]
        doc = cloud_registry.normalize("canales", dict(cloud_registry.empty("canales"), canales=rows))
        memory.files[cloud_registry.PATHS["canales"]] = (cloud_registry.payload(doc), "rev-reg-1")
    config = {"beatstars_profile_url": "https://www.beatstars.com/testproducer", "channels": [
        {"id": "beat-a", "active": True, "priority": 0, "selection_tags": [], "actions_slug": "beat-a",
         "slots": [{"weekday": 0, "hour": 18, "minute": 0}, {"weekday": 3, "hour": 18, "minute": 0}]},
        {"id": "beat-b", "active": False, "priority": 0, "selection_tags": [], "actions_slug": "beat-b",
         "slots": [{"weekday": 4, "hour": 20, "minute": 30}]}]}
    memory.files[CONFIG_PATH] = (json.dumps(config).encode(), "rev-cfg-1")
    return memory


class FakeKits:
    """Lo mínimo del panel de Loop kits que usa la pantalla (sin Dropbox)."""

    def __init__(self):
        self.automation = QComboBox()
        self.automation.addItem("Canal por defecto", "")
        self.automation.addItem("WyreSounds Kits", "wyresounds")

    def channel_chip(self, channel, slug, key):
        return ("✔ Listo", "#2e9e4f") if slug else ("◐ 2/5", "#d98e04")


class ScheduleTextTests(unittest.TestCase):
    def test_groups_by_time(self):
        self.assertEqual(schedule_text([{"weekday": 0, "hour": 18, "minute": 0},
                                        {"weekday": 3, "hour": 18, "minute": 0}]), "Lun, Jue · 18:00")
        self.assertEqual(schedule_text([{"weekday": d, "hour": 9, "minute": 5} for d in range(7)]),
                         "Todos los días · 09:05")
        self.assertEqual(schedule_text([]), "Sin horario")

    def test_dialog_builds_slots_and_requires_a_day(self):
        dialog = ScheduleDialog("x", [{"weekday": 1, "hour": 7, "minute": 15}])
        self.assertEqual(dialog.slots(), [{"weekday": 1, "hour": 7, "minute": 15}])
        dialog.checks[5].setChecked(True)
        self.assertEqual([s["weekday"] for s in dialog.slots()], [1, 5])
        dialog.deleteLater()


class MyChannelsTests(unittest.TestCase):
    def setUp(self):
        self.memory = seed(MemoryDropbox())
        self.panel = BeatPanel(cloud_provider=lambda: self.memory)
        pump(lambda: self.panel.task is None)
        self.view = MyChannelsView(self.panel, FakeKits())
        self.view.show()
        app.processEvents()

    def tearDown(self):
        self.view.deleteLater()
        self.panel.deleteLater()
        app.processEvents()

    def remote(self):
        return json.loads(self.memory.files[CONFIG_PATH][0].decode())

    def cards(self, kind=BeatCard):
        return self.view.body.findChildren(kind)

    def save(self):
        self.view.btn_save.click()
        self.assertTrue(pump(lambda: not self.view.saving and self.panel.task is None and (self.view.tick() or True)))
        self.view.tick()

    def test_lists_channels_with_schedule_and_health(self):
        self.assertFalse(self.view.blocked.isVisible())
        beats = self.cards()
        self.assertEqual(len(beats), 2)
        self.assertEqual(len(self.cards(KitCard)), 2)
        texts = " ".join(label.text() for label in beats[0].findChildren(type(self.view.status)))
        self.assertIn("Lun, Jue · 18:00", texts)
        self.assertEqual(beats[1].active.text(), "Pausada")
        self.assertFalse(self.view.btn_save.isVisible())

    def test_pause_and_save_updates_dropbox(self):
        self.cards()[0].active.setChecked(False)
        self.assertTrue(self.view.dirty)
        self.assertTrue(self.view.btn_save.isVisible())
        self.assertIn("sin guardar", self.view.status.text())
        self.save()
        self.assertFalse(self.view.dirty)
        self.assertIn("guardados", self.view.status.text())
        self.assertEqual([c["active"] for c in self.remote()["channels"]], [False, False])

    def test_change_schedule(self):
        new = [{"weekday": 2, "hour": 21, "minute": 0}]
        with mock.patch.object(ScheduleDialog, "exec_", return_value=True), \
                mock.patch.object(ScheduleDialog, "slots", return_value=new):
            self.cards()[1].btn_schedule.click()
        self.save()
        self.assertEqual(self.remote()["channels"][1]["slots"], new)

    def test_remove_asks_and_saves(self):
        with mock.patch("core.my_channels.QMessageBox.question", return_value=QMessageBox.Yes):
            self.view.remove(0)
        self.assertEqual(len(self.cards()), 1)
        self.save()
        self.assertEqual([c["id"] for c in self.remote()["channels"]], ["beat-b"])

    def test_open_kit_callback(self):
        opened = []
        self.view._open_kit = opened.append
        [b for b in self.cards(KitCard)[1].findChildren(type(self.view.btn_save)) if "Editar" in b.text()][0].click()
        self.assertEqual(opened, ["wyresounds"])


class BlockedTests(unittest.TestCase):
    def test_missing_registry_explains_and_links_to_connections(self):
        memory = seed(MemoryDropbox(), with_registry=False)
        panel = BeatPanel(cloud_provider=lambda: memory)
        pump(lambda: panel.task is None)
        view = MyChannelsView(panel, FakeKits())
        view.show()
        view.tick()
        self.assertTrue(view.blocked.isVisible())
        self.assertIn("Conexiones", view.blocked_reason() + " Conexiones")
        hits = []
        view.connections_requested.connect(lambda: hits.append(1))
        [b for b in view.blocked.findChildren(type(view.btn_save))][0].click()
        self.assertEqual(hits, [1])
        view.deleteLater()
        panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
