"""Default editorial artists without changing source metadata or historical modes."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from core import beat_seo
from core.beat_templates import apply_channel_templates
from core.beat_share import publication_link


class DysmoDefaultTests(unittest.TestCase):
    def snapshot(self, tags, mode='latin_dysmo_v2', previous=None, name='VERTE DE NUEVO'):
        channel = json.loads((Path(__file__).resolve().parents[1] /
                              'docs/islabeatz.channel.json').read_text(encoding='utf8'))
        channel['seo']['title_mode'] = mode
        apply_channel_templates(channel, dict(title_template=channel['seo']['title_template'],
                                              description_template=channel['seo']['description']))
        job = dict(id='j', channel=channel['id'], track_id='TK1', cycle=2 if previous else 1)
        track = dict(id='TK1', title=name, tags=tags)
        before = deepcopy(track)
        snap, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-08T16:00:00+00:00',
                                         previous_selected=previous)
        self.assertEqual(track, before)
        self.assertEqual(snap['track']['tags'], tags)
        beat_seo.validate_snapshot(snap, job)
        return snap, job, channel

    def test_default_pair_and_tags(self):
        snap, _, _ = self.snapshot(['reggaeton'])
        self.assertEqual(snap['selected']['title'],
                         '(FREE) Bad Bunny x Mora Type Beat - "VERTE DE NUEVO" | Reggaeton Type Beat')
        self.assertIn('bad bunny x mora type beat', snap['selected']['tags'])
        self.assertIn('mora type beat', snap['selected']['tags'])
        self.assertNotIn('Referencias de estilo:', snap['selected']['description'])

    def test_tagged_artists_and_moods_are_preserved(self):
        single = self.snapshot(['feid', 'reggaeton'])[0]['selected']
        self.assertIn('Feid Type Beat', single['title'])
        self.assertNotIn('mora', str(single).lower())
        pair = self.snapshot(['feid', 'tainy', 'dancehall'])[0]['selected']
        self.assertIn('Feid x Tainy Type Beat', pair['title'])
        sad = self.snapshot(['dancehall', 'sad'])[0]['selected']
        self.assertIn('Bad Bunny x Mora Type Beat', sad['title'])
        self.assertTrue(sad['title'].endswith('| Sad Dancehall Type Beat'))

    def test_legacy_snapshots_remain_valid_and_links_required(self):
        old, job, _ = self.snapshot(['reggaeton'], mode='latin_dysmo_v1')
        self.assertEqual(old['selected']['title'], '(FREE) Reggaeton Type Beat - "VERTE DE NUEVO"')
        _, _, channel = self.snapshot(['reggaeton'])
        self.assertEqual(beat_seo.validate_snapshot(old, job), old)
        with self.assertRaisesRegex(ValueError, 'beat_individual_link_missing'):
            publication_link(channel, dict(id='TK1', title='Name'), None)

    def test_long_names_and_repeat_keep_reference_pair(self):
        snap, _, _ = self.snapshot(['reggaeton'], name='N' * 400)
        self.assertLessEqual(len(snap['selected']['title']), 100)
        tags = snap['selected']['tags']
        self.assertLessEqual(len(','.join(tags)) + 2 * sum(' ' in t for t in tags), 450)
        repeated = self.snapshot(['reggaeton'], name='N' * 400,
                                 previous=snap['selected'])[0]['selected']
        self.assertEqual(repeated['title'], snap['selected']['title'])
        self.assertNotEqual(repeated['tags'], snap['selected']['tags'])
