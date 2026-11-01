"""Foto vertical entera con barras negras (image_fit='contain') o recortada ('cover')."""
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from core.beat_render import compose
from core.beat_visual import options


class ImageFitTests(unittest.TestCase):
    def render(self, fit):
        tmp = Path(tempfile.mkdtemp())
        Image.new('RGB', (600, 1000), (220, 30, 30)).save(tmp / 'v.jpg', 'JPEG')
        compose(tmp / 'v.jpg', 'Night Love', tmp / 'f.png', tmp / 't.jpg', plain=True, fit=fit)
        return Image.open(tmp / 'f.png').convert('RGB')

    def test_contain_keeps_whole_photo_with_black_bars(self):
        frame = self.render('contain')
        self.assertEqual(frame.size, (1920, 1080))
        self.assertEqual(frame.getpixel((20, 540)), (0, 0, 0))       # barra izquierda
        self.assertEqual(frame.getpixel((1900, 540)), (0, 0, 0))     # barra derecha
        self.assertGreater(frame.getpixel((960, 540))[0], 180)       # foto al centro

    def test_cover_fills_the_frame(self):
        frame = self.render('cover')
        self.assertGreater(frame.getpixel((20, 540))[0], 180)

    def test_invalid_fit_is_rejected(self):
        with self.assertRaises(ValueError):
            options({'visual': {'image_fit': 'stretch'}})


if __name__ == '__main__':
    unittest.main()
