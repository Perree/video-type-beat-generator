"""Kits nuevos de Dropbox que entran solos a la rueda del canal que corresponde."""
import os
import random
import sys
import unittest
from datetime import datetime
from unittest import mock

from core import kit_autoadd, kit_cloud, kit_week

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'scripts'))
import run_kit_weekly  # noqa: E402

LINK = 'https://wyresounds.com/b/guitars'
ROOT = '/Tienda'


def pack(name, category='guitarras', loops=4):
    return {'name': name, 'dropbox_path': f'{ROOT}/{category}/{name}', 'category': category,
            'loops': [{'name': f'{i}.wav', 'path': f'/x/{i}.wav'} for i in range(loops)],
            'images': [{'name': 'a.jpg', 'path': '/x/a.jpg', 'source': 'dropbox'}]}


def entry(folder, genre='guitarras', link=LINK, active=True):
    return {'folder': folder, 'name': folder, 'payhip_url': link, 'genre': genre,
            'active': active}


class PickGenreTests(unittest.TestCase):
    def test_single_genre_channel_takes_it(self):
        self.assertEqual(kit_autoadd.pick_genre('Guitar Kits', ['guitarras']), 'guitarras')

    def test_several_genres_match_category_name(self):
        genres = ['guitarras', 'reggaeton house']
        self.assertEqual(kit_autoadd.pick_genre('Reggaeton House', genres), 'reggaeton house')
        self.assertIsNone(kit_autoadd.pick_genre('Otros', genres))

    def test_no_genres_configured(self):
        self.assertEqual(kit_autoadd.pick_genre('lo que sea', None), '')


class NewEntriesTests(unittest.TestCase):
    def test_new_folder_enters_with_channel_link(self):
        added, warnings = kit_autoadd.new_entries(
            [pack('Viejo'), pack('Nuevo')], [entry('Viejo')], ['guitarras'], LINK)
        self.assertEqual(added, [entry('Nuevo')])
        self.assertEqual(len(warnings), 1)
        self.assertNotIn('Nuevo', warnings[0])  # los avisos no llevan nombres

    def test_known_kits_are_untouched_even_inactive_or_without_link(self):
        catalog = [entry('Apagado', active=False), entry('SinLink', link=''),
                   entry(f'{ROOT}/guitarras/PorRuta')]
        added, warnings = kit_autoadd.new_entries(
            [pack('Apagado'), pack('SinLink'), pack('PorRuta')], catalog, ['guitarras'], LINK)
        self.assertEqual((added, warnings), ([], []))

    def test_skips_copies_underscore_and_empty_folders(self):
        packs = [pack('Kit (1)'), pack('_refs'), pack('Vacio', loops=0)]
        self.assertEqual(kit_autoadd.new_entries(packs, [], ['guitarras'], LINK), ([], []))

    def test_without_channel_link_nothing_enters(self):
        added, warnings = kit_autoadd.new_entries([pack('Nuevo')], [], ['guitarras'], '')
        self.assertEqual(added, [])
        self.assertIn('no tiene link', warnings[0])

    def test_unknown_genre_stays_pending(self):
        genres = ['guitarras', 'reggaeton house']
        added, warnings = kit_autoadd.new_entries(
            [pack('G', 'guitarras'), pack('X', 'Otros')], [], genres, LINK)
        self.assertEqual([a['folder'] for a in added], ['G'])
        self.assertTrue(any('no se sabe su género' in w for w in warnings))

    def test_same_name_twice_uses_full_path(self):
        packs = [pack('Dup', 'guitarras'), pack('Dup', 'reggaeton house')]
        added, _ = kit_autoadd.new_entries(packs, [], ['guitarras', 'reggaeton house'], LINK)
        self.assertEqual([a['folder'] for a in added],
                         [p['dropbox_path'] for p in packs])


class PersistTests(unittest.TestCase):
    def test_appends_with_rev_and_keeps_existing(self):
        with mock.patch.object(kit_cloud, 'read_json_rev', return_value=([entry('Viejo')], 'r1')), \
                mock.patch.object(kit_cloud, 'write_json') as write:
            self.assertEqual(kit_autoadd.persist('/k.json', [entry('Nuevo')], ['guitarras']), 1)
        write.assert_called_once_with('/k.json', [entry('Viejo'), entry('Nuevo')], rev='r1',
                                      dbx=None)

    def test_retries_on_conflict_and_skips_already_added(self):
        reads = [([], 'r1'), ([entry('Nuevo', link='https://otro.com/x')], 'r2')]
        with mock.patch.object(kit_cloud, 'read_json_rev', side_effect=reads), \
                mock.patch.object(kit_cloud, 'write_json',
                                  side_effect=kit_cloud.KitCloudConflict()) as write:
            # Al releer, el panel ya lo había cargado con su propio link: no se pisa.
            self.assertEqual(kit_autoadd.persist('/k.json', [entry('Nuevo')]), 0)
        self.assertEqual(write.call_count, 1)

    def test_no_catalog_file_writes_nothing(self):
        with mock.patch.object(kit_cloud, 'read_json_rev', return_value=(None, None)), \
                mock.patch.object(kit_cloud, 'write_json') as write:
            self.assertEqual(kit_autoadd.persist('/k.json', [entry('Nuevo')]), 0)
        write.assert_not_called()


class SaveNewKitsTests(unittest.TestCase):
    def test_dry_run_does_not_write(self):
        with mock.patch.object(kit_autoadd, 'persist') as persist:
            warnings = run_kit_weekly.save_new_kits([entry('N')], {}, None, '/k.json', True)
        persist.assert_not_called()
        self.assertEqual(len(warnings), 1)

    def test_failure_is_a_warning_not_a_crash(self):
        with mock.patch.object(kit_autoadd, 'persist', side_effect=kit_cloud.KitCloudConflict()):
            warnings = run_kit_weekly.save_new_kits([entry('N')], {}, None, '/k.json', False)
        self.assertIn('próxima corrida', warnings[0])

    def test_writes_to_the_channel_catalog(self):
        config = {'kit_preview': {'genres': ['guitarras']}}
        with mock.patch.object(kit_autoadd, 'persist', return_value=1) as persist:
            self.assertEqual(run_kit_weekly.save_new_kits([entry('N')], config, 'dbx',
                                                          '/canal/kits.json', False), [])
        persist.assert_called_once_with('/canal/kits.json', [entry('N')], ['guitarras'],
                                        dbx='dbx')


class OpenWeekTests(unittest.TestCase):
    """Dos canales leen la misma tienda; cada uno solo ve sus categorías."""

    def week(self, genres, scan, catalog, link=LINK):
        store = {'guitarras': [pack('G1'), pack('G-nuevo')],
                 'reggaeton house': [pack('R1', 'reggaeton house'),
                                     pack('R-nuevo', 'reggaeton house')]}
        config = {'kit_preview': {'dropbox_root': ROOT, 'genres': genres, 'scan_folders': scan}}

        def list_packs(root, local_images_root=None, dbx=None, scan=None):
            return [p for cat in scan['scan_folders'] for p in store.get(cat, [])]
        with mock.patch.object(kit_cloud, 'read_json', return_value=catalog):
            return kit_week.open_week(config, {}, [], datetime(2026, 11, 2, 10), random.Random(1),
                                      list_packs_fn=list_packs, channel_link=link)

    def test_guitar_channel_gets_new_guitar_kit(self):
        week = self.week(['guitarras'], ['guitarras'], [entry('G1')])
        self.assertEqual([a['folder'] for a in week['added']], ['G-nuevo'])
        self.assertIn(f'{ROOT}/guitarras/G-nuevo', week['entries'])
        picked = {s['pack']['name'] for s in week['queue']}
        self.assertIn('G-nuevo', picked)
        self.assertNotIn('R-nuevo', picked)

    def test_two_genre_channel_gets_each_kit_with_its_genre(self):
        genres = ['guitarras', 'reggaeton house']
        week = self.week(genres, genres, [entry('G1'), entry('R1', 'reggaeton house')])
        self.assertEqual({a['folder']: a['genre'] for a in week['added']},
                         {'G-nuevo': 'guitarras', 'R-nuevo': 'reggaeton house'})

    def test_without_catalog_nothing_is_added(self):
        week = self.week(['guitarras'], ['guitarras'], None)
        self.assertEqual(week['added'], [])


if __name__ == '__main__':
    unittest.main()
