# -*- coding: utf-8 -*-
"""Biblioteca local de beats (SQLite) + historial de subidas."""
import hashlib
import os
import shutil
import sqlite3
from datetime import datetime, timedelta

DB_PATH = 'library.db'
LIBRARY_DIR = 'library'

KIND_BEAT = 'beat'
KIND_LOOP_KIT = 'loop_kit'
VALID_KINDS = (KIND_BEAT, KIND_LOOP_KIT)

SCHEMA = """
CREATE TABLE IF NOT EXISTS beats (
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
CREATE UNIQUE INDEX IF NOT EXISTS idx_beats_hash_kind ON beats(hash, kind);
"""


def library_dir_for_kind(kind=KIND_BEAT):
    """Carpeta de almacenamiento en disco según tipo de audio."""
    if kind == KIND_LOOP_KIT:
        return 'loop_kits'
    return LIBRARY_DIR


def _normalize_kind(kind):
    """Devuelve un kind válido; valores desconocidos caen en beat."""
    return kind if kind in VALID_KINDS else KIND_BEAT


def _ensure_kind_column(conn):
    """Migración idempotente: columna kind en beats (SQLite local)."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(beats)")}
    if 'kind' not in cols:
        conn.execute(
            "ALTER TABLE beats ADD COLUMN kind TEXT NOT NULL DEFAULT 'beat'")
    conn.execute(
        "UPDATE beats SET kind = ? WHERE kind IS NULL OR kind = ''",
        (KIND_BEAT,))


def _beats_has_global_hash_unique(conn):
    """True si hay un UNIQUE solo sobre hash (esquema previo a kind)."""
    for idx in conn.execute("PRAGMA index_list(beats)"):
        if not idx[2]:
            continue
        name = idx[1]
        if not all(ch.isalnum() or ch == '_' for ch in name):
            continue
        cols = [info[2] for info in conn.execute(f"PRAGMA index_info({name})")]
        if cols == ['hash']:
            return True
    return False


def _rebuild_beats_unique_hash_kind(conn):
    """Reescribe beats para que UNIQUE sea (hash, kind), no hash global."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.executescript("""
        CREATE TABLE beats_kind_mig (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            ruta TEXT NOT NULL,
            hash TEXT NOT NULL,
            bpm REAL,
            key TEXT,
            beatstars_url TEXT,
            notas TEXT,
            creado TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'beat',
            UNIQUE(hash, kind)
        );
        INSERT INTO beats_kind_mig
            (id, nombre, ruta, hash, bpm, key, beatstars_url, notas, creado, kind)
        SELECT id, nombre, ruta, hash, bpm, key, beatstars_url, notas, creado,
               CASE WHEN kind IS NULL OR kind = '' THEN 'beat' ELSE kind END
        FROM beats;
        DROP TABLE beats;
        ALTER TABLE beats_kind_mig RENAME TO beats;
        CREATE INDEX IF NOT EXISTS idx_uploads_beat ON uploads(beat_id, canal);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_beats_hash_kind ON beats(hash, kind);
    """)
    conn.execute("PRAGMA foreign_keys = ON")


def _connect(db_path=None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    _ensure_kind_column(conn)
    if _beats_has_global_hash_unique(conn):
        _rebuild_beats_unique_hash_kind(conn)
    conn.commit()
    return conn


def file_hash(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(chunk), b''):
            h.update(block)
    return h.hexdigest()


def import_beat(path, kind=KIND_BEAT, db_path=None, library_dir=None):
    """Copia el audio a library/ (o loop_kits/) y lo registra. Dedupe por hash.

    Args:
        path: archivo de audio de origen.
        kind: 'beat' o 'loop_kit'.

    Devuelve (beat_id, creado) donde creado=False si ya existía
    con el mismo hash y el mismo kind.
    """
    kind = _normalize_kind(kind)
    library_dir = library_dir or library_dir_for_kind(kind)
    digest = file_hash(path)
    with _connect(db_path) as conn:
        row = conn.execute(
            "SELECT id FROM beats WHERE hash = ? AND kind = ?",
            (digest, kind)).fetchone()
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
            "INSERT INTO beats (nombre, ruta, hash, creado, kind) VALUES (?, ?, ?, ?, ?)",
            (stem, dest, digest, datetime.now().isoformat(timespec='seconds'), kind))
        return cur.lastrowid, True


def update_beat(beat_id, db_path=None, **fields):
    allowed = {'nombre', 'bpm', 'key', 'beatstars_url', 'notas'}
    fields = {k: v for k, v in fields.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    with _connect(db_path) as conn:
        conn.execute(f"UPDATE beats SET {sets} WHERE id = ?", (*fields.values(), beat_id))


def find_beat_by_path(path, db_path=None, kind=None):
    """Busca un audio por ruta exacta, carpeta+nombre, basename o hash.

    Args:
        path: ruta o solo el nombre de archivo.
        kind: si se indica, solo filas de ese tipo (evita mezclar beats y kits).
    """
    if kind is not None:
        kind = _normalize_kind(kind)
    abs_path = os.path.abspath(path) if path else ''
    base = os.path.basename(path) if path else ''
    dirn = os.path.dirname(abs_path)
    with _connect(db_path) as conn:
        if kind:
            rows = [dict(r) for r in conn.execute(
                "SELECT * FROM beats WHERE kind = ?", (kind,))]
        else:
            rows = [dict(r) for r in conn.execute("SELECT * FROM beats")]
        for row in rows:
            if os.path.normcase(os.path.abspath(row['ruta'])) == os.path.normcase(abs_path):
                return row
        same_dir, same_base = [], []
        for row in rows:
            if os.path.basename(row['ruta']) != base:
                continue
            same_base.append(row)
            row_dir = os.path.normcase(os.path.abspath(os.path.dirname(row['ruta'])))
            if row_dir == os.path.normcase(dirn):
                same_dir.append(row)
        if same_dir:
            return same_dir[0]
        if same_base:
            return same_base[0]
        if path and os.path.exists(path):
            digest = file_hash(path)
            if kind:
                row = conn.execute(
                    "SELECT * FROM beats WHERE hash = ? AND kind = ?",
                    (digest, kind)).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM beats WHERE hash = ?", (digest,)).fetchone()
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


def youtube_uploads(beat_id, canal, db_path=None):
    """Subidas reales a YouTube (con youtube_id) de un beat en un canal, más recientes primero."""
    with _connect(db_path) as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM uploads WHERE beat_id = ? AND canal = ? AND youtube_id <> '' "
            "ORDER BY subido_en DESC", (beat_id, canal))]


def list_beats(filtro=None, canal=None, meses=6, texto='', kind=KIND_BEAT, db_path=None):
    """Lista beats con su última subida (global o del canal indicado).

    filtro: None | 'nunca' (sin subidas) | 'sin_canal' (sin subir al canal)
            | 'antiguos' (última subida hace más de `meses` meses)
    kind: 'beat' o 'loop_kit'; solo devuelve filas de ese tipo.
    """
    kind = _normalize_kind(kind)
    with _connect(db_path) as conn:
        beats = [dict(r) for r in conn.execute(
            "SELECT * FROM beats WHERE kind = ? ORDER BY creado DESC", (kind,))]
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
