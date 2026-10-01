# -*- coding: utf-8 -*-
"""Persistencia de Shorts (videos largos, transcripciones, clips) en library.db.

Tablas propias: no toca `beats` ni `uploads`.
"""
import json
import sqlite3
from datetime import datetime

from core import library

VIDEO_STATES = ('importado', 'transcribiendo', 'transcrito', 'eligiendo',
                'clips_listos', 'renderizando', 'listo', 'error')
CLIP_STATES = ('propuesto', 'aprobado', 'rechazado', 'renderizado',
               'subido', 'error')

SCHEMA = """
CREATE TABLE IF NOT EXISTS long_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    hash TEXT NOT NULL,
    duration_s REAL,
    camera_path TEXT,
    offset_ms INTEGER NOT NULL DEFAULT 0,
    layout_profile TEXT NOT NULL DEFAULT 'obs_unico',
    canal TEXT,
    estado TEXT NOT NULL DEFAULT 'importado',
    error TEXT,
    creado TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_long_videos_hash ON long_videos(hash);
CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES long_videos(id) ON DELETE CASCADE,
    model TEXT NOT NULL,
    language TEXT,
    words_json TEXT NOT NULL,
    creado TEXT NOT NULL,
    UNIQUE (video_id, model)
);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id INTEGER NOT NULL REFERENCES long_videos(id) ON DELETE CASCADE,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    start_modelo REAL,
    end_modelo REAL,
    titulo TEXT,
    gancho TEXT,
    motivo TEXT,
    puntaje REAL,
    estado TEXT NOT NULL DEFAULT 'propuesto',
    render_path TEXT,
    youtube_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_clips_video ON clips(video_id);
"""

_VIDEO_FIELDS = {'duration_s', 'camera_path', 'offset_ms', 'layout_profile',
                 'canal', 'estado', 'error'}


def _now():
    return datetime.now().isoformat(timespec='seconds')


def ensure_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


def connect(db_path=None):
    conn = sqlite3.connect(db_path or library.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    ensure_schema(conn)
    return conn


def upsert_video(path, file_hash, db_path=None, **fields):
    """Registra un video largo (dedupe por hash). Si existe, actualiza la ruta
    y los campos dados. Devuelve el id."""
    fields = {k: v for k, v in fields.items() if k in _VIDEO_FIELDS}
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM long_videos WHERE hash = ?", (file_hash,)).fetchone()
        if row:
            fields['path'] = path
            sets = ", ".join(f"{k} = ?" for k in fields)
            conn.execute(f"UPDATE long_videos SET {sets} WHERE id = ?",
                         (*fields.values(), row['id']))
            return row['id']
        cols = ['path', 'hash', 'creado', *fields]
        cur = conn.execute(
            f"INSERT INTO long_videos ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' * len(cols))})",
            (path, file_hash, _now(), *fields.values()))
        return cur.lastrowid


def get_video(video_id, db_path=None):
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM long_videos WHERE id = ?", (video_id,)).fetchone()
        return dict(row) if row else None


def update_video(video_id, db_path=None, **fields):
    fields = {k: v for k, v in fields.items() if k in _VIDEO_FIELDS}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with connect(db_path) as conn:
        conn.execute(f"UPDATE long_videos SET {sets} WHERE id = ?",
                     (*fields.values(), video_id))


def save_transcript(video_id, model, language, words, db_path=None):
    """Guarda (o reemplaza) la transcripción; words = [{t0, t1, w}, ...]."""
    payload = json.dumps(words, ensure_ascii=False)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO transcripts (video_id, model, language, words_json, creado) "
            "VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(video_id, model) DO UPDATE SET "
            "language = excluded.language, words_json = excluded.words_json, "
            "creado = excluded.creado",
            (video_id, model, language, payload, _now()))


def get_transcript(video_id, model, db_path=None):
    """Lista de palabras o None."""
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT words_json FROM transcripts WHERE video_id = ? AND model = ?",
            (video_id, model)).fetchone()
        return json.loads(row['words_json']) if row else None


def replace_clips(video_id, clips, db_path=None):
    """Reemplaza las propuestas no aprobadas por `clips`.

    Conserva filas aprobadas/renderizadas/subidas. Cada clip: start, end,
    titulo, gancho, motivo, puntaje. start_modelo/end_modelo quedan con lo que
    propuso el modelo y no se vuelven a tocar.
    """
    with connect(db_path) as conn:
        conn.execute(
            "DELETE FROM clips WHERE video_id = ? AND estado IN ('propuesto', 'rechazado', 'error')",
            (video_id,))
        conn.executemany(
            "INSERT INTO clips (video_id, start_s, end_s, start_modelo, end_modelo, "
            "titulo, gancho, motivo, puntaje) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(video_id, c['start'], c['end'], c['start'], c['end'],
              c.get('titulo'), c.get('gancho'), c.get('motivo'), c.get('puntaje'))
             for c in clips])


def list_clips(video_id, db_path=None):
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM clips WHERE video_id = ? ORDER BY start_s",
            (video_id,)).fetchall()
        return [dict(r) for r in rows]
