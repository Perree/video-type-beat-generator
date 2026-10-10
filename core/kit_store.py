# -*- coding: utf-8 -*-
"""Packs de loop kits y corridas de preview en library.db.

Tablas propias: no toca `beats` ni `uploads`.
"""
import json
import sqlite3
from datetime import datetime, timedelta

from core import library

AUDIO_MODES = ('named_preview', 'assembled')
RUN_STATES = ('rendered', 'scheduled', 'private_pending', 'uploaded', 'error')

SCHEMA = """
CREATE TABLE IF NOT EXISTS kit_packs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dropbox_path TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL,
    last_used_at TEXT
);
CREATE TABLE IF NOT EXISTS kit_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pack_id INTEGER NOT NULL REFERENCES kit_packs(id),
    canal TEXT,
    audio_mode TEXT NOT NULL,
    loops_json TEXT,
    image_path TEXT,
    video_path TEXT,
    youtube_id TEXT,
    url TEXT,
    publish_at TEXT,
    subido_en TEXT,
    estado TEXT
);
CREATE INDEX IF NOT EXISTS idx_kit_runs_pack ON kit_runs(pack_id);
CREATE INDEX IF NOT EXISTS idx_kit_packs_last_used ON kit_packs(last_used_at);
"""

_RUN_FIELDS = {
    'canal', 'audio_mode', 'loops_json', 'image_path', 'video_path',
    'youtube_id', 'url', 'publish_at', 'subido_en', 'estado',
}


def _now():
    return datetime.now().isoformat(timespec='seconds')


def ensure_schema(conn):
    """Crea kit_packs y kit_runs si no existen (idempotente)."""
    conn.executescript(SCHEMA)
    conn.commit()


def connect(db_path=None):
    conn = sqlite3.connect(db_path or library.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


def upsert_pack(dropbox_path, nombre, db_path=None):
    """Inserta o actualiza un pack por dropbox_path. Devuelve el id.

    No toca last_used_at: eso lo hace record_run sobre ese pack.
    """
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM kit_packs WHERE dropbox_path = ?",
            (dropbox_path,)).fetchone()
        if row:
            conn.execute(
                "UPDATE kit_packs SET nombre = ? WHERE id = ?",
                (nombre, row['id']))
            return row['id']
        cur = conn.execute(
            "INSERT INTO kit_packs (dropbox_path, nombre) VALUES (?, ?)",
            (dropbox_path, nombre))
        return cur.lastrowid


def record_run(pack_id, db_path=None, **fields):
    """Registra una corrida y actualiza last_used_at solo de ese pack.

    Args:
        pack_id: id en kit_packs.
        fields: canal, audio_mode, loops_json (list o str), image_path,
            video_path, youtube_id, url, publish_at, subido_en, estado.

    Returns:
        id de kit_runs.
    """
    fields = {k: v for k, v in fields.items() if k in _RUN_FIELDS}
    audio_mode = fields.get('audio_mode')
    if audio_mode not in AUDIO_MODES:
        raise ValueError(
            f"audio_mode debe ser {AUDIO_MODES}, no {audio_mode!r}")
    loops = fields.get('loops_json')
    if isinstance(loops, (list, dict)):
        fields['loops_json'] = json.dumps(loops, ensure_ascii=False)
    used_at = fields.get('subido_en') or _now()
    fields.setdefault('subido_en', used_at)
    cols = ['pack_id', *fields]
    with connect(db_path) as conn:
        cur = conn.execute(
            f"INSERT INTO kit_runs ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})",
            (pack_id, *fields.values()))
        run_id = cur.lastrowid
        conn.execute(
            "UPDATE kit_packs SET last_used_at = ? WHERE id = ?",
            (used_at, pack_id))
        return run_id


def recent_pack_paths(days, db_path=None):
    """Paths de packs no usados en los últimos `days` días.

    Incluye last_used_at nulo. El cooldown de selección usa este conjunto
    (elegibles), no los usados hace poco.
    """
    cutoff = (datetime.now() - timedelta(days=days)).isoformat(timespec='seconds')
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT dropbox_path FROM kit_packs "
            "WHERE last_used_at IS NULL OR last_used_at <= ?",
            (cutoff,)).fetchall()
        return {r['dropbox_path'] for r in rows}


def recent_images(pack_id, limit=8, db_path=None):
    """Últimas image_path de corridas de ese pack (más reciente primero)."""
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT image_path FROM kit_runs "
            "WHERE pack_id = ? AND image_path IS NOT NULL AND image_path != '' "
            "ORDER BY id DESC LIMIT ?",
            (pack_id, limit)).fetchall()
        return [r['image_path'] for r in rows]


def last_run_at(pack_id, db_path=None):
    """ISO de la última corrida (subido_en) o None."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT subido_en FROM kit_runs WHERE pack_id = ? "
            "ORDER BY id DESC LIMIT 1",
            (pack_id,)).fetchone()
        return row['subido_en'] if row else None


def selection_history(db_path=None):
    """Historial en memoria para ``kit_select.choose``.

    Returns:
        dict con ``last_used_by_path`` e ``last_image_by_path`` (por dropbox_path).
    """
    last_used_by_path = {}
    last_image_by_path = {}
    with connect(db_path) as conn:
        for row in conn.execute(
                "SELECT dropbox_path, last_used_at FROM kit_packs"):
            if row['last_used_at']:
                last_used_by_path[row['dropbox_path']] = row['last_used_at']
        for row in conn.execute(
                "SELECT p.dropbox_path, r.image_path FROM kit_runs r "
                "JOIN kit_packs p ON p.id = r.pack_id "
                "WHERE r.image_path IS NOT NULL AND r.image_path != '' "
                "ORDER BY r.id DESC"):
            path = row['dropbox_path']
            if path not in last_image_by_path:
                last_image_by_path[path] = row['image_path']
    return {
        'last_used_by_path': last_used_by_path,
        'last_image_by_path': last_image_by_path,
    }


def has_scheduled_run(publish_at, db_path=None):
    """True si ya hay corrida scheduled/uploaded para ese publish_at (ISO UTC)."""
    if not publish_at:
        return False
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM kit_runs WHERE publish_at = ? "
            "AND estado IN ('scheduled', 'uploaded') LIMIT 1",
            (publish_at,)).fetchone()
        return row is not None
