import unittest
from datetime import timedelta

from core.beat_cloud import BeatCloud
from core.beat_fakes import MemoryDropbox
from core.beat_schedule import apply_plan, plan, slots
from core.beat_schema import instant, migrate
from core.beat_state import BeatState


NOW = instant("2026-10-12T12:00:00-03:00")
CONFIG = {"channels": [{
    "id": "beats",
    "priority": 10,
    "slots": [
        {"weekday": 0, "hour": 18, "minute": 0},
        {"weekday": 3, "hour": 18, "minute": 0},
    ],
}]}
TRACKS = [{"id": f"TK{index}"} for index in range(8)]


class OccupiedDaysTests(unittest.TestCase):
    """Verifica que el planificador respete días ocupados sin perder huecos."""

    def test_occupied_monday_skips_to_next_configured_weekday(self):
        jobs = plan(CONFIG, {}, TRACKS, NOW, occupied_days={NOW.date()})

        self.assertTrue(jobs)
        self.assertEqual(instant(jobs[0]["slot"]), instant("2026-10-15T18:00:00-03:00"))
        self.assertNotIn(NOW.date(), {instant(job["slot"]).date() for job in jobs})

    def test_later_occupied_day_keeps_earlier_slots_free(self):
        occupied = (NOW + timedelta(days=10)).date()

        jobs = plan(CONFIG, {}, TRACKS, NOW, occupied_days={occupied})

        self.assertEqual(
            [instant(job["slot"]).date().isoformat() for job in jobs],
            ["2026-10-12", "2026-10-15", "2026-10-19"],
        )

    def test_empty_occupied_days_matches_omitted_argument(self):
        without_argument = plan(CONFIG, {}, TRACKS, NOW, seed=42)
        with_empty_days = plan(CONFIG, {}, TRACKS, NOW, seed=42, occupied_days=())

        self.assertEqual(with_empty_days, without_argument)

    def test_cancelled_job_still_blocks_its_exact_instant(self):
        one_track = [{"id": "TK1"}]
        state = migrate({}, "state")
        cancelled = plan(CONFIG, state, one_track, NOW)[0]
        cancelled["status"] = "cancelled"
        apply_plan(state, [cancelled])

        additions = plan(CONFIG, state, one_track, NOW, occupied_days=())

        self.assertEqual(len(additions), 1)
        self.assertEqual(instant(additions[0]["slot"]), instant("2026-10-15T18:00:00-03:00"))
        self.assertNotEqual(additions[0]["id"], cancelled["id"])
        self.assertEqual(additions[0]["track_id"], cancelled["track_id"])

    def test_fill_buffer_persists_shifted_jobs_without_duplicates(self):
        fake = MemoryDropbox()
        cloud = BeatCloud(fake, sleep=lambda _: None)
        store = BeatState(cloud, clock=lambda: NOW)
        owner = store.acquire()

        first = store.fill_buffer(CONFIG, TRACKS, owner, occupied_days={NOW.date()})
        second = store.fill_buffer(CONFIG, TRACKS, owner, occupied_days={NOW.date()})
        state, _ = cloud.read("state")

        self.assertTrue(first)
        self.assertEqual(second, [])
        self.assertEqual(len(state["jobs"]), len(first))
        self.assertNotIn(NOW.date(), {instant(job["slot"]).date() for job in first})

    def test_dry_run_threads_occupied_days_without_writes(self):
        fake = MemoryDropbox()
        store = BeatState(BeatCloud(fake, sleep=lambda _: None), clock=lambda: NOW)

        result = store.dry_run(CONFIG, TRACKS, occupied_days={NOW.date()})

        self.assertTrue(result["jobs"])
        self.assertNotIn(NOW.date(), {instant(job["slot"]).date() for job in result["jobs"]})
        self.assertEqual(fake.counter, 0)

    def test_slots_keep_strict_start_and_inclusive_end_boundaries(self):
        channel = migrate({"channels": [{
            "id": "beats",
            "slots": [
                {"weekday": 0, "hour": 12, "minute": 0},
                {"weekday": 0, "hour": 13, "minute": 0},
            ],
        }]}, "config")["channels"][0]

        values = slots(channel, NOW)

        self.assertNotIn(NOW, values)
        self.assertNotIn(NOW + timedelta(days=14, hours=1), values)
        self.assertIn(NOW + timedelta(days=14), values)
        self.assertTrue(all(NOW < value <= NOW + timedelta(days=14) for value in values))


if __name__ == "__main__":
    unittest.main()
