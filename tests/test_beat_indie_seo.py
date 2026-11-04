import unittest

from core import beat_indie_seo, beat_seo


class IndieSeoTests(unittest.TestCase):
    def profile(self):
        return {'title_mode': 'indie_v1',
                'title_template': '[FREE] {style} Type Beat - "{name}"',
                'tags': ['type beat', 'matwyre'], 'description': 'License: {url}'}

    def test_track_tags_control_the_style(self):
        for tags, expected in [(['indie pop'], 'Indie Pop'),
                               (['indie pop', 'indie rock'], 'Indie Pop x Indie Rock'),
                               (['indie pop', 'rock type beat'], 'Indie Pop x Indie Rock'),
                               (['indie bedroom'], 'Bedroom Pop'),
                               (['indie pop', 'bedroom'], 'Indie Pop x Bedroom Pop'),
                               (['guitar pop', 'juice wrld'], 'Guitar Pop'),
                               (['sad pop'], 'Sad Pop')]:
            self.assertEqual(beat_indie_seo.style({'tags': tags}), expected)
        with self.assertRaises(ValueError):
            beat_indie_seo.style({'tags': ['asap rocky', 'trap']})

    def test_snapshot_variations_keep_name_link_and_length(self):
        channel = {'id': 'poppyvibes', 'seo': self.profile()}
        job = {'id': 'job', 'channel': 'poppyvibes', 'track_id': 'TK25222454', 'cycle': 2}
        track = {'id': job['track_id'], 'title': 'Bleeding', 'tags': ['indie pop', 'indie rock']}
        snapshot, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-04T01:00:00+00:00')
        beat_seo.validate_snapshot(snapshot, job)
        titles = [o['title'] for o in snapshot['candidates']]
        self.assertEqual(len(set(titles)), 3)
        self.assertTrue(all('Bleeding' in t and 'Indie Rock' in t and len(t) <= 100 for t in titles))
        body = beat_seo.description(self.profile(), track, snapshot['candidates'][0], 'https://bsta.rs/example')
        self.assertEqual(body, 'License: https://bsta.rs/example')
        changed, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-04T01:00:00+00:00',
                                             previous_selected=snapshot['selected'])
        self.assertNotEqual(changed['selected']['title'], snapshot['selected']['title'])

    def test_long_names_are_bounded_and_order_is_stable(self):
        track = {'id': 'TK1', 'title': 'Long name ' * 40, 'tags': ['indie pop']}
        options = beat_indie_seo.variants(track, self.profile())
        self.assertEqual(options, beat_indie_seo.variants(track, self.profile()))
        self.assertTrue(all(len(o['title']) <= 100 for o in options))


if __name__ == '__main__':
    unittest.main()
