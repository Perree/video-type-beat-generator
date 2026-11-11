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
        self.assertEqual(len(set(titles)), 4)
        self.assertIn('[FREE] Indie Rock x Bedroom Pop Type Beat - "Bleeding" (prod. matwyre)', titles)
        self.assertTrue(all('Bleeding' in t and 'Indie Rock' in t and len(t) <= 100 for t in titles))
        body = beat_seo.description(self.profile(), track, snapshot['candidates'][0], 'https://bsta.rs/example')
        self.assertEqual(body, 'License: https://bsta.rs/example')
        changed, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-04T01:00:00+00:00',
                                             previous_selected=snapshot['selected'])
        self.assertNotEqual(changed['selected']['title'], snapshot['selected']['title'])

    def test_winner_leads_three_of_four_and_extensions_keep_its_structure(self):
        winner = '[FREE] Indie Rock x Bedroom Pop Type Beat - "Bleeding" (prod. matwyre)'
        firsts = []
        for i in range(400):
            track = {'id': f'TK{i}', 'title': 'Bleeding', 'tags': ['indie pop']}
            titles = [o['title'] for o in beat_indie_seo.variants(track, self.profile())]
            self.assertIn(winner, titles)
            self.assertTrue(all(t.startswith('[FREE] Indie Rock x Bedroom Pop Type Beat') for t in titles))
            firsts.append(titles[0] == winner)
        self.assertTrue(0.65 < sum(firsts) / len(firsts) < 0.85)
        other = beat_indie_seo.variants({'id': 'TK1', 'title': 'Bleeding', 'tags': ['sad pop']}, self.profile())
        self.assertTrue(all(o['title'].startswith('[FREE] Sad Pop Type Beat') and '(prod. matwyre)' in o['title']
                            for o in other))

    def test_historical_indie_snapshot_replays(self):
        channel = {'id': 'poppyvibes', 'seo': self.profile()}
        track = {'id': 'TK25222454', 'title': 'Bleeding', 'tags': ['indie pop', 'indie rock']}
        job = {'id': 'job', 'channel': channel['id'], 'track_id': track['id'], 'cycle': 1}
        snapshot, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-04T01:00:00+00:00')
        tags = ['indie pop x indie rock type beat', 'type beat', 'matwyre']
        snapshot['candidates'] = [dict(title=title, tags=tags) for title in (
            '[FREE] "Bleeding" | Indie Pop x Indie Rock Type Beat',
            '[FREE] Indie Pop x Indie Rock Instrumental - "Bleeding"',
            '[FREE] Indie Pop x Indie Rock Type Beat - "Bleeding"')]
        snapshot['selected'] = dict(snapshot['candidates'][0], description='License: {url}')
        del snapshot['sha256']
        snapshot['sha256'] = beat_seo.digest(snapshot)
        self.assertEqual(beat_seo.validate_snapshot(snapshot, job), snapshot)

    def test_long_names_are_bounded_and_order_is_stable(self):
        track = {'id': 'TK1', 'title': 'Long name ' * 40, 'tags': ['indie pop']}
        options = beat_indie_seo.variants(track, self.profile())
        self.assertEqual(options, beat_indie_seo.variants(track, self.profile()))
        self.assertTrue(all(len(o['title']) <= 100 for o in options))


if __name__ == '__main__':
    unittest.main()
