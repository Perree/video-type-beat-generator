"""years_for: November and December also allow next year; from 1 January only the current one."""
from datetime import date
import unittest

from core.beat_year import years_for


class BeatYearTests(unittest.TestCase):
    def test_november_and_december_add_next_year(self):
        self.assertEqual(years_for(date(2026, 11, 19)), [2026, 2027])
        self.assertEqual(years_for(date(2026, 11, 1)), [2026, 2027])
        self.assertEqual(years_for(date(2026, 12, 31)), [2026, 2027])

    def test_rest_of_year_only_current(self):
        self.assertEqual(years_for(date(2027, 1, 1)), [2027])
        self.assertEqual(years_for(date(2026, 10, 31)), [2026])
        self.assertEqual(years_for(date(2027, 6, 15)), [2027])

    def test_rule_is_generic(self):
        self.assertEqual(years_for(date(2030, 12, 1)), [2030, 2031])
        self.assertEqual(years_for(date(2031, 1, 1)), [2031])


if __name__ == '__main__':
    unittest.main()
