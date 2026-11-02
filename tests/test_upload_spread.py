"""Subidas escalonadas: mismo cronograma, pero cada video se sube pocos días antes."""
from datetime import timedelta
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

from core import upload_spread
from core.beat_schema import instant

REAL_SETTINGS = upload_spread.settings  # conftest la apaga para los tests viejos
sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_beat_daily as daily  # noqa: E402

NOW = daily.NOW


class SpreadUnitTests(unittest.TestCase):
    def test_settings(self):
        self.assertIsNone(REAL_SETTINGS(False))
        self.assertEqual(REAL_SETTINGS(None), {'min_days': 2, 'max_days': 4})
        self.assertEqual(REAL_SETTINGS({'min_days': 1, 'max_days': 1}), {'min_days': 1, 'max_days': 1})
        for bad in ({'min_days': 0}, {'min_days': 5, 'max_days': 3}, {'max_days': 20}, 'x'):
            with self.assertRaises(ValueError):
                REAL_SETTINGS(bad)

    def test_lead_is_stable_and_varies(self):
        cfg = REAL_SETTINGS(None)
        leads = [upload_spread.lead_days(f'job-{n}', cfg) for n in range(60)]
        self.assertEqual(leads, [upload_spread.lead_days(f'job-{n}', cfg) for n in range(60)])
        self.assertEqual(set(leads), {2, 3, 4})

    def test_too_early(self):
        with patch.object(upload_spread, 'settings', REAL_SETTINGS):
            job = {'id': 'abc'}
            lead = upload_spread.lead_days('abc', REAL_SETTINGS(None))
            slot = NOW + timedelta(days=lead, hours=1)
            self.assertTrue(upload_spread.too_early(job, slot, NOW, None))
            self.assertFalse(upload_spread.too_early(job, slot - timedelta(hours=2), NOW, None))
            self.assertFalse(upload_spread.too_early(job, slot + timedelta(days=9), NOW, False))


class SpreadWorkerTests(daily.DailyTests):
    """Reusa el entorno de test_beat_daily con un video por día de cronograma."""

    def test_daily_runs_upload_a_few_each_day_not_the_whole_buffer(self):
        with patch.object(upload_spread, 'settings', REAL_SETTINGS):
            summary = self.run_worker()
            self.assertGreater(summary['uploaded'], 0)
            self.assertLessEqual(summary['uploaded'], 4)  # como mucho los próximos 4 días
            state, _ = self.cloud.read('state')
            cfg = REAL_SETTINGS(None)
            for job in state['jobs'].values():
                if job['status'] == 'uploaded':
                    lead = upload_spread.lead_days(job['id'], cfg)
                    self.assertLessEqual(instant(job['slot']), NOW + timedelta(days=lead))
            # Lo que no se subió sigue planificado para corridas de otros días.
            self.assertTrue(any(j['status'] == 'planned' for j in state['jobs'].values()))


# Solo el test nuevo: los heredados ya corren en test_beat_daily.
for name in [n for n in dir(daily.DailyTests) if n.startswith('test_')]:
    setattr(SpreadWorkerTests, name, None)
SpreadWorkerTests.test_daily_runs_upload_a_few_each_day_not_the_whole_buffer = \
    SpreadWorkerTests.__dict__['test_daily_runs_upload_a_few_each_day_not_the_whole_buffer']

if __name__ == '__main__':
    unittest.main()
