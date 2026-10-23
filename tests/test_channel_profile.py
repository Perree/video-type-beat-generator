import json
import os
import tempfile
import unittest
from unittest import mock

from core import channel_profile as cp
from core import dropbox_local, local_migration


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_makes_folders_and_default_profile(self):
        profile = cp.create(self.root, "Mi Canal")
        for sub in ("fondos", "miniaturas"):
            self.assertTrue(os.path.isdir(os.path.join(self.root, "canales", "Mi Canal", sub)))
        self.assertTrue(os.path.isdir(os.path.join(self.root, "entrada", "Mi Canal")))
        self.assertEqual(profile["fondo"], cp.MODE_IMAGE)
        self.assertEqual(cp.list_channels(self.root), ["Mi Canal"])

    def test_save_load_roundtrip_and_validation(self):
        cp.create(self.root, "A")
        cp.save(self.root, "A", dict(cp.load(self.root, "A"), fondo="video", tags=[" x ", "", "y"]))
        loaded = cp.load(self.root, "A")
        self.assertEqual((loaded["fondo"], loaded["tags"]), ("video", ["x", "y"]))
        with self.assertRaises(cp.ProfileError):
            cp.save(self.root, "A", dict(loaded, fondo="gif"))
        with self.assertRaises(cp.ProfileError):
            cp.save(self.root, "A", dict(loaded, titulo="  "))

    def test_create_does_not_overwrite_existing_profile(self):
        cp.save(self.root, "A", dict(cp.default_profile("A"), titulo="Mío {name}"))
        cp.create(self.root, "A", cp.default_profile("A"))
        self.assertEqual(cp.load(self.root, "A")["titulo"], "Mío {name}")

    def test_invalid_names_rejected(self):
        for bad in ("", " a", "a/b", "a:b", "..", "x" * 81, "fin."):
            with self.assertRaises(cp.ProfileError, msg=bad):
                cp.check_name(bad)

    def test_duplicate_copies_style_not_backgrounds(self):
        cp.create(self.root, "Base")
        cp.save(self.root, "Base", dict(cp.load(self.root, "Base"), titulo="[FREE] {name}"))
        touch(os.path.join(self.root, "canales", "Base", "fondos", "a.jpg"))
        cp.duplicate(self.root, "Base", "Base Dark")
        self.assertEqual(cp.load(self.root, "Base Dark")["titulo"], "[FREE] {name}")
        self.assertEqual(cp.media(self.root, "Base Dark", cp.MODE_IMAGE), ([], []))
        with self.assertRaises(cp.ProfileError):
            cp.duplicate(self.root, "Base", "Base Dark")

    def test_media_splits_kinds_and_online_only(self):
        folder = os.path.join(self.root, "canales", "C", "fondos")
        img = touch(os.path.join(folder, "a.jfif"))
        remote = touch(os.path.join(folder, "b.png"))
        touch(os.path.join(folder, "v.mp4"))
        touch(os.path.join(folder, "notes.txt"))
        with mock.patch.object(cp, "online_only", side_effect=lambda p: p == remote):
            self.assertEqual(cp.media(self.root, "C", cp.MODE_IMAGE), ([img], [remote]))
        self.assertEqual(len(cp.media(self.root, "C", cp.MODE_VIDEO)[0]), 1)

    def test_conflicted_copies_detected(self):
        cp.create(self.root, "C")
        touch(os.path.join(self.root, "canales", "C", "perfil (Matías's conflicted copy 2026-10-22).json"))
        self.assertEqual(len(cp.conflicts(self.root, "C")), 1)

    def test_artists_validated(self):
        cp.create(self.root, "A")
        saved = cp.save(self.root, "A", dict(cp.load(self.root, "A"), artistas=[" Juice WRLD ", ""]))
        self.assertEqual(saved["artistas"], ["Juice WRLD"])
        with self.assertRaises(cp.ProfileError):
            cp.save(self.root, "A", dict(saved, artistas="Juice WRLD"))

    def test_fit_title_cuts_on_word(self):
        title = cp.fit_title("palabra " * 30)
        self.assertLessEqual(len(title), 100)
        self.assertFalse(title.endswith(" "))
        self.assertEqual(cp.fit_title("corto  |  x"), "corto | x")

    def test_render_tags_dedupes_and_caps_500(self):
        profile = dict(cp.default_profile("C"), tags=["{artist} type beat", "{name} type beat", "{name} TYPE BEAT"]
                       + ["t" * 90] * 10)
        tags = cp.render_tags(profile, {"name": "dark", "artist": "", "channel": "C"})
        self.assertEqual(tags[0], "dark type beat")  # el tag con {artist} vacío se omite
        self.assertLessEqual(len(", ".join(tags)), 500)
        self.assertNotIn("dark TYPE BEAT", tags)


class DropboxLocalTests(unittest.TestCase):
    def test_info_json_then_home_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            box = os.path.join(tmp, "Dropbox (Personal)")
            os.makedirs(box)
            touch(os.path.join(tmp, "app", "Dropbox", "info.json"),
                  json.dumps({"personal": {"path": box}}).encode())
            self.assertEqual(dropbox_local.find_dropbox({"LOCALAPPDATA": os.path.join(tmp, "app")}, tmp), box)
            self.assertIsNone(dropbox_local.find_dropbox({}, tmp))
            os.makedirs(os.path.join(tmp, "Dropbox"))
            self.assertEqual(dropbox_local.default_local_root({}, tmp),
                             os.path.join(tmp, "Dropbox", "TypeBeat Local"))


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = os.path.join(self.tmp.name, "repo")
        self.root = os.path.join(self.tmp.name, "local")
        touch(os.path.join(self.repo, "config", "app_config.json"), json.dumps({
            "name_template": "G {name}",
            "channels": {"Uno": {"groups": ["Principal", "Dark"], "title_template": "U {name}"},
                         "Vacío": {"groups": ["Principal"]}}}).encode())
        touch(os.path.join(self.repo, "images", "Uno", "Principal", "a.jpg"))
        touch(os.path.join(self.repo, "videos", "Uno", "Dark", "v.mp4"))
        touch(os.path.join(self.repo, "images", "Suelto", "principal", "b.png"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_groups_become_channels(self):
        actions = {a["canal"]: a for a in local_migration.plan(self.repo, self.root)}
        self.assertEqual(sorted(actions), ["Suelto", "Uno", "Uno - Dark", "Vacío"])
        self.assertEqual(actions["Uno"]["perfil"]["titulo"], "U {name}")
        self.assertEqual(actions["Uno - Dark"]["perfil"]["fondo"], cp.MODE_VIDEO)
        self.assertEqual(actions["Vacío"]["perfil"]["titulo"], "G {name}")
        self.assertFalse(os.path.exists(self.root))  # plan no escribe

    def test_apply_copies_without_overwriting_and_is_repeatable(self):
        cp.save(self.root, "Uno", dict(cp.default_profile("Uno"), titulo="Ya editado {name}"))
        actions = local_migration.plan(self.repo, self.root)
        result = local_migration.apply(actions, self.root)
        self.assertEqual(result["archivos"], 3)
        self.assertEqual(cp.load(self.root, "Uno")["titulo"], "Ya editado {name}")
        self.assertTrue(os.path.isfile(os.path.join(self.repo, "images", "Uno", "Principal", "a.jpg")))
        again = local_migration.apply(local_migration.plan(self.repo, self.root), self.root)
        self.assertEqual((again["canales"], again["archivos"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
