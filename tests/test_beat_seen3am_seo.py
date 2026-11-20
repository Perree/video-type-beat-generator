import json
import unittest
from copy import deepcopy
from pathlib import Path

from core import beat_seen3am_seo, beat_seo
from core.beat_schema import migrate
from core.beat_selection import eligible_tracks
from core.beat_settings import simulate
from core.beat_templates import apply_channel_templates
from core.beat_visual import options

NOV = '2026-11-21T13:00:00+00:00'   # 10:00 Buenos Aires
JAN = '2027-01-05T13:00:00+00:00'


class Seen3amTests(unittest.TestCase):
    def setUp(self):
        self.channel = json.loads((Path(__file__).resolve().parents[1] /
                                   'docs/seen3am.channel.json').read_text(encoding='utf-8'))
        self.track = dict(id='TK20772389', title='Hall of fame | Jerk x New Jazz x West Coast Type Beat 2025',
                          tags=['new jazz', 'jerk'], bpm=140, key='Fm', collaborators=['mlodyhubson', 'MatWyre'])

    def job(self, slot, cycle=1):
        return dict(id='job', channel='seen3am', track_id=self.track['id'], cycle=cycle, slot=slot)

    def test_profile_is_valid_and_daily_at_ten(self):
        migrate(dict(channels=[self.channel]), 'config')
        beat_seo.manual_profile(self.channel)
        self.assertEqual([(s['weekday'], s['hour'], s['minute']) for s in self.channel['slots']],
                         [(d, 10, 0) for d in range(7)])
        options(self.channel['visual'])
        visual = self.channel['visual']
        self.assertEqual((visual['mode'], visual['image_fit'], visual['custom_thumbnail']),
                         ('image', 'contain', False))

    def test_selection_by_style_tags_and_destino_excluded(self):
        tracks = [dict(id='TK' + str(i), title='x', tags=[tag]) for i, tag in enumerate(
            ['Plugg', 'pluggnb', 'New Jazz', 'west coast', 'west coast type beat', 'rnb', 'hyperpop'])]
        tracks.append(dict(id='TK26644857', title='plugg x suei type beat 2027 - Destino', tags=['plugg']))
        self.assertEqual([t['id'] for t in eligible_tracks(self.channel, tracks)],
                         ['TK0', 'TK1', 'TK2', 'TK3', 'TK4'])

    def test_title_year_follows_publication_day(self):
        for slot, year in ((NOV, '2027'), (JAN, '2027'), ('2027-11-02T13:00:00+00:00', '2028'),
                           ('2027-03-01T13:00:00+00:00', '2027')):
            option = beat_seen3am_seo.variants(self.track, self.channel['seo'], slot)[0]
            self.assertEqual(option['title'], f'(FREE) plugg x suei type beat {year} - "hall of fame"')
            self.assertIn(f'plugg x suei type beat {year}', option['tags'])
            tags = option['tags']
            self.assertLessEqual(sum(len(t) + (2 if ' ' in t else 0) + 1 for t in tags), 450)

    def test_snapshot_description_link_music_and_collaborators(self):
        job = self.job(NOV)
        snapshot, _ = beat_seo.build_snapshot(job, self.track, self.channel, '2026-11-20T18:00:00+00:00')
        beat_seo.validate_snapshot(snapshot, job)
        self.assertEqual(snapshot['experiment'], dict(year='2027', publication_day='2026-11-21',
                                                      version='seen3am_v1'))
        resolved = beat_seo.description(self.channel['seo'], self.track, snapshot['selected'], 'https://bsta.rs/x')
        self.assertTrue(resolved.startswith('🛒 Buy this beat here (Download): https://bsta.rs/x\n'))
        self.assertIn('BPM: 140\nKEY: Fm\nProd. by seen3am x mlodyhubson\n', resolved)
        self.assertNotIn('MatWyre', resolved.split('Prod. by')[1].split('\n')[0])
        self.assertNotIn('{', resolved)
        self.assertLessEqual(len(resolved), 5000)
        repeat, _ = beat_seo.build_snapshot(self.job(NOV, 2), self.track, self.channel,
                                            '2026-11-20T18:00:00+00:00', previous_selected=snapshot['selected'])
        self.assertEqual(repeat['selected']['title'], snapshot['selected']['title'])
        self.assertNotEqual(repeat['selected']['tags'], snapshot['selected']['tags'])

    def test_without_bpm_key_or_collaborators(self):
        track = dict(id='TK1', title='Waska', tags=['new jazz'])
        option = beat_seen3am_seo.variants(track, self.channel['seo'], NOV)[0]
        text = beat_seen3am_seo.description(self.channel['seo'], track, option)
        self.assertIn('SEND LOOPS: matwyreloops@gmail.com\n\nProd. by seen3am\n', text)

    def test_saved_channel_templates_accept_seen3am_tokens(self):
        channel = dict(deepcopy(self.channel), use_channel_templates=True)
        saved = dict(title_template=channel['seo']['title_template'],
                     description_template=channel['seo']['description'])
        self.assertEqual(apply_channel_templates(channel, saved)['seo']['description'],
                         self.channel['seo']['description'])

    def test_paused_has_no_jobs_and_active_schedules_ten_am(self):
        tracks = [dict(id='TK5', title='Waska', tags=['new jazz'])]
        now = '2026-11-20T15:00:00-03:00'
        self.assertEqual(simulate(dict(channels=[dict(self.channel, active=False)]), tracks, now=now)['jobs'], [])
        active = dict(channels=[dict(self.channel, active=True)])
        jobs = simulate(active, tracks, now=now)['jobs']
        self.assertTrue(jobs)
        self.assertTrue(all(j['slot'].endswith('T13:00:00+00:00') or 'T10:00:00-03:00' in j['slot']
                            for j in jobs), [j['slot'] for j in jobs])


if __name__ == '__main__':
    unittest.main()
