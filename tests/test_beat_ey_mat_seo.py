"""ey mat ey_mat_v1: own vs. competitor title format, year from the publication day."""
from copy import deepcopy
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import unittest

from core import beat_ey_mat_seo
from core.beat_schema import identity
from core.beat_seo import build_snapshot, fill_chapters, manual_profile, validate_snapshot

NOW = '2026-11-19T12:00:00+00:00'
DOC = json.loads(Path('docs/ey-mat.seo.json').read_text(encoding='utf-8'))
CID = DOC['channel_id']
START = '2026-11-19'


def channel(**changes):
    return {'id': CID, 'seo': dict(DOC['seo'], **dict({'test_start': START}, **changes))}


CHANNEL = channel()


def slot(day, hour=23):
    """20:00 in Buenos Aires (UTC-3)."""
    return datetime.fromisoformat(f'{day}T{hour:02d}:00:00+00:00').isoformat()


def job(track, when, cycle=1):
    return {'id': identity(track['id'], CID, cycle, when), 'track_id': track['id'],
            'channel': CID, 'cycle': cycle, 'slot': when, 'status': 'planned'}


TRACK = {'id': 'TK101', 'title': 'Lost Souls', 'tags': ['juice wrld type beat'], 'bpm': 160,
         'key': 'A Sharp Minor'}
PLAIN = {'id': 'TK202', 'title': 'Rain', 'tags': ['melodic']}
OWN = '[FREE] Juice WRLD x Melodic Type Beat {} "Lost Souls"'
COMP = '[FREE] Juice WRLD Type Beat {} - "Lost Souls"'


def profile(ch=CHANNEL):
    return manual_profile(ch)[1]


def title_of(day, track=TRACK):
    return beat_ey_mat_seo.variants(track, profile(), slot(day))[0]['title']


class EyMatTitleTests(unittest.TestCase):
    def test_november_alternates_formats_and_both_years(self):
        days = [(date(2026, 11, 19) + timedelta(i)).isoformat() for i in range(4)]
        self.assertEqual([title_of(d) for d in days],
                         [OWN.format(2026), COMP.format(2027), OWN.format(2027), COMP.format(2026)])

    def test_december_31_and_january_1(self):
        # 31/12/2026 is slot 42 (42 % 4 == 2: own format, next year).
        self.assertEqual(title_of('2026-12-31'), OWN.format(2027))
        self.assertEqual(title_of('2026-12-30'), COMP.format(2027))
        # From 1/1/2027 only 2027, formats keep alternating.
        days = [(date(2027, 1, 1) + timedelta(i)).isoformat() for i in range(4)]
        self.assertEqual([title_of(d) for d in days],
                         [COMP.format(2027), OWN.format(2027), COMP.format(2027), OWN.format(2027)])
        for i in range(0, 300, 7):
            title = title_of((date(2027, 1, 1) + timedelta(i)).isoformat())
            self.assertIn('2027', title)
            self.assertNotIn('2026', title)
            self.assertNotIn('2028', title)

    def test_year_uses_buenos_aires_day(self):
        # 31/12 22:00 in Buenos Aires is already 1/1 in UTC.
        late = beat_ey_mat_seo.plan(profile(), '2027-01-01T01:00:00+00:00')
        self.assertEqual((late['publication_day'], late['years']), ('2026-12-31', ['2026', '2027']))

    def test_before_start_uses_slot_zero(self):
        self.assertEqual(title_of('2026-11-10'), OWN.format(2026))

    def test_tags_follow_title_year_and_budget(self):
        tags = beat_ey_mat_seo.variants(TRACK, profile(), slot('2026-11-20'))[0]['tags']
        for tag in ('juice wrld type beat 2027', 'free juice wrld type beat 2027', 'type beat 2027'):
            self.assertIn(tag, tags)
        self.assertFalse(any('2026' in t for t in tags))
        self.assertEqual(len({t.casefold() for t in tags}), len(tags))
        many = channel(tags=[f'juice wrld style {i:02d} type beat 2026' for i in range(40)])
        tags = beat_ey_mat_seo.variants(TRACK, profile(many), slot('2026-11-19'))[0]['tags']
        self.assertLessEqual(sum(len(t) + 3 for t in tags), beat_ey_mat_seo.TAG_BUDGET)
        self.assertTrue(all('2026' in t for t in tags))

    def test_long_name_stays_within_100(self):
        long_name = dict(TRACK, title='x' * 300)
        for day in ('2026-11-19', '2026-11-20'):
            title = beat_ey_mat_seo.variants(long_name, profile(), slot(day))[0]['title']
            self.assertLessEqual(len(title), 100)

    def test_profile_validation(self):
        for change in ({'alt_title_template': '[FREE] Juice WRLD Type Beat - "{name}"'},
                       {'alt_title_template': '[FREE] Juice WRLD Type Beat {year}'},
                       {'alt_title_template': DOC['seo']['title_template']},
                       {'alt_title_template': '[FREE] ' + 'x' * 90 + ' {year} "{name}"'},
                       {'title_template': '[FREE] Juice WRLD Type Beat "{name}"'},
                       {'title_template': '[FREE] ' + 'x' * 90 + ' {year} "{name}"'},
                       {'test_start': '2026-13-01'}, {'test_start': 20261119}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                manual_profile(channel(**change))
        for key in beat_ey_mat_seo.EXTRA_FIELDS:
            missing = {k: v for k, v in CHANNEL['seo'].items() if k != key}
            with self.subTest(missing=key), self.assertRaises(ValueError):
                manual_profile({'id': CID, 'seo': missing})
        with self.assertRaises(ValueError):  # extra keys stay ey_mat-only
            manual_profile(channel(title_mode='melodic_fixed_v1'))


class EyMatSnapshotTests(unittest.TestCase):
    def test_description_follows_title(self):
        snapshot, _ = build_snapshot(job(TRACK, slot('2026-11-20')), TRACK, CHANNEL, NOW)
        text = snapshot['selected']['description']
        self.assertTrue(text.endswith('\n\n' + COMP.format(2027)))
        for part in ('BPM: 160', 'Key: A Sharp Minor', 'juice wrld type beat 2027',
                     '#juicewrldtypebeat2027', 'type beat 2027', '{url}', '{chapters}'):
            self.assertIn(part, text)
        self.assertNotIn('2026', text)
        self.assertNotIn('{year}', text)
        self.assertNotIn('{music_info}', text)

    def test_missing_music_info_and_chapters_removed_cleanly(self):
        snapshot, _ = build_snapshot(job(PLAIN, slot('2026-11-19')), PLAIN, CHANNEL, NOW)
        text = snapshot['selected']['description']
        self.assertNotIn('{music_info}', text)
        final = fill_chapters(text.replace('{url}', 'https://bsta.rs/x'))
        self.assertNotIn('{', final)
        self.assertNotIn('\n\n\n', final)
        self.assertIn('contact@matwyre.com\n\n❗️Free for Non-Profit', final)
        self.assertIn('kit.com/a7958f365e\n\n\U0001f4b0 Purchase', final)
        filled = fill_chapters(text, '0:00 Intro\n0:20 Chorus')
        self.assertIn('\n\n0:00 Intro\n0:20 Chorus\n\n', filled)
        self.assertEqual(fill_chapters('{chapters}\n\nA'), 'A')
        self.assertEqual(fill_chapters('A\n\n{chapters}'), 'A')
        self.assertEqual(fill_chapters('A'), 'A')

    def test_detected_chapters_fill_the_ey_mat_description(self):
        from core.beat_sections import chapters_text
        planned = job(TRACK, slot('2026-11-20'))
        snapshot, _ = build_snapshot(planned, TRACK, CHANNEL, NOW)
        validate_snapshot(snapshot, planned)  # stored with the {chapters} token
        chapters = chapters_text([{'start': 0, 'label': 'Intro'}, {'start': 36, 'label': 'Chorus'},
                                  {'start': 60, 'label': 'Verse'}, {'start': 96, 'label': 'Chorus'}])
        final = fill_chapters(snapshot['selected']['description'].replace('{url}', 'https://bsta.rs/x'),
                              chapters)
        self.assertIn('contact@matwyre.com\n\n0:00 Intro\n0:36 Chorus\n1:00 Verse\n1:36 Chorus\n\n❗️Free',
                      final)
        self.assertNotIn('{', final)

    def test_snapshot_records_experiment_and_replays(self):
        when = slot('2026-12-31')
        snapshot, _ = build_snapshot(job(TRACK, when), TRACK, CHANNEL, NOW)
        self.assertEqual(snapshot['experiment'], {
            'version': 'ey_mat_v1', 'format': 'own', 'year': '2027', 'years': ['2026', '2027'],
            'slot_index': 42, 'publication_day': '2026-12-31'})
        self.assertEqual(snapshot['selected']['title'], OWN.format(2027))
        self.assertEqual(validate_snapshot(snapshot, job(TRACK, when)), snapshot)
        forged = deepcopy(snapshot)
        forged['experiment']['format'] = 'competitor'
        with self.assertRaises(ValueError):
            validate_snapshot(forged, job(TRACK, when))

    def test_repeat_does_not_reuse_previous_selection(self):
        when = slot('2027-01-01')
        first, _ = build_snapshot(job(TRACK, when), TRACK, CHANNEL, NOW)
        repeat_job = job(TRACK, when, cycle=2)
        repeat, _ = build_snapshot(repeat_job, TRACK, CHANNEL, NOW, previous_selected=first['selected'])
        self.assertEqual(repeat['selected']['title'], first['selected']['title'])
        self.assertNotEqual(repeat['selected']['tags'], first['selected']['tags'])
        self.assertEqual(validate_snapshot(repeat, repeat_job), repeat)

    def test_ninety_days_replay_and_balance(self):
        counts = {}
        for i in range(90):
            day = date(2026, 11, 19) + timedelta(i)
            track = (TRACK, PLAIN)[i % 2]
            when = slot(day.isoformat())
            snapshot, _ = build_snapshot(job(track, when), track, CHANNEL, NOW)
            self.assertEqual(validate_snapshot(snapshot, job(track, when)), snapshot)
            exp, selected = snapshot['experiment'], snapshot['selected']
            self.assertIn(exp['year'], selected['title'])
            self.assertIn(f'juice wrld type beat {exp["year"]}', selected['tags'])
            self.assertLessEqual(len(selected['title']), 100)
            counts[(exp['format'], exp['year'])] = counts.get((exp['format'], exp['year']), 0) + 1
        # 43 Nov-Dec slots (0..42): slots 4k and 4k+3 advertise 2026; every format gets every year.
        self.assertEqual(counts[('own', '2026')] + counts[('competitor', '2026')], 21)
        self.assertEqual(set(counts), {('own', '2026'), ('own', '2027'),
                                       ('competitor', '2026'), ('competitor', '2027')})
        self.assertGreaterEqual(min(counts.values()), 10)


if __name__ == '__main__':
    unittest.main()
