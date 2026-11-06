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

    def test_fixed_bars_same_geometry_for_every_source_ratio(self):
        spec = options({'visual': {'image_fit': 'fixed_bars', 'plain_image': True}})
        for size in ((600, 1000), (1000, 1000), (1600, 900), (900, 1600)):
            with self.subTest(size=size), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                Image.new('RGB', size, (220, 30, 30)).save(root / 'source.png')
                compose(root / 'source.png', 'Beat', root / 'frame.png', root / 'thumb.jpg',
                        plain=spec['plain_image'], fit=spec['image_fit'])
                with Image.open(root / 'frame.png') as frame:
                    self.assertEqual(frame.size, (1920, 1080))
                    self.assertEqual(frame.getbbox(), (344, 0, 1576, 1080))
                with Image.open(root / 'thumb.jpg') as thumb:
                    self.assertEqual(thumb.size, (1280, 720))
                    self.assertLess(max(thumb.getpixel((220, 360))), 5)
                    self.assertGreater(thumb.getpixel((240, 360))[0], 180)
                    self.assertGreater(thumb.getpixel((1040, 360))[0], 180)
                    self.assertLess(max(thumb.getpixel((1060, 360))), 5)

    def test_fixed_bars_crops_symmetrically_without_stretching(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            # At native height, centered crop removes 344 px from both sides.
            source = Image.new('RGB', (1920, 1080), 'red')
            source.paste('blue', (344, 0, 1576, 1080))
            source.save(root / 'source.png')
            compose(root / 'source.png', 'Beat', root / 'frame.png', root / 'thumb.jpg',
                    plain=True, fit='fixed_bars')
            with Image.open(root / 'frame.png') as frame:
                self.assertEqual(frame.getpixel((344, 0)), (0, 0, 255))
                self.assertEqual(frame.getpixel((1575, 1079)), (0, 0, 255))


if __name__ == '__main__':
    unittest.main()
