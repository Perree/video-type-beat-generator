import json
import unittest
from datetime import datetime, timezone, timedelta
from core.beat_fakes import MemoryDropbox
from core.beat_cloud import Transient
from core.upload_budget import UploadBudget, UploadDeferred, initialize, PACIFIC
from core.upload_exception import PrivatePilotBudget, grant_path


class PilotExceptionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 4, 2, tzinfo=timezone.utc)
        self.transport = MemoryDropbox()
        initialize(self.transport, self.now)
        self.pilot = PrivatePilotBudget(self.transport, '123', clock=lambda: self.now)
        self.pilot.cloud.sleep = lambda _: None

    def grant(self, **patch):
        data = {'version': 1, 'run_id': '123', 'channel': 'kiezah',
                'quota_day': self.now.astimezone(PACIFIC).date().isoformat(),
                'private_pilot': True, 'consumed_by': None}
        data.update(patch)
        self.transport.write(grant_path('123'), json.dumps(data).encode(), None)

    def test_only_one_extra_and_normal_ledger_unchanged(self):
        self.grant()
        before = self.pilot.read()[0]
        self.assertEqual(self.pilot.reserve('kiezah'), '2026-11-03')
        with self.assertRaises(UploadDeferred): self.pilot.reserve('kiezah')
        self.assertEqual(self.pilot.read()[0], before)
        with self.assertRaises(UploadDeferred): UploadBudget(self.transport, lambda: self.now).reserve('kiezah')

    def test_missing_wrong_channel_day_run_and_nonprivate_grants_rejected(self):
        with self.assertRaises(UploadDeferred): self.pilot.reserve('kiezah')
        for patch in ({'channel': 'other'}, {'quota_day': '2026-11-02'},
                      {'run_id': '124'}, {'private_pilot': False}, {'consumed_by': 'used'}):
            self.setUp()
            self.grant(**patch)
            with self.subTest(patch=patch), self.assertRaises(UploadDeferred): self.pilot.reserve('kiezah')

    def test_lost_response_is_one_durable_consumption(self):
        self.grant()
        self.transport.faults = [('after_write', Transient())]
        self.pilot.reserve('kiezah')
        with self.assertRaises(UploadDeferred):
            PrivatePilotBudget(self.transport, '123', clock=lambda: self.now).reserve('kiezah')

    def test_actual_youtube_cooldown_cannot_be_overridden(self):
        self.grant()
        self.pilot._update(lambda doc: doc['blocked'].update(kiezah=(self.now + timedelta(hours=24)).isoformat()))
        with self.assertRaisesRegex(UploadDeferred, 'youtube_upload_limit'): self.pilot.reserve('kiezah')
        raw, _ = self.transport.read(grant_path('123'))
        self.assertIsNone(json.loads(raw)['consumed_by'])

    def test_two_workers_cannot_consume_the_same_grant(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        self.grant()
        barrier = Barrier(2)
        memory = self.transport
        class Racing:
            first = True
            def read(self, path):
                result = memory.read(path)
                if path == grant_path('123') and self.first:
                    self.first = False
                    barrier.wait(timeout=5)
                return result
            def write(self, *args):
                return memory.write(*args)
        def attempt(_):
            try:
                PrivatePilotBudget(Racing(), '123', clock=lambda: self.now).reserve('kiezah')
                return True
            except UploadDeferred:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sum(pool.map(attempt, range(2))), 1)


if __name__ == '__main__': unittest.main()
