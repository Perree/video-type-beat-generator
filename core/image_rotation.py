# -*- coding: utf-8 -*-
"""WyreScapes: elige la imagen fija de cada mixtape, rotando sin repetir.

Reglas (decisión del usuario):
- Se usan TODAS las imágenes de la carpeta ``Imagenes`` (jpg, jpeg, png, jfif, webp),
  leída en cada corrida para que las nuevas entren solas. Sin recursión: la subcarpeta
  ``Refes`` (y cualquier otra) nunca va a un video. Los ``.gif`` se saltean.
- Rotación: no se repite ninguna hasta usar todas. Después arranca una vuelta nueva y su
  primera imagen no puede ser la última de la vuelta anterior.
- Aviso cuando quedan pocas sin usar en la vuelta.
- Si una imagen no se puede abrir (ffmpeg), se avisa y se elige otra, sin romper.

Estado en un JSON local vecino al de los tracks: ``{"cycle_used": [...], "last": ...,
"cycles": n}``, por nombre de archivo. Se guarda solo si el render sale bien.
"""
import json
import os
import random
import subprocess

from core.ffmpeg_util import resolve_tool

IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.jfif', '.webp')
DEFAULT_STATE_PATH = os.path.join('config', 'wyrescapes_images.json')
LOW_THRESHOLD = 3


def scan_images(folder):
    """Rutas de las imágenes de ``folder`` (orden alfabético), sin entrar a subcarpetas."""
    if not os.path.isdir(folder):
        return []
    names = sorted(n for n in os.listdir(folder)
                   if n.lower().endswith(IMAGE_EXTS) and os.path.isfile(os.path.join(folder, n)))
    return [os.path.join(folder, n) for n in names]


def empty_state():
    return {'cycle_used': [], 'last': None, 'cycles': 0}


def load_state(path=DEFAULT_STATE_PATH):
    """Estado guardado, o uno vacío si no existe o está roto."""
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return empty_state()
    state = empty_state()
    if isinstance(data, dict):
        if isinstance(data.get('cycle_used'), list):
            state['cycle_used'] = [str(x) for x in data['cycle_used']]
        if data.get('last'):
            state['last'] = str(data['last'])
        state['cycles'] = int(data.get('cycles') or 0)
    return state


def save_state(state, path=DEFAULT_STATE_PATH):
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(state, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def ffmpeg_can_open(path):
    """True si ffmpeg decodifica un cuadro de la imagen sin errores."""
    ffmpeg = resolve_tool('ffmpeg')
    if not ffmpeg:
        return True  # sin ffmpeg no se puede chequear; el render dirá si falla
    try:
        result = subprocess.run(
            [ffmpeg, '-v', 'error', '-i', path, '-frames:v', '1', '-f', 'null', '-'],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60,
            stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and not (result.stderr or '').strip()


def pick_image(paths, state=None, rng=None, can_open=ffmpeg_can_open,
               low_threshold=LOW_THRESHOLD):
    """Elige la próxima imagen de la rotación.

    Args:
        paths: rutas de ``scan_images``.
        state: estado de ``load_state``.
        rng: ``random.Random`` (tests).
        can_open: ``fn(ruta) -> bool``; las que den False se saltean con aviso.
        low_threshold: avisar si después de esta quedan esa cantidad o menos en la vuelta.

    Returns:
        ``(ruta o None, estado_nuevo, avisos)``. El estado nuevo ya cuenta la imagen
        elegida; guardarlo solo si el render sale bien.
    """
    state = state or empty_state()
    rng = rng or random.Random()
    warnings = []
    by_name = {os.path.basename(p): p for p in paths}
    names = sorted(by_name)
    used = [n for n in state.get('cycle_used') or [] if n in by_name]
    last = state.get('last')
    cycles = int(state.get('cycles') or 0)
    bad = set()

    def try_pick(candidates):
        order = list(candidates)
        rng.shuffle(order)
        for name in order:
            if can_open(by_name[name]):
                return name
            bad.add(name)
            warnings.append(f'No se pudo abrir la imagen, se saltea: {name}')
        return None

    chosen = try_pick([n for n in names if n not in used])
    new_cycle = False
    if chosen is None:
        # Vuelta completa (o lo que quedaba no abre): arranca otra, sin repetir la última.
        new_cycle = True
        fresh = [n for n in names if n not in bad]
        chosen = try_pick([n for n in fresh if n != last]) if len(fresh) > 1 else None
        if chosen is None:
            chosen = try_pick([n for n in fresh if n not in bad])
    if chosen is None:
        warnings.append('No hay ninguna imagen utilizable')
        return None, state, warnings

    cycle_used = [chosen] if new_cycle else used + [chosen]
    new_state = {'cycle_used': cycle_used, 'last': chosen,
                 'cycles': cycles + 1 if new_cycle else max(cycles, 1)}
    left = [n for n in names if n not in cycle_used and n not in bad]
    if len(left) <= low_threshold:
        warnings.append(f'Quedan {len(left)} imagen(es) sin usar en esta vuelta; '
                        'conviene sumar imágenes nuevas a la carpeta.')
    return by_name[chosen], new_state, warnings
