"""prodbySSJBeatzz Fase D: miniaturas fixed_bars, test A/B 7 con logo / 7 sin logo y rotación de fotos."""
import io
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image, ImageDraw, ImageStat
from core.beat_assets import DropboxAssets, select_image
from core.beat_media_schema import validate_media_state
from core.beat_render import MediaTools, compose
from core.beat_schedule import identity
from core.beat_thumb_logo import (DEFAULT_CORNER, apply_logo, logo_options, place, plan,
                                  upload_index, variant_for)
from core.beat_video import render_reserved
from core.beat_visual import options
from test_beat_video import fixture, AssetsClient, Processes, Resolver, HLS

LOGO = '/logo/ssj-logo.png'
# Franja negra de fixed_bars en la miniatura de 1280 px: 344 * 1280 / 1920.
BAR = round(344 * 1280 / 1920)


def png(image):
    stream = io.BytesIO()
    image.save(stream, 'PNG')
    return stream.getvalue()


def photo(color='#d0d0d0'):
    return Image.new('RGB', (736, 920), color)


def logo_image():
    """Logo de prueba: cromado claro sobre fondo gris oscuro (como el PNG real)."""
    image = Image.new('RGB', (1672, 941), (40, 40, 40))
    ImageDraw.Draw(image).ellipse((300, 250, 1370, 690), outline='white', width=60)
    return image


def mean(picture, box):
    return ImageStat.Stat(picture.crop(box).convert('L')).mean[0]


class GeometryTests(unittest.TestCase):
    def render(self, folder, with_logo, corner=DEFAULT_CORNER):
        root = Path(folder)
        photo('white').save(root / 'photo.jpg')
        logo_image().save(root / 'logo.png')
        thumb = root / 'thumb.jpg'
        compose(root / 'photo.jpg', 'x', root / 'frame.png', thumb, plain=True, fit='fixed_bars')
        if with_logo:
            apply_logo(thumb, root / 'logo.png', corner)
        return Image.open(thumb).convert('RGB')

    def test_bars_and_size_without_logo(self):
        with TemporaryDirectory() as folder:
            picture = self.render(folder, False)
        self.assertEqual(picture.size, (1280, 720))
        self.assertLess(mean(picture, (0, 0, BAR - 2, 720)), 3)
        self.assertLess(mean(picture, (1280 - BAR + 2, 0, 1280, 720)), 3)
        self.assertGreater(mean(picture, (BAR + 2, 0, 1280 - BAR - 2, 720)), 250)

    def test_logo_stays_inside_photo_and_keeps_bars_black(self):
        for corner in ('top_left', 'top_right', 'bottom_left', 'bottom_right'):
            with self.subTest(corner=corner), TemporaryDirectory() as folder:
                photo_dark = Path(folder) / 'dark.jpg'
                photo('black').save(photo_dark)
                logo_image().save(Path(folder) / 'logo.png')
                thumb = Path(folder) / 'thumb.jpg'
                compose(photo_dark, 'x', Path(folder) / 'f.png', thumb, plain=True, fit='fixed_bars')
                apply_logo(thumb, Path(folder) / 'logo.png', corner)
                picture = Image.open(thumb).convert('RGB')
                self.assertEqual(picture.size, (1280, 720))
                # Franjas intactas: el logo no se sale de la foto central.
                self.assertLess(mean(picture, (0, 0, BAR - 2, 720)), 3)
                self.assertLess(mean(picture, (1280 - BAR + 2, 0, 1280, 720)), 3)
                # Fondo gris del PNG -> negro: fuera del cromado la foto negra sigue negra.
                box = picture.convert('L').point(lambda v: 255 if v > 60 else 0).getbbox()
                self.assertGreaterEqual(box[0], BAR)
                self.assertLessEqual(box[2], 1280 - BAR)
                width = box[2] - box[0]
                self.assertTrue(.20 * 1280 <= width <= .26 * 1280, width)
                left = corner.endswith('left')
                self.assertEqual(box[0] < 640, left)
                self.assertEqual(box[1] < 360, corner.startswith('top'))

    def test_screen_blend_does_not_cover_photo(self):
        with TemporaryDirectory() as folder:
            plain = self.render(folder, False)
        with TemporaryDirectory() as folder:
            logo = self.render(folder, True)
        # Foto blanca: en screen el logo no la oscurece fuera de la sombra suave del cromado.
        x, y = place((1280, 720), (307, 173), 'top_left')
        self.assertEqual(plain.getpixel((640, 600)), logo.getpixel((640, 600)))
        self.assertGreater(mean(logo, (x, y, x + 307, y + 173)), 200)

    def test_place_respects_margin_inside_photo(self):
        x, y = place((1280, 720), (300, 150), 'top_left')
        self.assertEqual((x, y), (BAR + 38, 38))
        x, y = place((1280, 720), (300, 150), 'bottom_right')
        self.assertEqual((x + 300, y + 150), (1280 - BAR - 38, 720 - 38))


class CycleTests(unittest.TestCase):
    def test_seven_seven_over_thirty_uploads(self):
        variants = [variant_for(i, [7, 7]) for i in range(30)]
        expected = (['logo'] * 7 + ['sin_logo'] * 7) * 2 + ['logo'] * 2
        self.assertEqual(variants, expected)
        self.assertEqual(variants.count('logo'), 16)

    def test_simulated_uploads_with_retries_are_stable(self):
        state = {'jobs': {}}
        settings = logo_options({'logo': LOGO, 'cycle': [7, 7]})
        seen = []
        for n in range(30):
            job = {'id': 'job%d' % n, 'channel': 'ssj', 'status': 'planned'}
            state['jobs'][job['id']] = job
            # Jobs de otro canal o fallidos no mueven el contador.
            state['jobs']['other%d' % n] = {'id': 'other%d' % n, 'channel': 'otro', 'status': 'uploaded'}
            state['jobs']['failed%d' % n] = {'id': 'failed%d' % n, 'channel': 'ssj', 'status': 'cancelled'}
            first = plan(settings, state, job)
            job['thumbnail_snapshot'] = first
            # Reintento: falla la subida, vuelve a renderizar con más estado y conserva la variante.
            state['jobs']['late%d' % n] = {'id': 'late%d' % n, 'channel': 'ssj', 'status': 'uploaded'}
            self.assertEqual(plan(settings, state, job), first)
            del state['jobs']['late%d' % n]
            job['status'] = 'uploaded'
            seen.append(first)
        self.assertEqual([row['upload_index'] for row in seen], list(range(30)))
        self.assertEqual([row['variant'] for row in seen],
                         [variant_for(i, [7, 7]) for i in range(30)])

    def test_upload_index_counts_only_channel_uploads(self):
        state = {'jobs': {
            'a': {'id': 'a', 'channel': 'ssj', 'status': 'uploaded'},
            'b': {'id': 'b', 'channel': 'ssj', 'status': 'failed'},
            'c': {'id': 'c', 'channel': 'x', 'status': 'uploaded'},
            'd': {'id': 'd', 'channel': 'ssj', 'status': 'planned'}}}
        self.assertEqual(upload_index(state, state['jobs']['d']), 1)

    def test_options_validation(self):
        self.assertEqual(logo_options({'logo': LOGO, 'cycle': [7, 7]}),
                         {'logo': LOGO, 'cycle': [7, 7], 'corner': 'top_left'})
        self.assertIsNone(logo_options(None))
        for raw in ('x', {'cycle': [7, 7]}, {'logo': 'relativo.png'}, {'logo': LOGO, 'cycle': [7]},
                    {'logo': LOGO, 'cycle': [0, 0]}, {'logo': LOGO, 'cycle': [7, '7']},
                    {'logo': LOGO, 'cycle': [True, 7]}, {'logo': LOGO, 'corner': 'centro'},
                    {'logo': LOGO, 'extra': 1}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                logo_options(raw)

    def test_channel_profile_of_phase_d(self):
        profile = json.loads(Path('docs/prodbyssjbeatzz.channel.json').read_text(encoding='utf-8'))
        spec = options(profile)
        self.assertEqual(spec['thumbnail_logo']['cycle'], [7, 7])
        self.assertEqual(spec['thumbnail_logo']['logo'], spec['intro']['logo'])
        self.assertEqual(spec['image_fit'], 'fixed_bars')
        self.assertEqual(spec['thumbnail_source'], 'auto')
        self.assertTrue(spec['custom_thumbnail'])
        self.assertIn('melodic', profile['dropbox_images'])

    def test_snapshot_schema(self):
        good = {'variant': 'logo', 'upload_index': 3, 'image': '/a/b.jpg'}
        validate_media_state({'jobs': {'j': {'thumbnail_snapshot': good}}})
        for bad in ({'variant': 'otro', 'upload_index': 0}, {'variant': 'logo', 'upload_index': -1},
                    {'variant': 'logo', 'upload_index': True}, dict(good, extra=1), 'logo'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_media_state({'jobs': {'j': {'thumbnail_snapshot': bad}}})


class FakeImages:
    def __init__(self, count):
        self.rows = [{'path': '/fotos/foto-%02d.jpg' % i, 'rev': 'r%d' % i, 'size': 10}
                     for i in range(1, count + 1)]

    def list_images(self, folder):
        return list(self.rows)


class RotationTests(unittest.TestCase):
    def test_twenty_nine_photos_without_repeat(self):
        channel = {'id': 'ssj', 'genres': ['melodic'], 'dropbox_images': {'melodic': '/fotos'}}
        state = {'jobs': {}, 'image_rotation': {'ssj': {'melodic': []}}}
        history = state['image_rotation']['ssj']['melodic']
        dropbox, picked = FakeImages(29), []
        for n in range(60):
            job = {'id': 'job%d' % n, 'channel': 'ssj', 'track_id': 'TK%d' % n, 'status': 'planned'}
            row = select_image(channel, 'melodic', state, job, dropbox)
            # Reintento del mismo job: misma foto.
            history.append({'job_id': job['id'], 'path': row['path'], 'rev': row['rev']})
            self.assertEqual(select_image(channel, 'melodic', state, job, dropbox), row)
            picked.append(row['path'])
        self.assertEqual(len(set(picked[:29])), 29)
        self.assertEqual(picked[29:58], picked[:29])
        self.assertEqual(len(set(picked[29:58])), 29)


class RenderTests(unittest.TestCase):
    def run_render(self, prior_uploads=0, frozen=None):
        cloud, key, track, channel = fixture()
        state, _ = cloud.read('state')
        for n in range(prior_uploads):
            tid, slot = 'TK%d' % (200 + n), '2026-10-%02dT18:00:00-03:00' % (1 + n)
            other = identity(tid, 'channel', 1, slot)
            state['jobs'][other] = {'id': other, 'track_id': tid, 'channel': 'channel', 'cycle': 1,
                                    'slot': slot, 'status': 'uploaded', 'video_id': 'vid%05d' % n,
                                    'uploaded_at': slot}
        if frozen:
            state['jobs'][key]['thumbnail_snapshot'] = frozen
        cloud.write('state', state, cloud.read('state')[1])
        channel['visual'] = {'mode': 'image', 'plain_image': True, 'image_fit': 'fixed_bars',
                             'thumbnail_logo': {'logo': LOGO, 'cycle': [7, 7]}}
        client = AssetsClient()
        client.files['/images/trap/a.png'] = png(photo('black'))
        del client.files['/images/trap/b.png']
        client.files[LOGO] = png(logo_image())
        with render_reserved(cloud, key, track, channel, 'trap', 'https://www.beatstars.com/fixture',
                             DropboxAssets(client), resolver=Resolver(), http=HLS(),
                             tools=MediaTools('fakeffmpeg', 'fakeprobe', Processes())) as result:
            picture = Image.open(result['thumbnail']).convert('RGB')
            variant = result['thumbnail_variant']
        state, _ = cloud.read('state')
        return picture, variant, state['jobs'][key]['thumbnail_snapshot'], client

    def test_first_upload_gets_logo_and_snapshot(self):
        picture, variant, snapshot, client = self.run_render()
        self.assertEqual(variant, 'logo')
        self.assertEqual(snapshot, {'variant': 'logo', 'upload_index': 0, 'image': '/images/trap/a.png'})
        self.assertIn(LOGO, client.downloads)
        self.assertGreater(mean(picture, (BAR, 0, 640, 360)), 5)
        self.assertLess(mean(picture, (0, 0, BAR - 2, 720)), 3)

    def test_eighth_upload_has_no_logo(self):
        picture, variant, snapshot, client = self.run_render(prior_uploads=7)
        self.assertEqual(variant, 'sin_logo')
        self.assertEqual(snapshot['upload_index'], 7)
        self.assertNotIn(LOGO, client.downloads)
        self.assertLess(mean(picture, (0, 0, 1280, 720)), 3)

    def test_retry_reuses_frozen_variant(self):
        frozen = {'variant': 'logo', 'upload_index': 6, 'image': '/images/trap/a.png'}
        _, variant, snapshot, _ = self.run_render(prior_uploads=9, frozen=frozen)
        self.assertEqual(variant, 'logo')
        self.assertEqual(snapshot, frozen)


if __name__ == '__main__':
    unittest.main()
