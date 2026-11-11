import json
import unittest
from pathlib import Path
from core import beat_seo
from core.beat_templates import apply_channel_templates

TITLE = '(BEAT PRO-527) [juice wrld, sad] This is for me - 160bpm - key A Sharp Minor (prod. @a)'


def channel(cid):
    return json.loads((Path('docs') / f'{cid}.channel.json').read_text(encoding='utf-8'))


class MusicInfoTests(unittest.TestCase):
    def test_bpm_and_key_from_beatstars_title(self):
        self.assertEqual(beat_seo.music_info({'title': TITLE}), 'BPM: 160\nKey: A Sharp Minor')

    def test_beat_channels_put_bpm_and_key_in_description(self):
        for cid in ('poppyvibes', 'kiezah', 'ravewavebeatz', 'mat-produced-this-one'):
            with self.subTest(cid=cid):
                profile = beat_seo.manual_profile(channel(cid))[1]
                tags = ['indie pop', 'house', 'melodic', 'makar']
                track = {'id': 'TK1', 'title': TITLE, 'tags': tags}
                text = beat_seo.description(profile, track, {}, 'https://x.test/a')
                self.assertIn('BPM: 160\nKey: A Sharp Minor', text)
                self.assertNotIn('{music_info}', text)

    def test_missing_data_leaves_no_gap(self):
        profile = {'description': 'Top\n\n{music_info}\n\nBottom', 'tags': []}
        text = beat_seo.description(profile, {'id': 'TK1', 'title': 'Simple Name', 'tags': []}, {})
        self.assertEqual(text, 'Top\n\nBottom')

    def test_channel_templates_accept_the_token(self):
        ch = {'id': 'x', 'use_channel_templates': True, 'seo': {'tags': ['a'], 'description': ''}}
        saved = {'title_template': '{name}', 'description_template': '{music_info}\n{url}'}
        self.assertIn('{music_info}', apply_channel_templates(ch, saved)['seo']['description'])


class BeatStarsDataTests(unittest.TestCase):
    TRACK = {'id': 'TK1', 'title': 'Night Love', 'tags': ['melodic'], 'bpm': 120, 'key': 'Gm',
             'collaborators': ['prodsantu', 'Other One']}

    def test_page_data_wins_over_title(self):
        track = dict(self.TRACK, title=TITLE)
        self.assertEqual(beat_seo.music_info(track), 'BPM: 120\nKey: Gm')

    def test_collaborators_extend_the_producer_line(self):
        profile = beat_seo.manual_profile(channel('mat-produced-this-one'))[1]
        text = beat_seo.description(profile, beat_seo.track_input(self.TRACK), {}, 'https://x.test/a')
        self.assertIn('\nProd. MatWyre x prodsantu x Other One\n', text)
        self.assertIn('BPM: 120\nKey: Gm', text)

    def test_no_collaborators_keeps_plain_credit(self):
        profile = beat_seo.manual_profile(channel('mat-produced-this-one'))[1]
        track = beat_seo.track_input({k: v for k, v in self.TRACK.items() if k != 'collaborators'})
        text = beat_seo.description(profile, track, {}, 'https://x.test/a')
        self.assertIn('\nProd. MatWyre\n', text)

    def test_murray_parenthesized_credit_and_optional_music_info(self):
        profile = beat_seo.manual_profile(channel('murraybeats'))[1]
        track = beat_seo.track_input(self.TRACK)
        text = beat_seo.description(profile, track, {}, 'https://x.test/a')
        self.assertIn('\n(prod. matwyre x prodsantu x Other One)\n', text)
        self.assertIn('BPM: 120\nKey: Gm', text)
        for key, value in (('bpm', 120), ('key', 'Gm')):
            track = beat_seo.track_input({'id': 'TK1', 'title': 'Night Love', 'tags': [], key: value})
            text = beat_seo.description(profile, track, {}, 'https://x.test/a')
            self.assertIn('\n(prod. matwyre)\n', text)
            self.assertIn('BPM: 120' if key == 'bpm' else 'Key: Gm', text)
            self.assertNotIn('Key:' if key == 'bpm' else 'BPM:', text)
        text = beat_seo.description(profile, {'title': 'Night Love'}, {}, 'https://x.test/a')
        self.assertIn('Instagram: @matwyreoff\n\n(prod. matwyre)', text)

    def test_track_input_cleans_extras(self):
        track = beat_seo.track_input(dict(self.TRACK, collaborators=['MatWyre', '{url}x', 'ok', 'ok']))
        self.assertEqual(track['collaborators'], ['urlx', 'ok'])

    def test_catalog_parse_reads_bpm_key_collaborators(self):
        from core.beat_source import _music
        raw = {'metadata': {'bpm': 120, 'keyNote': {'value': 'Gm'}},
               'collaborators': [{'displayName': 'prodsantu'}, {'displayName': ''}]}
        self.assertEqual(_music(raw), (120, 'Gm', ('prodsantu',)))
        self.assertEqual(_music({'metadata': {'bpm': None, 'keyNote': None}}), (None, '', ()))
        self.assertEqual(_music({'metadata': {'bpm': None, 'keyNote': {'value': 'None'}}}),
                         (None, '', ()))



class IndieTitleCollaboratorsTests(unittest.TestCase):
    PROFILE = {'tags': ['indie pop'], 'description': ''}

    def titles(self, **extra):
        from core import beat_indie_seo
        track = dict({'id': 'TK7', 'title': 'Night Love', 'tags': ['indie pop']}, **extra)
        return [o['title'] for o in beat_indie_seo.variants(track, self.PROFILE)]

    def test_title_credits_collaborators(self):
        titles = self.titles(collaborators=['ProdSantu', 'Other'])
        self.assertTrue(all('(prod. matwyre x prodsantu' in t for t in titles))
        self.assertTrue(any('(prod. matwyre x prodsantu x other)' in t for t in titles))
        self.assertTrue(all(len(t) <= 100 for t in titles))

    def test_title_unchanged_without_collaborators(self):
        self.assertTrue(all('(prod. matwyre)' in t for t in self.titles()))

    def test_long_credit_never_squeezes_the_name(self):
        titles = self.titles(collaborators=['a' * 60, 'b' * 60, 'short'])
        self.assertTrue(all(len(t) <= 100 and 'Night Love' in t for t in titles))


if __name__ == '__main__':
    unittest.main()
