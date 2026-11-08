"""Prepared channel, metadata limits and isolated visual rotation."""
from datetime import timedelta
import json
import os
import subprocess
import wave
from pathlib import Path
import tempfile
import unittest

from core.beat_seo import build_snapshot, validate_snapshot
from core.beat_schema import migrate, instant
from core.beat_selection import eligible_tracks
from core.beat_visual import options
from core.beat_visual_schedule import job_options
from core.beat_templates import apply_channel_templates
from core.beat_film_overlay import create_gate, filters
from core.beat_montage import render_montage, verify_output
from core.beat_visual import video_catalog
from core.beat_render import MediaTools
from PIL import Image


def channel():
    return json.loads((Path(__file__).resolve().parents[1] / 'docs/emotional-house.channel.json').read_text('utf-8'))


class EmotionalHouseTests(unittest.TestCase):
    def test_profile_is_paused_and_schema_valid(self):
        ch = channel()
        migrate({'channels': [ch]}, 'config')
        self.assertFalse(ch['active'])
        self.assertFalse(options(ch)['custom_thumbnail'])
        self.assertEqual(ch['youtube_channel_id'], 'UCqSN_dCTnhNcRcMmW3qc3JQ')
        self.assertEqual(ch['interval_schedule']['days'], 2)

    def test_rotation_is_slot_based_and_does_not_mix_pools(self):
        ch = channel()
        anchor = instant(ch['interval_schedule']['anchor'])
        for index in range(7):
            job = {'slot': (anchor + timedelta(days=2 * index)).isoformat(), 'cycle': 27}
            first = job_options(ch, job)
            self.assertEqual(first, job_options(ch, job))
            group = ch['visual']['video_groups'][index % 3]
            self.assertEqual(first['videos_folder'], group['folder'])
            self.assertEqual(first['clip_min_seconds'], group['min_seconds'])
            self.assertEqual(first['video_group'], group['name'])
        with self.assertRaisesRegex(ValueError, 'off_schedule'):
            job_options(ch, {'slot': (anchor + timedelta(days=1)).isoformat()})

    def test_legacy_visuals_and_overlay_validation(self):
        self.assertNotIn('film_overlay', options({}))
        self.assertNotIn('video_groups', options({}))
        for key, value in [('film_overlay', 'unknown'), ('video_fit', 'bad'), ('video_groups', []),
                           ('video_groups', [{'name': 'bad'}])]:
            with self.assertRaises(ValueError):
                options({'visual': {key: value}})
        ch = channel()
        ch['visual']['video_groups'][0]['min_seconds'] = True
        with self.assertRaises(ValueError):
            options(ch)

    def test_seo_matches_families_and_keeps_own_identity(self):
        ch = channel()
        examples = [(['deep house', 'jersey club', 'emotional'], 'Deep House x Jersey Club'),
                    (['deep house', 'reggaeton'], 'Deep House x Reggaeton'),
                    (['afrohouse'], 'Afro House'), (['tech house', 'techno'], 'Tech House x Techno')]
        for tags, expected in examples:
            track = {'id': 'TK123', 'title': 'OUR NIGHT', 'tags': tags}
            job = {'id': 'j', 'channel': ch['id'], 'track_id': track['id'], 'cycle': 1}
            snap, _ = build_snapshot(job, track, ch, '2026-11-08T18:00:00-03:00')
            validate_snapshot(snap, job)
            selected = snap['selected']
            self.assertIn(expected, selected['title'])
            self.assertIn('"OUR NIGHT"', selected['title'])
            self.assertTrue(selected['description'].startswith(selected['title']))
            self.assertNotIn('Klein', selected['description'])
            self.assertLessEqual(len(selected['title']), 100)
            self.assertLessEqual(len(','.join(selected['tags'])) + 2 * sum(' ' in t for t in selected['tags']), 450)
            if 'jersey club' not in tags:
                self.assertNotIn('jersey club type beat', selected['tags'])
        self.assertEqual(eligible_tracks(ch, [{'id': 'a', 'tags': ['emotional', 'reggaeton']}]), [])
        ch['use_channel_templates'] = True
        apply_channel_templates(ch, {'title_template': ch['seo']['title_template'], 'description_template': ch['seo']['description']})

    def test_transparent_gate_and_opt_in_filter(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            create_gate(root / 'gate.png')
            with Image.open(root / 'gate.png') as picture:
                self.assertEqual(picture.size, (1920, 1080))
                self.assertEqual(picture.getpixel((960, 540))[3], 0)
                self.assertGreater(picture.getpixel((95, 540))[3], 0)
            inputs, graph = filters(channel()['visual'], root)
            self.assertIn('noise=', ' '.join(graph))
            self.assertTrue(inputs)
            inputs, graph = filters({}, root)
            self.assertEqual(inputs, [])
            self.assertNotIn('noise=', ' '.join(graph))

    @unittest.skipUnless(os.environ.get('BEAT_REAL_FFMPEG_SMOKE') == '1', 'Opt-in FFmpeg render')
    def test_real_vertical_overlay_montage_and_audio(self):
        tools = MediaTools()
        self.assertTrue(tools.ffmpeg and tools.ffprobe)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            sources = root / 'sources'
            sources.mkdir()
            for name, color in [('a', 'blue'), ('b', 'green')]:
                subprocess.run([tools.ffmpeg, '-nostdin', '-v', 'error', '-y', '-f', 'lavfi',
                    '-i', f'color=c={color}:s=180x320:r=30:d=2', '-f', 'lavfi',
                    '-i', 'sine=frequency=1000:duration=2', '-c:v', 'libx264', '-c:a', 'aac',
                    '-shortest', str(sources / f'{name}.mp4')], check=True, capture_output=True, timeout=30)
            audio = root / 'beat.wav'
            with wave.open(str(audio), 'wb') as stream:
                stream.setparams((1, 2, 48000, 0, 'NONE', ''))
                stream.writeframes(b'\x00\x00' * 120000)
            spec = options({'visual': {'mode': 'video', 'videos_folder': str(sources),
                'clip_min_seconds': .5, 'clip_max_seconds': .5, 'video_fit': 'contain',
                'film_overlay': 'film_gate_red_v1'}})
            output = root / 'out.mp4'
            result = render_montage(audio, output, 2.5, video_catalog(spec, None), spec,
                                    root, None, tools, 'overlay-smoke')
            verify_output(output, 2.5, tools)
            self.assertEqual(len(result['clips']), 5)
            # Real decode checks padding, visible gate, portrait area and source-audio removal.
            frame = root / 'frame.png'
            subprocess.run([tools.ffmpeg, '-v', 'error', '-i', str(output), '-frames:v', '1',
                            str(frame)], check=True, capture_output=True, timeout=30)
            with Image.open(frame) as picture:
                self.assertLess(max(picture.getpixel((250, 200))[:3]), 20)
                red, green, blue = picture.getpixel((95, 540))[:3]
                self.assertGreater(red, green + 40)
                self.assertGreater(max(picture.getpixel((960, 540))[:3]), 60)
            decoded = subprocess.run([tools.ffmpeg, '-v', 'error', '-i', str(output),
                '-map', '0:a:0', '-f', 's16le', '-'], check=True, capture_output=True, timeout=30)
            self.assertTrue(decoded.stdout)
            self.assertFalse(any(decoded.stdout))
