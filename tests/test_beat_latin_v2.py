"""WyreLatinBeatz: truthful metadata, snapshot replay and two-day scheduling."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from core import beat_seo, beat_latin_seo_v2 as latin
from core.beat_interval import slots
from core.beat_schedule import plan, apply_plan
from core.beat_schema import migrate
from core.beat_selection import eligible_tracks
from core.beat_templates import apply_channel_templates
from core.beat_share import publication_link


class LatinV2Tests(unittest.TestCase):
    def channel(self):
        path = Path(__file__).resolve().parents[1] / 'docs/wyrelatinbeatz.channel.json'
        return json.loads(path.read_text(encoding='utf-8'))

    def snapshot(self, tags, title='Noche', previous=None):
        ch = self.channel()
        apply_channel_templates(ch, {'title_template': ch['seo']['title_template'],
                                    'description_template': ch['seo']['description']})
        job = {'id': 'job', 'channel': ch['id'], 'track_id': 'TK1', 'cycle': 2 if previous else 1}
        result, _ = beat_seo.build_snapshot(job, {'id': 'TK1', 'title': title, 'tags': tags},
                                           ch, '2026-11-07T12:00:00-03:00', previous_selected=previous)
        self.assertEqual(beat_seo.validate_snapshot(result, job), result)
        return result, job

    def test_artists_require_exact_source_tags_and_descriptions_agree(self):
        selected = self.snapshot(['reggaeton', 'de la rose', 'omar courtz'])[0]['selected']
        self.assertEqual(selected['title'], '(FREE) Omar Courtz x De La Rose Type Beat - "Noche" | Reggaeton')
        self.assertIn('Omar Courtz x De La Rose', selected['description'])
        self.assertIn('#omarcourtztypebeat #delarosetypebeat', selected['description'])
        self.assertIn('de la rose type beat', selected['tags'])
        self.assertNotIn('bad bunny', str(selected).lower())
        single = self.snapshot(['latin trap', 'Feid'])[0]['selected']
        self.assertIn('Feid Type Beat', single['title'])
        self.assertNotIn(' x ', single['title'])
        unrelated = self.snapshot(['reggaeton', 'moral', 'bad bunny inspired maybe'])[0]['selected']
        self.assertEqual(unrelated['title'], '(FREE) Reggaeton Type Beat - "Noche"')

    def test_genres_moods_and_artist_aliases(self):
        for tags, style in [(['dancehall'], 'Dancehall'), (['trap latino'], 'Latin Trap'),
                            (['latin r&b'], 'Latin R&B'), (['trapnb'], 'Trap/R&B'),
                            (['reggaeton rnb'], 'Reggaeton R&B'), (['latin pop'], 'Latin Pop'),
                            (['sad reggaeton'], 'Sad Reggaeton')]:
            with self.subTest(tags=tags):
                self.assertIn(style, self.snapshot(tags)[0]['selected']['title'])
        self.assertIn('Rauw Alejandro', self.snapshot(['dancehall', 'rauw type beat'])[0]['selected']['title'])
        for tags in (['rnb'], ['pop'], ['trap'], ['Bad Bunny']):
            with self.assertRaisesRegex(ValueError, 'latin_style_missing'):
                self.snapshot(tags)

    def test_technical_values_missing_values_and_individual_link(self):
        s, _ = self.snapshot(['latin trap'], 'Noche - 94bpm - key C Major')
        self.assertIn('"Noche"', s['selected']['title'])
        self.assertNotIn('94', s['selected']['title'])
        self.assertIn('BPM: 94\nKey: C Major', s['selected']['description'])
        value = beat_seo.description(s['manual'], s['track'], s['selected'], 'https://bsta.rs/abcd')
        self.assertIn('https://bsta.rs/abcd', value)
        self.assertNotIn('{url}', value)
        missing = self.snapshot(['reggaeton'])[0]['selected']['description']
        self.assertNotIn('BPM:', missing)
        self.assertNotIn('Key:', missing)
        self.assertNotIn('Ignore Tags', missing)

    def test_limits_repeat_retry_and_tamper(self):
        s, _ = self.snapshot(['reggaeton', 'rauw', 'bad bunny', 'emotional'], 'N' * 300)
        self.assertLessEqual(len(s['selected']['title']), 100)
        tags = s['selected']['tags']
        self.assertLessEqual(len(','.join(tags)) + 2 * sum(' ' in t for t in tags), 450)
        self.assertEqual(s, self.snapshot(['reggaeton', 'rauw', 'bad bunny', 'emotional'], 'N' * 300)[0])
        repeated, job = self.snapshot(['reggaeton', 'rauw', 'bad bunny', 'emotional'], 'N' * 300, s['selected'])
        self.assertNotEqual(s['selected']['tags'], repeated['selected']['tags'])
        repeated['selected']['description'] += ' invented metadata'
        repeated['sha256'] = beat_seo.digest({k: v for k, v in repeated.items() if k != 'sha256'})
        with self.assertRaises(ValueError):
            beat_seo.validate_snapshot(repeated, job)

    def test_source_filters_supported_and_unrelated_tracks_excluded(self):
        ch = self.channel()
        self.assertEqual(set(ch['selection_tags']), set(latin.SELECTION_TAGS))
        for tag in ch['selection_tags']:
            self.snapshot([tag])
        tracks = [{'id': 'TK1', 'tags': ['reggaeton']}, {'id': 'TK2', 'tags': ['rnb']},
                  {'id': 'TK3', 'tags': ['latin trap'], 'active': False},
                  {'id': 'TK4', 'tags': ['Bad Bunny']}]
        self.assertEqual(eligible_tracks(ch, tracks), tracks[:1])

    def test_publication_requires_the_selected_beats_individual_link(self):
        track = {'id': 'TK1', 'title': 'Noche', 'url': 'https://www.beatstars.com/beat/original-slug-1'}
        self.assertEqual(publication_link(self.channel(), track, None), track['url'])
        self.assertEqual(publication_link(self.channel(), track, 'https://bsta.rs/abcd'),
                         'https://bsta.rs/abcd')
        for url in ('https://www.beatstars.com/matwyre', 'https://www.beatstars.com/beat/noche-2', ''):
            with self.assertRaisesRegex(ValueError, 'beat_individual_link_missing'):
                publication_link(self.channel(), dict(track, url=url), None)

    def test_two_day_calendar_at_fifteen_survives_restart(self):
        ch = self.channel()
        ch['active'] = False  # The deployed channel may already be active.
        self.assertFalse(ch['active'])
        self.assertEqual(ch['visual']['mode'], 'video')
        dates = slots(ch, '2026-11-07T23:00:00-03:00')
        self.assertEqual([d.day for d in dates], [8, 10, 12, 14, 16, 18, 20])
        self.assertTrue(all(d.hour == 15 and d.minute == 0 for d in dates))
        ch['active'] = True
        config = migrate({'channels': [ch]}, 'config')
        tracks = [{'id': 'TK' + str(i), 'tags': ['reggaeton']} for i in range(20)]
        state = migrate({}, 'state')
        apply_plan(state, plan(config, state, tracks, '2026-11-07T23:00:00-03:00'))
        before = deepcopy(state)
        self.assertEqual(plan(config, state, tracks, '2026-11-07T23:00:00-03:00'), [])
        additional = plan(config, state, tracks, '2026-11-09T00:00:00-03:00')
        self.assertEqual([job['slot'] for job in additional], ['2026-11-22T15:00:00-03:00'])
        self.assertEqual(state, before)


if __name__ == '__main__':
    unittest.main()
