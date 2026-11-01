"""Portada sin IA: un fallo de la API de imágenes nunca deja la corrida sin videos."""
import os
import random
import tempfile
import unittest
from datetime import datetime
from unittest import mock

from PIL import Image

from core import dropbox_client, kit_art, kit_spend

NOW = datetime(2026, 10, 31, 12, 0)
ROOT = '/kits/_referencias'


def _entries(folder, names):
    return [{'name': n, 'path': f'{folder}/{n}', 'is_folder': False} for n in names]


def _fake_fetch(color=(200, 40, 40)):
    calls = []

    def fetch(paths, dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
        out = []
        for i, _ in enumerate(paths):
            path = os.path.join(dest_dir, f'r{i}.png')
            Image.new('RGB', (300, 200), color).save(path)
            out.append(path)
        calls.append(list(paths))
        return out
    return fetch, calls


def _failing_client(prompt, images, cfg):
    error = kit_art.KitArtError('HTTP 429')
    error.billable = False
    raise error


class FreeBackgroundTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def cfg(self, mode='auto'):
        return {'cover_mode': mode, 'art': {'refs_root': ROOT, 'genre': 'reggaeton house'}}

    def test_uses_reference_of_genre(self):
        folder = ROOT + '/reggaeton_house'
        fetch, calls = _fake_fetch()
        with mock.patch.object(dropbox_client, 'list_folder_entries',
                               return_value=_entries(folder, ['a.jpg', 'b.png'])):
            path, refs = kit_art.free_background(self.cfg(), None, random.Random(1),
                                                 self.tmp.name, now=NOW, fetch=fetch)
        self.assertEqual(len(refs), 1)
        self.assertTrue(refs[0].startswith(folder + '/'))
        self.assertEqual(calls, [refs])
        with Image.open(path) as img:
            self.assertEqual(img.size, (kit_art.FREE_SIZE, kit_art.FREE_SIZE))
            # Oscurecida: el centro queda más oscuro que el rojo original.
            self.assertLess(img.getpixel((512, 512))[0], 200)

    def test_skips_reference_used_recently(self):
        folder = ROOT + '/reggaeton_house'
        store = mock.Mock(ref_usage=lambda: {f'{folder}/a.jpg': NOW.isoformat()})
        fetch, _ = _fake_fetch()
        with mock.patch.object(dropbox_client, 'list_folder_entries',
                               return_value=_entries(folder, ['a.jpg', 'b.png'])):
            _, refs = kit_art.free_background(self.cfg(), store, random.Random(1),
                                              self.tmp.name, now=NOW, fetch=fetch)
        self.assertEqual(refs, [f'{folder}/b.png'])

    def test_prefers_backgrounds_folder(self):
        folder = ROOT + '/reggaeton_house'
        seen = []

        def listing(path, dbx=None):
            seen.append(path)
            if path.endswith('/fondos'):
                return _entries(path, ['fondo.jpg'])
            return [{'name': 'fondos', 'path': folder + '/fondos', 'is_folder': True},
                    *_entries(path, ['ref.jpg'])]
        fetch, _ = _fake_fetch()
        for mode in ('template', 'auto', 'dropbox'):
            seen.clear()
            with mock.patch.object(dropbox_client, 'list_folder_entries', side_effect=listing):
                _, refs = kit_art.free_background(self.cfg(mode), None, random.Random(1),
                                                  self.tmp.name, now=NOW, fetch=fetch)
            self.assertEqual(seen, [folder, folder + '/fondos'])
            self.assertEqual(refs, [folder + '/fondos/fondo.jpg'])

    def test_empty_backgrounds_folder_falls_back_to_genre_folder(self):
        folder = ROOT + '/reggaeton_house'

        def listing(path, dbx=None):
            if path.endswith('/fondos'):
                return []
            return [{'name': 'Fondos', 'path': folder + '/Fondos', 'is_folder': True},
                    *_entries(path, ['ref.jpg'])]
        fetch, _ = _fake_fetch()
        with mock.patch.object(dropbox_client, 'list_folder_entries', side_effect=listing):
            _, refs = kit_art.free_background(self.cfg(), None, random.Random(1),
                                              self.tmp.name, now=NOW, fetch=fetch)
        self.assertEqual(refs, [folder + '/ref.jpg'])

    def test_image_is_used_sharp(self):
        """La imagen de Dropbox va tal cual: sin desenfoque, solo recortada y con viñeta."""
        folder = ROOT + '/reggaeton_house'

        def fetch(paths, dest_dir):
            os.makedirs(dest_dir, exist_ok=True)
            img = Image.new('RGB', (400, 400), (0, 0, 0))
            for x in range(0, 400, 2):            # rayas finas: un desenfoque las borraría
                for y in range(400):
                    img.putpixel((x, y), (255, 255, 255))
            path = os.path.join(dest_dir, 'r.png')
            img.save(path)
            return [path]
        with mock.patch.object(dropbox_client, 'list_folder_entries',
                               return_value=_entries(folder, ['a.jpg'])):
            path, _ = kit_art.dropbox_image(self.cfg('dropbox'), None, random.Random(1),
                                            self.tmp.name, now=NOW, fetch=fetch)
        with Image.open(path) as img:
            row = [img.getpixel((x, 512))[0] for x in range(500, 524)]
        self.assertGreater(max(row) - min(row), 100)

    def test_dropbox_image_without_config_or_images(self):
        self.assertEqual(kit_art.dropbox_image({'cover_mode': 'dropbox'}, None,
                                               random.Random(1), self.tmp.name), (None, []))
        with mock.patch.object(dropbox_client, 'list_folder_entries', return_value=[]):
            self.assertEqual(kit_art.dropbox_image(self.cfg('dropbox'), None, random.Random(1),
                                                   self.tmp.name), (None, []))

    def test_gradient_when_no_images_or_dropbox_fails(self):
        for listing in ([], OSError('dropbox caído')):
            kw = {'return_value': listing} if isinstance(listing, list) else {'side_effect': listing}
            with mock.patch.object(dropbox_client, 'list_folder_entries', **kw):
                path, refs = kit_art.free_background(self.cfg(), None, random.Random(2),
                                                     self.tmp.name, now=NOW)
            self.assertEqual(refs, [])
            with Image.open(path) as img:
                self.assertEqual(img.size, (kit_art.FREE_SIZE, kit_art.FREE_SIZE))
                self.assertGreater(len(img.resize((32, 32)).getcolors(4096)), 10)

    def test_gradient_without_config(self):
        path, refs = kit_art.free_background({'cover_mode': 'auto'}, None, random.Random(3),
                                             self.tmp.name)
        self.assertTrue(os.path.exists(path))
        self.assertEqual(refs, [])

    def test_unknown_genre_has_stable_colors(self):
        self.assertEqual(kit_art.genre_colors('trap oscuro'), kit_art.genre_colors('Trap  Oscuro'))
        self.assertNotEqual(kit_art.genre_colors('trap oscuro'), kit_art.genre_colors('drill'))


class ForCoverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_api_failure_without_kit_image_still_gives_cover(self):
        cfg = {'cover_mode': 'auto', 'art': {'refs_root': ROOT, 'genre': 'guitarras'}}
        folder = ROOT + '/guitarras'
        notes = []
        budget = kit_spend.Budget({}, None, NOW)
        with mock.patch.object(dropbox_client, 'list_folder_entries',
                               return_value=_entries(folder, ['x.jpg'])), \
                mock.patch.object(kit_art.kit_source, 'download_pack_files',
                                  side_effect=lambda paths, dest, dbx=None: _fake_fetch()[0](paths, dest)):
            results = [kit_art.for_cover(cfg, 'Kit', 'Titulo', None, None, random.Random(i),
                                         os.path.join(self.tmp.name, str(i)),
                                         client=_failing_client, notify=notes.append,
                                         now=NOW, budget=budget) for i in range(2)]
        for path, refs, complete in results:
            self.assertTrue(path and os.path.exists(path))
            self.assertEqual(refs, [folder + '/x.jpg'])
            self.assertFalse(complete)
        # El aviso por Telegram sale una sola vez por corrida, no uno por video.
        self.assertEqual(len(notes), 1)

    def _fetch_patch(self):
        return mock.patch.object(
            kit_art.kit_source, 'download_pack_files',
            side_effect=lambda paths, dest, dbx=None: _fake_fetch()[0](paths, dest))

    def test_dropbox_mode_never_calls_ai_and_rotates(self):
        cfg = {'cover_mode': 'dropbox', 'art': {'refs_root': ROOT, 'genre': 'guitarras'}}
        folder = ROOT + '/guitarras'
        used = {}
        store = mock.Mock(ref_usage=lambda: dict(used))

        def no_ai(*_a, **_k):
            raise AssertionError('no debe llamar a la IA')
        with mock.patch.object(dropbox_client, 'list_folder_entries',
                               return_value=_entries(folder, ['a.jpg', 'b.jpg', 'c.jpg'])), \
                self._fetch_patch():
            picked = []
            for i in range(3):
                path, refs, complete = kit_art.for_cover(
                    cfg, 'Kit', 'T', '/tmp/kit.png', store, random.Random(i),
                    os.path.join(self.tmp.name, str(i)), client=no_ai, now=NOW)
                self.assertTrue(os.path.exists(path))
                self.assertFalse(complete)
                used[refs[0]] = NOW.isoformat()
                picked.append(refs[0])
        self.assertEqual(len(set(picked)), 3)   # no repite mientras haya otras
        self.assertTrue(kit_art.generates(cfg))

    def test_api_failure_prefers_dropbox_over_kit_image(self):
        cfg = {'cover_mode': 'auto', 'art': {'refs_root': ROOT, 'genre': 'guitarras'}}
        folder = ROOT + '/guitarras'
        with mock.patch.object(dropbox_client, 'list_folder_entries',
                               return_value=_entries(folder, ['x.jpg'])), self._fetch_patch():
            path, refs, _ = kit_art.for_cover(
                cfg, 'Kit', 'T', '/tmp/kit.png', None, random.Random(1), self.tmp.name,
                client=_failing_client, notify=lambda _: None, now=NOW,
                budget=kit_spend.Budget({}, None, NOW))
        self.assertNotEqual(path, '/tmp/kit.png')
        self.assertEqual(refs, [folder + '/x.jpg'])

    def test_manual_kit_image_still_wins(self):
        cfg = {'cover_mode': 'auto', 'art': {}}
        got = kit_art.for_cover(cfg, 'Kit', 'T', '/tmp/kit.png', None, random.Random(1),
                                self.tmp.name, notify=lambda _: None, now=NOW)
        self.assertEqual(got, ('/tmp/kit.png', [], False))

    def test_manual_mode_without_image_is_unchanged(self):
        got = kit_art.for_cover({}, 'Kit', 'T', None, None, random.Random(1), self.tmp.name)
        self.assertEqual(got, (None, [], False))


if __name__ == '__main__':
    unittest.main()
