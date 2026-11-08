"""Reference title/tag format, truthful artist fallback, and snapshot compatibility."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from core import beat_seo
from core.beat_templates import apply_channel_templates
from core.beat_share import publication_link


class DysmoTests(unittest.TestCase):
    def snapshot(self, tags, name='Nuestra historia', previous=None, legacy=False):
        channel = json.loads((Path(__file__).resolve().parents[1] /
                              'docs/islabeatz.channel.json').read_text(encoding='utf8'))
        channel['seo'].update(title_mode='latin_v2' if legacy else 'latin_dysmo_v1',
                              title_template='(FREE) {style} Type Beat - "{name}"{detail}')
        apply_channel_templates(channel, dict(title_template=channel['seo']['title_template'],
                                              description_template=channel['seo']['description']))
        job = dict(id='j', channel=channel['id'], track_id='TK1', cycle=2 if previous else 1)
        result, _ = beat_seo.build_snapshot(job, dict(id='TK1', title=name, tags=tags),
                                            channel, '2026-11-08T15:00:00-03:00',
                                            previous_selected=previous)
        beat_seo.validate_snapshot(result, job)
        return result, job, channel

    def test_reference_title_and_keyword_combinations(self):
        selected = self.snapshot(['bad bunny', 'mora', 'dancehall', 'sad'])[0]['selected']
        self.assertEqual(selected['title'],
                         '(FREE) Bad Bunny x Mora Type Beat - "Nuestra historia" | Sad Dancehall Type Beat')
        for tag in ('sad dancehall type beat', 'bad bunny x mora type beat',
                    'mora x bad bunny type beat', 'type beat mora', 'beat mora'):
            self.assertIn(tag, selected['tags'])
        self.assertIn('Sad Dancehall', selected['description'])
        self.assertNotIn('dysmo', str(selected).casefold())
        self.assertNotIn('sold', selected['title'].casefold())

    def test_single_artist_and_genre_fallback(self):
        selected = self.snapshot(['feid', 'reggaeton'])[0]['selected']
        self.assertIn('Feid Type Beat', selected['title'])
        self.assertNotIn('mora', str(selected).casefold())
        self.assertNotIn('sad', str(selected).casefold())
        selected = self.snapshot(['reggaeton'])[0]['selected']
        self.assertEqual(selected['title'], '(FREE) Reggaeton Type Beat - "Nuestra historia"')
        self.assertNotIn('bad bunny', str(selected).casefold())
        self.assertNotIn(' x ', selected['title'])

    def test_limits_repeat_and_legacy_snapshots(self):
        tags = ['bad bunny', 'mora', 'reggaeton sad']
        snap, job, _ = self.snapshot(tags, 'N' * 400)
        selected = snap['selected']
        self.assertLessEqual(len(selected['title']), 100)
        self.assertTrue(selected['title'].endswith('| Sad Reggaeton Type Beat'))
        keywords = selected['tags']
        self.assertEqual(len(keywords), len(set(keywords)))
        self.assertLessEqual(len(','.join(keywords)) + 2 * sum(' ' in t for t in keywords), 450)
        repeated = self.snapshot(tags, 'N' * 400, previous=selected)[0]['selected']
        self.assertEqual(repeated['title'], selected['title'])
        self.assertNotEqual(repeated['tags'], selected['tags'])
        old, job, _ = self.snapshot(tags, legacy=True)
        self.assertEqual(beat_seo.validate_snapshot(old, job), old)

    def test_tampering_and_missing_individual_link(self):
        snap, job, channel = self.snapshot(['bad bunny', 'dancehall'])
        tampered = deepcopy(snap)
        tampered['selected']['tags'].append('mora type beat')
        tampered['sha256'] = beat_seo.digest({k: v for k, v in tampered.items() if k != 'sha256'})
        with self.assertRaises(ValueError):
            beat_seo.validate_snapshot(tampered, job)
        with self.assertRaisesRegex(ValueError, 'beat_individual_link_missing'):
            publication_link(channel, dict(id='TK1', title='Nuestra historia'), None)
