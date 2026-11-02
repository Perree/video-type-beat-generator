"""Variación humana de horarios: estable, acotada y un video por día."""
from datetime import datetime, timedelta
import unittest

from core import human_schedule
from core.beat_schedule import apply_plan, plan, slots
from core.kit_publish import next_slot
from core.publish_calendar import next_free_slots

ON = {'minutes': 45, 'days': 1}
KIT = human_schedule.annotate([{'weekday': 1, 'hour': 12, 'minute': 17},
                               {'weekday': 4, 'hour': 16, 'minute': 43}], ON)
NOW = datetime(2026, 11, 1, 20, 0)


def channel(**extra):
    base = dict(id='c1', active=True, priority=0, human_schedule=ON,
                slots=[{'weekday': d, 'hour': 18, 'minute': 0} for d in (0, 2, 4)])
    return {**base, **extra}


class VaryTests(unittest.TestCase):
    def test_settings(self):
        self.assertEqual(human_schedule.settings(False), {'minutes': 0, 'days': 0})
        self.assertEqual(human_schedule.settings({'minutes': 10, 'days': 2}), {'minutes': 10, 'days': 2})
        for bad in ({'minutes': -1}, {'days': 5}, 'x', {'minutes': 1.5}):
            with self.assertRaises(ValueError):
                human_schedule.settings(bad)

    def test_off_returns_base(self):
        base = datetime(2026, 11, 3, 12, 17)
        self.assertEqual(human_schedule.vary(base, {'vary_minutes': 0, 'vary_days': 0}), base)

    def test_stable_bounded_and_varied(self):
        spec = KIT[0]
        finals = []
        for week in range(40):
            base = datetime(2026, 11, 3, 12, 17) + timedelta(weeks=week)
            value = human_schedule.vary(base, spec)
            self.assertEqual(value, human_schedule.vary(base, spec))
            self.assertLessEqual(abs(value - base), timedelta(days=1, minutes=45))
            finals.append(value)
        self.assertGreater(len({(v.hour, v.minute) for v in finals}), 20)
        self.assertGreater(len({v.weekday() for v in finals}), 1)


class KitTests(unittest.TestCase):
    def test_next_slot_moves_forward_and_is_repeatable(self):
        cur = NOW
        for _ in range(30):
            nxt = next_slot(cur, KIT)
            self.assertGreater(nxt, cur)
            # publish_preview recalcula con un minuto antes del slot elegido.
            self.assertEqual(next_slot(nxt - timedelta(minutes=1), KIT), nxt)
            cur = nxt

    def test_free_slots_one_per_day(self):
        found = next_free_slots(KIT, NOW, set(), 20, 120)
        days = [v.date() for v in found]
        self.assertEqual(len(days), len(set(days)))


class BeatTests(unittest.TestCase):
    now = datetime.fromisoformat('2026-11-01T20:00:00-03:00')

    def test_slots_stable_and_inside_window(self):
        first = slots(channel(), self.now)
        self.assertEqual(first, slots(channel(), self.now))
        for value in first:
            self.assertTrue(self.now < value <= self.now + timedelta(days=14))
        exact = slots(channel(human_schedule=False), self.now)
        self.assertNotEqual(first, exact)

    def test_replan_adds_nothing_and_one_video_per_day(self):
        config = {'channels': [channel()]}
        state = {'jobs': {}, 'attempts': {}, 'lock': None}
        tracks = [{'id': f'T{n}'} for n in range(20)]
        first = plan(config, state, tracks, self.now)
        self.assertTrue(first)
        days = [datetime.fromisoformat(j['slot']).date() for j in first]
        self.assertEqual(len(days), len(set(days)))
        apply_plan(state, first)
        self.assertEqual(plan(config, state, tracks, self.now), [])

    def test_old_exact_jobs_block_their_day(self):
        config_off = {'channels': [channel(human_schedule=False)]}
        state = {'jobs': {}, 'attempts': {}, 'lock': None}
        tracks = [{'id': f'T{n}'} for n in range(20)]
        apply_plan(state, plan(config_off, state, tracks, self.now))
        added = plan({'channels': [channel(human_schedule={'minutes': 45, 'days': 0})]},
                     state, tracks, self.now)
        self.assertEqual(added, [])


if __name__ == '__main__':
    unittest.main()
