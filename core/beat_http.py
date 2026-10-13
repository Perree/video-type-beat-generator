"""Bounded, anonymous transport for the public BeatStars metadata endpoint."""
import json
import math
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit
from core.beat_queries import PROFILE_QUERY, TRACKS_QUERY, PREVIEWS_QUERY, SHARE_QUERY

ENDPOINT = "https://core.prod.beatstars.net/graphql"
PROFILE_HOSTS = frozenset({"beatstars.com", "www.beatstars.com"})
API_HOSTS = frozenset({"core.prod.beatstars.net"})


class BeatError(Exception):
    """Only fixed codes: never include remote bodies, URLs or local paths."""


def check_url(value, hosts):
    try:
        p = urlsplit(value)
        valid = (isinstance(value, str) and len(value) <= 2048
                 and p.scheme == "https" and p.hostname in hosts
                 and not p.username and not p.password and p.port in (None, 443)
                 and not p.fragment and not any(ord(c) <= 32 for c in value))
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise BeatError("url_rejected") from None
    return p


@dataclass(frozen=True)
class Limits:
    timeout: float = 10
    scan_seconds: float = 120
    max_bytes: int = 2_000_000
    page_size: int = 50
    max_pages: int = 100
    max_tracks: int = 5000

    def __post_init__(self):
        for name, ceiling in (("timeout", 30), ("scan_seconds", 600)):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 < v <= ceiling:
                raise BeatError("invalid_limits")
        for name, ceiling in (("max_bytes", 4_000_000), ("page_size", 100),
                              ("max_pages", 200), ("max_tracks", 10000)):
            v = getattr(self, name)
            if type(v) is not int or not 1 <= v <= ceiling:
                raise BeatError("invalid_limits")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise BeatError("redirect_rejected")


class PublicTransport:
    def __init__(self, limits=None):
        self.limits = limits or Limits()
        # No environment proxies, cookie jar, authentication or automatic redirects.
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect())

    def query(self, query, variables, deadline):
        if query not in (PROFILE_QUERY, TRACKS_QUERY, PREVIEWS_QUERY, SHARE_QUERY):
            raise BeatError("query_rejected")
        check_url(ENDPOINT, API_HOSTS)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BeatError("scan_timeout")
        body = json.dumps({"query": query, "variables": variables}).encode("utf-8")
        req = urllib.request.Request(ENDPOINT, data=body, headers={
            "Content-Type": "application/json", "Accept": "application/json",
            "Accept-Encoding": "identity", "User-Agent": "TypeBeatCatalog/1"})
        try:
            with self._opener.open(req, timeout=min(self.limits.timeout, remaining)) as r:
                if r.status != 200:
                    raise BeatError("http_error")
                if r.headers.get_content_type() != "application/json" or r.headers.get("Content-Encoding", "identity") != "identity":
                    raise BeatError("response_rejected")
                length = r.headers.get("Content-Length")
                if length and (not length.isdecimal() or int(length) > self.limits.max_bytes):
                    raise BeatError("response_limit")
                data = bytearray()
                while True:
                    if time.monotonic() >= deadline:
                        raise BeatError("scan_timeout")
                    chunk = r.read1(min(65536, self.limits.max_bytes + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > self.limits.max_bytes:
                        raise BeatError("response_limit")
            result = json.loads(data)
        except BeatError:
            raise
        except (TimeoutError, OSError, ValueError, RecursionError, urllib.error.URLError):
            raise BeatError("request_failed") from None
        if not isinstance(result, dict) or result.get("errors") or not isinstance(result.get("data"), dict):
            raise BeatError("remote_schema_error")
        return result["data"]
