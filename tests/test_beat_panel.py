"""Phase 3 offline integration over an in-memory Dropbox: no app_config.json is read or written."""
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

from core import beat_settings, cloud_registry
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


CONFIG_PATH = "/type-beats/config.json"


def registry_doc():
    rows = [dict(slug=slug, tipo=tipo, clave=clave, nombre=clave, activo=True)
            for slug, tipo, clave in (("beat-a", "beats", "beat-a"), ("beat-b", "beats", "beat-b"),
                                      ("kits", "loops", "kits"))]
    return cloud_registry.normalize("canales", dict(cloud_registry.empty("canales"), canales=rows))


def seed(memory, config=None):
    memory.files[cloud_registry.PATHS["canales"]] = (cloud_registry.payload(registry_doc()), "rev-reg-1")
    if config is not None:
        memory.files[CONFIG_PATH] = (json.dumps(config).encode(), "rev-cfg-1")
    return memory


def open_panel(memory, **kwargs):
    panel = BeatPanel(cloud_provider=lambda: memory, **kwargs)
    pump(lambda: panel.task is None)
    return panel


class PanelTests(unittest.TestCase):
    def setUp(self):
        self.memory = seed(MemoryDropbox())
        self.panel = open_panel(self.memory)
        self.addCleanup(self.cleanup_panel)

    def remote(self):
        return json.loads(self.memory.files[CONFIG_PATH][0].decode())

    def remote_bytes(self):
        return self.memory.files.get(CONFIG_PATH)

    def publish(self, panel=None):
        panel = panel or self.panel
        panel.save_and_publish()
        pump(lambda: panel.task is None)

    def reopen(self):
        panel = open_panel(self.memory)
        self.addCleanup(panel.deleteLater)
        return panel

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

    def test_tab_shell_and_save_simulate_smoke(self):
        self.assertEqual(self.panel.tabs.count(), 4)
        self.assertEqual(
            [self.panel.tabs.tabText(i) for i in range(4)],
            ["Conexiones", "Canal", "SEO y tendencias", "Avanzado"],
        )
        self.assertEqual(self.panel.save_publish_button.text(), 'Publicar al robot')
        self.assertEqual(self.panel.simulate_button.text(), 'Probar sin subir')
        self.assertEqual(self.panel.cloud_reload_button.text(), 'Recargar desde Dropbox')
        self.assertFalse(hasattr(self.panel, 'save_button'))
        self.assertFalse(hasattr(self.panel, 'config_path'))
        self.configure()
        self.publish()
        self.assertEqual(self.remote()["channels"][0]["tags"], ["trap", "dark"])
        self.panel.transport = Transport()
        username = self.panel.transport.pages["profile"]["profileByUsername"]["username"]
        self.panel.profile.setText("https://www.beatstars.com/" + username)
        self.panel.analyze_profile()
        pump(lambda: self.panel.task is None)
        self.panel.simulate()
        pump(lambda: self.panel.task is None)
        self.assertGreater(self.panel.job_model.rowCount(), 0)

    def test_combo_lists_only_beats_channels_of_the_registry(self):
        names = [self.panel.channel.itemText(i) for i in range(self.panel.channel.count())]
        self.assertEqual(names, ["beat-a", "beat-b"])

    def test_publish_touches_only_dropbox_documents(self):
        self.configure()
        cwd_files = set(os.listdir("."))
        self.publish()
        self.assertEqual(set(self.memory.files),
                         {CONFIG_PATH, cloud_registry.PATHS["canales"]})
        self.assertEqual(self.memory.files[cloud_registry.PATHS["canales"]][1], "rev-reg-1")
        self.assertEqual(set(os.listdir(".")), cwd_files)
        self.assertEqual(self.reopen().tags.text(), "trap, dark")

    def test_templates_are_edited_in_seo_tab_and_saved_to_registry(self):
        self.configure()
        self.panel.use_templates.setChecked(True)
        self.panel.title_template.setText('[X] {name} | Free')
        self.panel.description_template.setPlainText('{name}\n{beatstars_url}\n{socials}')
        self.panel.socials.setText('IG @x')
        self.publish()
        registry = json.loads(self.memory.files[cloud_registry.PATHS["canales"]][0])
        row = next(r for r in registry["canales"] if r["clave"] == "beat-a")
        self.assertEqual(row["plantillas"]["title_template"], '[X] {name} | Free')
        seo = self.remote()["channels"][0]["seo"]
        self.assertEqual(seo["title_template"], '[X] {name} | Free')
        self.assertEqual(seo["description"], '{name}\n{url}\nIG @x')
        reopened = self.reopen()
        self.assertTrue(reopened.use_templates.isChecked())
        self.assertEqual(reopened.socials.text(), 'IG @x')

    def test_new_channel_goes_to_registry_as_beats(self):
        self.configure()
        self.panel.add_channel()
        self.panel.ask_new_channel_name = lambda: "Canal Nuevo"
        self.panel.add_channel()
        self.assertEqual(self.panel.channel.currentText(), "canal-nuevo")
        self.panel.ask_new_channel_name = lambda: "Beat A"  # slug beat-a ya existe
        self.panel.add_channel()
        self.assertEqual(len(self.panel.config["channels"]), 3)
        self.publish()
        registry = json.loads(self.memory.files[cloud_registry.PATHS["canales"]][0])
        row = next(r for r in registry["canales"] if r["slug"] == "canal-nuevo")
        self.assertEqual((row["tipo"], row["clave"], row["nombre"]), ("beats", "canal-nuevo", "Canal Nuevo"))
        self.assertEqual([c["id"] for c in self.remote()["channels"]], ["beat-a", "beat-b", "canal-nuevo"])

    def test_save_preserves_other_documents_and_channel_edits(self):
        self.configure()
        self.memory.files["/type-beats/state.json"] = (b"opaque", "rev-state")
        self.publish()
        self.assertEqual(self.memory.files["/type-beats/state.json"], (b"opaque", "rev-state"))
        self.assertEqual(self.remote()["channels"][0]["tags"], ["trap", "dark"])
        self.assertEqual(self.reopen().tags.text(), "trap, dark")

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

    def test_selection_tags_are_independent_per_channel_and_persist(self):
        self.configure()
        self.panel.selection_tags.setText(' Ambient , Artist Alpha ')
        self.panel.add_channel()
        self.assertEqual(self.panel.selection_tags.text(), '')
        self.panel.selection_tags.setText('Jazz')
        self.panel.automations.setCurrentRow(0)
        self.assertEqual(self.panel.selection_tags.text(), 'Ambient, Artist Alpha')
        self.assertEqual(self.panel.tags.text(), 'trap, dark')
        self.publish()
        channels = self.remote()['channels']
        self.assertEqual(channels[0]['selection_tags'], ['Ambient', 'Artist Alpha'])
        self.assertEqual(channels[0]['tags'], ['trap', 'dark'])
        self.assertEqual(channels[1]['selection_tags'], ['Jazz'])
        reopened = self.reopen()
        self.assertEqual(reopened.selection_tags.text(), 'Ambient, Artist Alpha')
        reopened.automations.setCurrentRow(1)
        self.assertEqual(reopened.selection_tags.text(), 'Jazz')

    def test_legacy_channel_loads_without_selection_filter(self):
        seed(self.memory, {'beatstars_profile_url': 'https://www.beatstars.com/testproducer',
            'channels': [{'id': 'beat-a', 'tags': ['trap'],
                          'slots': [{'weekday': 0, 'hour': 18, 'minute': 0}]}]})
        self.panel.reload()
        pump(lambda: self.panel.task is None)
        self.assertEqual(self.panel.selection_tags.text(), '')
        self.assertEqual(self.panel.tags.text(), 'trap')
        self.assertTrue(plan(self.panel.draft(), {}, [{'id': 'TK1', 'tags': ['other']}],
                             '2026-10-12T12:00:00-03:00'))

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
        self.publish()
        reopened = self.reopen()
        self.assertEqual(reopened.videos_folder.text(), '/type-beats/videos/channel-a')
        self.assertEqual(reopened.thumbnail_path.text(), '/type-beats/thumbnails/channel-a.png')
        self.assertEqual(reopened.clip_min.value(), 1.5)
        self.assertEqual(reopened.clip_max.value(), 4.5)

    def test_invalid_visual_settings_preserve_remote(self):
        self.configure()
        self.publish()
        before = self.remote_bytes()
        self.panel.clip_min.setValue(8)
        self.panel.clip_max.setValue(2)
        self.publish()
        self.assertEqual(self.remote_bytes(), before)
        self.panel.clip_min.setValue(1)
        self.panel.dropbox_images.setPlainText('not a mapping')
        self.publish()
        self.assertEqual(self.remote_bytes(), before)

    def test_invalid_visual_drafts_survive_channel_switch(self):
        self.configure()
        self.publish()
        before = self.remote_bytes()
        self.panel.clip_min.setValue(8)
        self.panel.clip_max.setValue(2)
        self.panel.dropbox_images.setPlainText('not a mapping')
        self.panel.add_channel()
        self.panel.automations.setCurrentRow(0)
        self.assertEqual(self.panel.clip_min.value(), 8)
        self.assertEqual(self.panel.clip_max.value(), 2)
        self.assertEqual(self.panel.dropbox_images.toPlainText(), 'not a mapping')
        self.publish()
        self.assertEqual(self.remote_bytes(), before)
        self.panel.clip_min.setValue(1)
        self.panel.dropbox_images.setPlainText('Trap=/type-beats/images/trap')
        self.publish()
        self.assertNotEqual(self.remote_bytes(), before)

    def test_validation_rejects_duplicate_slots_and_non_beats(self):
        self.configure()
        self.panel._add_slot()
        self.publish()
        self.assertIsNone(self.remote_bytes())
        self.panel.slots.removeRow(1)
        config = self.panel.draft()
        for bad in ("kits", "personal", "no-registrado"):
            config["channels"][0]["id"] = bad
            with self.assertRaises(ValueError):
                beat_settings.validate(config, self.panel.registry)
        config["channels"][0].update(id="beat-a", actions_slug="otro-slug")
        with self.assertRaisesRegex(ValueError, "registro"):
            beat_settings.validate(config, self.panel.registry)

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
        panel = open_panel(self.memory, parent=dialog)
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
        self.publish()
        reopened = self.reopen()
        self.assertEqual(reopened.priority.text(), "1000000000000000000000000")
        self.assertEqual(reopened.draft()["channels"][0]["priority"], 10 ** 24)

    def test_loaded_bad_metadata_cannot_be_silently_rewritten(self):
        self.configure()
        self.publish()
        config = self.remote()
        config["channels"][0]["tags"] = "trap"
        self.memory.files[CONFIG_PATH] = (json.dumps(config).encode(), "rev-bad")
        reopened = self.reopen()
        self.assertFalse(reopened.save_publish_button.isEnabled())
        self.assertFalse(reopened.config_readable)
        reopened.save_and_publish()
        self.assertIsNone(reopened.task)
        self.assertEqual(self.memory.files[CONFIG_PATH][1], "rev-bad")

    def test_registry_and_config_reject_ambiguous_json(self):
        for content in (b'[]', b'{"canales": [], "canales": []}', b'{"x": NaN}'):
            self.memory.files[cloud_registry.PATHS["canales"]] = (content, "rev-x")
            reopened = self.reopen()
            self.assertFalse(reopened.config_readable)
            self.assertFalse(reopened.save_publish_button.isEnabled())

    def test_cancel_cloud_retry_after_without_another_request(self):
        entered = Event()
        class TransientReader:
            calls = 0
            def read(self, path):
                self.calls += 1
                entered.set()
                raise Transient(delay=30)
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
        self.memory.files[CONFIG_PATH] = (b'{"broken":', "rev-broken")
        self.panel = open_panel(self.memory, state_reader=lambda: migrate({}, "state"))
        self.panel.read_state()
        pump(lambda: self.panel.task is None)
        self.assertFalse(self.panel.save_publish_button.isEnabled())
        self.assertFalse(self.panel.add_button.isEnabled())
        self.panel.save_and_publish()
        self.assertEqual(self.memory.files[CONFIG_PATH], (b'{"broken":', "rev-broken"))

    def test_publish_checklist_follows_live_channel_combo(self):
        self.configure()
        self.panel.config["channels"][0]["actions_slug"] = "alpha-slug"
        self.panel.add_channel()
        self.panel.automations.setCurrentRow(0)
        self.assertEqual(self.panel.channel.currentText(), "beat-a")
        captured = []
        from core import beat_panel_form as form_mod
        orig = form_mod.status.readiness_beats

        def spy(channel, slug, *args, **kwargs):
            captured.append((channel, slug))
            return orig(channel, slug, *args, **kwargs)

        form_mod.status.readiness_beats = spy
        try:
            self.panel.channel.setCurrentText("beat-b")
        finally:
            form_mod.status.readiness_beats = orig
        self.assertEqual(self.panel.channel.currentText(), "beat-b")
        self.assertEqual(captured[-1], ("beat-b", "alpha-slug"))

    def test_connections_follow_channel_list(self):
        self.panel.add_channel()
        self.panel.add_channel()
        self.panel.config["channels"].append({
            "id": "beat-c", "active": False, "priority": 0, "selection_tags": [],
            "actions_slug": "cee", "slots": [{"weekday": 0, "hour": 18, "minute": 0}],
        })
        for ch in self.panel.config["channels"]:
            ch.setdefault("actions_slug", ch["id"])
        self.panel.reload_connection_channels()
        self.panel.conn_channel.setCurrentText("beat-b")
        del self.panel.config["channels"][1]
        self.assertEqual(self.panel.conn_channel.currentText(), "beat-b")
        self.assertEqual(self.panel._conn_selection(), ("", ""))
        self.panel.remove_channel()
        names = [self.panel.conn_channel.itemText(i) for i in range(self.panel.conn_channel.count())]
        self.assertEqual(names, [ch["id"] for ch in self.panel.config["channels"]])
        self.assertEqual(self.panel._conn_selection()[0], self.panel.conn_channel.currentText())

    def test_no_late_result_after_cancel(self):
        delivered = []
        self.panel.task = BeatTask(lambda event, progress: None, self.panel)
        self.panel.task.cancel()
        self.panel._deliver({"tracks": []}, delivered.append)
        self.assertEqual(delivered, [])
        self.panel.task = None


if __name__ == "__main__":
    unittest.main()
