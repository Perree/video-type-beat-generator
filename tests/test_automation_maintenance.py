import unittest
from datetime import datetime, timezone, date
from core.automation_maintenance import next_slots


class MaintenanceTests(unittest.TestCase):
    def test_tuesday_thursday_argentina_and_occupied_days(self):
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        self.assertEqual(next_slots(now, 3), ['2026-11-03T13:00:00Z',
            '2026-11-05T13:00:00Z', '2026-11-10T13:00:00Z'])
        self.assertEqual(next_slots(now, 1, {date(2026, 11, 3)}), ['2026-11-05T13:00:00Z'])

    def test_passed_slot_is_skipped(self):
        self.assertEqual(next_slots(datetime(2026, 11, 3, 13, tzinfo=timezone.utc), 1),
                         ['2026-11-05T13:00:00Z'])
