"""Título de Loops: solo el nombre del kit, sin la descripción de la tienda."""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.kit_names import short_name


class ShortNameTests(unittest.TestCase):
    def test_store_titles_keep_only_the_kit_name(self):
        cases = {
            'CYPRUS - Melodic House x Reggaeton (Production Suite)': 'CYPRUS',
            'Vertigo - Reggaeton x Latin House (Loop Kit)': 'Vertigo',
            'Lucid Dreams - Uplifting Emotional Guitars (Loop Kit) !': 'Lucid Dreams',
            '999 - Emotional Guitars (Production Suite)': '999',
            'Cold Summer (Loop Kit)': 'Cold Summer',
            'MIDNIGHT': 'MIDNIGHT',
        }
        for full, expected in cases.items():
            with self.subTest(full=full):
                self.assertEqual(short_name(full), expected)

    def test_empty_or_only_description_falls_back(self):
        self.assertEqual(short_name(''), '')
        self.assertEqual(short_name('(Loop Kit)'), '(Loop Kit)')


if __name__ == '__main__':
    unittest.main()
