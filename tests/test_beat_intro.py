"""Fase B prodbySSJBeatzz: intro con logo, video_fit=fixed_bars y duración total."""
import json
import math
import struct
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from PIL import Image, ImageDraw
from core.beat_film_overlay import normalize_filter
from core.beat_intro import cached_intro, intro_options, prepared_logo, frame_count, LOGO_SHARE
from core.beat_montage import render_montage
from core.beat_render import MediaTools
from core.beat_visual import options, video_catalog
from core.ffmpeg_util import resolve_tool

FFMPEG, FFPROBE = resolve_tool('ffmpeg'), resolve_tool('ffprobe')
LOGO = '/Soft Projects/Type Beat Generator/contenido/canales/prodbyssjbeatzz/logo/ssj-logo.png'
needs_ffmpeg = unittest.skipUnless(FFMPEG and FFPROBE, 'ffmpeg no disponible')


def make_logo(path):
    """Logo de prueba: cromado claro sobre fondo gris oscuro texturado (como el real)."""
    image = Image.new('RGB', (1600, 900), (45, 45, 45))
    draw = ImageDraw.Draw(image)
    draw.ellipse((200, 250, 1400, 650), outline=(235, 235, 235), width=30)
    draw.rectangle((600, 380, 1000, 520), fill=(250, 250, 250))
    image.save(path)


def probe(path):
    return json.loads(subprocess.run([FFPROBE, '-v', 'error', '-show_entries',
        'format=duration:stream=codec_type,width,height,avg_frame_rate,nb_frames,start_time',
        '-of', 'json', str(path)], capture_output=True, check=True).stdout)


def frame_at(path, seconds, target):
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-ss', str(seconds), '-i', str(path),
                    '-frames:v', '1', str(target)], check=True)
    return Image.open(target).convert('L')


def source_clip(path, color, seconds=6, size='1280x720'):
    subprocess.run([FFMPEG, '-v', 'error', '-y', '-f', 'lavfi', '-i',
                    f'color=c={color}:s={size}:r=30:d={seconds}', '-c:v', 'libx264',
                    '-pix_fmt', 'yuv420p', str(path)], check=True)


def tone(path, seconds):
    with wave.open(str(path), 'wb') as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(22050)
        out.writeframes(b''.join(struct.pack('<h', int(8000 * math.sin(i / 10)))
                                 for i in range(int(22050 * seconds))))


def strip_mean(image, box):
    pixels = list(image.crop(box).get_flattened_data())
    return sum(pixels) / len(pixels)


class IntroOptionsTests(unittest.TestCase):
    def test_valid_profile_and_whole_frames(self):
        self.assertEqual(intro_options({'logo': LOGO, 'seconds': 3.5}), {'logo': LOGO, 'seconds': 3.5})
        self.assertEqual(intro_options({'logo': LOGO, 'seconds': 3.51})['seconds'], 105 / 30)
        self.assertIsNone(intro_options(None))

    def test_invalid_intro_rejected(self):
        for raw in ({'seconds': 3.5}, {'logo': LOGO, 'seconds': 0.5}, {'logo': LOGO, 'seconds': 20},
                    {'logo': LOGO, 'seconds': True}, {'logo': LOGO, 'extra': 1}, 'logo.png',
                    {'logo': 'sin/barra.png', 'seconds': 3.5}):
            with self.assertRaises(ValueError, msg=raw):
                intro_options(raw)

    def test_profile_fields_of_phase_b(self):
        profile = json.loads(Path('docs/prodbyssjbeatzz.channel.json').read_text(encoding='utf-8'))
        # Solo los campos de B (thumbnail_logo e image_fit se prueban en test_beat_thumb_logo).
        visual = {k: v for k, v in profile['visual'].items() if k not in ('thumbnail_source', 'thumbnail_logo')}
        spec = options({'visual': visual})
        self.assertEqual(spec['video_fit'], 'fixed_bars')
        self.assertEqual(spec['intro'], {'logo': LOGO, 'seconds': 3.5})
        # Los segmentos de Dropbox duran 12 s y ya vienen sin bordes: el recorte no puede comérselos.
        self.assertLessEqual(2 * spec['source_trim_seconds'] + spec['clip_max_seconds'], 12)
        with self.assertRaises(ValueError):
            options({'visual': {'video_fit': 'bars'}})

    def test_fixed_bars_filter_geometry(self):
        graph = normalize_filter('fixed_bars')
        self.assertIn('crop=1232:1080', graph)
        self.assertIn('pad=1920:1080:344:0:color=black', graph)
        self.assertEqual(344 * 2 + 1232, 1920)


@needs_ffmpeg
class IntroRenderTests(unittest.TestCase):
    def test_logo_is_cleaned_and_sized(self):
        with tempfile.TemporaryDirectory() as folder:
            logo = Path(folder) / 'logo.png'
            make_logo(logo)
            image = prepared_logo(logo)
            self.assertAlmostEqual(image.width / 1920, LOGO_SHARE, delta=.01)
            self.assertEqual(image.getpixel((2, 2)), (0, 0, 0))  # fondo gris -> negro puro

    def test_intro_geometry_animation_and_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            logo = root / 'logo.png'
            make_logo(logo)
            tools = MediaTools()
            intro = cached_intro('prodbyssjbeatzz', logo, 3.5, tools, cache=root / 'cache')
            info = probe(intro)
            video = info['streams'][0]
            self.assertEqual(len(info['streams']), 1)
            self.assertEqual((video['width'], video['height'], video['avg_frame_rate']), (1920, 1080, '30/1'))
            self.assertEqual(int(video['nb_frames']), frame_count(3.5))
            start = frame_at(intro, 0, root / 'a.png')
            sharp = frame_at(intro, 2.0, root / 'b.png')
            # Entra oscuro/desenfocado y queda nítido: más contraste al final.
            self.assertLess(max(start.get_flattened_data()), max(sharp.get_flattened_data()))
            self.assertGreater(max(sharp.get_flattened_data()), 200)
            self.assertLess(strip_mean(sharp, (0, 0, 200, 1080)), 3)
            # Cacheada: la segunda llamada no vuelve a codificar.
            calls = []
            spy = MediaTools(run=lambda *a, **k: calls.append(a) or subprocess.run(*a, **k))
            self.assertEqual(cached_intro('prodbyssjbeatzz', logo, 3.5, spy, cache=root / 'cache'), intro)
            self.assertEqual(calls, [])
            make_logo(logo)
            Image.open(logo).rotate(180).save(logo)  # logo distinto -> otra entrada de caché
            self.assertNotEqual(cached_intro('prodbyssjbeatzz', logo, 3.5, tools, cache=root / 'cache'), intro)

    def test_intro_plus_montage_keeps_beat_length_and_black_bars(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clips = root / 'clips'
            clips.mkdir()
            source_clip(clips / 'a.mp4', 'red')
            source_clip(clips / 'b.mp4', 'blue', size='720x1280')  # vertical: también recorta, no deforma
            logo, audio = root / 'logo.png', root / 'audio.bin'
            make_logo(logo)
            tone(audio, 9.4)
            spec = options({'visual': {'mode': 'video', 'videos_folder': str(clips), 'clip_min_seconds': 1,
                                       'clip_max_seconds': 2, 'video_fit': 'fixed_bars',
                                       'intro': {'logo': LOGO, 'seconds': 3.5}}})
            tools = MediaTools()
            intro = {'path': cached_intro('test', logo, spec['intro']['seconds'], tools, cache=root / 'cache'),
                     'seconds': spec['intro']['seconds']}
            output = root / 'video.mp4'
            result = render_montage(audio, output, 9.4, video_catalog(spec, None), spec, root, None,
                                    tools, 'job-1', intro=intro)
            info = probe(output)
            self.assertAlmostEqual(float(info['format']['duration']), 9.4, delta=1 / 30 + .001)
            audio_stream = next(s for s in info['streams'] if s['codec_type'] == 'audio')
            self.assertAlmostEqual(float(audio_stream['start_time']), 0, delta=.05)
            self.assertAlmostEqual(sum(row['seconds'] for row in result['clips']), 9.4 - 3.5, places=6)
            self.assertEqual(result['intro_seconds'], 3.5)
            # Durante la intro: logo al centro sobre negro.
            during = frame_at(output, 2.5, root / 'intro.png')
            self.assertGreater(max(during.crop((560, 300, 1360, 780)).get_flattened_data()), 200)
            # Después: franjas laterales de 344 px negras y clip en el centro.
            for second in (4.0, 6.0, 8.5):
                frame = frame_at(output, second, root / f'm{second}.png')
                self.assertLess(strip_mean(frame, (0, 0, 340, 1080)), 20)
                self.assertLess(strip_mean(frame, (1580, 0, 1920, 1080)), 20)
                self.assertGreater(strip_mean(frame, (360, 0, 1560, 1080)), 25)


if __name__ == '__main__':
    unittest.main()
