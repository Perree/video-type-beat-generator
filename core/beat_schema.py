"""Versioned Type Beats documents; pure, idempotent migrations."""
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import json
import re

BA = timezone(timedelta(hours=-3), "America/Argentina/Buenos_Aires")
VERSION = 1


def instant(value):
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("aware_datetime_required")
    # Argentina has used UTC-3 without DST since March 2009.
    if dt.year < 2010:
        raise ValueError("unsupported_historical_date")
    return dt.astimezone(BA)


def identity(track_id, channel, cycle, slot):
    if not isinstance(track_id, str) or not track_id or not isinstance(channel, str) or not channel:
        raise ValueError("invalid_identity")
    if type(cycle) is not int or cycle < 1:
        raise ValueError("invalid_cycle")
    return json.dumps([track_id, channel, cycle, instant(slot).isoformat()],
                      ensure_ascii=False, separators=(",", ":"))


def migrate(document, kind):
    if kind not in ("config", "state") or not isinstance(document, dict):
        raise ValueError("invalid_document")
    result = deepcopy(document)
    version = result.get("schema_version", 0)
    if type(version) is not int or version not in (0, VERSION):
        raise ValueError("unsupported_schema_version")
    if version == VERSION:
        required = {"namespace", "schema_version"} | (
            {"channels", "buffer_days", "daily_upload_attempts"} if kind == "config"
            else {"jobs", "attempts", "lock"})
        if not required <= result.keys():
            raise ValueError("incomplete_versioned_document")
    if result.get("namespace", "type-beats") != "type-beats":
        raise ValueError("wrong_namespace")
    result.update(schema_version=VERSION, namespace="type-beats")
    if kind == "config":
        result.setdefault("channels", [])
        result.setdefault("buffer_days", 14)
        result.setdefault("daily_upload_attempts", 6)
        if result["buffer_days"] != 14 or result["daily_upload_attempts"] != 6:
            raise ValueError("invalid_fixed_limits")
        channels = result["channels"]
        if not isinstance(channels, list) or len(channels) > 100:
            raise ValueError("invalid_channels")
        seen = set()
        for ch in channels:
            if not isinstance(ch, dict):
                raise ValueError("invalid_channel")
            if version == VERSION and not {"id", "active", "priority", "slots"} <= ch.keys():
                raise ValueError("incomplete_versioned_channel")
            cid = ch.get("id")
            if not isinstance(cid, str) or not cid.strip() or len(cid) > 200 or cid in seen:
                raise ValueError("invalid_channel_id")
            seen.add(cid)
            ch.setdefault("active", True)
            ch.setdefault("priority", 0)
            if type(ch["active"]) is not bool or type(ch["priority"]) is not int:
                raise ValueError("invalid_channel_options")
            slots = ch.get("slots")
            if not isinstance(slots, list) or not slots or len(slots) > 168:
                raise ValueError("invalid_slots")
            keys = set()
            for s in slots:
                if not isinstance(s, dict):
                    raise ValueError("invalid_slot")
                key = tuple(s.get(k) for k in ("weekday", "hour", "minute"))
                if any(type(v) is not int for v in key) or not (0 <= key[0] <= 6 and 0 <= key[1] <= 23 and 0 <= key[2] <= 59) or key in keys:
                    raise ValueError("invalid_slot")
                keys.add(key)
    else:
        result.setdefault("jobs", {})
        result.setdefault("attempts", {})
        result.setdefault("lock", None)
        if not isinstance(result["jobs"], dict) or not isinstance(result["attempts"], dict):
            raise ValueError("invalid_state")
        occupied = set()
        for key, job in result["jobs"].items():
            if not isinstance(job, dict) or key != identity(job.get("track_id"), job.get("channel"), job.get("cycle"), job.get("slot")):
                raise ValueError("invalid_job_identity")
            if version == 0:
                job.setdefault("id", key)
            if job.get("id") != key:
                raise ValueError("invalid_job_identity")
            if job.get("status") not in ("planned", "uploaded", "failed", "cancelled"):
                raise ValueError("invalid_job_status")
            pair = (job["channel"], instant(job["slot"]))
            if pair in occupied:
                raise ValueError("duplicate_channel_slot")
            occupied.add(pair)
        tokens = set()
        for day, attempts in result["attempts"].items():
            datetime.strptime(day, "%Y-%m-%d")
            if not isinstance(attempts, dict) or len(attempts) > 6:
                raise ValueError("invalid_attempts")
            for token, entry in attempts.items():
                if not isinstance(token, str) or not token or not isinstance(entry, dict) or entry.get("job_id") not in result["jobs"]:
                    raise ValueError("invalid_attempt")
                if token in tokens or instant(entry.get("reserved_at")).date().isoformat() != day:
                    raise ValueError("invalid_attempt_date")
                tokens.add(token)
        lock = result["lock"]
        if lock is not None:
            if not isinstance(lock, dict) or not isinstance(lock.get("owner"), str) or not lock["owner"]:
                raise ValueError("invalid_lock")
            instant(lock.get("expires_at"))
        from core.beat_media_schema import validate_media_state
        try:
            validate_media_state(result)
        except Exception:
            raise ValueError("invalid_media_state") from None
        from core.beat_seo import validate_snapshot
        # Cache content is revalidated at use, so corruption can fall back to manual.
        for job in result['jobs'].values():
            if 'youtube_id' in job:
                if (job['status'] != 'uploaded' or not isinstance(job['youtube_id'], str)
                        or not re.fullmatch(r'[A-Za-z0-9_-]{11}', job['youtube_id'])):
                    raise ValueError('invalid_upload_receipt')
                instant(job.get('uploaded_at'))
            if 'seo_snapshot' in job:
                try:
                    validate_snapshot(job['seo_snapshot'], job)
                except Exception:
                    raise ValueError('invalid_seo_snapshot') from None
    return result
