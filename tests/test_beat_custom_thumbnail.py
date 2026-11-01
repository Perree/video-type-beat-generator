"""Canal sin miniatura propia: no se llama a thumbnails.set (falla en canales sin verificar)."""
import unittest

from core.beat_daily import channel_thumbnailer
from core.beat_visual import options


def thumbnailer(*_):
    raise AssertionError('no se debería llamar')


class CustomThumbnailTests(unittest.TestCase):
    def test_default_keeps_thumbnailer(self):
        self.assertIs(channel_thumbnailer({'visual': {}}, thumbnailer), thumbnailer)

    def test_off_skips_thumbnailer(self):
        channel = {'visual': {'custom_thumbnail': False}}
        self.assertIsNone(channel_thumbnailer(channel, thumbnailer))

    def test_value_must_be_bool(self):
        with self.assertRaises(ValueError):
            options({'visual': {'custom_thumbnail': 'no'}})


if __name__ == '__main__':
    unittest.main()
