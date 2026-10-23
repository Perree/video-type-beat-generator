import json
import os
import tempfile
import unittest

from core import beat_cloud, channel_kind, cloud_registry, dropbox_layout as L, dropbox_local, kit_channel


class LayoutTests(unittest.TestCase):
    def test_everything_lives_under_one_root(self):
        for path in (channel_kind.BEATS_DOCUMENT, cloud_registry.PATHS["canales"], cloud_registry.PATHS["ajustes"],
                     *kit_channel.default_paths({})[1:4], *kit_channel.paths("wyresounds", {})[1:4]):
            self.assertTrue(path.startswith(L.ROOT + "/datos/"), path)
        self.assertEqual(kit_channel.paths("wyresounds", {}).state, L.KITS_STATE_DIR + "/wyresounds/state.json")

    def test_translate_old_paths_keeping_lowercase_style(self):
        self.assertEqual(L.translate_path("/type-beats/state.json"), (L.BEATS_DIR + "/state.json").lower())
        self.assertEqual(L.translate_path("/AudioVisual Stuff/Type Beats - STUFF/ey mat thumbnails"),
                         L.CHANNELS_DIR + "/ey mat/miniaturas")
        self.assertEqual(L.translate_path("/audiovisual stuff/type beats - stuff/ey mat/clip.mp4"),
                         (L.CHANNELS_DIR + "/ey mat/fondos").lower() + "/clip.mp4")
        self.assertEqual(L.translate_path("/loop_kits/_referencias/guitarras/fondos/a.jfif"),
                         (L.KITS_REFS_DIR + "/guitarras/fondos/a.jfif").lower())
        # sin tocar: límites de carpeta, otras rutas y textos
        for value in ("/AudioVisual Stuff/Type Beats - STUFF/ey matx", "/Music Production Stuff/x", "hola", 3):
            self.assertEqual(L.translate_path(value), value)

    def test_translate_documents_recursively_including_keys(self):
        doc = {"refs_root": "/loop_kits/_referencias", "runs": [{"ref_images": ["/loop_kits/_referencias/g/a.jfif"]}],
               "packs": {"/loop_kits/_referencias/k": 1}, "n": 1}
        out = L.translate(doc)
        self.assertTrue(out["refs_root"].endswith("contenido/loop_kits/referencias"))
        self.assertTrue(out["runs"][0]["ref_images"][0].endswith("referencias/g/a.jfif"))
        self.assertEqual(list(out["packs"]), [(L.KITS_REFS_DIR + "/k").lower()])
        self.assertEqual(doc["refs_root"], "/loop_kits/_referencias")  # no modifica la entrada

    def test_cloud_documents_are_translated_when_read(self):
        data = json.dumps({"channels": [{"dropbox_images": {
            "melodic": "/AudioVisual Stuff/Type Beats - STUFF/ey mat thumbnails"}}]}).encode()
        decoded = beat_cloud.decode_document(data)
        self.assertEqual(decoded["channels"][0]["dropbox_images"]["melodic"], L.CHANNELS_DIR + "/ey mat/miniaturas")

    def test_local_root_prefers_unified_folder_when_synced(self):
        with tempfile.TemporaryDirectory() as home:
            os.makedirs(os.path.join(home, "Dropbox"))
            self.assertEqual(dropbox_local.default_local_root({}, home),
                             os.path.join(home, "Dropbox", "TypeBeat Local"))
            unified = os.path.join(home, "Dropbox", *L.CONTENT.strip("/").split("/"))
            os.makedirs(os.path.join(unified, "canales"))
            self.assertEqual(dropbox_local.default_local_root({}, home), unified)


if __name__ == "__main__":
    unittest.main()
