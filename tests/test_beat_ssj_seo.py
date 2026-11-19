"""prodbySSJBeatzz ssj_v1: monthly main artist, alternating solo/duo titles, year by slot."""
from collections import Counter
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


# Tags name other artists on purpose: the title must ignore them.
TRACK = {'id': 'TK101', 'title': 'Lost Souls', 'tags': ['juice wrld type beat', 'iann dior'],
         'bpm': 140, 'key': 'C Minor'}
UNTAGGED = {'id': 'TK202', 'title': 'Rain', 'tags': ['melodic', 'piano']}


def profile(**changes):
    return dict(manual_profile(CHANNEL)[1], **changes)


def title_of(track, day):
    return beat_ssj_seo.variants(track, profile(), slot(day))[0]['title']


class SsjUnitTests(unittest.TestCase):
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
        mains = [beat_ssj_seo.plan(UNTAGGED, profile(), slot(day))['main']
                 for day in ('2026-12-01', '2026-12-31', '2027-01-01', '2027-02-01', '2027-03-01')]
        self.assertEqual(mains, ['Polo G', 'Polo G', 'Lil Tjay', 'Polo G', 'Lil Tjay'])

    def test_solo_duo_pattern_balances_years(self):
        self.assertEqual([beat_ssj_seo.is_duo(i) for i in range(8)],
                         [False, True, False, True, True, False, True, False])
        start = date(2026, 12, 1)
        by_variant = {True: Counter(), False: Counter()}
        for i in range(16):
            by_variant[beat_ssj_seo.is_duo(i)][beat_ssj_seo.year_for(start, start + timedelta(i))] += 1
        self.assertEqual(by_variant[True], by_variant[False])
        self.assertEqual([beat_ssj_seo.duo_count(i) for i in (0, 1, 2, 4, 8, 9, 17)],
                         [0, 0, 1, 2, 4, 4, 8])

    def test_first_titles(self):
        self.assertEqual([title_of(TRACK, d) for d in ('2026-12-01', '2026-12-02', '2026-12-03',
                                                        '2026-12-04', '2026-12-05')],
                         ['[FREE] Polo G Type Beat 2026 "Lost Souls"',
                          '[FREE] Polo G x Lil Tjay Type Beat "Lost Souls"',
                          '[FREE] Polo G Type Beat 2027 "Lost Souls"',
                          '[FREE] Polo G x Scorey Type Beat "Lost Souls"',
                          '[FREE] Polo G x Sleepy Hallow Type Beat 2026 "Lost Souls"'])

    def test_second_ignores_tags_and_follows_rotation(self):
        days = [date(2026, 12, 1) + timedelta(i) for i in range(30)]
        tagged = [beat_ssj_seo.plan(TRACK, profile(), slot(d.isoformat()))['second'] for d in days]
        plain = [beat_ssj_seo.plan(UNTAGGED, profile(), slot(d.isoformat()))['second'] for d in days]
        self.assertEqual(tagged, plain)
        self.assertNotIn('Iann Dior', tagged)
        duos = [s for s in tagged if s]
        self.assertEqual(duos[:9], ['Lil Tjay', 'Scorey', 'Sleepy Hallow', 'Toosii', 'Juice WRLD',
                                    'Lil Tjay', 'Scorey', 'Sleepy Hallow', 'Toosii'])

    def test_juice_wrld_every_other_round_and_main_replaced(self):
        self.assertEqual(beat_ssj_seo.partner_cycle(profile(), 'Polo G'),
                         ['Lil Tjay', 'Scorey', 'Sleepy Hallow', 'Toosii', 'Juice WRLD',
                          'Lil Tjay', 'Scorey', 'Sleepy Hallow', 'Toosii'])
        self.assertEqual(beat_ssj_seo.partner_cycle(profile(), 'Lil Tjay'),
                         ['Polo G', 'Scorey', 'Sleepy Hallow', 'Toosii', 'Juice WRLD',
                          'Polo G', 'Scorey', 'Sleepy Hallow', 'Toosii'])
        every = profile(second_every={})
        self.assertEqual(len(beat_ssj_seo.partner_cycle(every, 'Polo G')), 5)

    def test_year_rotation_and_2026_retired_in_2027(self):
        start = date(2026, 12, 1)
        days = [start + timedelta(days=i) for i in range(8)]
        self.assertEqual([beat_ssj_seo.year_for(start, d) for d in days],
                         [' 2026', '', ' 2027', '', ' 2026', '', ' 2027', ''])
        self.assertEqual(beat_ssj_seo.year_for(start, date(2027, 1, 2)), '')  # former 2026 slot
        self.assertEqual(beat_ssj_seo.year_for(start, date(2027, 1, 4)), ' 2027')

    def test_tags_follow_title_artists(self):
        solo = beat_ssj_seo.variants(TRACK, profile(), slot('2026-12-01'))[0]['tags']
        self.assertEqual(solo[:2], ['polo g type beat', 'free polo g type beat'])
        duo = beat_ssj_seo.variants(TRACK, profile(), slot('2026-12-02'))[0]['tags']
        self.assertEqual(duo[:3], ['polo g type beat', 'lil tjay type beat', 'polo g x lil tjay type beat'])
        self.assertFalse(any('juice' in t for t in solo + duo))
        long_name = dict(TRACK, title='x' * 300)
        self.assertLessEqual(len(beat_ssj_seo.variants(long_name, profile(),
                                                       slot('2026-12-02'))[0]['title']), 100)

    def test_description_structure(self):
        snapshot, _ = build_snapshot(job(TRACK, slot('2026-12-02')), TRACK, CHANNEL, NOW)
        text = snapshot['selected']['description']
        self.assertTrue(text.startswith('Polo G x Lil Tjay Type Beat - "Lost Souls"\n'))
        for part in ('{url}', 'https://www.beatstars.com/matwyre', 'BPM: 140', 'Key: C Minor',
                     'Prod. MatWyre', 'NON-PROFIT', 'lease', 'Content ID',
                     'polo g x lil tjay type beat', 'lil tjay instrumental',
                     '#PoloGTypeBeat #LilTjayTypeBeat'):
            self.assertIn(part, text)
        self.assertNotIn('{', text.replace('{url}', ''))
        solo, _ = build_snapshot(job(TRACK, slot('2026-12-01')), TRACK, CHANNEL, NOW)
        text = solo['selected']['description']
        self.assertTrue(text.startswith('Polo G Type Beat 2026 - "Lost Souls"\n'))
        self.assertNotIn(' x ', text.split('\n')[0])
        self.assertIn('#PoloGTypeBeat #TypeBeat', text)
        self.assertNotIn('lil tjay', text)
        collab = dict(TRACK, collaborators=['Nomad'])
        snapshot, _ = build_snapshot(job(collab, slot('2026-12-02')), collab, CHANNEL, NOW)
        self.assertIn('\nProd. MatWyre x Nomad\n', snapshot['selected']['description'])

    def test_snapshot_records_plan_and_replays(self):
        when = slot('2027-01-03')
        snapshot, _ = build_snapshot(job(TRACK, when), TRACK, CHANNEL, NOW)
        self.assertEqual(snapshot['experiment'], {
            'version': 'ssj_v1', 'variant': 'duo', 'main': 'Lil Tjay', 'second': 'Sleepy Hallow',
            'year': '', 'test_month': 2, 'slot_index': 33, 'publication_day': '2027-01-03'})
        self.assertEqual(snapshot['selected']['title'],
                         '[FREE] Lil Tjay x Sleepy Hallow Type Beat "Lost Souls"')
        self.assertEqual(validate_snapshot(snapshot, job(TRACK, when)), snapshot)
        forged = deepcopy(snapshot)
        forged['experiment']['variant'] = 'solo'
        with self.assertRaises(ValueError):
            validate_snapshot(forged, job(TRACK, when))
        solo, _ = build_snapshot(job(TRACK, slot('2027-01-01')), TRACK, CHANNEL, NOW)
        self.assertEqual((solo['experiment']['variant'], solo['experiment']['second']), ('solo', None))
        repeat_job = job(TRACK, when, cycle=2)
        repeat, _ = build_snapshot(repeat_job, TRACK, CHANNEL, NOW,
                                   previous_selected=snapshot['selected'])
        self.assertEqual(repeat['selected']['title'], snapshot['selected']['title'])
        self.assertNotEqual(repeat['selected']['tags'], snapshot['selected']['tags'])
        self.assertEqual(validate_snapshot(repeat, repeat_job), repeat)

    def test_profile_validation(self):
        for change in ({'main_rotation': []}, {'main_rotation': ['Polo G', 'Polo G']},
                       {'main_rotation': ['Polo {G}']}, {'second_rotation': []},
                       {'second_rotation': ['Polo G']},  # month 1 would have no partner
                       {'second_every': {'Drake': 2}}, {'second_every': {'Juice WRLD': 0}},
                       {'second_every': []}, {'test_start': '2026-13-01'}, {'test_start': 20261201},
                       {'title_template': '[FREE] {main} & {second} Type Beat{year} "{name}"'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                manual_profile(dict(CHANNEL, seo=dict(CHANNEL['seo'], **change)))
        for key in beat_ssj_seo.EXTRA_FIELDS:
            missing = {k: v for k, v in CHANNEL['seo'].items() if k != key}
            with self.subTest(missing=key), self.assertRaises(ValueError):
                manual_profile(dict(CHANNEL, seo=missing))
        other = dict(CHANNEL['seo'], title_mode='melodic_fixed_v1')
        with self.assertRaises(ValueError):  # extra keys stay ssj-only
            manual_profile(dict(CHANNEL, seo=other))


class SsjSimulationTests(unittest.TestCase):
    def test_sixty_daily_slots(self):
        start = date.fromisoformat(START)
        tracks = [TRACK, UNTAGGED, dict(TRACK, id='TK303', title='Hollow', tags=['lil tjay type beat']),
                  dict(UNTAGGED, id='TK404', title='Fade', tags=['toosii', 'scorey type beat'])]
        title = re.compile(r'\[FREE\] (.+?)(?: x (.+))? Type Beat( 2026| 2027)? "(.+)"')
        mains, variants, seconds = {}, Counter(), {1: Counter(), 2: Counter()}
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
            self.assertEqual(plan['variant'], 'duo' if second else 'solo')
            self.assertNotEqual(main, second)
            self.assertLessEqual(len(selected['title']), 100)
            if day.year >= 2027:
                self.assertNotIn('2026', selected['title'])
                self.assertNotIn('2026', selected['description'])
            mains.setdefault(plan['test_month'], set()).add(main)
            variants[plan['variant']] += 1
            if second:
                seconds[plan['test_month']][second] += 1
        self.assertEqual(mains, {1: {'Polo G'}, 2: {'Lil Tjay'}})
        self.assertEqual(variants, {'solo': 30, 'duo': 30})
        self.assertNotIn('Lil Tjay', seconds[2])
        self.assertIn('Polo G', seconds[2])
        self.assertNotIn('Polo G', seconds[1])
        self.assertEqual(set(seconds[1]), {'Lil Tjay', 'Scorey', 'Sleepy Hallow', 'Toosii', 'Juice WRLD'})
        juice = seconds[1]['Juice WRLD'] + seconds[2]['Juice WRLD']
        self.assertLess(juice, min(seconds[1]['Scorey'] + seconds[2]['Scorey'],
                                   seconds[1]['Toosii'] + seconds[2]['Toosii']))


if __name__ == '__main__':
    unittest.main()
