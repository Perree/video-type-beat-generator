"""ey mat Fase 2: miniatura estilo Taigen (Parental Advisory, firma en cursiva, grano/viñeta)."""
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image, ImageStat
from core.beat_assets import DropboxAssets
from core.beat_media_schema import validate_media_state
from core.beat_render import MediaTools, compose
from core.beat_thumb_badges import (ADVISORY_SHARE, DEFAULTS, advisory_label, apply_badges,
                                    badge_options, signature_layer, texture)
from core.beat_thumb_logo import place
from core.beat_video import render_reserved
from core.beat_visual import options
from test_beat_video import fixture, AssetsClient, Processes, Resolver, HLS

BAR = round(344 * 1280 / 1920)
DOC = Path('docs/ey-mat.thumbnail.json')


def png(image):
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def mean(picture, box):
    return ImageStat.Stat(picture.crop(box).convert('L')).mean[0]


def render(folder, color, settings):
    root = Path(folder)
    Image.new('RGB', (736, 920), color).save(root / 'photo.jpg')
    thumb = root / 'thumb.jpg'
    compose(root / 'photo.jpg', 'x', root / 'frame.png', thumb, plain=True, fit='fixed_bars')
    apply_badges(thumb, settings)
    return Image.open(thumb).convert('RGB')


class OptionTests(unittest.TestCase):
    def test_defaults_and_overrides(self):
        self.assertEqual(badge_options({}), DEFAULTS)
        self.assertEqual(badge_options({'signature': '', 'grain': 0})['grain'], 0.0)
        self.assertFalse(badge_options({'advisory': False})['advisory'])

    def test_rejects_bad_values(self):
        for raw in (None, 'x', {'extra': 1}, {'advisory': 1}, {'signature': 5}, {'signature': 'x' * 31},
                    {'signature': 'a\nb'}, {'font': 'arial'}, {'grain': -.1}, {'grain': .5},
                    {'vignette': True}, {'vignette': '0.3'}, {'vignette': .9}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                badge_options(raw)

    def test_visual_options_validate_key(self):
        spec = options({'visual': {'thumbnail_badges': {'signature': 'ey mat'}}})
        self.assertEqual(spec['thumbnail_badges'], DEFAULTS)
        with self.assertRaises(ValueError):
            options({'visual': {'thumbnail_badges': {'font': 'comic'}}})

    def test_phase_six_block(self):
        block = json.loads(DOC.read_text(encoding='utf-8'))
        spec = options({'visual': block})
        self.assertEqual(spec['image_fit'], 'fixed_bars')
        self.assertEqual(spec['thumbnail_source'], 'auto')
        self.assertTrue(spec['custom_thumbnail'])
        self.assertTrue(spec['plain_image'])
        self.assertEqual(spec['thumbnail_badges']['font'], 'great_vibes')
        self.assertEqual(spec['thumbnail_badges']['signature'], 'ey mat')

    def test_snapshot_schema(self):
        for good in ({'image': '/a.jpg', 'badges': DEFAULTS},
                     {'variant': 'logo', 'upload_index': 2, 'image': '/a.jpg', 'badges': DEFAULTS}):
            validate_media_state({'jobs': {'j': {'thumbnail_snapshot': good}}})
        for bad in ({'image': '/a.jpg'}, {'badges': {'grain': 2}}, {'badges': {}},
                    {'badges': DEFAULTS, 'upload_index': 1}, {'badges': DEFAULTS, 'extra': 1}):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_media_state({'jobs': {'j': {'thumbnail_snapshot': bad}}})


class DrawingTests(unittest.TestCase):
    def test_advisory_label_is_black_and_white(self):
        label = advisory_label(154)
        self.assertEqual(label.size, (154, 92))
        gray = label.convert('L')
        self.assertGreater(gray.getpixel((1, 1)), 240)          # borde blanco
        self.assertLess(gray.getpixel((10, 8)), 20)              # fondo negro arriba
        self.assertGreater(mean(label, (12, 31, 142, 33)), 230)  # banda blanca de ADVISORY

    def test_signature_is_white_on_transparent(self):
        layer = signature_layer('ey mat', 'great_vibes', 54)
        self.assertEqual(layer.mode, 'RGBA')
        self.assertEqual(layer.getpixel((0, 0))[3], 0)
        self.assertGreater(layer.width, layer.height)

    def test_texture_keeps_bars_black_and_is_deterministic(self):
        picture = Image.new('RGB', (1280, 720), 'black')
        picture.paste(Image.new('RGB', (1280 - 2 * BAR, 720), (128, 128, 128)), (BAR, 0))
        first, second = texture(picture, .035, .35), texture(picture, .035, .35)
        self.assertEqual(first.tobytes(), second.tobytes())
        self.assertEqual(mean(first, (0, 0, BAR - 1, 720)), 0)
        self.assertLess(mean(first, (BAR, 0, BAR + 30, 30)), mean(first, (610, 330, 670, 390)))
        self.assertEqual(texture(picture, 0, 0).tobytes(), picture.tobytes())


class GeometryTests(unittest.TestCase):
    def test_badges_stay_inside_photo(self):
        with TemporaryDirectory() as folder:
            picture = render(folder, 'black', badge_options({'grain': 0, 'vignette': 0}))
        self.assertEqual(picture.size, (1280, 720))
        self.assertLess(mean(picture, (0, 0, BAR - 2, 720)), 3)
        self.assertLess(mean(picture, (1280 - BAR + 2, 0, 1280, 720)), 3)
        box = picture.convert('L').point(lambda v: 255 if v > 60 else 0).getbbox()
        self.assertGreaterEqual(box[0], BAR)
        self.assertLessEqual(box[2], 1280 - BAR)

    def test_advisory_bottom_left_and_signature_top_right(self):
        with TemporaryDirectory() as folder:
            picture = render(folder, 'black', badge_options({'grain': 0, 'vignette': 0}))
        size = (round(1280 * ADVISORY_SHARE), round(1280 * ADVISORY_SHARE * .6))
        x, y = place((1280, 720), size, 'bottom_left')
        self.assertGreater(mean(picture, (x, y, x + size[0], y + size[1])), 60)
        self.assertGreater(mean(picture, (640, 0, 1280 - BAR, 120)), 3)  # firma
        self.assertLess(mean(picture, (BAR, 0, 640, 120)), 3)
        self.assertLess(mean(picture, (640, 600, 1280 - BAR, 720)), 3)

    def test_disabled_badges_only_texture(self):
        settings = badge_options({'advisory': False, 'signature': '', 'grain': 0, 'vignette': 0})
        with TemporaryDirectory() as folder:
            picture = render(folder, 'black', settings)
        self.assertLess(mean(picture, (0, 0, 1280, 720)), 2)


class RenderTests(unittest.TestCase):
    def run_render(self, frozen=None, logo=False):
        cloud, key, track, channel = fixture()
        state, _ = cloud.read('state')
        if frozen:
            state['jobs'][key]['thumbnail_snapshot'] = frozen
        cloud.write('state', state, cloud.read('state')[1])
        channel['visual'] = {'mode': 'image', 'plain_image': True, 'image_fit': 'fixed_bars',
                             'thumbnail_badges': {'grain': 0, 'vignette': 0}}
        client = AssetsClient()
        client.files['/images/trap/a.png'] = png(Image.new('RGB', (736, 920), 'black'))
        del client.files['/images/trap/b.png']
        if logo:
            from test_beat_thumb_logo import LOGO, logo_image
            channel['visual']['thumbnail_logo'] = {'logo': LOGO, 'cycle': [7, 7]}
            client.files[LOGO] = png(logo_image())
        with render_reserved(cloud, key, track, channel, 'trap', 'https://www.beatstars.com/fixture',
                             DropboxAssets(client), resolver=Resolver(), http=HLS(),
                             tools=MediaTools('fakeffmpeg', 'fakeprobe', Processes())) as result:
            picture = Image.open(result['thumbnail']).convert('RGB')
            variant = result['thumbnail_variant']
        state, _ = cloud.read('state')
        return picture, variant, state['jobs'][key]['thumbnail_snapshot']

    def test_badges_applied_and_frozen(self):
        picture, variant, snapshot = self.run_render()
        self.assertIsNone(variant)
        expected = badge_options({'grain': 0, 'vignette': 0})
        self.assertEqual(snapshot, {'image': '/images/trap/a.png', 'badges': expected})
        self.assertGreater(mean(picture, (BAR, 520, 640, 720)), 5)

    def test_retry_reuses_frozen_badges(self):
        frozen = {'image': '/images/trap/a.png',
                  'badges': badge_options({'advisory': False, 'signature': '', 'grain': 0, 'vignette': 0})}
        picture, _, snapshot = self.run_render(frozen=frozen)
        self.assertEqual(snapshot, frozen)
        self.assertLess(mean(picture, (0, 0, 1280, 720)), 2)

    def test_combines_with_logo_test(self):
        _, variant, snapshot = self.run_render(logo=True)
        self.assertEqual(variant, 'logo')
        self.assertEqual(snapshot['variant'], 'logo')
        self.assertIn('badges', snapshot)


if __name__ == '__main__':
    unittest.main()
