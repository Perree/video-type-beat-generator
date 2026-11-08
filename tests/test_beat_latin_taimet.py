"""Taimet-inspired format without inventing artists or invalidating older jobs."""
from copy import deepcopy
import json
from pathlib import Path
import unittest
from core import beat_seo
from core.beat_templates import apply_channel_templates
from core.beat_share import publication_link


class LatinTaimetTests(unittest.TestCase):
    def channel(self):
        ch = json.loads((Path(__file__).resolve().parents[1] / 'docs/wyrelatinbeatz.channel.json').read_text(encoding='utf-8'))
        ch['seo'].update(title_mode='latin_taimet_v1',
                         title_template='(FREE) {style} TYPE BEAT - "{name}"')
        apply_channel_templates(ch, {'title_template': ch['seo']['title_template'],
                                    'description_template': ch['seo']['description']})
        return ch

    def snapshot(self, tags, title='Beauty Girl', previous=None, legacy=False):
        ch = self.channel()
        if legacy:
            ch['seo'].update(title_mode='latin_v2', title_template='(FREE) {style} Type Beat - "{name}"{detail}')
        job = {'id': 'j', 'channel': ch['id'], 'track_id': 'TK1', 'cycle': 2 if previous else 1}
        result, _ = beat_seo.build_snapshot(job, {'id': 'TK1', 'title': title, 'tags': tags},
                                           ch, '2026-11-07T20:00:00-03:00', previous_selected=previous)
        self.assertEqual(beat_seo.validate_snapshot(result, job), result)
        return result, job

    def test_reference_format_and_matching_metadata(self):
        s, _ = self.snapshot(['feid', 'mora', 'reggaeton sad'])
        self.assertEqual(s['selected']['title'], '(FREE) FEID x MORA TYPE BEAT - "BEAUTY GIRL"')
        self.assertIn('Sad Reggaeton', s['selected']['description'])
        self.assertIn('sad reggaeton type beat', s['selected']['tags'])
        self.assertNotIn('|', s['selected']['title'])

    def test_single_artist_and_genre_fallback(self):
        self.assertEqual(self.snapshot(['bad bunny', 'latin trap'], 'New York')[0]['selected']['title'],
                         '(FREE) BAD BUNNY TYPE BEAT - "NEW YORK"')
        selected = self.snapshot(['reggaeton', 'emotional'], 'Na Naa')[0]['selected']
        self.assertEqual(selected['title'], '(FREE) REGGAETON TYPE BEAT - "NA NAA"')
        self.assertNotIn('bad bunny', str(selected).lower())
        with self.assertRaisesRegex(ValueError, 'latin_style_missing'):
            self.snapshot(['Bad Bunny'])

    def test_unicode_uppercase_limits_retry_and_repeat(self):
        s, _ = self.snapshot(['bad bunny', 'rauw alejandro', 'reggaeton'], 'Straße ' * 60)
        self.assertLessEqual(len(s['selected']['title']), 100)
        self.assertTrue(s['selected']['title'].endswith('"'))
        self.assertEqual(s, self.snapshot(['bad bunny', 'rauw alejandro', 'reggaeton'], 'Straße ' * 60)[0])
        repeated, _ = self.snapshot(['bad bunny', 'rauw alejandro', 'reggaeton'], 'Straße ' * 60, s['selected'])
        self.assertEqual(repeated['selected']['title'], s['selected']['title'])
        self.assertNotEqual(repeated['selected']['tags'], s['selected']['tags'])

    def test_legacy_snapshot_and_individual_links(self):
        old, job = self.snapshot(['feid', 'mora', 'reggaeton sad'], legacy=True)
        self.snapshot(['feid', 'mora', 'reggaeton sad'])
        self.assertEqual(beat_seo.validate_snapshot(old, job), old)
        with self.assertRaisesRegex(ValueError, 'beat_individual_link_missing'):
            publication_link(self.channel(), {'id': 'TK1', 'title': 'Beauty Girl'}, None)

    def test_tamper_rejected_even_after_rehash(self):
        s, job = self.snapshot(['feid', 'mora', 'reggaeton sad'])
        bad = deepcopy(s)
        bad['selected']['title'] = bad['selected']['title'].replace('FEID', 'TAINY')
        bad['sha256'] = beat_seo.digest({k: v for k, v in bad.items() if k != 'sha256'})
        with self.assertRaises(ValueError):
            beat_seo.validate_snapshot(bad, job)
