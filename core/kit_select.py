# -*- coding: utf-8 -*-
"""Elige pack, modo de audio e imagen para un video de loop kit.

Recibe la lista de ``kit_source.list_packs`` y un historial en memoria
(last_used e imagen reciente por ``dropbox_path``). No accede a Dropbox.
"""
import os
import random
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

DateLike = Union[datetime, str, None]


class KitSelectError(Exception):
    """No hay packs, loops o imágenes suficientes para armar la preview."""


def _parse_when(value: DateLike) -> Optional[datetime]:
    """Normaliza ISO o datetime; None si no hay fecha."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value)


def _pack_last_used(history: dict, dropbox_path: str) -> Optional[datetime]:
    """Último uso del pack según history['last_used_by_path']."""
    by_path = history.get('last_used_by_path') or {}
    return _parse_when(by_path.get(dropbox_path))


def _pack_last_image(history: dict, dropbox_path: str) -> Optional[str]:
    """image_path de la última corrida de ese pack."""
    by_path = history.get('last_image_by_path') or {}
    return by_path.get(dropbox_path)


def _eligible_packs(
    packs: List[dict],
    history: dict,
    now: datetime,
    cooldown_days: int,
) -> List[dict]:
    """Packs con last_used nulo o anterior al cooldown."""
    cutoff = now - timedelta(days=cooldown_days)
    eligible = []
    for pack in packs:
        last = _pack_last_used(history, pack['dropbox_path'])
        if last is None or last <= cutoff:
            eligible.append(pack)
    return eligible


def _pick_pack_relaxed(
    packs: List[dict],
    history: dict,
) -> dict:
    """Pack con last_used más antiguo (None = nunca usado, prioridad máxima)."""
    def sort_key(pack: dict) -> tuple:
        last = _pack_last_used(history, pack['dropbox_path'])
        if last is None:
            return (0, datetime.min, pack['dropbox_path'])
        return (1, last, pack['dropbox_path'])

    return min(packs, key=sort_key)


def _stem(filename: str) -> str:
    return os.path.splitext(filename)[0]


def _pick_named_preview(named_previews: List[dict]) -> dict:
    """Un preview nombrado: stem exacto preview, luego prefijo preview, nombre más corto."""

    def rank(rec: dict) -> tuple:
        stem = _stem(rec['name']).lower()
        if stem == 'preview':
            tier = 0
        elif stem.startswith('preview'):
            tier = 1
        else:
            tier = 2
        return (tier, len(rec['name']), rec['name'].lower())

    return min(named_previews, key=rank)


def _pick_loops(
    loops: List[dict],
    rng: random.Random,
    loops_min: int,
    loops_max: int,
    warnings: List[str],
) -> List[dict]:
    """Entre loops_min y loops_max al azar si alcanza; si no, todos con aviso."""
    n = len(loops)
    if n == 0:
        raise KitSelectError('El pack no tiene loops para modo assembled')
    if n < loops_min:
        warnings.append(
            f'Solo hay {n} loop(s); se usan todos (mínimo deseado {loops_min}).')
        chosen = list(loops)
    else:
        k = rng.randint(loops_min, min(loops_max, n))
        chosen = rng.sample(loops, k)
    rng.shuffle(chosen)
    return chosen


def _pick_image(
    pack: dict,
    history: dict,
    rng: random.Random,
) -> dict:
    """Elige imagen evitando repetir la última de ese pack si hay alternativa."""
    images = pack.get('images') or []
    if not images:
        raise KitSelectError(
            f"El pack {pack.get('name', pack['dropbox_path'])} no tiene imágenes")
    last_path = _pack_last_image(history, pack['dropbox_path'])
    pool = images
    if last_path is not None and len(images) > 1:
        alt = [img for img in images if img['path'] != last_path]
        if alt:
            pool = alt
    return rng.choice(pool)


def choose(
    packs: List[dict],
    history: dict,
    now: datetime,
    rng: random.Random,
    cooldown_days: int = 30,
    loops_min: int = 6,
    loops_max: int = 8,
    prefer_named_preview: bool = True,
) -> Dict[str, Any]:
    """Elige pack, audio e imagen según cooldown y preferencias.

    Args:
        packs: salida de ``kit_source.list_packs``.
        history: ``last_used_by_path`` e ``last_image_by_path`` (ISO o datetime).
        now: instante de referencia para el cooldown.
        rng: generador para pack, cantidad de loops e imagen.
        cooldown_days: días mínimos desde ``last_used_at``.
        loops_min, loops_max: rango en modo ``assembled``.
        prefer_named_preview: usar un solo archivo de ``named_previews`` si existe.

    Returns:
        dict con pack, audio_mode, audio_files, image, warnings, cooldown_relaxed.
    """
    if not packs:
        raise KitSelectError('No hay packs para elegir')

    warnings: List[str] = []
    eligible = _eligible_packs(packs, history, now, cooldown_days)
    cooldown_relaxed = False
    if eligible:
        pack = rng.choice(eligible)
    else:
        pack = _pick_pack_relaxed(packs, history)
        cooldown_relaxed = True
        warnings.append(
            f'Todos los packs fueron usados en los últimos {cooldown_days} días; '
            f'se eligió el más antiguo ({pack.get("name", pack["dropbox_path"])}).')

    use_named = (
        prefer_named_preview
        and bool(pack.get('named_previews'))
    )
    if use_named:
        audio_mode = 'named_preview'
        audio_files = [_pick_named_preview(pack['named_previews'])]
    else:
        audio_mode = 'assembled'
        audio_files = _pick_loops(
            pack.get('loops') or [], rng, loops_min, loops_max, warnings)

    image = _pick_image(pack, history, rng)

    return {
        'pack': pack,
        'audio_mode': audio_mode,
        'audio_files': audio_files,
        'image': image,
        'warnings': warnings,
        'cooldown_relaxed': cooldown_relaxed,
    }
