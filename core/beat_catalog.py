"""Separate SQLite catalog: atomic incremental updates and retained revisions."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from core.beat_http import BeatError

SCHEMA_VERSION = 1
MAX_STORED_TRACKS = 20000
RETAIN_VERSIONS = 20


class BeatCatalog:
    def __init__(self, path):
        self.path = Path(path)
        with self._db() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise BeatError("unsupported_catalog_version")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS profiles (
                    member_id TEXT PRIMARY KEY, username TEXT NOT NULL,
                    version INTEGER NOT NULL, scanned_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tracks (
                    member_id TEXT NOT NULL, track_id TEXT NOT NULL,
                    payload TEXT NOT NULL, active INTEGER NOT NULL,
                    first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
                    changed_version INTEGER NOT NULL,
                    PRIMARY KEY(member_id, track_id));
                CREATE TABLE IF NOT EXISTS revisions (
                    member_id TEXT NOT NULL, version INTEGER NOT NULL,
                    track_id TEXT NOT NULL, payload TEXT NOT NULL,
                    active INTEGER NOT NULL, changed_at TEXT NOT NULL,
                    PRIMARY KEY(member_id, version, track_id));
            """)
            db.execute("PRAGMA user_version = 1")

    @contextmanager
    def _db(self):
        db = None
        try:
            db = sqlite3.connect(self.path, timeout=5)
            db.row_factory = sqlite3.Row
            with db:
                yield db
        except (sqlite3.Error, OSError, ValueError):
            raise BeatError("catalog_error") from None
        finally:
            if db is not None:
                db.close()

    def apply(self, snapshot):
        """Only called after a complete scan; any failure rolls back all changes."""
        now = datetime.now(timezone.utc).isoformat()
        incoming = {t.id: json.dumps(t.payload(), sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")) for t in snapshot.tracks}
        if len(incoming) != len(snapshot.tracks) or len(incoming) > 10000:
            raise BeatError("catalog_limit")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            profile = db.execute("SELECT * FROM profiles WHERE member_id=?", (snapshot.member_id,)).fetchone()
            old = {r["track_id"]: r for r in db.execute(
                "SELECT * FROM tracks WHERE member_id=?", (snapshot.member_id,))}
            stored = db.execute("SELECT count(*) FROM tracks").fetchone()[0]
            if stored + len(incoming.keys() - old.keys()) > MAX_STORED_TRACKS:
                raise BeatError("catalog_limit")
            added = incoming.keys() - old.keys()
            updated = {k for k in incoming.keys() & old.keys() if incoming[k] != old[k]["payload"]}
            reactivated = {k for k in incoming.keys() & old.keys() if not old[k]["active"]}
            inactive = {k for k in old.keys() - incoming.keys() if old[k]["active"]}
            changed = added | updated | reactivated | inactive
            version = (profile["version"] if profile else 0)
            if changed or not profile or profile["username"] != snapshot.username:
                version += 1
            for key, payload in incoming.items():
                db.execute("""INSERT INTO tracks VALUES (?,?,?,1,?,?,?)
                    ON CONFLICT(member_id,track_id) DO UPDATE SET
                    payload=excluded.payload, active=1, last_seen=excluded.last_seen,
                    changed_version=excluded.changed_version""",
                    (snapshot.member_id, key, payload, now, now,
                     version if key in changed else old[key]["changed_version"]))
            for key in inactive:
                db.execute("UPDATE tracks SET active=0, changed_version=? WHERE member_id=? AND track_id=?",
                           (version, snapshot.member_id, key))
            for key in changed:
                db.execute("INSERT INTO revisions VALUES (?,?,?,?,?,?)",
                           (snapshot.member_id, version, key,
                            incoming.get(key, old[key]["payload"] if key in old else ""),
                            int(key in incoming), now))
            db.execute("""INSERT INTO profiles VALUES (?,?,?,?)
                ON CONFLICT(member_id) DO UPDATE SET username=excluded.username,
                version=excluded.version, scanned_at=excluded.scanned_at""",
                (snapshot.member_id, snapshot.username, version, now))
            db.execute("DELETE FROM revisions WHERE member_id=? AND version<=?",
                       (snapshot.member_id, version - RETAIN_VERSIONS))
        return {"schema_version": SCHEMA_VERSION, "catalog_version": version,
                "added": len(added), "updated": len(updated),
                "reactivated": len(reactivated), "inactivated": len(inactive),
                "unchanged": len(incoming) - len(added | updated | reactivated)}

    def tracks(self, member_id, include_inactive=False):
        with self._db() as db:
            rows = db.execute("""SELECT * FROM tracks WHERE member_id=?
                AND (active=1 OR ?) ORDER BY track_id LIMIT ?""",
                (member_id, int(include_inactive), MAX_STORED_TRACKS))
            return [dict(json.loads(r["payload"]), active=bool(r["active"]),
                         first_seen=r["first_seen"], last_seen=r["last_seen"],
                         changed_version=r["changed_version"]) for r in rows]

    def revisions(self, member_id):
        with self._db() as db:
            return [dict(r) for r in db.execute("""SELECT version,track_id,active,payload,changed_at
                FROM revisions WHERE member_id=? ORDER BY version,track_id""", (member_id,))]
