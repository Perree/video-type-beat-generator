from copy import deepcopy
import unittest
from core.beat_seo import build_snapshot, validate_snapshot
from core.beat_selection import eligible_tracks
from core.beat_templates import apply_channel_templates

TEMPLATE = '(FREE) Makar x {style} Type Beat - "{name}"'


def channel():
    return {'id': 'rave', 'selection_tags': ['makar', 'house', 'deep house', 'afro house'],
            'seo': {'title_mode': 'house_v1', 'title_template': TEMPLATE,
                    'description': 'Makar x {style} Type Beat - "{name}"\nBuy: {url}',
                    'tags': ['makar type beat', 'house type beat']}}


def snapshot(tags, title='NOCHE', tid='TK123', previous=None):
    track = {'id': tid, 'title': title, 'tags': tags}
    job = {'id': 'j', 'channel': 'rave', 'track_id': tid, 'cycle': 2 if previous else 1}
    s, _ = build_snapshot(job, track, channel(), '2026-11-03T15:00:00-03:00', previous_selected=previous)
    assert validate_snapshot(s, job) == s
    return s


class HouseSeoTests(unittest.TestCase):
    def test_style_follows_explicit_tags(self):
        for tags, style in [(['deep house', 'house'], 'Deep House'), (['melodic deep house'], 'Deep House'),
                            (['afro house', 'house'], 'Afro House'), (['deep house', 'Afro House'], 'Afro House'),
                            (['house', 'club'], 'House'), (['makar', 'emotional'], 'House')]:
            with self.subTest(tags=tags):
                s = snapshot(tags)
                self.assertEqual(s['selected']['title'], f'(FREE) Makar x {style} Type Beat - "NOCHE"')
                self.assertTrue(s['selected']['description'].startswith(f'Makar x {style} Type Beat - "NOCHE"'))
                self.assertIn('Buy: {url}', s['selected']['description'])

    def test_style_tags_lead_and_limits_hold(self):
        tags = snapshot(['afro house'])['selected']['tags']
        self.assertEqual(tags[:2], ['afro house type beat', 'afro house instrumental'])
        self.assertNotIn('deep house type beat', tags)
        self.assertNotIn('deep house type beat', snapshot(['house'])['selected']['tags'])
        long = snapshot(['house'], title='N' * 200)['selected']
        self.assertLessEqual(len(long['title']), 100)
        self.assertLessEqual(len(','.join(long['tags'])), 450)

    def test_catalog_names_are_cleaned(self):
        for title, name in [('Makar Type Beat - MOËT', 'MOËT'),
                            ('VELVET | Deep House Type Beat', 'VELVET'),
                            ('"CONNECTION" - Emotional Guitar Deep House Type Beat', 'CONNECTION')]:
            with self.subTest(title=title):
                self.assertIn(f'"{name}"', snapshot(['house'], title=title)['selected']['title'])

    def test_repeat_rotates_tags_and_tamper_rejected(self):
        s = snapshot(['deep house'])
        again = snapshot(['deep house'], previous=s['selected'])
        self.assertEqual(again['selected']['title'], s['selected']['title'])
        self.assertNotEqual(again['selected']['tags'], s['selected']['tags'])
        bad = deepcopy(s)
        bad['selected']['title'] = bad['selected']['title'].replace('Deep House', 'Afro House')
        with self.assertRaises(ValueError):
            validate_snapshot(bad, {'id': 'j', 'channel': 'rave', 'track_id': 'TK123', 'cycle': 1})

    def test_template_requires_style_and_survives_recompilation(self):
        ch = channel()
        ch['seo']['title_template'] = '(FREE) Makar Type Beat - "{name}"'
        with self.assertRaisesRegex(ValueError, 'seo_title_mode_invalid'):
            build_snapshot(
                {'id': 'j', 'channel': 'rave', 'track_id': 'TK1', 'cycle': 1},
                {'id': 'TK1', 'title': 'X', 'tags': ['house']}, ch, '2026-11-03T15:00:00-03:00')
        ch = channel()
        ch['use_channel_templates'] = True
        apply_channel_templates(ch, {'title_template': TEMPLATE, 'description_template': ch['seo']['description']})
        self.assertEqual(ch['seo']['title_mode'], 'house_v1')
        ch['seo']['description'] = '{bpm} BPM'
        with self.assertRaisesRegex(ValueError, 'placeholder_unsupported'):
            apply_channel_templates(ch, {'title_template': TEMPLATE, 'description_template': '{bpm} BPM'})

    def test_unrelated_beats_stay_out(self):
        tracks = [{'id': 'a', 'tags': ['afro', 'afrobeat']}, {'id': 'b', 'tags': ['afro house']}]
        self.assertEqual(eligible_tracks(channel(), tracks), [tracks[1]])


if __name__ == '__main__':
    unittest.main()
