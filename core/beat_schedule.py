"""Pure slot/buffer planning, one assignment per channel per priority round."""
from copy import deepcopy
from datetime import timedelta
import hashlib
from core.beat_schema import identity, instant, migrate
from core.beat_rotation import repeat_ready, publication_time
from core.beat_performance import performance, choose
from core.beat_selection import eligible_tracks


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


def plan(config, state, tracks, now, *, seed=None, reports=None):
    if seed is not None and type(seed) not in (int, str):
        raise ValueError('invalid_selection_seed')
    config, state = migrate(config, "config"), migrate(state, "state")
    tracks = list(tracks)
    if any(not isinstance(t, dict) or not isinstance(t.get("id"), str) or not t["id"]
           or type(t.get("active", True)) is not bool for t in tracks):
        raise ValueError("invalid_track_id")
    channels = sorted((ch for ch in config["channels"] if ch["active"]),
                      key=lambda ch: (-ch["priority"], ch["id"]))
    pools = {ch['id']: eligible_tracks(ch, tracks) for ch in channels}
    catalog_ids = {cid: sorted({track['id'] for track in pool}) for cid, pool in pools.items()}
    occupied = {(j["channel"], instant(j["slot"])) for j in state["jobs"].values()}
    queues = {ch["id"]: [s for s in slots(ch, now)
                         if pools[ch['id']] and (ch["id"], s) not in occupied]
              for ch in channels}
    jobs = list(state["jobs"].values())
    attempted_ids = {entry['job_id'] for entries in state['attempts'].values()
                     for entry in entries.values()}
    metrics = {ch['id']: performance((reports or {}).get(ch['id']), ch['id'],
                                    pools[ch['id']], instant(now)) for ch in channels}
    additions = []
    while any(queues.values()):
        for ch in channels:
            cid = ch["id"]
            if not queues[cid]:
                continue
            ids = catalog_ids[cid]
            history = [j for j in jobs if j["channel"] == cid]
            cycle = max((j["cycle"] for j in history), default=1)
            used = {j["track_id"] for j in history if j["cycle"] == cycle and j["status"] != "cancelled"}
            available = [tid for tid in ids if tid not in used]
            if not available:
                cycle += 1
                available = ids
            slot = queues[cid].pop(0).isoformat()
            available = [tid for tid in available if repeat_ready(history, tid, slot, attempted_ids)]
            if not available:
                continue
            # Missing performance data: oldest public use first, stable ID ties.
            def lru(tid):
                dates = [publication_time(j) for j in history
                         if j['track_id'] == tid and j['status'] == 'uploaded']
                tie = tid if seed is None else hashlib.sha256(
                    repr((seed, cid, cycle, slot, tid)).encode()).hexdigest()
                return (max(dates) if dates else instant(now) - timedelta(days=100000), tie, tid)
            tid, bucket = min(available, key=lru), 'lru'
            scores, report_hash = metrics[cid]
            if cycle > 1:
                tid, bucket = choose(available, ids, scores, history, cid, seed, lru)
            job = dict(track_id=tid, channel=cid, cycle=cycle, slot=slot, status="planned")
            if cycle > 1:
                job['selection'] = {'bucket': bucket, 'score': scores.get(tid),
                                    'report_hash': report_hash}
            job["id"] = identity(job["track_id"], cid, cycle, slot)
            jobs.append(job)
            additions.append(job)
    return additions


def apply_plan(state, additions):
    for job in additions:
        state["jobs"].setdefault(job["id"], deepcopy(job))
