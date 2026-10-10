#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: reconstruir uploads (beat_id nullable + clip_id). Solo SQLite, sin red."""

import os
import shutil
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import library, shorts_store

# Esquema viejo: beat_id NOT NULL y sin clip_id. La migración tiene que aflojarlo.
OLD_SCHEMA = """
CREATE TABLE beats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    ruta TEXT NOT NULL,
    hash TEXT NOT NULL,
    bpm REAL,
    key TEXT,
    beatstars_url TEXT,
    notas TEXT,
    creado TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'beat'
);
CREATE UNIQUE INDEX idx_beats_hash_kind ON beats(hash, kind);
CREATE TABLE uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    beat_id INTEGER NOT NULL REFERENCES beats(id) ON DELETE CASCADE,
    canal TEXT,
    grupo TEXT,
    youtube_id TEXT,
    url TEXT,
    titulo TEXT,
    subido_en TEXT NOT NULL,
    estado TEXT
);
CREATE INDEX idx_uploads_beat ON uploads(beat_id, canal);
"""


def _counts(path):
    conn = sqlite3.connect(path)
    try:
        beats = conn.execute("SELECT COUNT(*) FROM beats").fetchone()[0]
        uploads = conn.execute("SELECT COUNT(*) FROM uploads").fetchone()[0]
        return beats, uploads
    finally:
        conn.close()


def main() -> int:
    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "library.db")
    bak = os.path.join(tmp, "library.db.bak")

    conn = sqlite3.connect(db)
    conn.executescript(OLD_SCHEMA)
    conn.execute(
        "INSERT INTO beats (nombre, ruta, hash, creado) VALUES (?, ?, ?, ?)",
        ("beat viejo", "library/beat.wav", "hash-viejo", "2024-01-01T00:00:00"))
    conn.execute(
        "INSERT INTO uploads (beat_id, canal, grupo, youtube_id, url, titulo, subido_en, estado) "
        "VALUES (1, 'canal', 'g', 'yt-viejo', 'https://youtu.be/yt-viejo', 'titulo', "
        "'2024-06-01T12:00:00', 'private')")
    conn.commit()
    conn.close()

    before_beats, before_uploads = _counts(db)
    shutil.copy2(db, bak)

    library._connect(db)

    beats, uploads = _counts(db)
    bak_beats, bak_uploads = _counts(bak)
    if (beats, uploads) != (before_beats, before_uploads) or (beats, uploads) != (bak_beats, bak_uploads):
        print("FAIL: counts", beats, uploads, "backup", bak_beats, bak_uploads)
        return 1
    if beats != 1 or uploads != 1:
        print("FAIL: se esperaba 1 beat y 1 upload", beats, uploads)
        return 1

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    info = {row[1]: row for row in conn.execute("PRAGMA table_info(uploads)")}
    if "clip_id" not in info or info["beat_id"][3] != 0:
        print("FAIL: columnas", {k: v[3] for k, v in info.items()})
        return 1
    old = conn.execute(
        "SELECT beat_id, clip_id, youtube_id FROM uploads WHERE id = 1").fetchone()
    conn.close()
    if old["beat_id"] != 1 or old["youtube_id"] != "yt-viejo" or old["clip_id"] is not None:
        print("FAIL: fila vieja", dict(old))
        return 1

    try:
        library.record_upload(None, "canal", db_path=db)
        print("FAIL: aceptó beat_id y clip_id vacíos")
        return 1
    except ValueError:
        pass

    try:
        with library._connect(db) as conn:
            conn.execute(
                "INSERT INTO uploads (beat_id, clip_id, subido_en) VALUES (NULL, NULL, 'x')")
        print("FAIL: el CHECK dejó pasar los dos NULL")
        return 1
    except sqlite3.IntegrityError:
        pass

    vid = shorts_store.upsert_video("C:/videos/largo.mp4", "hash-video", db_path=db)
    shorts_store.replace_clips(vid, [{
        "start": 10.0, "end": 40.0, "titulo": "Tip de mezcla",
    }], db_path=db)
    clip_id = shorts_store.list_clips(vid, db_path=db)[0]["id"]
    library.record_upload(
        None, "personal", youtube_id="yt-short", url="https://youtu.be/yt-short",
        titulo="Tip", estado="private", db_path=db, clip_id=clip_id)
    beat_row_id = library.record_upload(
        1, "canal", youtube_id="yt-beat", titulo="otro", estado="private", db_path=db)

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    short_row = conn.execute(
        "SELECT beat_id, clip_id, youtube_id FROM uploads WHERE clip_id = ?",
        (clip_id,)).fetchone()
    beat_row = conn.execute(
        "SELECT beat_id, clip_id FROM uploads WHERE id = ?", (beat_row_id,)).fetchone()
    still = conn.execute(
        "SELECT beat_id, youtube_id FROM uploads WHERE id = 1").fetchone()
    fk = conn.execute("PRAGMA foreign_key_check").fetchall()
    conn.close()
    if short_row["beat_id"] is not None or short_row["clip_id"] != clip_id:
        print("FAIL: fila de short", dict(short_row))
        return 1
    if beat_row["beat_id"] != 1 or beat_row["clip_id"] is not None:
        print("FAIL: fila de beat", dict(beat_row))
        return 1
    if still["beat_id"] != 1 or still["youtube_id"] != "yt-viejo":
        print("FAIL: la fila histórica cambió", dict(still))
        return 1
    if fk:
        print("FAIL: foreign_key_check", fk)
        return 1

    # Borrar el video largo no puede chocar con el CHECK de uploads.
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("DELETE FROM long_videos WHERE id = ?", (vid,))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        print("FAIL: borrar el video largo chocó con uploads", exc)
        return 1
    short_left = conn.execute(
        "SELECT COUNT(*) FROM uploads WHERE youtube_id = 'yt-short'").fetchone()[0]
    beats_left = conn.execute(
        "SELECT COUNT(*) FROM uploads WHERE beat_id IS NOT NULL").fetchone()[0]
    on_delete = ""
    for row in conn.execute("PRAGMA foreign_key_list(uploads)"):
        if row[3] == "clip_id":
            on_delete = (row[6] or "").upper()
    conn.close()
    if short_left != 0 or beats_left != 2 or on_delete != "CASCADE":
        print("FAIL: delete clip", short_left, beats_left, on_delete)
        return 1

    # Segunda conexión: la migración no se repite ni duplica filas.
    library._connect(db)
    if _counts(db)[0] != 1:
        print("FAIL: beats cambiaron al reconectar")
        return 1

    # Una base que ya migró con SET NULL tiene que pasar a CASCADE.
    db_setnull = os.path.join(tmp, "setnull.db")
    conn = sqlite3.connect(db_setnull)
    conn.executescript("""
        CREATE TABLE beats (
            id INTEGER PRIMARY KEY, nombre TEXT, ruta TEXT, hash TEXT,
            bpm REAL, key TEXT, beatstars_url TEXT, notas TEXT, creado TEXT, kind TEXT
        );
        CREATE TABLE clips (id INTEGER PRIMARY KEY, video_id INTEGER);
        CREATE TABLE uploads (
            id INTEGER PRIMARY KEY,
            beat_id INTEGER REFERENCES beats(id) ON DELETE CASCADE,
            clip_id INTEGER REFERENCES clips(id) ON DELETE SET NULL,
            canal TEXT, grupo TEXT, youtube_id TEXT, url TEXT, titulo TEXT,
            subido_en TEXT NOT NULL, estado TEXT,
            CHECK (beat_id IS NOT NULL OR clip_id IS NOT NULL)
        );
        INSERT INTO clips (id, video_id) VALUES (7, 1);
        INSERT INTO uploads (beat_id, clip_id, youtube_id, subido_en)
        VALUES (NULL, 7, 'yt-setnull', '2024-01-01T00:00:00');
    """)
    conn.commit()
    conn.close()
    library._connect(db_setnull)
    conn = sqlite3.connect(db_setnull)
    action = ""
    for row in conn.execute("PRAGMA foreign_key_list(uploads)"):
        if row[3] == "clip_id":
            action = (row[6] or "").upper()
    kept = conn.execute(
        "SELECT clip_id, youtube_id FROM uploads WHERE youtube_id = 'yt-setnull'").fetchone()
    conn.close()
    if action != "CASCADE" or kept is None or kept[0] != 7:
        print("FAIL: remigración SET NULL", action, kept)
        return 1

    # Fila con beat y clip: borrar el clip no puede llevarse la subida del beat.
    mix_vid = shorts_store.upsert_video("C:/videos/mix.mp4", "hash-mix", db_path=db)
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        "INSERT INTO clips (video_id, start_s, end_s) VALUES (?, 0, 30)", (mix_vid,))
    mixed_clip = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO uploads (beat_id, clip_id, youtube_id, subido_en) "
        "VALUES (1, ?, 'yt-mix', '2024-01-02T00:00:00')", (mixed_clip,))
    conn.commit()
    try:
        conn.execute("DELETE FROM clips WHERE id = ?", (mixed_clip,))
        conn.commit()
    except sqlite3.IntegrityError as exc:
        print("FAIL: borrar clip mixto", exc)
        return 1
    mixed = conn.execute(
        "SELECT beat_id, clip_id, youtube_id FROM uploads WHERE youtube_id = 'yt-mix'"
    ).fetchone()
    conn.close()
    if mixed is None or mixed[0] != 1 or mixed[1] is not None:
        print("FAIL: la subida del beat no sobrevivió", mixed)
        return 1

    from core.ffmpeg_util import escape_filter_path
    escaped = escape_filter_path("C:/videos/it's a test.ass")
    if "\\'" not in escaped or "\\:" not in escaped:
        print("FAIL: escape_filter_path", escaped)
        return 1

    print("OK smoke_uploads_migration")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
