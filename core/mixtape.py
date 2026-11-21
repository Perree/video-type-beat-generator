# -*- coding: utf-8 -*-
"""WyreScapes: elige qué tracks entran en la mixtape del día y en qué orden.

Reglas (decisión del usuario):
- La carpeta de tracks se lee en cada corrida (``.wav``/``.mp3``; ``.asd`` y el resto se
  ignoran), así los tracks nuevos entran solos.
- Cada track aparece UNA sola vez por video. Nunca se repite para alargar.
- Orden al azar y distinto del orden del video anterior.
- Duración = suma de los tracks. ``max_seconds`` (~2 h) es solo un tope: si la música
  lo supera, entra un subconjunto priorizando los tracks menos usados.

El estado (orden anterior y conteo de usos por track) vive en un JSON local, por nombre
de archivo. Este módulo no llama a ffmpeg: las duraciones llegan como dict.
"""
import json
import os
import random

AUDIO_EXTS = ('.wav', '.mp3')
DEFAULT_MAX_SECONDS = 2 * 60 * 60
DEFAULT_STATE_PATH = os.path.join('config', 'wyrescapes_state.json')
_SHUFFLE_TRIES = 50


def scan_tracks(folder):
    """Rutas de los tracks de ``folder`` (orden alfabético). Ignora ``.asd`` y otros."""
    if not os.path.isdir(folder):
        return []
    names = sorted(n for n in os.listdir(folder)
                   if n.lower().endswith(AUDIO_EXTS) and os.path.isfile(os.path.join(folder, n)))
    return [os.path.join(folder, n) for n in names]


def empty_state():
    return {'last_order': [], 'counts': {}, 'videos': 0}


def load_state(path=DEFAULT_STATE_PATH):
    """Estado guardado, o uno vacío si no existe o está roto."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return empty_state()
    state = empty_state()
    if isinstance(data, dict):
        if isinstance(data.get('last_order'), list):
            state['last_order'] = [str(x) for x in data['last_order']]
        if isinstance(data.get('counts'), dict):
            state['counts'] = {str(k): int(v) for k, v in data['counts'].items()
                               if isinstance(v, (int, float))}
        state['videos'] = int(data.get('videos') or 0)
    return state


def save_state(state, path=DEFAULT_STATE_PATH):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _select(names, durations, counts, rng, max_seconds):
    """Todos si entran en el tope; si no, los menos usados (empate al azar) que quepan."""
    total = sum(durations[n] for n in names)
    if total <= max_seconds:
        return list(names)
    ranked = sorted(names, key=lambda n: (counts.get(n, 0), rng.random()))
    chosen, used = [], 0.0
    for name in ranked:
        if used + durations[name] <= max_seconds:
            chosen.append(name)
            used += durations[name]
    return chosen or ranked[:1]  # un track más largo que el tope igual sale solo


def _shuffle_unlike(names, previous, rng):
    """Orden al azar distinto de ``previous`` (si hay más de un track)."""
    order = list(names)
    for _ in range(_SHUFFLE_TRIES):
        rng.shuffle(order)
        if order != previous:
            return order
    if len(order) > 1:
        order[0], order[1] = order[1], order[0]
    return order


def plan_mixtape(names, durations, state=None, rng=None, max_seconds=DEFAULT_MAX_SECONDS):
    """Orden de tracks (nombres de archivo) para el próximo video.

    Args:
        names: nombres de archivo disponibles.
        durations: ``{nombre: segundos}``; los que falten o valgan <= 0 se descartan.
        state: estado de ``load_state`` (orden anterior y conteos).
        rng: ``random.Random`` (tests); por defecto uno nuevo.
        max_seconds: tope de duración del video.

    Returns:
        Lista sin repetidos, distinta del orden anterior cuando hay más de un track.
    """
    state = state or empty_state()
    rng = rng or random.Random()
    valid = sorted({n for n in names if (durations.get(n) or 0) > 0})
    if not valid:
        return []
    chosen = _select(valid, durations, state.get('counts') or {}, rng, max_seconds)
    return _shuffle_unlike(chosen, list(state.get('last_order') or []), rng)


def record_use(state, order):
    """Anota el video hecho: orden anterior y +1 a cada track usado. Devuelve el estado."""
    counts = dict(state.get('counts') or {})
    for name in order:
        counts[name] = counts.get(name, 0) + 1
    return {'last_order': list(order), 'counts': counts,
            'videos': int(state.get('videos') or 0) + 1}
