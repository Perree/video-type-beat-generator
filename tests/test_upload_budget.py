"""Cross-worker CAS budget, lost responses and per-channel cooldowns, offline."""
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier
from unittest.mock import patch

from core.beat_cloud import CloudError, Conflict, Missing, Transient
from core.beat_fakes import MemoryDropbox
from core.upload_budget import UploadBudget, UploadDeferred, PATH, initialize


class BudgetTests(unittest.TestCase):
    def test_legacy_config_migrates_to_ten(self):
        from core.beat_schema import migrate
        self.assertEqual(migrate({'daily_upload_attempts': 6}, 'config')['daily_upload_attempts'], 10)

    def setUp(self):
        self.now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
        self.memory = MemoryDropbox()
        initialize(self.memory, self.now - timedelta(days=1))
        self.budget = UploadBudget(self.memory, lambda: self.now)
        self.budget.cloud.sleep = lambda _: None

    def test_mixed_beats_loops_stop_at_ten_across_instances(self):
        for i in range(10):
            UploadBudget(self.memory, lambda: self.now).reserve('beat' if i % 2 else 'loops')
        with self.assertRaises(UploadDeferred):
            self.budget.call('another-channel', lambda: self.fail('must not upload'))
        self.assertEqual(len(self.budget.read()[0]['days']['2026-11-04']), 10)

    def test_concurrent_workers_cannot_overspend(self):
        barrier = Barrier(12)
        memory = self.memory
        class Racing:
            first = True
            def read(self, path):
                value = memory.read(path)
                if self.first:
                    self.first = False
                    barrier.wait(timeout=5)
                return value
            def write(self, *args):
                return memory.write(*args)
        def run(i):
            try:
                UploadBudget(Racing(), lambda: self.now).reserve(str(i))
                return True
            except (UploadDeferred, Conflict):
                return False
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(run, range(12)))
        self.assertEqual(sum(results), 10)

    def test_lost_write_response_does_not_double_charge(self):
        self.memory.faults = [('after_write', Transient())]
        self.budget.reserve('beat')
        self.assertEqual(len(self.budget.read()[0]['days']['2026-11-04']), 1)

    def test_failure_never_refunds_and_missing_state_never_resets(self):
        with self.assertRaises(TimeoutError):
            self.budget.call('beat', lambda: (_ for _ in ()).throw(TimeoutError()))
        self.assertEqual(len(self.budget.read()[0]['days']['2026-11-04']), 1)
        with self.assertRaises(Missing):
            UploadBudget(MemoryDropbox()).reserve('beat')
        with self.assertRaises(Conflict):
            initialize(self.memory)

    def test_corrupt_state_fails_closed(self):
        self.memory.write(PATH, b'{}', self.memory.read(PATH)[1])
        with self.assertRaises(CloudError):
            self.budget.call('beat', lambda: self.fail('must not upload'))

    def test_pacific_reset_and_activation_day(self):
        self.now = datetime(2026, 11, 4, 7, 59, 59, tzinfo=timezone.utc)
        with self.assertRaises(UploadDeferred):
            self.budget.reserve('beat')  # Still the fully reserved activation day in PT.
        self.now += timedelta(seconds=1)
        day = self.budget.reserve('beat')
        self.assertEqual(day, '2026-11-04')
        self.now += timedelta(days=1)
        with self.assertRaises(UploadDeferred):
            self.budget.check_day(day)

    def test_channel_limit_persists_24h_without_blocking_others(self):
        with patch('core.beat_reasons.classify', return_value='youtube_upload_limit'):
            with self.assertRaises(UploadDeferred):
                self.budget.call('beat', lambda: (_ for _ in ()).throw(ValueError()))
        fresh = UploadBudget(self.memory, lambda: self.now)
        with self.assertRaises(UploadDeferred):
            fresh.reserve('beat')
        fresh.reserve('loops')
        self.now += timedelta(hours=24)
        fresh.reserve('beat')

    def test_kit_private_fallback_consumes_two_attempts(self):
        from core import youtube
        from core.kit_publish import publish_preview
        from unittest.mock import Mock
        with patch('core.kit_publish._insert', side_effect=[
                youtube.YouTubeError('publishAt rejected'), {'youtube_id': 'video000001'}]) as insert:
            result = publish_preview('loops', 'video', None, 'pack',
                [{'weekday': 0, 'hour': 18}], {}, pack_id=1, audio_mode='assembled',
                now=self.now, store=Mock(), upload_budget=self.budget)
        self.assertEqual(insert.call_count, 2)
        self.assertEqual(result['estado'], 'private_pending')
        self.assertEqual(len(self.budget.read()[0]['days']['2026-11-04']), 2)


if __name__ == '__main__':
    unittest.main()
