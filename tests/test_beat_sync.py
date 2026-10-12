import copy
import io
import json
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from core.beat_catalog import BeatCatalog
from core.beat_http import BeatError, Limits, PublicTransport, _NoRedirect
from core.beat_source import BeatStarsSource, PROFILE_QUERY, parse_track, profile_username
from core.beat_sync import sync_configured

FIXTURE = json.loads((Path(__file__).parent / "fixtures/beatstars_pages.json").read_text())
CONFIG = {"beat_automation": {"beatstars_profile_url": "https://www.beatstars.com/fixtureproducer/tracks"}}


class FakeTransport:
    def __init__(self, fixture=None):
        self.fixture = copy.deepcopy(fixture or FIXTURE)
        self.calls = []

    def query(self, query, variables, deadline):
        self.calls.append((query, variables))
        if query == PROFILE_QUERY:
            return self.fixture["profile"]
        return self.fixture["pages"][variables["page"]]


def single_page(raws):
    fixture = copy.deepcopy(FIXTURE)
    fixture["pages"] = [{"profileTracks": {"totalElements": len(raws), "totalPages": 1,
                          "number": 0, "last": True, "content": raws}}]
    return fixture


class SyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.catalog = BeatCatalog(Path(self.temp.name) / "catalog.db")

    def sync(self, fixture=None):
        fake = FakeTransport(fixture)
        result = sync_configured(CONFIG, self.catalog, BeatStarsSource(fake, Limits(page_size=1)))
        return result, fake

    def test_scan_only_metadata_and_retains_no_private_fields(self):
        result, fake = self.sync()
        self.assertEqual(result["added"], 2)
        self.assertEqual(len(fake.calls), 3)
        self.assertTrue(all("mutation" not in q and "url" not in q.lower() for q, _ in fake.calls))
        tracks = self.catalog.tracks("MR100")
        self.assertEqual(tracks[0]["duration"], 180)
        self.assertEqual(tracks[0]["tags"], ["trap", "dark"])
        self.assertEqual(tracks[0]["preview_ref"]["track_id"], "TK101")
        self.assertNotIn("fixture-secret", json.dumps(tracks))
        self.assertEqual(tracks[0]["url"], "https://www.beatstars.com/beat/fixture-trap-101")

    def test_incremental_rename_inactive_and_reactivation(self):
        self.sync()
        before = self.catalog.tracks("MR100")
        noop, _ = self.sync()
        self.assertEqual(noop["catalog_version"], 1)
        self.assertEqual(noop["unchanged"], 2)
        self.assertEqual(len(self.catalog.revisions("MR100")), 2)
        raw = copy.deepcopy(FIXTURE["pages"][0]["profileTracks"]["content"][0])
        raw["title"] = "Renamed"
        raw["seoMetadata"]["slug"] = "renamed-101"
        change, _ = self.sync(single_page([raw]))
        self.assertEqual((change["updated"], change["inactivated"], change["catalog_version"]), (1, 1, 2))
        self.assertEqual(len(self.catalog.tracks("MR100")), 1)
        all_tracks = self.catalog.tracks("MR100", True)
        self.assertEqual(all_tracks[0]["first_seen"], before[0]["first_seen"])
        self.assertFalse(all_tracks[1]["active"])
        returned, _ = self.sync()
        self.assertEqual(returned["reactivated"], 1)
        self.assertEqual(returned["catalog_version"], 3)

    def test_empty_complete_scan_inactivates(self):
        self.sync()
        result, _ = self.sync(single_page([]))
        self.assertEqual(result["inactivated"], 2)

    def test_new_track_added_incrementally(self):
        raw = copy.deepcopy(FIXTURE["pages"][0]["profileTracks"]["content"][0])
        self.sync(single_page([raw]))
        result, _ = self.sync()
        self.assertEqual((result["added"], result["unchanged"], result["catalog_version"]), (1, 1, 2))

    def test_other_profile_is_isolated(self):
        self.sync()
        fixture = copy.deepcopy(FIXTURE)
        fixture["profile"]["profileByUsername"]["memberId"] = "MR200"
        for page in fixture["pages"]:
            for raw in page["profileTracks"]["content"]:
                raw["profile"]["memberId"] = "MR200"
        self.sync(fixture)
        self.assertEqual(len(self.catalog.tracks("MR100")), 2)
        self.assertEqual(len(self.catalog.tracks("MR200")), 2)

    def test_revision_retention(self):
        raw = copy.deepcopy(FIXTURE["pages"][0]["profileTracks"]["content"][0])
        for number in range(25):
            raw["title"] = "Title " + str(number)
            self.sync(single_page([copy.deepcopy(raw)]))
        history = self.catalog.revisions("MR100")
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0]["version"], 6)

    def test_failed_or_partial_scan_never_changes_catalog(self):
        self.sync()
        before = self.catalog.tracks("MR100", True)
        fixtures = []
        for field, value in (("totalElements", 999999), ("number", 4), ("last", True), ("content", [])):
            fixture = copy.deepcopy(FIXTURE)
            fixture["pages"][0]["profileTracks"][field] = value
            fixtures.append(fixture)
        bad_owner = copy.deepcopy(FIXTURE)
        bad_owner["pages"][1]["profileTracks"]["content"][0]["profile"]["memberId"] = "MR999"
        fixtures.append(bad_owner)
        duplicate = copy.deepcopy(FIXTURE)
        duplicate["pages"][1]["profileTracks"]["content"] = duplicate["pages"][0]["profileTracks"]["content"]
        fixtures.append(duplicate)
        changed_total = copy.deepcopy(FIXTURE)
        changed_total["pages"][1]["profileTracks"]["totalElements"] = 1
        fixtures.append(changed_total)
        for fixture in fixtures:
            with self.subTest(fixture=fixtures.index(fixture)):
                with self.assertRaises(BeatError):
                    self.sync(fixture)
                self.assertEqual(self.catalog.tracks("MR100", True), before)

    def test_page_limit_and_deadline(self):
        with self.assertRaises(BeatError):
            BeatStarsSource(FakeTransport(), Limits(max_pages=1)).scan(CONFIG["beat_automation"]["beatstars_profile_url"])
        with patch("core.beat_source.time.monotonic", side_effect=[0, 121]):
            with self.assertRaisesRegex(BeatError, "scan_timeout"):
                BeatStarsSource(FakeTransport()).scan(CONFIG["beat_automation"]["beatstars_profile_url"])

    def test_malformed_metadata_rejected(self):
        for field, value in (("id", "private-id"), ("v2Id", 999), ("title", "x" * 501),
                             ("metadata", {"tags": ["x"] * 41}), ("seoMetadata", {"slug": "../../101"}),
                             ("bundle", {"hls": {"duration": float("nan")}})):
            fixture = copy.deepcopy(FIXTURE)
            fixture["pages"][0]["profileTracks"]["content"][0][field] = value
            with self.subTest(field=field), self.assertRaises(BeatError):
                self.sync(fixture)

    def test_large_duration_rejected_without_changing_catalog(self):
        self.sync()
        before = self.catalog.tracks("MR100", True)
        history = self.catalog.revisions("MR100")
        for kind in ("hls", "stream"):
            for duration in (10**400, -(10**400)):
                fixture = copy.deepcopy(FIXTURE)
                fixture["pages"][0]["profileTracks"]["content"][0]["bundle"] = {
                    kind: {"duration": duration}}
                with self.subTest(kind=kind, positive=duration > 0):
                    with self.assertRaisesRegex(BeatError, "^invalid_metadata$"):
                        self.sync(fixture)
                    self.assertEqual(self.catalog.tracks("MR100", True), before)
                    self.assertEqual(self.catalog.revisions("MR100"), history)

    def test_actual_track_limit_stops_before_processing_excess_page(self):
        self.sync()
        before = self.catalog.tracks("MR100", True)
        history = self.catalog.revisions("MR100")
        fixture = copy.deepcopy(FIXTURE)
        third = copy.deepcopy(fixture["pages"][1])
        raw = third["profileTracks"]["content"][0]
        raw.update(id="TK103", v2Id=103, seoMetadata={"slug": "fixture-third-103"})
        fixture["pages"].append(third)
        for number, page in enumerate(fixture["pages"]):
            page["profileTracks"].update(totalElements=1, totalPages=3,
                                         number=number, last=number == 2)
        fake = FakeTransport(fixture)
        source = BeatStarsSource(fake, Limits(max_tracks=1, page_size=1))
        with patch("core.beat_source.parse_track", wraps=parse_track) as parsed:
            with self.assertRaisesRegex(BeatError, "^scan_limit$"):
                sync_configured(CONFIG, self.catalog, source)
            self.assertEqual(parsed.call_count, 1)
        self.assertEqual(len(fake.calls), 3)  # profile + first two pages; no third page
        self.assertEqual(self.catalog.tracks("MR100", True), before)
        self.assertEqual(self.catalog.revisions("MR100"), history)

    def test_actual_track_limit_rejects_oversized_first_page(self):
        raws = [copy.deepcopy(page["profileTracks"]["content"][0]) for page in FIXTURE["pages"]]
        fixture = single_page(raws)
        fixture["pages"][0]["profileTracks"]["totalElements"] = 1
        source = BeatStarsSource(FakeTransport(fixture), Limits(max_tracks=1))
        with patch("core.beat_source.parse_track", wraps=parse_track) as parsed:
            with self.assertRaisesRegex(BeatError, "^scan_limit$"):
                sync_configured(CONFIG, self.catalog, source)
            parsed.assert_not_called()
        self.assertEqual(self.catalog.tracks("MR100", True), [])

    def test_config_and_host_allowlist(self):
        for url in ("http://www.beatstars.com/a", "https://www.beatstars.com.evil.invalid/a",
                    "https://user:secret@www.beatstars.com/a", "https://localhost/a",
                    "https://www.beatstars.com:444/a", "https://www.beatstars.com/a?token=secret",
                    "https://www.beatstars.com/a#fragment", "https://www.beatstars.com/a\n"):
            with self.subTest(url=url), self.assertRaises(BeatError):
                profile_username(url)
        with self.assertRaisesRegex(BeatError, "profile_not_configured"):
            sync_configured({}, self.catalog)

    def test_transport_errors_are_sanitized(self):
        fake = FakeTransport()
        fake.query = lambda *args: (_ for _ in ()).throw(RuntimeError("private secret URL"))
        with self.assertRaisesRegex(BeatError, "^request_failed$"):
            sync_configured(CONFIG, self.catalog, BeatStarsSource(fake))

    def test_unknown_schema_rejected(self):
        path = Path(self.temp.name) / "future.db"
        with closing(sqlite3.connect(path)) as db, db:
            db.execute("PRAGMA user_version=99")
        with self.assertRaisesRegex(BeatError, "unsupported_catalog_version"):
            BeatCatalog(path)

    def test_transaction_rolls_back(self):
        self.sync()
        before = self.catalog.tracks("MR100", True)
        with closing(sqlite3.connect(self.catalog.path)) as db, db:
            db.execute("CREATE TRIGGER reject_revision BEFORE INSERT ON revisions BEGIN SELECT RAISE(ABORT,'private'); END")
        with self.assertRaisesRegex(BeatError, "^catalog_error$"):
            self.sync(single_page([]))
        self.assertEqual(self.catalog.tracks("MR100", True), before)


class Response(io.BytesIO):
    status = 200

    def __init__(self, body, content_type="application/json", length=None):
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if length is not None:
            self.headers["Content-Length"] = str(length)


class HttpTests(unittest.TestCase):
    def query(self, response, limits=None):
        transport = PublicTransport(limits)
        with patch.object(transport._opener, "open", return_value=response) as opened:
            result = transport.query(PROFILE_QUERY, {"username": "fixtureproducer"}, time.monotonic() + 5)
            req = opened.call_args.args[0]
            self.assertEqual(req.full_url, "https://core.prod.beatstars.net/graphql")
            self.assertNotIn("Authorization", req.headers)
            self.assertNotIn("Cookie", req.headers)
            self.assertLessEqual(opened.call_args.kwargs["timeout"], 5)
            return result

    def test_valid_response(self):
        self.assertEqual(self.query(Response(b'{"data":{"ok":true}}')), {"ok": True})

    def test_size_and_content_limits(self):
        for response in (Response(b"x" * 101), Response(b"{}", length=101),
                         Response(b"audio", "audio/mpeg"), Response(b"not json"),
                         Response(b'{"errors":[{"message":"private secret"}]}')):
            with self.assertRaises(BeatError) as error:
                self.query(response, Limits(max_bytes=100))
            self.assertNotIn("secret", str(error.exception))

    def test_redirect_rejected_even_to_allowed_host(self):
        with self.assertRaisesRegex(BeatError, "redirect_rejected"):
            _NoRedirect().redirect_request(None, None, 302, "private", {}, "https://www.beatstars.com/a")

    def test_invalid_limits(self):
        for values in ({"timeout": 0}, {"max_bytes": 999999999}, {"max_pages": True},
                       {"scan_seconds": float("inf")}, {"page_size": 101}):
            with self.assertRaisesRegex(BeatError, "invalid_limits"):
                Limits(**values)

    def test_only_fixed_read_queries_allowed(self):
        transport = PublicTransport()
        with patch.object(transport._opener, "open") as opened:
            with self.assertRaisesRegex(BeatError, "query_rejected"):
                transport.query("mutation {anything}", {}, time.monotonic() + 5)
            opened.assert_not_called()

    def test_network_timeout_is_sanitized(self):
        transport = PublicTransport()
        with patch.object(transport._opener, "open", side_effect=TimeoutError("private URL")):
            with self.assertRaisesRegex(BeatError, "^request_failed$"):
                transport.query(PROFILE_QUERY, {}, time.monotonic() + 5)


if __name__ == "__main__":
    unittest.main()
