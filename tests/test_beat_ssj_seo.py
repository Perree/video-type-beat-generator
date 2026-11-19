"""prodbySSJBeatzz ssj_v1: monthly main artist, tag-backed second artist, year by slot."""
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import re
import unittest

from core import beat_ssj_seo
from core.beat_schema import identity
from core.beat_seo import build_snapshot, manual_profile, validate_snapshot

NOW = '2026-11-19T12:00:00+00:00'
CHANNEL = json.loads(Path('docs/prodbyssjbeatzz.channel.json').read_text(encoding='utf-8'))
START = CHANNEL['seo']['test_start']


def slot(day, hour=21):
    """18:00 in Buenos Aires (UTC-3)."""
    return datetime.fromisoformat(f'{day}T{hour:02d}:00:00+00:00').isoformat()


def job(track, when, cycle=1):
    return {'id': identity(track['id'], CHANNEL['id'], cycle, when), 'track_id': track['id'],
            'channel': CHANNEL['id'], 'cycle': cycle, 'slot': when, 'status': 'planned'}


TRACK = {'id': 'TK101', 'title': 'Lost Souls', 'tags': ['sad', 'juice wrld type beat', 'polo g'],
         'bpm': 140, 'key': 'C Minor'}
UNTAGGED = {'id': 'TK202', 'title': 'Rain', 'tags': ['melodic', 'piano']}


class SsjUnitTests(unittest.TestCase):
    def profile(self, **changes):
        return dict(manual_profile(CHANNEL)[1], **changes)

    def test_test_month_counts_monthly_anniversaries(self):
        start = date(2026, 12, 1)
        self.assertEqual(beat_ssj_seo.test_month(start, date(2026, 11, 20)), 1)  # before start
        self.assertEqual(beat_ssj_seo.test_month(start, date(2026, 12, 31)), 1)
        self.assertEqual(beat_ssj_seo.test_month(start, date(2027, 1, 1)), 2)
        self.assertEqual(beat_ssj_seo.test_month(start, date(2027, 2, 1)), 3)
        late = date(2027, 1, 31)
        self.assertEqual(beat_ssj_seo.test_month(late, date(2027, 2, 27)), 1)
        self.assertEqual(beat_ssj_seo.test_month(late, date(2027, 2, 28)), 2)  # clamped day

    def test_main_artist_alternates_by_month(self):
        profile = self.profile()
        mains = [beat_ssj_seo.plan(UNTAGGED, profile, slot(day))['main']
                 for day in ('2026-12-01', '2026-12-31', '2027-01-01', '2027-02-01', '2027-03-01')]
        self.assertEqual(mains, ['Polo G', 'Polo G', 'Lil Tjay', 'Polo G', 'Lil Tjay'])

    def test_second_artist_comes_from_real_tags_without_repeating_main(self):
        profile = self.profile()
        dec = beat_ssj_seo.plan(TRACK, profile, slot('2026-12-05'))
        self.assertEqual((dec['main'], dec['second'], dec['second_source']),
                         ('Polo G', 'Juice WRLD', 'tags'))
        only_main = dict(TRACK, tags=['polo g type beat', 'polog', 'Iann Dior Type Beat'])
        self.assertEqual(beat_ssj_seo.second_artist(only_main, 'Polo G'), ('Iann Dior', 'tags'))
        laroi = dict(TRACK, tags=['Laroi Type Beat'])
        self.assertEqual(beat_ssj_seo.second_artist(laroi, 'Polo G'), ('The Kid Laroi', 'tags'))

    def test_second_artist_fallback_is_stable_and_never_main(self):
        for main in ('Polo G', 'Lil Tjay'):
            name, source = beat_ssj_seo.second_artist(UNTAGGED, main)
            self.assertEqual(source, 'rotation')
            self.assertNotEqual(name, main)
            self.assertIn(name, beat_ssj_seo.NAMES)
            self.assertEqual(beat_ssj_seo.second_artist(UNTAGGED, main)[0], name)
        seconds = {beat_ssj_seo.second_artist(dict(UNTAGGED, id=f'TK{i}'), 'Polo G')[0]
                   for i in range(60)}
        self.assertGreater(len(seconds), 3)

    def test_year_rotation_and_2026_retired_in_2027(self):
        start = date(2026, 12, 1)
        days = [start + timedelta(days=i) for i in range(8)]
        self.assertEqual([beat_ssj_seo.year_for(start, d) for d in days],
                         [' 2026', '', ' 2027', '', ' 2026', '', ' 2027', ''])
        self.assertEqual(beat_ssj_seo.year_for(start, date(2027, 1, 2)), '')  # former 2026 slot
        self.assertEqual(beat_ssj_seo.year_for(start, date(2027, 1, 4)), ' 2027')

    def test_title_format_and_tags(self):
        option = beat_ssj_seo.variants(TRACK, self.profile(), slot('2026-12-01'))[0]
        self.assertEqual(option['title'], '[FREE] Polo G x Juice WRLD Type Beat 2026 "Lost Souls"')
        self.assertEqual(option['tags'][:3], ['polo g type beat', 'juice wrld type beat',
                                              'polo g x juice wrld type beat'])
        long_name = dict(TRACK, title='x' * 300)
        self.assertLessEqual(len(beat_ssj_seo.variants(long_name, self.profile(),
                                                       slot('2026-12-01'))[0]['title']), 100)

    def test_description_structure(self):
        snapshot, _ = build_snapshot(job(TRACK, slot('2026-12-02')), TRACK, CHANNEL, NOW)
        text = snapshot['selected']['description']
        self.assertTrue(text.startswith('Polo G x Juice WRLD Type Beat - "Lost Souls"\n'))
        for part in ('{url}', 'https://www.beatstars.com/matwyre', 'BPM: 140', 'Key: C Minor',
                     'Prod. MatWyre', 'NON-PROFIT', 'lease', 'Content ID',
                     'polo g x juice wrld type beat', 'juice wrld instrumental',
                     '#PoloGTypeBeat #JuiceWRLDTypeBeat'):
            self.assertIn(part, text)
        self.assertNotIn('{', text.replace('{url}', ''))
        collab = dict(TRACK, collaborators=['Nomad'])
        snapshot, _ = build_snapshot(job(collab, slot('2026-12-02')), collab, CHANNEL, NOW)
        self.assertIn('\nProd. MatWyre x Nomad\n', snapshot['selected']['description'])

    def test_snapshot_records_plan_and_replays(self):
        when = slot('2027-01-03')
        snapshot, _ = build_snapshot(job(TRACK, when), TRACK, CHANNEL, NOW)
        self.assertEqual(snapshot['experiment'], {
            'version': 'ssj_v1', 'main': 'Lil Tjay', 'second': 'Juice WRLD', 'second_source': 'tags',
            'year': '', 'test_month': 2, 'publication_day': '2027-01-03'})
        self.assertEqual(validate_snapshot(snapshot, job(TRACK, when)), snapshot)
        forged = deepcopy(snapshot)
        forged['experiment']['main'] = 'Polo G'
        with self.assertRaises(ValueError):
            validate_snapshot(forged, job(TRACK, when))
        repeat_job = job(TRACK, when, cycle=2)
        repeat, _ = build_snapshot(repeat_job, TRACK, CHANNEL, NOW,
                                   previous_selected=snapshot['selected'])
        self.assertEqual(repeat['selected']['title'], snapshot['selected']['title'])
        self.assertNotEqual(repeat['selected']['tags'], snapshot['selected']['tags'])
        self.assertEqual(validate_snapshot(repeat, repeat_job), repeat)

    def test_profile_validation(self):
        for change in ({'main_rotation': []}, {'main_rotation': ['Drake']},
                       {'main_rotation': ['Polo G', 'Polo G']}, {'test_start': '2026-13-01'},
                       {'test_start': 20261201}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                manual_profile(dict(CHANNEL, seo=dict(CHANNEL['seo'], **change)))
        missing = {k: v for k, v in CHANNEL['seo'].items() if k != 'test_start'}
        with self.assertRaises(ValueError):
            manual_profile(dict(CHANNEL, seo=missing))
        other = dict(CHANNEL['seo'], title_mode='melodic_fixed_v1')
        with self.assertRaises(ValueError):  # extra keys stay ssj-only
            manual_profile(dict(CHANNEL, seo=other))


class SsjSimulationTests(unittest.TestCase):
    def test_sixty_daily_slots(self):
        start = date.fromisoformat(START)
        tracks = [TRACK, UNTAGGED, dict(TRACK, id='TK303', title='Hollow', tags=['lil tjay type beat']),
                  dict(UNTAGGED, id='TK404', title='Fade', tags=['toosii', 'scorey type beat'])]
        title = re.compile(r'\[FREE\] (.+) x (.+) Type Beat( 2026| 2027)? "(.+)"')
        mains = {}
        for i in range(60):
            day = start + timedelta(days=i)
            track = tracks[i % len(tracks)]
            when = slot(day.isoformat())
            snapshot, _ = build_snapshot(job(track, when), track, CHANNEL, NOW)
            self.assertEqual(validate_snapshot(snapshot, job(track, when)), snapshot)
            selected, plan = snapshot['selected'], snapshot['experiment']
            match = title.fullmatch(selected['title'])
            self.assertIsNotNone(match, selected['title'])
            main, second = match.group(1), match.group(2)
            self.assertEqual((main, second), (plan['main'], plan['second']))
            self.assertNotEqual(main, second)
            self.assertIn(second, beat_ssj_seo.NAMES)
            self.assertLessEqual(len(selected['title']), 100)
            if day.year >= 2027:
                self.assertNotIn('2026', selected['title'])
                self.assertNotIn('2026', selected['description'])
            mains.setdefault(plan['test_month'], set()).add(main)
        self.assertEqual(mains, {1: {'Polo G'}, 2: {'Lil Tjay'}})


if __name__ == '__main__':
    unittest.main()
