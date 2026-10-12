"""Atomic reservations and expiring, fenced planner leases in the same CAS file."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from core.beat_schema import instant
from core.beat_schedule import plan, apply_plan


class Locked(Exception):
    pass


class BudgetExhausted(Exception):
    pass


class BeatState:
    def __init__(self, cloud, clock=lambda: datetime.now(timezone.utc)):
        self.cloud, self.clock = cloud, clock

    def _lease(self, state, owner):
        lock = state["lock"]
        if not lock or lock["owner"] != owner or instant(lock["expires_at"]) <= instant(self.clock()):
            raise Locked("lease_lost")

    def acquire(self, ttl=300, *, require_existing=False):
        if type(ttl) is not int or not 1 <= ttl <= 3600:
            raise ValueError("invalid_lock_ttl")
        owner = uuid4().hex
        expires_at = None
        def mutate(state):
            nonlocal expires_at
            now = instant(self.clock())
            lock = state["lock"]
            if lock and instant(lock["expires_at"]) > now and lock["owner"] != owner:
                raise Locked("lock_busy")
            expires_at = now + timedelta(seconds=ttl)
            state["lock"] = {"owner": owner, "expires_at": expires_at.isoformat()}
            return owner
        def guard(_):
            if instant(self.clock()) >= expires_at:
                raise Locked("lease_expired_before_commit")
        return self.cloud.update("state", mutate, guard=guard, require_existing=require_existing)

    def renew(self, owner, ttl=300):
        if type(ttl) is not int or not 1 <= ttl <= 3600:
            raise ValueError("invalid_lock_ttl")
        def mutate(state):
            self._lease(state, owner)
            state["lock"]["expires_at"] = (instant(self.clock()) + timedelta(seconds=ttl)).isoformat()
        self.cloud.update("state", mutate, guard=lambda source: self._lease(source, owner))

    def release(self, owner):
        def mutate(state):
            if state["lock"] and state["lock"]["owner"] == owner:
                state["lock"] = None
        self.cloud.update("state", mutate, require_existing=True)

    def fill_buffer(self, config, tracks, owner, *, seed=None, reports=None):
        tracks = list(tracks)
        proposed = {}
        def mutate(state):
            self._lease(state, owner)
            # Recover only our exact proposals after a committed write lost its
            # response; never return unrelated jobs added by another planner.
            recovered = [state["jobs"][key] for key, job in proposed.items()
                         if state["jobs"].get(key) == job]
            additions = plan(config, state, tracks, self.clock(), seed=seed, reports=reports)
            proposed.update((job["id"], job) for job in additions)
            apply_plan(state, additions)
            return recovered + additions
        return self.cloud.update("state", mutate, guard=lambda source: self._lease(source, owner))

    def reserve_attempt(self, job_id, attempt_id, *, exclusive=False):
        """Reserve BEFORE an upload call. Failures/unknown outcomes never refund.

        Same attempt_id is only a retry of this reservation; each new external
        upload call must use a fresh ID. This method never performs uploads.
        """
        if not isinstance(attempt_id, str) or not attempt_id or len(attempt_id) > 200:
            raise ValueError("invalid_attempt_id")
        reserved_day = None
        def mutate(state):
            nonlocal reserved_day
            for entries in state["attempts"].values():
                if attempt_id in entries:
                    if entries[attempt_id]["job_id"] != job_id:
                        raise ValueError("attempt_identity_conflict")
                    reserved_day = instant(entries[attempt_id]['reserved_at']).date()
                    return dict(entries[attempt_id], replayed=True)
            job = state["jobs"].get(job_id)
            if not job or job["status"] not in ("planned", "failed"):
                raise ValueError("job_not_uploadable")
            if exclusive:
                from core.beat_rotation import check_repeat
                check_repeat(state, job, self.clock())
            # Daily worker: any previous intent, including an unknown outcome,
            # is a permanent barrier. Check and reserve in the SAME CAS write.
            if exclusive and any(entry['job_id'] == job_id
                                 for entries in state['attempts'].values()
                                 for entry in entries.values()):
                raise ValueError('upload_already_attempted')
            now = instant(self.clock())
            reserved_day = now.date()
            entries = state["attempts"].setdefault(now.date().isoformat(), {})
            if len(entries) >= 6:
                raise BudgetExhausted("daily_upload_budget_exhausted")
            entry = {"job_id": job_id, "reserved_at": now.isoformat()}
            entries[attempt_id] = entry
            return dict(entry, replayed=False)
        def guard(_):
            if instant(self.clock()).date() != reserved_day:
                raise ValueError('upload_reservation_day_changed')
        return self.cloud.update("state", mutate, guard=guard if exclusive else None)

    def dry_run(self, config, tracks, now=None, *, seed=None, reports=None):
        state, _ = self.cloud.read("state")
        now = instant(self.clock() if now is None else now)
        return {"as_of": now.isoformat(), "timezone": "America/Argentina/Buenos_Aires",
                "buffer_days": 14, "upload_attempts_remaining": 6 - len(state["attempts"].get(now.date().isoformat(), {})),
                "jobs": plan(config, state, tracks, now, seed=seed, reports=reports)}
