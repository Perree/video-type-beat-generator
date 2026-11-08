"""New-channel selection, honest metadata and replay do not affect legacy modes."""
import unittest
from core import beat_seo
from core.beat_selection import eligible_tracks, require_track, TrackNotMatching
from core.beat_templates import apply_channel_templates
from core.beat_share import publication_link


class GuitarTests(unittest.TestCase):
    def channel(self):
        return {'id': 'guitar-trap', 'selection_tags': ['guitar-trap:v1'],
                'use_channel_templates': True, 'seo': {
                    'title_mode': 'guitar_v1',
                    'title_template': '[FREE] {style} Type Beat - "{name}"',
                    'description': '{title}\n{url}\n{music_info}\n{credits}\n{guitar_hashtags}',
                    'tags': ['type beat', 'matwyre']}}

    def snapshot(self, tags, title='My Song', previous=None):
        ch = self.channel()
        apply_channel_templates(ch, {'title_template': ch['seo']['title_template'],
                                    'description_template': ch['seo']['description']})
        job = {'id': 'job', 'channel': ch['id'], 'track_id': 'TK1', 'cycle': 2}
        snap, _ = beat_seo.build_snapshot(job, {'id': 'TK1', 'title': title, 'tags': tags},
                                         ch, '2026-11-07T18:00:00-03:00', previous_selected=previous)
        beat_seo.validate_snapshot(snap, job)
        return snap['selected']

    def test_selection_and_legacy_boundary(self):
        good = [['Juice WRLD'], ['juicewrld type beat'], ['GUITAR'], ['trap guitar'],
                ['acoustic guitar'], ['emo rap'], ['pain beat'], ['melodic trap'], ['Nino Paid']]
        bad = [['sad'], ['emotional'], ['trap'], ['melodic house'], ['guitar pop'],
               ['afro guitar'], ['guitar', 'reggaeton'], ['juice wrldish'], ['guitarist']]
        for tags in good + bad:
            track = {'id': 'TK1', 'tags': tags}
            self.assertEqual(bool(eligible_tracks(self.channel(), [track])), tags in good, tags)
            if tags in bad:
                with self.assertRaises(TrackNotMatching):
                    require_track(self.channel(), track)
        self.assertEqual(eligible_tracks({'selection_tags': ['guitar']}, [{'tags': ['trap guitar']}]), [])
        self.assertEqual(eligible_tracks(self.channel(), [{'tags': None}, {},
                         {'id': 'TK1', 'tags': ['guitar'], 'active': False}]), [])

    def test_artists_instruments_and_moods_are_not_invented(self):
        for tags, style in [(['juice wrld'], 'Juice WRLD'),
                            (['juice wrld', 'guitar'], 'Guitar x Juice WRLD'),
                            (['guitar', 'sad'], 'Sad Guitar'),
                            (['guitar', 'trap'], 'Guitar Trap'),
                            (['guitar', 'hurricane wisdom', 'nino paid'], 'Guitar x Hurricane Wisdom x Nino Paid'),
                            (['emo rap'], 'Emo Rap')]:
            selected = self.snapshot(tags)
            self.assertEqual(selected['title'], f'[FREE] {style} Type Beat - "My Song"')
            self.assertTrue(selected['description'].startswith(selected['title']))
        plain = self.snapshot(['juice wrld'])
        self.assertNotIn('guitar', ','.join(plain['tags']))
        self.assertNotIn('Nino', plain['description'])
        self.assertNotIn('BPM:', plain['description'])

    def test_name_music_credit_limits_and_repeat(self):
        s = self.snapshot(['guitar', 'juice wrld'],
                          'My Song - 160bpm - key A Sharp Minor (prod. @matwyre x @guest)')
        self.assertTrue(s['title'].endswith('"My Song"'))
        self.assertIn('BPM: 160', s['description'])
        self.assertIn('Key: A Sharp Minor', s['description'])
        self.assertIn('@guest', s['description'])
        long = self.snapshot(['guitar', 'Hurricane Wisdom', 'Nino Paid'], 'Name ' * 80)
        self.assertLessEqual(len(long['title']), 100)
        self.assertLessEqual(len(','.join(long['tags'])) + 2 * sum(' ' in t for t in long['tags']), 500)
        again = self.snapshot(['guitar', 'Hurricane Wisdom', 'Nino Paid'], 'Name ' * 80, long)
        self.assertNotEqual(long['tags'], again['tags'])

    def test_individual_link_required(self):
        track = {'id': 'TK1', 'title': 'My Song', 'url': 'https://www.beatstars.com/beat/my-song-1'}
        self.assertEqual(publication_link(self.channel(), track, None), track['url'])
        self.assertEqual(publication_link(self.channel(), track, 'https://bsta.rs/abcd'), 'https://bsta.rs/abcd')
        with self.assertRaisesRegex(ValueError, 'beat_individual_link_missing'):
            publication_link(self.channel(), dict(track, url='https://www.beatstars.com/beat/other-2'), None)


if __name__ == '__main__':
    unittest.main()
