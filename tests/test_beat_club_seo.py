import json
from pathlib import Path
import unittest
from core import beat_club_seo, beat_seo
from core.beat_selection import eligible_tracks
from core.beat_templates import apply_channel_templates


class ClubSeoTests(unittest.TestCase):
    def test_exact_genres_and_no_artist_inference(self):
        for tags, expected in [(['afro house'], 'Afro House'), (['melodic deep house'], 'Melodic Deep House'),
                               (['melodic house'], 'Melodic House'), (['deep house'], 'Deep House'),
                               (['house', 'club banger'], 'House x Club Banger'), (['EDM'], 'EDM'),
                               (['club'], 'Club'), (['latin house'], 'Latin House'),
                               (['HOUSE', 'makar'], 'House')]:
            self.assertEqual(beat_club_seo.style({'tags': tags}), expected)
        for tag in ('makar', 'afrobeat', 'jersey club', 'dancehall'):
            with self.assertRaises(ValueError): beat_club_seo.style({'tags': [tag]})

    def test_channel_snapshot_and_repeat(self):
        ch = json.loads((Path(__file__).resolve().parents[1] / 'docs/kiezah.channel.json').read_text(encoding='utf-8'))
        self.assertEqual(ch['interval_schedule']['days'], 2)
        ch['seo'].update(title_mode='club_v1', title_template='[FREE] {style} Type Beat - "{name}"')
        apply_channel_templates(ch, {'title_template': ch['seo']['title_template'], 'description_template': ch['seo']['description']})
        self.assertEqual(eligible_tracks(ch, [{'id':'TK2','tags':['makar']}]), [])
        for name in ('Makar Type Beat - MOËT', 'N' * 400):
            track = {'id': 'TK1', 'title': name, 'tags': ['melodic house']}
            job = {'id': 'job', 'channel': ch['id'], 'track_id': track['id'], 'cycle': 2}
            snapshot, _ = beat_seo.build_snapshot(job, track, ch, '2026-11-03T23:00:00-03:00')
            beat_seo.validate_snapshot(snapshot, job)
            self.assertEqual(len(snapshot['candidates']), 3)
            self.assertTrue(all(len(v['title']) <= 100 and 'Makar' not in v['title'] for v in snapshot['candidates']))
            again, _ = beat_seo.build_snapshot(job, track, ch, '2026-11-03T23:00:00-03:00', previous_selected=snapshot['selected'])
            self.assertNotEqual(again['selected']['title'], snapshot['selected']['title'])
            body = beat_seo.description(ch['seo'], track, snapshot['selected'], 'https://bsta.rs/example')
            self.assertNotIn('{url}', body)
            self.assertIn('Prod. MatWyre', body)
            self.assertNotIn('wyrebeats.vercel.app', body)


if __name__ == '__main__': unittest.main()
