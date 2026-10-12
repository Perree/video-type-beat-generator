import copy
import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from core.beat_cloud import BeatCloud, CloudError, Conflict, Transient
from core.beat_fakes import MemoryDropbox
from core.beat_schema import identity, instant, migrate
from core.beat_schedule import apply_plan, plan, slots
from core.beat_state import BeatState, Locked, BudgetExhausted

NOW = instant("2026-10-12T12:00:00-03:00")
CONFIG = {"channels": [
    {"id": "low", "priority": 0, "slots": [{"weekday": 0, "hour": 18, "minute": 0}]},
    {"id": "high", "priority": 10, "slots": [{"weekday": 0, "hour": 18, "minute": 0}]},
]}
TRACKS = [{"id": "TK2"}, {"id": "TK1"}, {"id": "TK0", "active": False}]


class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.fake = MemoryDropbox()
        self.cloud = BeatCloud(self.fake, retries=10, sleep=lambda _: None)
        self.now = NOW
        self.store = BeatState(self.cloud, clock=lambda: self.now)

    def prepare(self):
        owner = self.store.acquire()
        jobs = self.store.fill_buffer(CONFIG, TRACKS, owner)
        self.store.release(owner)
        return jobs

    def test_migrations_idempotent_preserve_fields(self):
        for kind, document in (("config", CONFIG), ("state", {"extra": {"keep": 1}})):
            original = copy.deepcopy(document)
            migrated = migrate(document, kind)
            self.assertEqual(migrate(migrated, kind), migrated)
            self.assertEqual(document, original)
        self.cloud.initialize()
        writes = self.fake.counter
        self.cloud.initialize()
        self.assertEqual(self.fake.counter, writes)

    def test_persist_v0_migration_with_rev(self):
        self.fake.write("/type-beats/state.json", b'{"extra":42}', None)
        self.cloud.initialize()
        data, _ = self.fake.read("/type-beats/state.json")
        self.assertEqual(json.loads(data)["schema_version"], 1)
        self.assertEqual(json.loads(data)["extra"], 42)

    def test_bad_documents_fail_closed(self):
        for document in ({"schema_version": 2}, {"namespace": "loopkits"},
                         {"jobs": []}, {"lock": {"owner": "x", "expires_at": "bad"}}):
            with self.assertRaises((ValueError, TypeError)):
                migrate(document, "state")
        for change in ({"buffer_days": 15}, {"daily_upload_attempts": 7},
                       {"channels": [{"id": "x", "slots": [{"weekday": True, "hour": 18, "minute": 0}]}]}):
            with self.assertRaises(ValueError):
                migrate(change, "config")
        self.fake.write("/type-beats/state.json", b'broken', None)
        with self.assertRaises(CloudError):
            self.store.acquire()
        self.assertEqual(self.fake.counter, 1)

    def test_conditional_create_update_and_stale_revisions(self):
        state, rev = self.cloud.read("state")
        new = self.cloud.write("state", state, rev)
        with self.assertRaises(Conflict):
            self.cloud.write("state", state, None)
        state["extra"] = 1
        self.cloud.write("state", state, new)
        with self.assertRaises(Conflict):
            self.cloud.write("state", state, new)

    def test_retries_and_exhaustion(self):
        delays = []
        cloud = BeatCloud(self.fake, retries=2, sleep=delays.append)
        self.fake.faults = [("read", Transient(2))]
        cloud.read("state")
        self.assertEqual(delays, [2])
        self.fake.faults = [("read", Transient()), ("read", Transient())]
        with self.assertRaises(CloudError):
            cloud.read("state")

    def test_lock_expiry_fencing_and_release(self):
        owner = self.store.acquire(ttl=10)
        with self.assertRaises(Locked):
            self.store.acquire()
        self.now += timedelta(seconds=10)
        successor = self.store.acquire()
        for call in (lambda: self.store.renew(owner),
                     lambda: self.store.fill_buffer(CONFIG, TRACKS, owner)):
            with self.assertRaises(Locked):
                call()
        self.store.release(owner)
        self.assertEqual(self.cloud.read("state")[0]["lock"]["owner"], successor)
        self.store.renew(successor)
        self.store.release(successor)
        self.assertIsNone(self.cloud.read("state")[0]["lock"])

    def test_rounds_priority_cycles_and_repeat_fill(self):
        jobs = self.prepare()
        self.assertEqual([j["channel"] for j in jobs], ["high", "low", "high", "low"])
        self.assertEqual([j["track_id"] for j in jobs], ["TK1", "TK1", "TK2", "TK2"])
        self.assertTrue(all(j["cycle"] == 1 for j in jobs))
        self.assertEqual(self.prepare(), [])
        self.now += timedelta(days=7)
        additions = self.prepare()
        self.assertEqual(len(additions), 2)
        self.assertTrue(all(j["cycle"] == 2 for j in additions))
        self.assertEqual(len({j["id"] for j in jobs + additions}), 6)

    def test_identity_offset_canonical_and_full_tuple(self):
        key = identity("TK1", "channel", 1, NOW)
        self.assertEqual(key, identity("TK1", "channel", 1, "2026-10-12T15:00:00+00:00"))
        for tid, ch, cycle, slot in (("TK2", "channel", 1, NOW), ("TK1", "other", 1, NOW),
                                     ("TK1", "channel", 2, NOW), ("TK1", "channel", 1, NOW + timedelta(hours=1))):
            self.assertNotEqual(key, identity(tid, ch, cycle, slot))

    def test_slots_window_boundaries_buenos_aires(self):
        ch = migrate(CONFIG, "config")["channels"][0]
        now = instant("2026-10-12T21:00:00+00:00")
        values = slots(ch, now)
        self.assertEqual([v.isoformat() for v in values],
                         ["2026-10-19T18:00:00-03:00", "2026-10-26T18:00:00-03:00"])
        with self.assertRaises(ValueError):
            instant("2026-10-12T12:00:00")

    def test_dry_run_deterministic_no_writes(self):
        first = self.store.dry_run(CONFIG, TRACKS)
        config = copy.deepcopy(CONFIG)
        config["channels"].reverse()
        second = self.store.dry_run(config, reversed(TRACKS))
        self.assertEqual(first, second)
        self.assertEqual(self.fake.counter, 0)
        self.assertEqual(first["upload_attempts_remaining"], 6)

    def test_cancelled_and_failed_slots_not_duplicated(self):
        state = migrate({}, "state")
        jobs = plan(CONFIG, state, TRACKS, NOW)
        jobs[0]["status"], jobs[1]["status"] = "cancelled", "failed"
        apply_plan(state, jobs)
        self.assertEqual(plan(CONFIG, state, TRACKS, NOW), [])

    def test_global_six_attempts_retries_count_and_midnight(self):
        jobs = self.prepare()
        for i in range(6):
            self.store.reserve_attempt(jobs[i % 4]["id"], str(i))
        with self.assertRaises(BudgetExhausted):
            self.store.reserve_attempt(jobs[0]["id"], "seventh")
        self.assertTrue(self.store.reserve_attempt(jobs[0]["id"], "0")["replayed"])
        with self.assertRaises(ValueError):
            self.store.reserve_attempt(jobs[1]["id"], "0")
        self.now = instant("2026-10-13T02:59:59+00:00")
        with self.assertRaises(BudgetExhausted):
            self.store.reserve_attempt(jobs[0]["id"], "still-monday")
        self.now += timedelta(seconds=1)
        self.assertFalse(self.store.reserve_attempt(jobs[0]["id"], "tuesday")["replayed"])

    def test_lost_response_reservation_not_double_counted(self):
        job = self.prepare()[0]
        self.fake.faults = [("after_write", Transient())]
        result = self.store.reserve_attempt(job["id"], "unique")
        self.assertTrue(result["replayed"])
        self.assertEqual(len(self.cloud.read("state")[0]["attempts"]["2026-10-12"]), 1)

    def test_concurrent_cas_global_budget(self):
        jobs = self.prepare()
        barrier = Barrier(8)
        fake = self.fake
        class RacingDropbox:
            def __init__(self):
                self.first = True
            def read(self, path):
                result = fake.read(path)
                if self.first:
                    self.first = False
                    barrier.wait(timeout=5)
                return result
            def write(self, *args):
                return fake.write(*args)
        def reserve(i):
            store = BeatState(BeatCloud(RacingDropbox(), retries=10, sleep=lambda _: None), clock=lambda: NOW)
            try:
                store.reserve_attempt(jobs[i % 4]["id"], "thread-" + str(i))
                return True
            except BudgetExhausted:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(reserve, range(8)))
        self.assertEqual(sum(results), 6)
        self.assertEqual(len(self.cloud.read("state")[0]["attempts"]["2026-10-12"]), 6)

    def test_incomplete_v1_never_resets_budget_or_jobs(self):
        self.prepare()
        state, _ = self.cloud.read("state")
        for field in ("jobs", "attempts", "lock", "namespace"):
            broken = copy.deepcopy(state)
            del broken[field]
            self.fake.files["/type-beats/state.json"] = (json.dumps(broken).encode(), "0000000000000001")
            with self.subTest(field=field), self.assertRaises(CloudError):
                self.cloud.initialize()
            with self.assertRaises(CloudError):
                self.store.acquire()
        config = migrate(CONFIG, "config")
        del config["channels"]
        with self.assertRaises(ValueError):
            migrate(config, "config")

    def test_duplicate_json_keys_and_nonfinite_rejected(self):
        for payload in (b'{"attempts":{},"attempts":{}}', b'{"extra":NaN}', b'{"extra":Infinity}', b'{"extra":1e1000}'):
            self.fake.files["/type-beats/state.json"] = (payload, "0000000000000001")
            with self.subTest(payload=payload), self.assertRaises(CloudError):
                self.cloud.read("state")
            with self.assertRaises(CloudError):
                self.cloud.initialize()

    def test_job_id_must_match_dictionary_key(self):
        self.prepare()
        state, _ = self.cloud.read("state")
        key = next(iter(state["jobs"]))
        state["jobs"][key]["id"] = "wrong"
        with self.assertRaises(ValueError):
            migrate(state, "state")
        del state["jobs"][key]["id"]
        with self.assertRaises(ValueError):
            migrate(state, "state")
        state["schema_version"] = 0
        self.assertEqual(migrate(state, "state")["jobs"][key]["id"], key)

    def test_expiring_lease_during_retry_does_not_write_plan(self):
        owner = self.store.acquire(ttl=1)
        before, rev = self.cloud.read("state")
        self.cloud.sleep = lambda _: setattr(self, "now", self.now + timedelta(seconds=2))
        self.fake.faults = [("write", Transient())]
        with self.assertRaises(Locked):
            self.store.fill_buffer(CONFIG, TRACKS, owner)
        after, after_rev = self.cloud.read("state")
        self.assertEqual(before, after)
        self.assertEqual(rev, after_rev)

    def test_renew_retry_uses_original_expiration(self):
        owner = self.store.acquire(ttl=1)
        before, rev = self.cloud.read("state")
        self.cloud.sleep = lambda _: setattr(self, "now", self.now + timedelta(seconds=2))
        self.fake.faults = [("write", Transient())]
        with self.assertRaises(Locked):
            self.store.renew(owner, ttl=300)
        self.assertEqual(self.cloud.read("state"), (before, rev))

    def test_acquire_never_returns_expired_lease_after_retry(self):
        self.cloud.sleep = lambda _: setattr(self, "now", self.now + timedelta(seconds=2))
        self.fake.faults = [("write", Transient())]
        with self.assertRaises(Locked):
            self.store.acquire(ttl=1)
        self.assertEqual(self.fake.counter, 0)

    def test_incomplete_v1_channel_cannot_reactivate(self):
        config = migrate(CONFIG, "config")
        config["channels"][0]["active"] = False
        del config["channels"][0]["active"]
        with self.assertRaises(ValueError):
            migrate(config, "config")

    def test_fill_recovers_committed_jobs_after_lost_response(self):
        owner = self.store.acquire()
        expected = self.store.dry_run(CONFIG, TRACKS)["jobs"]
        self.fake.faults = [("after_write", Transient())]
        actual = self.store.fill_buffer(CONFIG, TRACKS, owner)
        self.assertEqual(actual, expected)
        self.assertEqual(len(self.cloud.read("state")[0]["jobs"]), len(expected))
        self.assertEqual(self.store.fill_buffer(CONFIG, TRACKS, owner), [])

    def test_cancelling_latest_cycle_never_regresses_cycle(self):
        self.prepare()
        self.now += timedelta(days=7)
        additions = self.prepare()
        self.assertTrue(all(j["cycle"] == 2 for j in additions))
        def cancel(state):
            for j in state["jobs"].values():
                if j["cycle"] == 2:
                    j["status"] = "cancelled"
        self.cloud.update("state", cancel)
        self.now += timedelta(days=7)
        additions = self.prepare()
        self.assertTrue(additions)
        self.assertTrue(all(j["cycle"] == 2 for j in additions))


if __name__ == "__main__":
    unittest.main()
