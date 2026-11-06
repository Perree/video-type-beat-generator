import unittest

from core import beat_melodic_seo as melodic, beat_seo
from core.beat_selection import eligible_tracks


class MelodicSeoTests(unittest.TestCase):
    def profile(self):
        return dict(title_mode='melodic_v1',
                    title_template='(FREE) {style} Type Beat - "{name}"',
                    tags=['type beat', 'matwyre'], description='{style}: {url}')

    def test_only_tagged_artists_appear(self):
        for tags, expected in [(['topoppgen', 'fattmack'], 'Fattmack x Topoppgen'),
                               (['juice wrld'], 'Juice WRLD'),
                               (['duki type beat', 'khea'], 'Duki x Khea'),
                               (['melodic'], 'Melodic'),
                               (['melodic hard type beat'], 'Melodic')]:
            self.assertEqual(melodic.style(dict(tags=tags)), expected)
        for tag in ['melodic house', 'melodic deep house', 'trap', 'not juice wrld']:
            with self.assertRaises(ValueError):
                melodic.style(dict(tags=[tag]))

    def test_snapshot_replay_and_repeat(self):
        track = dict(id='TK123', title='Call me', tags=['topoppgen'])
        job = dict(id='job', channel='test', track_id=track['id'], cycle=2)
        channel = dict(id='test', seo=self.profile())
        snapshot, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-06T12:00:00+00:00')
        beat_seo.validate_snapshot(snapshot, job)
        self.assertIn('Topoppgen Type Beat', snapshot['selected']['title'])
        self.assertNotIn('Fattmack', snapshot['selected']['title'])
        self.assertEqual(snapshot['selected']['description'], 'Topoppgen: {url}')
        changed, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-06T12:00:00+00:00',
                                             previous_selected=snapshot['selected'])
        self.assertNotEqual(snapshot['selected']['title'], changed['selected']['title'])

    def test_title_and_tag_budgets(self):
        track = dict(id='TK1', title='Long name ' * 40, tags=['juicewrld', 'melodic'])
        profile = self.profile()
        profile['tags'] = ['long tag ' + str(i) for i in range(50)]
        for option in melodic.variants(track, profile):
            self.assertLessEqual(len(option['title']), 100)
            self.assertLessEqual(sum(len(t) + (2 if ' ' in t else 0) + 1
                                     for t in option['tags']), 450)

    def test_selection_uses_exact_tags(self):
        channel = dict(selection_tags=['melodic', 'juice wrld'])
        tracks = [dict(id='1', tags=['melodic house']),
                  dict(id='2', tags=['melodic']), dict(id='3', tags=['juice wrld'])]
        self.assertEqual([t['id'] for t in eligible_tracks(channel, tracks)], ['2', '3'])
