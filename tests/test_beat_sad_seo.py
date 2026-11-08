import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from PIL import Image, ImageChops, ImageStat
from core import beat_sad_seo, beat_seo
from core.beat_render import compose
from core.beat_selection import eligible_tracks
from core.beat_settings import simulate
from core.beat_templates import apply_channel_templates
from core.beat_visual import options


class SadChannelTests(unittest.TestCase):
    def setUp(self):
        self.channel = json.loads((Path(__file__).resolve().parents[1] /
                                   'docs/sad-melodic.channel.json').read_text(encoding='utf-8'))

    def test_exact_or_selection_and_truthful_artists(self):
        tracks = [dict(id='TK' + str(i), title='Motion', tags=[tag]) for i, tag in enumerate(
            ['Juice WRLD', 'iann dior', 'the kid laroi', 'sad beat', 'sad',
             'not juice wrld', 'melodic house'])]
        selected = eligible_tracks(self.channel, tracks)
        self.assertEqual([t['id'] for t in selected], ['TK0', 'TK1', 'TK2', 'TK3'])
        for track, expected in zip(selected, ['Juice WRLD', 'iann dior', 'The Kid LAROI', 'Sad']):
            self.assertEqual(beat_sad_seo.variants(track, self.channel['seo'])[0]['title'],
                             f'(FREE) {expected} Type Beat - "Motion"')
        with self.assertRaises(ValueError):
            beat_sad_seo.context(tracks[-1])

    def test_snapshot_link_technical_data_and_repeat(self):
        track = dict(id='TK123', title='Motion - 145bpm - key B Minor',
                     tags=['juice wrld', 'sad beat'])
        job = dict(id='job', channel=self.channel['id'], track_id=track['id'], cycle=2)
        snapshot, _ = beat_seo.build_snapshot(job, track, self.channel, '2026-11-08T12:00:00+00:00')
        beat_seo.validate_snapshot(snapshot, job)
        selected = snapshot['selected']
        self.assertEqual(selected['title'], '(FREE) Sad Juice WRLD Type Beat - "Motion"')
        self.assertIn('BPM: 145\nKey: B Minor', selected['description'])
        self.assertNotIn('iann', selected['description'])
        resolved = beat_seo.description(self.channel['seo'], track, selected, 'https://bsta.rs/example')
        self.assertIn('https://bsta.rs/example', resolved)
        self.assertNotIn('{', resolved)
        repeat, _ = beat_seo.build_snapshot(job, track, self.channel, '2026-11-08T12:00:00+00:00',
                                            previous_selected=selected)
        beat_seo.validate_snapshot(repeat, job)
        self.assertEqual(repeat['selected']['title'], selected['title'])
        self.assertNotEqual(repeat['selected']['tags'], selected['tags'])

    def test_paused_and_daily_argentina_schedule(self):
        config = dict(channels=[self.channel])
        tracks = [dict(id='TK123', title='Motion', tags=['sad beat'])]
        now = '2026-11-08T19:00:00-03:00'
        self.assertEqual(simulate(config, tracks, now=now)['jobs'], [])
        active = deepcopy(config)
        active['channels'][0]['active'] = True
        jobs = simulate(active, tracks, now=now)['jobs']
        self.assertTrue(jobs)
        self.assertTrue(all(j['slot'].endswith('20:00:00-03:00') for j in jobs))
        self.assertEqual({s['weekday'] for s in self.channel['slots']}, set(range(7)))

    def test_title_budget_and_template_compilation(self):
        track = dict(id='TK1', title='Long ' * 90,
                     tags=['juice wrld', 'iann dior', 'the kid laroi', 'sad beat'])
        for option in beat_sad_seo.variants(track, self.channel['seo']):
            self.assertLessEqual(len(option['title']), 100)
            self.assertLessEqual(len(','.join(option['tags'])) +
                                 2 * sum(' ' in t for t in option['tags']), 450)
        self.channel['use_channel_templates'] = True
        apply_channel_templates(self.channel, dict(
            title_template=self.channel['seo']['title_template'],
            description_template=self.channel['seo']['description']))

    def test_same_plain_composition_for_video_and_thumbnail(self):
        spec = options(self.channel)
        self.assertFalse(spec['custom_thumbnail'])
        self.assertEqual(spec['mode'], 'image')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            Image.new('RGB', (700, 700), (80, 40, 120)).save(root / 'source.png')
            compose(root / 'source.png', 'Motion', root / 'frame.png', root / 'thumb.jpg',
                    plain=spec['plain_image'], fit=spec['image_fit'])
            with Image.open(root / 'frame.png') as frame, Image.open(root / 'thumb.jpg') as thumb:
                self.assertEqual(frame.getbbox(), (420, 0, 1500, 1080))
                difference = ImageChops.difference(frame.resize(thumb.size), thumb)
                self.assertLess(sum(ImageStat.Stat(difference).mean) / 3, 2)
