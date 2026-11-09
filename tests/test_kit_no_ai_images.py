"""Portadas de Loops sin IA: auto y template usan una foto de Dropbox y nunca llaman a la API."""
import os
import random
import sys
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_art, kit_template_art


class NoAiImagesTests(unittest.TestCase):
    def test_switch_is_off(self):
        self.assertFalse(kit_art.AI_IMAGES_ENABLED)

    def test_ai_modes_use_dropbox_photo_without_calling_the_api(self):
        def forbidden(*args, **kwargs):
            raise AssertionError('no se debe generar ninguna imagen con IA')
        for current in ('auto', 'template'):
            with self.subTest(mode=current), \
                    mock.patch.object(kit_art, 'for_video', forbidden), \
                    mock.patch.object(kit_template_art, 'for_video', forbidden), \
                    mock.patch.object(kit_art, 'dropbox_image',
                                      return_value=('/tmp/foto.jpg', [{'path': '/fondos/foto.jpg'}])):
                path, refs, complete = kit_art.for_cover(
                    {'cover_mode': current, 'art': {'refs_root': '/refs', 'genre': 'guitarras'}},
                    'Kit', 'Kit', None, store=None, rng=random.Random(1), work_dir='/tmp')
                self.assertEqual(path, '/tmp/foto.jpg')
                self.assertFalse(complete)


if __name__ == '__main__':
    unittest.main()
