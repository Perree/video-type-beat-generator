"""Regresiones de la revisión del modo solo-Dropbox (sin red: dobles en memoria)."""
import io
import json
import os
import sys
import time
import unittest
from contextlib import redirect_stderr
from copy import deepcopy

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, "scripts")):
    if path not in sys.path:
        sys.path.insert(0, path)

from PyQt5.QtWidgets import QApplication

from core import cloud_merge, cloud_registry, kit_cloud, kit_settings
from core.beat_cloud import Conflict
from core.beat_fakes import MemoryDropbox
from test_beat_panel import CONFIG_PATH, open_panel, pump, seed

APP = QApplication.instance() or QApplication([])


def registry(*rows):
    return cloud_registry.normalize("canales", dict(cloud_registry.empty("canales"), canales=list(rows)))


def ficha(slug, tipo, clave=None):
    return {"slug": slug, "tipo": tipo, "clave": clave or slug, "nombre": clave or slug, "activo": True}


class KitPanelTests(unittest.TestCase):
    def setUp(self):
        from smoke_kit_state import FakeDropbox
        from loop_kit_panel import LoopKitPanel
        self.dbx = FakeDropbox()
        self.panel = LoopKitPanel(dbx_provider=lambda: self.dbx)
        self.addCleanup(self.panel.shutdown)

    def wait(self):
        deadline = time.monotonic() + 5
        while self.panel._task is not None and time.monotonic() < deadline:
            APP.processEvents()
        APP.processEvents()

    def put(self, path, doc):
        kit_cloud.write_json(path, doc, rev=None, dbx=self.dbx)

    def test_channel_without_section_is_an_error_not_a_crash(self):
        self.put(kit_settings.CONFIG_PATH, {"channels": {"x": {"title_template": "T"}},
                                            "kit_preview": {"channel": "x"}})
        self.panel.reload()
        self.wait()
        self.assertIn("tipo definido", self.panel.status.text())
        self.panel._base_config = {"channels": {"x": {}}}
        self.panel.ask_new_automation()  # no debe abortar Qt
        self.assertIn("tipo definido", self.panel.status.text())

    def test_unreadable_registry_still_loads_kits_and_blocks_new_channels(self):
        self.put(kit_settings.CONFIG_PATH, {"channels": {"c": {"section": "loop_kits"}},
                                            "kit_preview": {"channel": "c", "genres": ["g"]}})
        self.dbx.files[cloud_registry.PATHS["canales"]] = ("0000000000aa", b"{roto")
        self.panel.reload()
        self.wait()
        self.assertEqual(self.panel.channel.currentText(), "c")
        self.assertIn("Registro de canales", self.panel.status.text())
        uploads = self.dbx.uploads
        self.panel.ask_new_automation()
        self.assertEqual(self.dbx.uploads, uploads)

    def test_beats_channel_cannot_get_a_kits_automation(self):
        self.put(cloud_registry.PATHS["canales"], registry(ficha("ey-mat", "beats", "ey mat")))
        self.put(kit_settings.CONFIG_PATH, {"channels": {}, "kit_preview": {}})
        self.panel.reload()
        self.wait()
        self.panel.create_automation("ey mat")
        self.wait()
        self.assertIn("Beats", self.panel.status.text())
        self.assertNotIn("/Soft Projects/Type Beat Generator/datos/loop_kits/ey-mat/config.json", self.dbx.files)


    def test_new_automation_reports_errors_to_the_caller(self):
        self.put(cloud_registry.PATHS["canales"], registry(ficha("ey-mat", "beats", "ey mat")))
        self.put(kit_settings.CONFIG_PATH, {"channels": {}, "kit_preview": {}})
        self.panel.reload()
        results = []
        self.assertFalse(self.panel.ask_new_automation(lambda ok, text: results.append((ok, text))))
        self.assertEqual(results[0][0], False)  # ocupado leyendo: se avisa, no se ignora
        self.wait()
        self.panel.create_automation("ey mat", lambda ok, text: results.append((ok, text)))
        self.wait()
        self.assertEqual(results[1][0], False)
        self.assertIn("Beats", results[1][1])


class WorkerChannelTests(unittest.TestCase):
    def test_untyped_channels_are_reported_and_only_fatal_when_selected(self):
        from run_kit_preview import resolve_channel
        config = {"channels": {"kits": {"section": "loop_kits", "title_template": "T"},
                               "suelto": {"title_template": "x"}}}
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(resolve_channel(config, None)[0], "kits")
            self.assertEqual(resolve_channel(config, "kits")[0], "kits")
            with self.assertRaises(SystemExit):
                resolve_channel(config, "suelto")
            with self.assertRaises(SystemExit):
                resolve_channel({"channels": {"suelto": {}}}, None)
        self.assertIn("sin section", err.getvalue())


class BeatPanelFixTests(unittest.TestCase):
    def setUp(self):
        self.memory = seed(MemoryDropbox())
        self.panel = open_panel(self.memory)
        self.addCleanup(self.panel.deleteLater)

    def test_templates_follow_the_channel_in_the_combo(self):
        panel = self.panel
        panel.profile.setText("https://www.beatstars.com/testproducer")
        panel.add_channel()
        panel.title_template.setText("Plantilla de A {name}")
        panel.channel.setCurrentText("beat-b")
        self.assertEqual(panel.title_template.text(), "")
        panel.title_template.setText("Plantilla de B {name}")
        panel.add_channel()  # cambia de fila: guarda lo mostrado
        rows = {r["clave"]: r.get("plantillas", {}) for r in panel.registry["canales"]}
        self.assertEqual(rows["beat-a"].get("title_template"), "Plantilla de A {name}")
        self.assertEqual(rows["beat-b"].get("title_template"), "Plantilla de B {name}")

    def test_wizard_slug_must_match_registry(self):
        panel = self.panel
        panel.add_channel()
        notes = []
        panel.wizard_notify = lambda ok, text="": notes.append((ok, text))
        self.assertFalse(panel.wizard_set_slug("beat-a", "otro-slug"))
        self.assertNotIn("actions_slug", panel.config["channels"][0])
        self.assertTrue(notes and "registro" in notes[-1][1])


class RetryExhaustionTests(unittest.TestCase):
    def test_exhausted_retries_raise_revision_conflict_not_a_field_clash(self):
        def write(doc, rev):
            raise Conflict("revision_conflict")
        with self.assertRaises(Conflict):
            cloud_merge.save_merged(lambda: ({"a": 1}, "r"), write, {"a": 1}, {"a": 1, "b": 2},
                                    "r0", (Conflict,))


if __name__ == "__main__":
    unittest.main()
