"""Afrowyre: family selection, honest metadata, replay and fixed cadence."""
import json
from pathlib import Path
import unittest
from core import beat_seo
from core.beat_selection import eligible_tracks, require_track, TrackNotMatching
from core.beat_templates import apply_channel_templates
from core.beat_interval import slots
from core.beat_schema import migrate
from core.beat_share import publication_link


class AfroTests(unittest.TestCase):
    def channel(self):
        return json.loads((Path(__file__).resolve().parents[1] / 'docs/afrowyre.channel.json').read_text(encoding='utf-8'))

    def snapshot(self, tags, title='Ocean Therapy', previous=None):
        ch = self.channel()
        apply_channel_templates(ch, {'title_template': ch['seo']['title_template'],
                                    'description_template': ch['seo']['description']})
        job = {'id': 'job', 'channel': ch['id'], 'track_id': 'TK1', 'cycle': 2}
        result, _ = beat_seo.build_snapshot(job, {'id': 'TK1', 'title': title, 'tags': tags},
                                           ch, '2026-11-07T12:00:00-03:00', previous_selected=previous)
        beat_seo.validate_snapshot(result, job)
        return result

    def test_family_selection_includes_combined_tags_and_skips_non_afro(self):
        ch = self.channel()
        good = ['afro', 'AFRO R&B', 'afro-guitar', 'guitar afro', 'afrobeat type beat',
                'afrobeats', 'afroswing', 'afropop', 'afrohouse', 'afro fusion', 'afrornb']
        bad = ['rnb', 'guitar', 'Burna Boy', 'house', 'afrodisiac', 'nonafro']
        for tag in good + bad:
            track = {'id': 'TK1', 'tags': [tag]}
            self.assertEqual(bool(eligible_tracks(ch, [track])), tag in good, tag)
            if tag in bad:
                with self.assertRaises(TrackNotMatching):
                    require_track(ch, track)
        self.assertEqual(eligible_tracks(ch, [{'tags': ['afro'], 'active': False}, {'tags': None}, {}]), [])
        self.assertEqual(eligible_tracks({'selection_tags': ['afro']}, [{'tags': ['afrobeat']}]), [])

    def test_styles_and_artists_are_from_track_only(self):
        for tags, expected in [(['afro'], 'Afrobeat'), (['afro', 'r&b', 'Tems'], 'Afro R&B x Tems'),
                               (['afro guitar'], 'Afro Guitar'), (['afroswing'], 'Afroswing'),
                               (['afro house'], 'Afro House'), (['afrornb'], 'Afro R&B')]:
            selected = self.snapshot(tags)['selected']
            self.assertEqual(selected['title'], f'(FREE) {expected} Type Beat - "Ocean Therapy"')
            self.assertTrue(selected['description'].startswith(selected['title']))
            if 'Tems' not in tags:
                self.assertNotIn('Tems', selected['title'])
            self.assertNotIn('Burna Boy', selected['title'])
        with self.assertRaisesRegex(ValueError, 'afro_style_missing'):
            self.snapshot(['rnb', 'Tems'])

    def test_description_short_link_and_technical_values(self):
        s = self.snapshot(['afro'], 'Ocean Therapy - 105bpm - key C# Minor')
        self.assertIn('BPM: 105 | Key: C# Minor', s['selected']['description'])
        desc = beat_seo.description(s['manual'], s['track'], s['selected'], 'https://bsta.rs/example')
        self.assertIn('https://bsta.rs/example', desc)
        self.assertNotIn('{url}', desc)
        missing = self.snapshot(['afro'])['selected']['description']
        self.assertNotIn('BPM:', missing)
        self.assertNotIn('Key:', missing)
        self.assertNotIn('burnaboy', missing)
        self.assertIn('contact@matwyre.com', missing)

    def test_long_names_bounded_tags_and_repeat_replay(self):
        s = self.snapshot(['afro rnb', 'Omah Lay', 'Burna Boy'], 'Name ' * 80)
        self.assertLessEqual(len(s['selected']['title']), 100)
        tags = s['selected']['tags']
        self.assertLessEqual(len(','.join(tags)) + 2 * sum(' ' in t for t in tags), 500)
        again = self.snapshot(['afro rnb', 'Omah Lay', 'Burna Boy'], 'Name ' * 80, s['selected'])
        self.assertNotEqual(s['selected']['tags'], again['selected']['tags'])

    def test_short_links_required_only_for_afro_mode(self):
        track = {'id': 'TK1', 'title': 'Ocean Therapy'}
        for link in (None, '', 'https://www.beatstars.com/beat/ocean-therapy-1',
                     'https://bsta.rs/abcd?tracking=1'):
            with self.assertRaisesRegex(ValueError, 'beat_short_link_missing'):
                publication_link(self.channel(), track, link)
        self.assertEqual(publication_link(self.channel(), track, 'https://bsta.rs/abcd'),
                         'https://bsta.rs/abcd')
        self.assertTrue(publication_link({}, track, None).startswith('https://www.beatstars.com/beat/'))

    def test_paused_config_and_three_day_cadence_survive_restart(self):
        ch = self.channel()
        migrate({'channels': [ch]}, 'config')
        self.assertFalse(ch['active'])
        dates = slots(ch, '2026-11-07T23:00:00-03:00')
        self.assertEqual([d.day for d in dates], [8, 11, 14, 17, 20])
        self.assertTrue(all(d.hour == 14 and d.utcoffset().total_seconds() == -10800 for d in dates))
        self.assertEqual(slots(ch, '2026-11-09T00:00:00-03:00'), dates[1:])


if __name__ == '__main__':
    unittest.main()
