# -*- coding: utf-8 -*-
"""Biblioteca local de beats (SQLite) + historial de subidas."""
import hashlib
import os
import shutil
import sqlite3
from datetime import datetime, timedelta

DB_PATH = 'library.db'
LIBRARY_DIR = 'library'

SCHEMA = """
CREATE TABLE IF NOT EXISTS beats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL,
    ruta TEXT NOT NULL,
    hash TEXT NOT NULL UNIQUE,
    bpm REAL,
    key TEXT,
    beatstars_url TEXT,
    notas TEXT,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS uploads (
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
CREATE INDEX IF NOT EXISTS idx_uploads_beat ON uploads(beat_id, canal);
"""


def _connect(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def file_hash(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def import_beat(path, db_path=None, library_dir=None):
    """Copia el audio a library/ y lo registra. Dedupe por hash.

    Devuelve (beat_id, creado) donde creado=False si ya existía.
    """
    library_dir = library_dir or LIBRARY_DIR
    digest = file_hash(path)
    with _connect(db_path) as conn:
        row = conn.execute("SELECT id FROM beats WHERE hash = ?", (digest,)).fetchone()
        if row:
            return row['id'], False
        os.makedirs(library_dir, exist_ok=True)
        filename = os.path.basename(path)
        dest = os.path.join(library_dir, filename)
        stem, ext = os.path.splitext(filename)
        n = 1
        while os.path.exists(dest):
            dest = os.path.join(library_dir, f"{stem}_{n}{ext}")
            n += 1
        shutil.copy2(path, dest)
        cur = conn.execute(
            "INSERT INTO beats (nombre, ruta, hash, creado) VALUES (?, ?, ?, ?)",
            (stem, dest, digest, datetime.now().isoformat(timespec='seconds')))
        return cur.lastrowid, True


def update_beat(beat_id, db_path=None, **fields):
    allowed = {'nombre', 'bpm', 'key', 'beatstars_url', 'notas'}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with _connect(db_path) as conn:
        conn.execute(f"UPDATE beats SET {sets} WHERE id = ?", (*fields.values(), beat_id))


def find_beat_by_path(path, db_path=None):
    """Busca un beat por ruta exacta, por nombre de archivo o por hash."""
    with _connect(db_path) as conn:
        base = os.path.basename(path)
        for row in conn.execute("SELECT * FROM beats"):
            if os.path.basename(row['ruta']) == base:
                return dict(row)
        if os.path.exists(path):
            row = conn.execute("SELECT * FROM beats WHERE hash = ?", (file_hash(path),)).fetchone()
            if row:
                return dict(row)
    return None


def record_upload(beat_id, canal, grupo='', youtube_id='', url='', titulo='',
                  estado='generado', subido_en=None, db_path=None):
    subido_en = subido_en or datetime.now().isoformat(timespec='seconds')
    with _connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO uploads (beat_id, canal, grupo, youtube_id, url, titulo, subido_en, estado) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (beat_id, canal, grupo, youtube_id, url, titulo, subido_en, estado))
        return cur.lastrowid


def last_upload(beat_id, canal=None, db_path=None):
    q = "SELECT * FROM uploads WHERE beat_id = ?"
    args = [beat_id]
    if canal:
        q += " AND canal = ?"
        args.append(canal)
    q += " ORDER BY subido_en DESC LIMIT 1"
    with _connect(db_path) as conn:
        row = conn.execute(q, args).fetchone()
        return dict(row) if row else None


def list_beats(filtro=None, canal=None, meses=6, texto='', db_path=None):
    """Lista beats con su última subida (global o del canal indicado).

    filtro: None | 'nunca' (sin subidas) | 'sin_canal' (sin subir al canal)
            | 'antiguos' (última subida hace más de `meses` meses)
    """
    with _connect(db_path) as conn:
        beats = [dict(r) for r in conn.execute("SELECT * FROM beats ORDER BY creado DESC")]
        last = {}
        for r in conn.execute(
                "SELECT beat_id, canal, MAX(subido_en) AS ult FROM uploads GROUP BY beat_id, canal"):
            last.setdefault(r['beat_id'], {})[r['canal']] = r['ult']
    limite = (datetime.now() - timedelta(days=30 * meses)).isoformat(timespec='seconds')
    result = []
    for b in beats:
        por_canal = last.get(b['id'], {})
        b['subidas_por_canal'] = por_canal
        fechas = [por_canal[canal]] if canal and canal in por_canal else (
            [] if canal else list(por_canal.values()))
        b['ultima_subida'] = max(fechas) if fechas else None
        if texto and texto.lower() not in b['nombre'].lower():
            continue
        if filtro == 'nunca' and por_canal:
            continue
        if filtro == 'sin_canal' and canal and canal in por_canal:
            continue
        if filtro == 'antiguos' and not (b['ultima_subida'] and b['ultima_subida'] < limite):
            continue
        result.append(b)
    return result


def humanize_ago(fecha, now=None):
    """'hace 3 meses'. Acepta ISO str o datetime; None -> 'nunca'."""
    if not fecha:
        return 'nunca'
    if isinstance(fecha, str):
        fecha = datetime.fromisoformat(fecha)
    secs = int(((now or datetime.now()) - fecha).total_seconds())
    if secs < 60:
        return 'hace un momento'
    units = [(365 * 86400, 'año', 'años'), (30 * 86400, 'mes', 'meses'),
             (7 * 86400, 'semana', 'semanas'), (86400, 'día', 'días'),
             (3600, 'hora', 'horas'), (60, 'minuto', 'minutos')]
    for size, uno, varios in units:
        n = secs // size
        if n >= 1:
            return f"hace {n} {uno if n == 1 else varios}"
