"""mat produced this one: foto y montaje con las mismas barras negras laterales."""
import json
import unittest
from pathlib import Path

from core.beat_visual import options

PROFILE = Path(__file__).resolve().parents[1] / 'docs' / 'mat-produced-this-one.channel.json'


class MatProducedBarsTests(unittest.TestCase):
    def test_photo_and_video_use_fixed_bars(self):
        spec = options(json.loads(PROFILE.read_text(encoding='utf-8')))
        self.assertEqual(spec['mode'], 'alternate')
        self.assertEqual(spec['image_fit'], 'fixed_bars')
        self.assertEqual(spec['video_fit'], 'fixed_bars')


if __name__ == '__main__':
    unittest.main()
