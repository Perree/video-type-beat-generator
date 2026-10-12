"""Pure slot/buffer planning, one assignment per channel per priority round."""
from copy import deepcopy
from datetime import timedelta
from core.beat_schema import identity, instant, migrate


def slots(channel, now):
    start = instant(now)
    end = start + timedelta(days=14)
    result = []
    for offset in range(15):
        day = start.date() + timedelta(days=offset)
        for spec in channel["slots"]:
            if day.weekday() == spec["weekday"]:
                value = start.replace(year=day.year, month=day.month, day=day.day,
                                      hour=spec["hour"], minute=spec["minute"], second=0, microsecond=0)
                if start < value <= end:
                    result.append(value)
    return sorted(set(result))


def plan(config, state, tracks, now):
    config, state = migrate(config, "config"), migrate(state, "state")
    tracks = list(tracks)
    if any(not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t["id"]
           or type(t.get("active", True)) is not bool for t in tracks):
        raise ValueError("invalid_track_id")
    ids = sorted({t["id"] for t in tracks if t.get("active", True)})
    channels = sorted((ch for ch in config["channels"] if ch["active"]),
                      key=lambda ch: (-ch["priority"], ch["id"]))
    occupied = {(j["channel"], instant(j["slot"])) for j in state["jobs"].values()}
    queues = {ch["id"]: [s for s in slots(ch, now) if (ch["id"], s) not in occupied]
              for ch in channels}
    jobs = list(state["jobs"].values())
    additions = []
    while ids and any(queues.values()):
        for ch in channels:
            cid = ch["id"]
            if not queues[cid]:
                continue
            history = [j for j in jobs if j["channel"] == cid]
            cycle = max((j["cycle"] for j in history), default=1)
            used = {j["track_id"] for j in history if j["cycle"] == cycle and j["status"] != "cancelled"}
            available = [tid for tid in ids if tid not in used]
            if not available:
                cycle += 1
                available = ids
            slot = queues[cid].pop(0).isoformat()
            job = dict(track_id=available[0], channel=cid, cycle=cycle, slot=slot, status="planned")
            job["id"] = identity(job["track_id"], cid, cycle, slot)
            jobs.append(job)
            additions.append(job)
    return additions


def apply_plan(state, additions):
    for job in additions:
        state["jobs"].setdefault(job["id"], deepcopy(job))
