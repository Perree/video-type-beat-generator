# -*- coding: utf-8 -*-
"""Estado de loop kits en un state.json de Dropbox (para correr sin library.db).

Mismas funciones que ``kit_store`` usa ``run_kit_preview`` (el argumento ``db_path`` acá es
la ruta del state.json en Dropbox), más un lock con vencimiento y el ciclo por kit.
Cada cambio relee, modifica y escribe con el rev leído: si otro escribió en el medio,
se reintenta sobre el estado nuevo.
"""
import contextlib
import os
import uuid
from datetime import datetime, timedelta, timezone

from core import kit_cloud, kit_spend
from core.kit_store import AUDIO_MODES, _RUN_FIELDS

STATE_PATH = os.environ.get('KIT_STATE_PATH') or '/loop_kits_state/state.json'
LOCK_TTL_SEC = 2 * 60 * 60
CYCLE_FIELDS = ('cycle_videos', 'rest_until', 'used_names', 'used_ref_images')
_CYCLE_LISTS = ('used_names', 'used_ref_images')
# Campos extra de cada corrida que solo existen en el estado de la nube (junto al youtube_id).
STATE_RUN_FIELDS = ('video_name', 'tracking_id', 'ref_images')
_WRITE_ATTEMPTS = 4


class KitStateError(Exception):
    pass


class KitLockError(KitStateError):
    """Hay otra corrida con el lock vigente."""


def _now():
    return datetime.now().isoformat(timespec='seconds')


def _utcnow():
    return datetime.now(timezone.utc)


def _empty():
    return {'version': 1, 'lock': None, 'packs': {}, 'runs': [],
            'next_pack_id': 1, 'next_run_id': 1}


def _empty_cycle():
    return {'cycle_videos': 0, 'rest_until': None, 'used_names': [], 'used_ref_images': []}


def _load(path, dbx):
    state, rev = kit_cloud.read_json_rev(path or STATE_PATH, dbx=dbx)
    if state is None:
        return _empty(), None
    if not isinstance(state, dict):
        raise KitStateError("state.json no tiene el formato esperado.")
    for key, value in _empty().items():
        state.setdefault(key, value)
    return state, rev


def load(db_path=None, dbx=None):
    """Estado completo (solo lectura)."""
    return _load(db_path, dbx)[0]


def _mutate(change, path, dbx):
    """Aplica ``change(state)`` y guarda; ante un conflicto de rev relee y reintenta."""
    for _ in range(_WRITE_ATTEMPTS):
        state, rev = _load(path, dbx)
        result = change(state)
        try:
            kit_cloud.write_json(path or STATE_PATH, state,
                                 rev=rev if rev else kit_cloud.NEW, dbx=dbx)
        except kit_cloud.KitCloudConflict:
            continue
        return result
    raise KitStateError("No se pudo guardar el estado: otro proceso lo sigue cambiando.")


# --- Mismas funciones que kit_store ---

def upsert_pack(dropbox_path, nombre, db_path=None, dbx=None):
    """Inserta o actualiza un pack por dropbox_path. Devuelve el id.

    No toca last_used_at: eso lo hace record_run sobre ese pack.
    """
    def change(state):
        pack = state['packs'].get(dropbox_path)
        if pack:
            pack['nombre'] = nombre
            return pack['id']
        pack_id = state['next_pack_id']
        state['next_pack_id'] = pack_id + 1
        state['packs'][dropbox_path] = {
            'id': pack_id, 'nombre': nombre, 'last_used_at': None, 'cycle': _empty_cycle()}
        return pack_id
    return _mutate(change, db_path, dbx)


def record_run(pack_id, db_path=None, dbx=None, **fields):
    """Registra una corrida y actualiza last_used_at solo de ese pack. Devuelve el id.

    Acepta los mismos campos que ``kit_store.record_run``.
    """
    fields = {k: v for k, v in fields.items() if k in _RUN_FIELDS or k in STATE_RUN_FIELDS}
    audio_mode = fields.get('audio_mode')
    if audio_mode not in AUDIO_MODES:
        raise ValueError(
            f"audio_mode debe ser {AUDIO_MODES}, no {audio_mode!r}")
    used_at = fields.get('subido_en') or _now()
    fields.setdefault('subido_en', used_at)

    def change(state):
        pack = next((p for p in state['packs'].values() if p['id'] == pack_id), None)
        if pack is None:
            raise ValueError(f"No existe el pack {pack_id!r}")
        run_id = state['next_run_id']
        state['next_run_id'] = run_id + 1
        state['runs'].append({'id': run_id, 'pack_id': pack_id, **fields})
        pack['last_used_at'] = used_at
        return run_id
    return _mutate(change, db_path, dbx)


def selection_history(db_path=None, dbx=None):
    """Historial en memoria para ``kit_select.choose``.

    Returns:
        dict con ``last_used_by_path`` e ``last_image_by_path`` (por dropbox_path).
    """
    state = load(db_path, dbx)
    path_by_id = {p['id']: path for path, p in state['packs'].items()}
    last_used_by_path = {
        path: p['last_used_at'] for path, p in state['packs'].items() if p.get('last_used_at')}
    last_image_by_path = {}
    for run in sorted(state['runs'], key=lambda r: r['id'], reverse=True):
        path = path_by_id.get(run.get('pack_id'))
        if path and run.get('image_path') and path not in last_image_by_path:
            last_image_by_path[path] = run['image_path']
    return {
        'last_used_by_path': last_used_by_path,
        'last_image_by_path': last_image_by_path,
    }


def has_scheduled_run(publish_at, db_path=None, dbx=None):
    """True si ya hay corrida scheduled/uploaded para ese publish_at (ISO UTC)."""
    if not publish_at:
        return False
    return any(
        run.get('publish_at') == publish_at and run.get('estado') in ('scheduled', 'uploaded')
        for run in load(db_path, dbx)['runs'])


# --- Lock con vencimiento ---

def _lock_is_live(lock, now):
    if not lock:
        return False
    try:
        expires = datetime.fromisoformat(lock['expires_at'])
    except (KeyError, TypeError, ValueError):
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > now


def acquire_lock(owner=None, ttl_sec=LOCK_TTL_SEC, now=None, db_path=None, dbx=None):
    """Toma el lock de corrida y devuelve el owner (para ``release_lock``).

    Si otro owner tiene un lock vigente levanta KitLockError. Un lock vencido se pisa:
    cubre el caso de una corrida que murió sin liberar. El mismo owner lo renueva.
    """
    owner = owner or uuid.uuid4().hex
    now = now or _utcnow()

    def change(state):
        lock = state.get('lock')
        if _lock_is_live(lock, now) and lock.get('owner') != owner:
            raise KitLockError(f"Ya hay una corrida en curso (vence {lock['expires_at']}).")
        state['lock'] = {
            'owner': owner,
            'acquired_at': now.isoformat(timespec='seconds'),
            'expires_at': (now + timedelta(seconds=ttl_sec)).isoformat(timespec='seconds'),
        }
        return owner
    return _mutate(change, db_path, dbx)


def release_lock(owner, db_path=None, dbx=None):
    """Libera el lock solo si es de ``owner``. Devuelve True si lo liberó."""
    def change(state):
        if (state.get('lock') or {}).get('owner') != owner:
            return False
        state['lock'] = None
        return True
    return _mutate(change, db_path, dbx)


@contextlib.contextmanager
def locked(ttl_sec=LOCK_TTL_SEC, db_path=None, dbx=None):
    owner = acquire_lock(ttl_sec=ttl_sec, db_path=db_path, dbx=dbx)
    try:
        yield owner
    finally:
        release_lock(owner, db_path=db_path, dbx=dbx)


# --- Ciclo por kit ---

def get_cycle(dropbox_path, db_path=None, dbx=None):
    """Ciclo del kit: cycle_videos, rest_until, used_names, used_ref_images."""
    pack = load(db_path, dbx)['packs'].get(dropbox_path) or {}
    return {**_empty_cycle(), **(pack.get('cycle') or {})}


def update_cycle(dropbox_path, db_path=None, dbx=None, **fields):
    """Pisa campos del ciclo de un kit ya registrado y devuelve el ciclo resultante.

    Args:
        cycle_videos: cantidad de videos publicados en el ciclo actual.
        rest_until: ISO hasta cuándo descansa el kit, o None.
        used_names: nombres ya usados en el ciclo (lista completa, sin repetidos).
        used_ref_images: imágenes de referencia ya usadas (lista completa, sin repetidos).
    """
    unknown = set(fields) - set(CYCLE_FIELDS)
    if unknown:
        raise ValueError(f"Campos de ciclo desconocidos: {sorted(unknown)}")
    for key in _CYCLE_LISTS:
        if key in fields:
            fields[key] = list(dict.fromkeys(fields[key] or []))

    def change(state):
        pack = state['packs'].get(dropbox_path)
        if pack is None:
            raise ValueError("El kit no está registrado; llamar antes a upsert_pack.")
        pack['cycle'] = {**_empty_cycle(), **(pack.get('cycle') or {}), **fields}
        return dict(pack['cycle'])
    return _mutate(change, db_path, dbx)


# --- Gasto estimado de portadas (por mes) ---

def get_spend(month, db_path=None, dbx=None):
    """Gasto estimado del mes ``YYYY-MM``: ``{usd, images, verifications}``."""
    return kit_spend.month_entry(load(db_path, dbx), month)


def add_spend(month, usd, db_path=None, dbx=None, images=0, verifications=0):
    """Suma un gasto estimado al mes y devuelve la entrada resultante."""
    return _mutate(lambda state: kit_spend.record(state, month, usd, images, verifications),
                   db_path, dbx)
