"""Public metadata extractor. Never requests audio, stream URLs or user secrets."""
import math
import re
import time
from dataclasses import dataclass, asdict

from core.beat_http import BeatError, Limits, PROFILE_HOSTS, PublicTransport, check_url
from core.beat_queries import PROFILE_QUERY, TRACKS_QUERY


def profile_username(url):
    p = check_url(url, PROFILE_HOSTS)
    match = re.fullmatch(r"/([A-Za-z0-9_-]{1,80})(?:/tracks)?/?", p.path)
    if not match or p.query:
        raise BeatError("invalid_profile")
    return match[1]


def _id(value, prefix):
    if not isinstance(value, str) or not re.fullmatch(prefix + r"[0-9]{1,20}", value):
        raise BeatError("invalid_metadata")
    return value


def _text(value, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise BeatError("invalid_metadata")
    return value


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    url: str
    tags: tuple
    duration: float | None
    preview_ref: dict

    def payload(self):
        result = asdict(self)
        result["tags"] = list(self.tags)
        return result


@dataclass(frozen=True)
class Snapshot:
    member_id: str
    username: str
    tracks: tuple


def parse_track(raw, member_id):
    try:
        track_id = _id(raw["id"], "TK")
        if raw["profile"]["memberId"] != member_id:
            raise BeatError("owner_mismatch")
        v2 = raw["v2Id"]
        if isinstance(v2, bool) or not re.fullmatch(r"[0-9]{1,20}", str(v2)) or str(v2) != track_id[2:]:
            raise BeatError("invalid_metadata")
        slug = raw["seoMetadata"]["slug"]
        if not isinstance(slug, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,400}", slug) or not slug.endswith("-" + str(v2)):
            raise BeatError("invalid_metadata")
        tags = raw["metadata"]["tags"]
        if not isinstance(tags, list) or len(tags) > 40:
            raise BeatError("invalid_metadata")
        tags = tuple(dict.fromkeys(_text(tag, 100) for tag in tags))
        bundle = raw.get("bundle") or {}
        duration = None
        for kind in ("hls", "stream"):
            if bundle.get(kind) and bundle[kind].get("duration") is not None:
                duration = bundle[kind]["duration"]
                if (isinstance(duration, bool) or not isinstance(duration, (int, float))
                    or not 0 < duration <= 86400 or not math.isfinite(duration)):
                    raise BeatError("invalid_metadata")
                duration = float(duration)
                break
        url = "https://www.beatstars.com/beat/" + slug
        return Track(track_id, _text(raw["title"], 500), url, tags, duration,
                     {"provider": "beatstars", "track_id": track_id,
                      "v2_id": str(v2), "page_url": url})
    except (KeyError, TypeError, AttributeError):
        raise BeatError("invalid_metadata") from None


class BeatStarsSource:
    def __init__(self, transport=None, limits=None):
        self.limits = limits or Limits()
        self.transport = transport or PublicTransport(self.limits)

    def scan(self, profile_url):
        username = profile_username(profile_url)
        deadline = time.monotonic() + self.limits.scan_seconds
        try:
            profile = self._query(PROFILE_QUERY, {"username": username}, deadline)["profileByUsername"]
            member_id = _id(profile["memberId"], "MR")
            canonical = profile_username("https://www.beatstars.com/" + profile["username"])
            if canonical.casefold() != username.casefold():
                raise BeatError("profile_mismatch")
            tracks, expected = {}, None
            for page in range(self.limits.max_pages):
                data = self._query(TRACKS_QUERY, {"memberId": member_id, "page": page,
                                                "size": self.limits.page_size}, deadline)["profileTracks"]
                total, pages, number, last = (data[k] for k in ("totalElements", "totalPages", "number", "last"))
                content = data["content"]
                if (type(total) is not int or not 0 <= total <= self.limits.max_tracks
                    or type(pages) is not int or not 0 <= pages <= self.limits.max_pages
                    or type(number) is not int or number != page or type(last) is not bool
                    or not isinstance(content, list) or len(content) > self.limits.page_size):
                    raise BeatError("pagination_rejected")
                if expected is None:
                    expected = (total, pages)
                if expected != (total, pages) or (not last and not content):
                    raise BeatError("scan_inconsistent")
                if len(tracks) + len(content) > self.limits.max_tracks:
                    raise BeatError("scan_limit")
                for raw in content:
                    track = parse_track(raw, member_id)
                    if track.id in tracks:
                        raise BeatError("duplicate_track")
                    tracks[track.id] = track
                if last:
                    if len(tracks) != total or page + 1 != max(pages, 1):
                        raise BeatError("scan_incomplete")
                    return Snapshot(member_id, canonical, tuple(tracks.values()))
            raise BeatError("scan_limit")
        except (KeyError, TypeError, AttributeError):
            raise BeatError("remote_schema_error") from None

    def _query(self, query, variables, deadline):
        if time.monotonic() >= deadline:
            raise BeatError("scan_timeout")
        try:
            data = self.transport.query(query, variables, deadline)
        except BeatError:
            raise
        except Exception:
            raise BeatError("request_failed") from None
        if time.monotonic() >= deadline:
            raise BeatError("scan_timeout")
        return data
