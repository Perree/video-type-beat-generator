import unittest
from copy import deepcopy
from core.beat_schedule import slots, plan, apply_plan
from core.beat_schema import migrate


def channel():
    return {'id': 'kiezah', 'active': True, 'priority': 1, 'slots': [],
            'interval_schedule': {'days': 2, 'anchor': '2026-11-05T15:00:00-03:00'}}


class IntervalTests(unittest.TestCase):
    def test_anchor_survives_restart_and_month_year_boundaries(self):
        ch = channel()
        values = slots(ch, '2026-11-03T23:00:00-03:00')
        self.assertEqual([v.day for v in values], [5, 7, 9, 11, 13, 15, 17])
        self.assertEqual(slots(ch, '2026-11-06T12:00:00-03:00')[:6], values[1:])
        for now in ('2026-11-30T16:00:00-03:00', '2026-12-31T16:00:00-03:00'):
            found = slots(ch, now)
            self.assertEqual(len(found), 7)
            self.assertTrue(all((b-a).total_seconds() == 172800 for a,b in zip(found, found[1:])))
            self.assertTrue(all(v.hour == 15 for v in found))

    def test_exact_anchor_is_not_replanned_and_utc_is_converted(self):
        values = slots(channel(), '2026-11-05T18:00:00+00:00')
        self.assertEqual(values[0].isoformat(), '2026-11-07T15:00:00-03:00')

    def test_invalid_and_mixed_schedules_rejected(self):
        for patch in ({'days': True}, {'days': 0}, {'days': 31}, {'days': 2.5},
                      {'anchor': '2026-11-05T15:00:00'}, {'anchor': '2026-11-05T15:00:01-03:00'},
                      {'extra': 1}):
            ch = channel()
            ch['interval_schedule'].update(patch)
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                migrate({'channels': [ch]}, 'config')
        for patch in ({'slots': [{'weekday': 0, 'hour': 15, 'minute': 0}]},
                      {'human_schedule': {'minutes': 10}}, {'interval_schedule': None}):
            ch = dict(channel(), **patch)
            with self.assertRaises(ValueError): migrate({'channels': [ch]}, 'config')

    def test_plan_preserves_cadence_and_channel_local_history(self):
        config = {'channels': [channel()]}
        state = migrate({}, 'state')
        tracks = [{'id': f'TK{i}', 'tags': ['house']} for i in range(1, 12)]
        now = '2026-11-03T23:00:00-03:00'
        additions = plan(config, state, tracks, now, occupied_days={slots(channel(), now)[1].date()})
        self.assertEqual(len(additions), 6)
        self.assertEqual(additions[1]['slot'], '2026-11-09T15:00:00-03:00')
        foreign = deepcopy(additions[0])
        from core.beat_schema import identity
        foreign.update(channel='ravewavebeatz', status='uploaded')
        foreign['id'] = identity(foreign['track_id'], foreign['channel'], 1, foreign['slot'])
        state['jobs'][foreign['id']] = foreign
        self.assertEqual(plan(config, state, tracks, now)[0]['track_id'], additions[0]['track_id'])
        apply_plan(state, plan(config, state, tracks, now))
        self.assertEqual(plan(config, state, tracks, now), [])


if __name__ == '__main__': unittest.main()
