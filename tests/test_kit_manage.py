import os
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QComboBox, QMessageBox

app = QApplication.instance() or QApplication([])

from core import gh_status, kit_channel, kit_cloud, kit_manage
from core.cloud_fakes import FakeGhRun


def pump(until, timeout=5):
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return until()


class ScheduleTests(unittest.TestCase):
    def test_none_token_means_no_channel_and_empty_keeps_default(self):
        self.assertEqual(kit_channel.parse_schedule("-"), [])
        self.assertEqual(kit_channel.matrix("-", 6), [])
        self.assertEqual(kit_channel.parse_schedule(""), [("default", 6)])

    def test_format_and_apply(self):
        self.assertEqual(kit_manage.format_schedule({}), "-")
        self.assertEqual(kit_manage.format_schedule({"wyre-kits": 2, "default": 6}), "default=6,wyre-kits=2")
        new = kit_manage.apply_changes({"default": 6, "a": 1}, {
            "default": {"active": False, "day": 6}, "a": {"active": True, "day": 3}, "b": {"active": True, "day": 0},
            "c": "remove"})
        self.assertEqual(new, {"a": 3, "b": 0})
        with self.assertRaises(kit_manage.KitManageError):
            kit_manage.apply_changes({}, {"a": {"active": True, "day": 9}})


class GhTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGhRun(variables={"KIT_CHANNELS": "default=6,wyre-kits=2"})
        self.client = gh_status.GhStatus(run=self.gh)

    def test_read_needs_session(self):
        self.assertEqual(kit_manage.read_schedule(self.client), {"default": 6, "wyre-kits": 2})
        self.gh.logged_in = False
        self.client.invalidate()
        self.assertIsNone(kit_manage.read_schedule(self.client))

    def test_save_pauses_all_and_removes_from_index(self):
        index = {"channels": [{"name": "Wyre Kits", "slug": "wyre-kits"}]}

        def read_rev(path, dbx=None):
            return dict(index), "rev1"

        def write(path, data, rev=None, dbx=None):
            index.clear()
            index.update(data)
            return "rev2"
        with mock.patch.object(kit_cloud, "read_json_rev", read_rev), mock.patch.object(kit_cloud, "write_json", write):
            result = kit_manage.save({"default": {"active": False, "day": 6}, "wyre-kits": "remove"}, self.client)
        self.assertEqual(self.gh.variables["KIT_CHANNELS"], "-")
        self.assertEqual(result["removed"], ["wyre-kits"])
        self.assertEqual(index["channels"], [])

    def test_default_cannot_be_removed(self):
        with self.assertRaises(kit_manage.KitManageError):
            kit_manage.remove_from_index("")


class FakeKits:
    def __init__(self):
        self.automation = QComboBox()
        self.automation.addItem("Canal por defecto", "")
        self.automation.addItem("Wyre Kits", "wyre-kits")

    def channel_chip(self, channel, slug, key):
        return "✔ Listo", "#2e9e4f"


class MyChannelsKitsTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGhRun(variables={"KIT_CHANNELS": "default=6,wyre-kits=2"})
        self.prev = gh_status.set_default(gh_status.GhStatus(run=self.gh))
        from core.beat_fakes import MemoryDropbox
        from core.beat_panel import BeatPanel
        from core.my_channels import KitCard, MyChannelsView
        self.KitCard = KitCard
        self.panel = BeatPanel(cloud_provider=MemoryDropbox)
        pump(lambda: self.panel.task is None)
        self.view = MyChannelsView(self.panel, FakeKits())
        self.view.show()
        self.view.tick()

    def tearDown(self):
        gh_status.set_default(self.prev)
        self.view.deleteLater()
        self.panel.deleteLater()
        app.processEvents()

    def cards(self):
        return self.view.kit_cards

    def test_cards_show_active_and_day_from_github(self):
        default, wyre = self.cards()
        self.assertTrue(default.active.isChecked())
        self.assertEqual(default.day.currentIndex(), 6)
        self.assertEqual(wyre.day.currentIndex(), 2)
        self.assertFalse(any(b.text() == "Quitar" for b in default.findChildren(type(self.view.btn_save))))

    def test_pause_change_day_remove_then_save(self):
        default, wyre = self.cards()
        default.active.setChecked(False)
        self.assertTrue(self.view.btn_save.isVisible())
        self.cards()[1].day.setCurrentIndex(4)
        with mock.patch("core.my_channels.QMessageBox.question", return_value=QMessageBox.No):
            self.view.remove_kit("wyre-kits", "Wyre Kits")
        self.assertEqual(self.view.kit_changes["wyre-kits"], {"active": True, "day": 4})
        with mock.patch.object(kit_manage, "remove_from_index", return_value=True):
            self.view.save()
            self.assertTrue(pump(lambda: not self.view.kit_saving))
        self.assertEqual(self.gh.variables["KIT_CHANNELS"], "wyre-kits=4")
        self.assertEqual(self.view.kit_changes, {})
        self.assertIn("guardados", self.view.status.text())

    def test_undo_remove_and_no_op_change(self):
        with mock.patch("core.my_channels.QMessageBox.question", return_value=QMessageBox.Yes):
            self.view.remove_kit("wyre-kits", "Wyre Kits")
        self.assertEqual(self.view.kit_changes, {"wyre-kits": "remove"})
        undo = [b for b in self.cards()[1].findChildren(type(self.view.btn_save)) if b.text() == "Deshacer"][0]
        undo.click()
        self.assertEqual(self.view.kit_changes, {})
        self.view.kit_change("default", {"active": True, "day": 6})  # igual a GitHub: no es cambio
        self.assertEqual(self.view.kit_changes, {})


if __name__ == "__main__":
    unittest.main()
