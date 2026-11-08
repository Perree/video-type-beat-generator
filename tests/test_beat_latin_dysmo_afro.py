"""Afro labels follow catalog tags; historical title modes remain replayable."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from core import beat_seo


class DysmoAfroTests(unittest.TestCase):
    def snapshot(self, tags, mode='latin_dysmo_v3'):
        channel = json.loads((Path(__file__).resolve().parents[1] /
                              'docs/islabeatz.channel.json').read_text(encoding='utf8'))
        channel['seo']['title_mode'] = mode
        job = dict(id='j', channel=channel['id'], track_id='TK1', cycle=1)
        track = dict(id='TK1', title='Nombre', tags=tags)
        original = deepcopy(track)
        snap, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-08T16:30:00+00:00')
        self.assertEqual(track, original)
        beat_seo.validate_snapshot(snap, job)
        return snap, job

    def test_afro_reggaeton_and_default_artists(self):
        selected = self.snapshot(['afrobeat', 'reggaeton', 'sad'])[0]['selected']
        self.assertEqual(selected['title'],
            '(FREE) Bad Bunny x Mora Type Beat - "Nombre" | Sad Afro Reggaeton Type Beat')
        self.assertIn('sad afro reggaeton type beat', selected['tags'])
        self.assertIn('Sad Afro Reggaeton', selected['description'])

    def test_afro_and_tagged_artist(self):
        selected = self.snapshot(['afro', 'dancehall', 'mora'])[0]['selected']
        self.assertEqual(selected['title'], '(FREE) Mora Type Beat - "Nombre" | Afro Type Beat')
        self.assertIn('afro type beat', selected['tags'])
        self.assertIn('#afrotypebeat', selected['description'])
        self.assertNotIn('bad bunny', str(selected).casefold())

    def test_genre_is_not_randomly_replaced_and_pure_afro_is_supported(self):
        selected = self.snapshot(['dancehall'])[0]['selected']
        self.assertTrue(selected['title'].endswith('| Dancehall Type Beat'))
        self.assertNotIn('afro', str(selected).casefold())
        selected = self.snapshot(['afrobeat'])[0]['selected']
        self.assertTrue(selected['title'].endswith('| Afro Type Beat'))

    def test_old_snapshots_and_non_afro_titles_are_unchanged(self):
        for tags in (['reggaeton'], ['feid', 'tainy', 'reggaeton']):
            old, job = self.snapshot(tags, mode='latin_dysmo_v2')
            new, _ = self.snapshot(tags)
            self.assertEqual(old['selected'], new['selected'])
            self.assertEqual(beat_seo.validate_snapshot(old, job), old)
