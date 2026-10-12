"""Phase 3 offline integration: settings isolation, planner and Qt task lifetime."""
import ast
import json
import os
from pathlib import Path
import tempfile
from threading import Event
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from core import beat_settings
from core.beat_panel import BeatDialog, BeatPanel
from core.beat_schema import migrate
from core.beat_schedule import plan
from core.beat_tasks import BeatTask, load_state
from core.beat_cloud import CloudError, Transient
from core.beat_fakes import MemoryDropbox


APP = QApplication.instance() or QApplication([])


def pump(until, timeout=3):
    deadline = time.monotonic() + timeout
    while not until() and time.monotonic() < deadline:
        APP.processEvents()
        time.sleep(.002)
    APP.processEvents()
    if not until():
        raise AssertionError("Qt task did not complete")


class Transport:
    def __init__(self, entered=None, release=None):
        self.entered, self.release = entered, release
        self.calls = 0
        self.pages = json.loads(Path("tests/fixtures/beatstars_pages.json").read_text(encoding="utf-8"))

    def query(self, query, variables, deadline):
        self.calls += 1
        if self.entered:
            self.entered.set()
            if not self.release.wait(2):
                raise RuntimeError("test_timeout")
        if "username" in variables:
            return self.pages["profile"]
        return self.pages["pages"][variables["page"]]


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "app.json"
        self.app = {"channels": {"beat-a": {}, "beat-b": {"section": "beats"},
                                 "kits": {"section": "loop_kits"},
                                 "personal": {"section": "personal"}},
                    "kit_preview": {"sentinel": [1, 2]}, "personal": {"sentinel": 3}}
        self.path.write_text(json.dumps(self.app), encoding="utf-8")
        self.panel = BeatPanel(config_path=self.path)
        self.addCleanup(self.cleanup_panel)

    def cleanup_panel(self):
        if self.panel.task:
            self.panel.cancel()
            pump(lambda: self.panel.task is None)
        self.panel.close()
        self.panel.deleteLater()
        APP.processEvents()

    def configure(self):
        self.panel.profile.setText("https://www.beatstars.com/testproducer")
        self.panel.add_channel()
        self.panel.active.setChecked(True)
        self.panel.tags.setText("trap, dark")
        self.panel.genres.setText("Trap")

    def test_save_preserves_other_sections_and_channel_edits(self):
        self.configure()
        latest = dict(self.app, last_section="personal")
        self.path.write_text(json.dumps(latest), encoding="utf-8")
        self.panel.save()
        saved = beat_settings.read_app(self.path)
        self.assertEqual({k: v for k, v in saved.items() if k != "beat_automation"}, latest)
        self.assertEqual(saved["beat_automation"]["channels"][0]["tags"], ["trap", "dark"])
        reopened = BeatPanel(config_path=self.path)
        self.assertEqual(reopened.tags.text(), "trap, dark")
        reopened.deleteLater()

    def test_channel_switch_preserves_draft_and_pause(self):
        self.configure()
        self.panel.add_channel()
        self.assertFalse(self.panel.active.isChecked())
        self.panel.priority.setText("12")
        self.panel.automations.setCurrentRow(0)
        self.assertEqual(self.panel.tags.text(), "trap, dark")
        config = self.panel.draft()
        self.assertEqual(config["channels"][1]["priority"], 12)
        self.assertEqual(len(plan(config, {}, [{"id": "TK1"}], "2026-10-12T12:00:00-03:00")), 1)

    def test_visual_options_per_channel_save_and_reload(self):
        self.configure()
        self.panel.visual_mode.setCurrentIndex(1)
        self.panel.video_source.setCurrentIndex(1)
        self.panel.videos_folder.setText('/type-beats/videos/channel-a')
        self.panel.clip_min.setValue(1.5)
        self.panel.clip_max.setValue(4.5)
        self.panel.thumbnail_source.setCurrentIndex(2)
        self.panel.thumbnail_path.setText('/type-beats/thumbnails/channel-a.png')
        self.panel.dropbox_images.setPlainText('Trap=/type-beats/images/channel-a')
        self.panel.add_channel()
        self.assertEqual(self.panel.visual_mode.currentData(), 'image')
        self.panel.automations.setCurrentRow(0)
        self.assertEqual(self.panel.visual_mode.currentData(), 'video')
        self.panel.save()
        saved = beat_settings.read_app(self.path)
        self.assertEqual(saved['kit_preview'], self.app['kit_preview'])
        self.assertEqual(saved['personal'], self.app['personal'])
        reopened = BeatPanel(config_path=self.path)
        self.addCleanup(reopened.deleteLater)
        self.assertEqual(reopened.videos_folder.text(), '/type-beats/videos/channel-a')
        self.assertEqual(reopened.thumbnail_path.text(), '/type-beats/thumbnails/channel-a.png')
        self.assertEqual(reopened.clip_min.value(), 1.5)
        self.assertEqual(reopened.clip_max.value(), 4.5)

    def test_invalid_visual_settings_preserve_file(self):
        self.configure()
        self.panel.save()
        before = self.path.read_bytes()
        self.panel.clip_min.setValue(8)
        self.panel.clip_max.setValue(2)
        self.panel.save()
        self.assertEqual(self.path.read_bytes(), before)
        self.panel.clip_min.setValue(1)
        self.panel.dropbox_images.setPlainText('not a mapping')
        self.panel.save()
        self.assertEqual(self.path.read_bytes(), before)

    def test_invalid_visual_drafts_survive_channel_switch(self):
        self.configure()
        self.panel.save()
        before = self.path.read_bytes()
        self.panel.clip_min.setValue(8)
        self.panel.clip_max.setValue(2)
        self.panel.dropbox_images.setPlainText('not a mapping')
        self.panel.add_channel()
        self.panel.automations.setCurrentRow(0)
        self.assertEqual(self.panel.clip_min.value(), 8)
        self.assertEqual(self.panel.clip_max.value(), 2)
        self.assertEqual(self.panel.dropbox_images.toPlainText(), 'not a mapping')
        self.panel.save()
        self.assertEqual(self.path.read_bytes(), before)
        self.panel.clip_min.setValue(1)
        self.panel.dropbox_images.setPlainText('Trap=/type-beats/images/trap')
        self.panel.save()
        self.assertNotEqual(self.path.read_bytes(), before)

    def test_validation_rejects_duplicate_slots_and_non_beats(self):
        self.configure()
        self.panel._add_slot()
        before = self.path.read_bytes()
        self.panel.save()
        self.assertEqual(self.path.read_bytes(), before)
        self.panel.slots.removeRow(1)
        config = self.panel.draft()
        config["channels"][0]["id"] = "kits"
        with self.assertRaises(ValueError):
            beat_settings.validate(config, self.app)

    def test_simulation_matches_pure_planner_without_mutation(self):
        self.configure()
        config = self.panel.draft()
        tracks = [{"id": "TK1"}, {"id": "TK2"}]
        state = migrate({}, "state")
        before = json.dumps(state)
        now = "2026-10-12T12:00:00-03:00"
        result = beat_settings.simulate(config, tracks, state, now)
        self.assertEqual(result["jobs"], plan(config, state, tracks, now))
        self.assertEqual(json.dumps(state), before)
        self.assertEqual(result["remaining"], 6)

    def test_qthread_responsive_cancel_and_no_result(self):
        entered, release = Event(), Event()
        self.panel.transport = Transport(entered, release)
        self.panel.profile.setText("https://www.beatstars.com/testproducer")
        ticks = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(5)
        try:
            self.panel.analyze_profile()
            pump(lambda: entered.is_set() and len(ticks) >= 3)
            self.panel.cancel()
            release.set()
            pump(lambda: self.panel.task is None)
            self.assertIsNone(self.panel.analysis)
            self.assertEqual(self.panel.transport.calls, 1)
            self.assertTrue(self.panel.analyze_button.isEnabled())
        finally:
            timer.stop()
            release.set()

    def test_success_and_profile_change_invalidates_analysis(self):
        self.panel.transport = Transport()
        username = self.panel.transport.pages["profile"]["profileByUsername"]["username"]
        self.panel.profile.setText("https://www.beatstars.com/" + username)
        self.panel.analyze_profile()
        pump(lambda: self.panel.task is None)
        self.assertIsNotNone(self.panel.analysis, self.panel.status.text())
        self.assertIn("Tracks:", self.panel.output.toPlainText())
        self.panel.add_channel()
        self.panel.active.setChecked(True)
        self.panel.simulate()
        pump(lambda: self.panel.task is None)
        self.assertEqual(self.panel.job_model.rowCount(), 2)
        self.panel.profile.setText("https://www.beatstars.com/another")
        self.assertIsNone(self.panel.analysis)
        self.assertEqual(self.panel.job_model.rowCount(), 0)

    def test_close_defers_until_task_exits(self):
        dialog = BeatDialog()
        panel = BeatPanel(dialog, config_path=self.path)
        dialog.panel = panel
        release = Event()
        dialog.show()
        panel._start(lambda event, progress: release.wait(2), lambda result: None)
        dialog.close()
        self.assertTrue(dialog.isVisible())
        self.assertTrue(dialog.close_pending)
        release.set()
        pump(lambda: panel.task is None)
        self.assertFalse(dialog.isVisible())
        dialog.deleteLater()

    def test_remote_state_read_and_missing_state_never_initialize(self):
        self.panel.state_reader = lambda: migrate({}, "state")
        self.panel.read_state()
        pump(lambda: self.panel.task is None)
        self.assertEqual(self.panel.state, migrate({}, "state"))
        self.assertIn("0/6", self.panel.quota.text())
        previous = self.panel.state
        def fail():
            raise CloudError("synthetic_failure")
        self.panel.state_reader = fail
        self.panel.read_state()
        pump(lambda: self.panel.task is None)
        self.assertIs(self.panel.state, previous)
        self.assertEqual("synthetic_failure", self.panel.status.text())

    def test_priority_larger_than_qt_integer_preserved(self):
        self.configure()
        self.panel.priority.setText("1000000000000000000000000")
        self.panel.save()
        reopened = BeatPanel(config_path=self.path)
        self.assertEqual(reopened.priority.text(), "1000000000000000000000000")
        self.assertEqual(reopened.draft()["channels"][0]["priority"], 10 ** 24)
        reopened.deleteLater()

    def test_loaded_bad_metadata_cannot_be_silently_rewritten(self):
        self.configure()
        self.panel.save()
        app = beat_settings.read_app(self.path)
        app["beat_automation"]["channels"][0]["tags"] = "trap"
        self.path.write_text(json.dumps(app), encoding="utf-8")
        reopened = BeatPanel(config_path=self.path)
        self.assertFalse(reopened.save_button.isEnabled())
        self.assertFalse(reopened.config_readable)
        reopened.deleteLater()

    def test_config_root_and_ambiguous_json_rejected(self):
        for content in ('[]', '{"channels": {}, "channels": {}}', '{"x": NaN}'):
            self.path.write_text(content, encoding="utf-8")
            with self.assertRaises(ValueError):
                beat_settings.read_app(self.path)

    def test_cancel_cloud_retry_after_without_another_request(self):
        entered = Event()
        class TransientReader:
            calls = 0
            def read(self, path):
                self.calls += 1
                entered.set()
                raise Transient(delay=3600)
        transport = TransientReader()
        values = []
        self.panel._start(lambda event, progress: load_state(event, transport), values.append)
        pump(entered.is_set)
        self.panel.cancel()
        pump(lambda: self.panel.task is None)
        self.assertEqual(transport.calls, 1)
        self.assertEqual(values, [])
        self.assertIn("cancelada", self.panel.status.text())

    def test_missing_cloud_state_is_explicit_and_read_only(self):
        transport = MemoryDropbox()
        with self.assertRaisesRegex(CloudError, "beat_state_not_initialized"):
            load_state(Event(), transport)
        self.assertEqual(transport.files, {})

    def test_large_simulation_model_keeps_all_jobs(self):
        from PyQt5.QtCore import Qt
        jobs = [{"slot": "2026-10-12T18:00:00-03:00", "channel": "beat-a",
                 "track_id": f"TK{i}", "cycle": 1} for i in range(33600)]
        self.panel.job_model.set_jobs(jobs)
        self.assertEqual(self.panel.job_model.rowCount(), 33600)
        self.assertEqual(self.panel.job_model.data(self.panel.job_model.index(33599, 2)), "TK33599")
        self.assertEqual(self.panel.job_model.headerData(3, Qt.Horizontal), "Ciclo")

    def test_failed_reanalysis_clears_previous_summary(self):
        self.panel.profile.setText("https://www.beatstars.com/testproducer")
        self.panel.output.setPlainText("Tracks: resultado anterior")
        class FailedTransport:
            def query(self, *args):
                raise RuntimeError("failure")
        self.panel.transport = FailedTransport()
        self.panel.analyze_profile()
        pump(lambda: self.panel.task is None)
        self.assertEqual(self.panel.output.toPlainText(), "")
        self.assertIsNone(self.panel.analysis)

    def test_invalid_config_cannot_be_overwritten_after_task(self):
        self.panel.deleteLater()
        self.path.write_text('{"broken":', encoding="utf-8")
        self.panel = BeatPanel(config_path=self.path, state_reader=lambda: migrate({}, "state"))
        self.panel.read_state()
        pump(lambda: self.panel.task is None)
        self.assertFalse(self.panel.save_button.isEnabled())
        self.assertFalse(self.panel.add_button.isEnabled())
        self.panel.save()
        self.assertEqual(self.path.read_text(encoding="utf-8"), '{"broken":')

    def test_main_wiring_button_visible_only_in_beats(self):
        # Exercise the actual wiring method without launching watchers or loading
        # personal configuration through MainWindow.__init__.
        tree = ast.parse(Path("main.py").read_text(encoding="utf-8"))
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "MainWindow")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "_apply_workflow_ui")
        namespace = {"SECTION_BEATS": "beats", "SECTION_LOOP_KITS": "loop_kits", "DEFAULT_SECTION": "beats"}
        exec(compile(ast.Module(body=[method], type_ignores=[]), "main.py", "exec"), namespace)
        from types import SimpleNamespace
        from PyQt5.QtWidgets import QPushButton, QLabel
        fake = SimpleNamespace(btn_beat_config=QPushButton(), btn_kit_config=QPushButton(),
                               beats_title=QLabel(), beats_label=QLabel(), assigned_label=QLabel(),
                               btn_load_beats=QPushButton())
        for section in ("beats", "loop_kits", "personal"):
            fake.current_section = section
            namespace["_apply_workflow_ui"](fake)
            self.assertEqual(not fake.btn_beat_config.isHidden(), section == "beats")
            self.assertEqual(not fake.btn_kit_config.isHidden(), section == "loop_kits")

    def test_no_late_result_after_cancel(self):
        delivered = []
        self.panel.task = BeatTask(lambda event, progress: None, self.panel)
        self.panel.task.cancel()
        self.panel._deliver({"tracks": []}, delivered.append)
        self.assertEqual(delivered, [])
        self.panel.task = None


if __name__ == "__main__":
    unittest.main()
