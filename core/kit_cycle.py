# -*- coding: utf-8 -*-
"""Ciclo de videos por kit: hasta N videos, descanso y ciclo nuevo.

Funciones puras sobre el estado de ``kit_state.load()``; no leen ni escriben
Dropbox. Los plazos se cuentan por fecha de calendario: una corrida semanal que
arranca unos minutos antes que la anterior igual cumple los 7 días.
"""
import json
from datetime import datetime, timedelta

from core.kit_select import KitSelectError, choose

DEFAULTS = {
    'cycle_max_videos': 3,
    'cycle_rest_days': 30,
    'kit_min_gap_days': 7,
    'kits_per_week': 3,
}
_COUNTED_STATES = ('rendered', 'scheduled', 'private_pending', 'uploaded')


class KitCycleError(Exception):
    """El kit no puede sumar un video ahora (está en descanso)."""


def settings(kit_cfg=None):
    """Reglas del ciclo desde ``kit_preview`` (con defaults)."""
    kit_cfg = kit_cfg or {}
    cfg = {key: int(kit_cfg.get(key, default)) for key, default in DEFAULTS.items()}
    if cfg['cycle_max_videos'] < 1 or cfg['kits_per_week'] < 1:
        raise ValueError("cycle_max_videos y kits_per_week deben ser al menos 1")
    if cfg['cycle_rest_days'] < 0 or cfg['kit_min_gap_days'] < 0:
        raise ValueError("Los días de descanso y de separación no pueden ser negativos")
    return cfg


def _when(value):
    """ISO o datetime a datetime naive en hora local; None si no hay fecha."""
    if not value:
        return None
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(value)
    if value.tzinfo is not None:
        value = value.astimezone().replace(tzinfo=None)
    return value


def _days_between(earlier, later):
    return (later.date() - earlier.date()).days


def current(cycle, now, cfg=None, last_used_at=None):
    """Ciclo vigente a ``now``: ``{cycle_videos, rest_until}``.

    Con el descanso cumplido arranca un ciclo nuevo en 0. Un ciclo lleno sin
    ``rest_until`` (estado a medio guardar) descansa desde ``last_used_at``.
    """
    cfg = cfg or settings()
    now = _when(now)
    videos = int((cycle or {}).get('cycle_videos') or 0)
    rest_until = _when((cycle or {}).get('rest_until'))
    if rest_until is None and videos >= cfg['cycle_max_videos']:
        last = _when(last_used_at)
        rest_until = last + timedelta(days=cfg['cycle_rest_days']) if last else now
    if rest_until is not None and _days_between(rest_until, now) >= 0:
        return {'cycle_videos': 0, 'rest_until': None}
    return {'cycle_videos': videos,
            'rest_until': rest_until.isoformat(timespec='seconds') if rest_until else None}


def status(cycle, last_used_at, now, cfg=None):
    """Si el kit puede usarse en ``now``.

    Returns:
        dict ``{eligible, reason, cycle_videos, rest_until}``; reason es 'ok',
        'resting' (descanso del ciclo) o 'gap' (usado hace menos de kit_min_gap_days).
    """
    cfg = cfg or settings()
    now = _when(now)
    cur = current(cycle, now, cfg, last_used_at)
    reason = 'ok'
    last = _when(last_used_at)
    if cur['rest_until']:
        reason = 'resting'
    elif last is not None and _days_between(last, now) < cfg['kit_min_gap_days']:
        reason = 'gap'
    return {'eligible': reason == 'ok', 'reason': reason, **cur}


def advance(cycle, when, cfg=None, close=False, last_used_at=None):
    """Campos de ciclo después de sumar un video en ``when``.

    Al llegar a cycle_max_videos (o con ``close``, para un kit que no da para
    otro video) el kit queda en descanso cycle_rest_days. El resultado se pasa
    tal cual a ``kit_state.update_cycle``.

    Raises:
        KitCycleError: el kit está en descanso.
    """
    cfg = cfg or settings()
    when = _when(when)
    cur = current(cycle, when, cfg, last_used_at)
    if cur['rest_until']:
        raise KitCycleError(f"El kit descansa hasta {cur['rest_until']}")
    videos = cur['cycle_videos'] + 1
    rest_until = None
    if close or videos >= cfg['cycle_max_videos']:
        rest_until = (when + timedelta(days=cfg['cycle_rest_days'])).isoformat(timespec='seconds')
    return {'cycle_videos': videos, 'rest_until': rest_until}


def _pack_state(state, dropbox_path):
    return ((state or {}).get('packs') or {}).get(dropbox_path) or {}


def eligible_packs(packs, state, now, cfg=None, exclude=()):
    """Packs que pueden usarse en ``now`` (ni en descanso ni dentro de la separación)."""
    cfg = cfg or settings()
    skip = set(exclude)
    out = []
    for pack in packs:
        if pack['dropbox_path'] in skip:
            continue
        saved = _pack_state(state, pack['dropbox_path'])
        if status(saved.get('cycle'), saved.get('last_used_at'), now, cfg)['eligible']:
            out.append(pack)
    return out


def used_segments(state, dropbox_path, now, cfg=None):
    """Tramos de audio de los videos del ciclo vigente del kit, del más viejo al más nuevo.

    Salen de ``loops_json`` de las últimas ``cycle_videos`` corridas del pack; es lo
    que ``kit_audio.plan_audio`` espera en ``used_before``.
    """
    saved = _pack_state(state, dropbox_path)
    count = current(saved.get('cycle'), now, cfg, saved.get('last_used_at'))['cycle_videos']
    if not count or saved.get('id') is None:
        return []
    runs = [run for run in ((state or {}).get('runs') or [])
            if run.get('pack_id') == saved['id'] and run.get('estado') in _COUNTED_STATES]
    runs.sort(key=lambda run: run.get('id') or 0)
    segments = []
    for run in runs[-count:]:
        loops = run.get('loops_json')
        if isinstance(loops, str):
            try:
                loops = json.loads(loops)
            except ValueError:
                loops = None
        segments.extend(seg for seg in (loops or []) if isinstance(seg, dict))
    return segments


def pick_week(packs, state, history, now, rng, cfg=None, exclude=(), require_images=True,
              choose_fn=choose, limit=None, keep_order=False, **choose_kw):
    """Elige hasta kits_per_week kits distintos entre los que pueden usarse.

    Van primero los que hace más que no salen (los nunca usados antes que nadie); el
    azar solo desempata. La imagen la decide ``kit_select.choose``; el audio de esa
    elección no se usa (lo planifica ``kit_audio``). Un kit que ``choose`` no puede
    armar (sin audio) se saltea y se sigue con el resto.

    Args:
        require_images: con False un kit sin imágenes también entra (portada automática)
            y su selección lleva ``image`` en None.
        limit: tope de kits a devolver en lugar de ``kits_per_week``.
        keep_order: desempata el orden de ``packs`` (el del recorrido de carpetas) en
            lugar del azar.

    Returns:
        dict ``{selections, warnings}``. Cada selección es la de ``choose`` más
        ``cycle_videos`` (videos ya hechos en el ciclo vigente).
    """
    cfg = cfg or settings()
    want = cfg['kits_per_week'] if limit is None else int(limit)
    warnings = []
    pool = eligible_packs(packs, state, now, cfg, exclude)
    if require_images:
        with_images = [pack for pack in pool if pack.get('images')]
        if len(with_images) < len(pool):
            warnings.append(f"{len(pool) - len(with_images)} kit(s) sin imágenes quedan afuera.")
        pool = with_images
    # El filtro por fechas ya está hecho: choose recibe el historial sin usos para que
    # no aplique ni relaje su propio cooldown (solo le sirve la última imagen).
    history = {**(history or {}), 'last_used_by_path': {}}
    pool = list(pool)
    if not keep_order:
        rng.shuffle(pool)
    pool.sort(key=lambda pack: str(_pack_state(state, pack['dropbox_path']).get('last_used_at')
                                   or ''))
    selections = []
    unusable = 0
    for pack in pool:
        if len(selections) >= want:
            break
        try:
            selection = choose_fn([pack], history, now, rng, cooldown_days=0,
                                  require_image=require_images, **choose_kw)
        except KitSelectError:
            unusable += 1
            continue
        saved = _pack_state(state, pack['dropbox_path'])
        selection['cycle_videos'] = current(
            saved.get('cycle'), now, cfg, saved.get('last_used_at'))['cycle_videos']
        selections.append(selection)
    if unusable:
        warnings.append(f"{unusable} kit(s) no se pudieron elegir (sin audio).")
    if len(selections) < want:
        warnings.append(
            f"Solo hay {len(selections)} kit(s) disponibles de {want} "
            "(el resto descansa o se usó hace poco).")
    return {'selections': selections, 'warnings': warnings}
