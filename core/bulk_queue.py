# -*- coding: utf-8 -*-
"""Tandas en bulk: beats soltados en ``entrada/<canal>/`` → videos de cada canal. Sin Qt.

- Solo se toman audios sueltos de ``entrada/<canal>/`` (no las subcarpetas).
- Un archivo que se está copiando o sincronizando (cambia de tamaño o fecha entre dos lecturas,
  o Dropbox todavía no lo bajó) se saltea y queda para la próxima vez.
- Al generarse bien, el beat pasa a ``entrada/<canal>/hechos/``. Si falla, se queda donde está
  y el error se anota en ``entrada/<canal>/errores.txt``.
"""
import os
import shutil
import time
from datetime import datetime

from core import channel_profile as cp
from core import manual_render as mr

DONE_DIR = 'hechos'
ERRORS_FILE = 'errores.txt'
SETTLE_SECONDS = 2.0
_TEMP_SUFFIXES = ('.part', '.tmp', '.crdownload', '.download', '.partial')


def input_channels(root):
    """Canales que tienen carpeta en ``entrada/`` (aunque todavía no tengan perfil)."""
    base = os.path.join(root, cp.INPUT_DIR)
    if not os.path.isdir(base):
        return []
    names = []
    for name in os.listdir(base):
        try:
            cp.check_name(name)
        except cp.ProfileError:
            continue
        if os.path.isdir(os.path.join(base, name)):
            names.append(name)
    return sorted(names, key=str.lower)


def _audio_files(folder):
    files = []
    for entry in sorted(os.listdir(folder), key=str.lower):
        path = os.path.join(folder, entry)
        low = entry.lower()
        if (os.path.isfile(path) and low.endswith(mr.AUDIO_SUFFIXES) and not low.startswith(('~$', '.'))
                and not low.endswith(_TEMP_SUFFIXES)):
            files.append(path)
    return files


def scan(root):
    """``(beats, avisos)``. ``beats``: dicts ``{channel, path}`` listos para revisar.

    ``avisos``: textos para la UI (canal sin perfil, archivos sin bajar de Dropbox).
    """
    beats, notes = [], []
    profiles = set(cp.list_channels(root))
    for channel in input_channels(root):
        files = _audio_files(cp.input_dir(root, channel))
        if not files:
            continue
        if channel not in profiles:
            notes.append(f'{channel}: {len(files)} beats sin perfil de canal (creá el canal con ese nombre).')
            continue
        remote = [f for f in files if cp.online_only(f)]
        if remote:
            notes.append(f'{channel}: {len(remote)} beats todavía sin bajar de Dropbox (quedan para después).')
        beats.extend({'channel': channel, 'path': f} for f in files if f not in remote)
    return beats, notes


def _signature(path, stat):
    try:
        info = stat(path)
    except OSError:
        return None
    return info.st_size, info.st_mtime


def settled(beats, wait=SETTLE_SECONDS, sleep=time.sleep, stat=os.stat):
    """``(listos, en_curso)``: los que no cambiaron de tamaño ni fecha durante ``wait`` segundos."""
    before = {b['path']: _signature(b['path'], stat) for b in beats}
    if beats and wait:
        sleep(wait)
    ready, busy = [], []
    for beat in beats:
        now = _signature(beat['path'], stat)
        (ready if now is not None and now == before[beat['path']] and now[0] > 0 else busy).append(beat)
    return ready, busy


def mark_done(root, channel, path):
    """Mueve el beat a ``entrada/<canal>/hechos/`` sin pisar otro con el mismo nombre."""
    done = os.path.join(cp.input_dir(root, channel), DONE_DIR)
    os.makedirs(done, exist_ok=True)
    stem, ext = os.path.splitext(os.path.basename(path))
    target, n = os.path.join(done, stem + ext), 2
    while os.path.exists(target):
        target, n = os.path.join(done, f'{stem} ({n}){ext}'), n + 1
    shutil.move(path, target)
    return target


def log_error(root, channel, path, message, now=None):
    folder = cp.input_dir(root, channel)
    os.makedirs(folder, exist_ok=True)
    stamp = (now or datetime.now()).strftime('%Y-%m-%d %H:%M')
    with open(os.path.join(folder, ERRORS_FILE), 'a', encoding='utf-8') as f:
        f.write(f'{stamp}  {os.path.basename(path)}: {message}\n')


def run_bulk(root, output_root, beats, titles=None, progress=lambda done, total, text: None,
             cancelled=lambda: False, tools=None, today=None):
    """Genera todos los beats agrupados por canal. Devuelve ``{canal: {'ok': n, 'errores': [...]}}``.

    Un canal con problemas (sin perfil, sin fondos) no frena a los demás.
    """
    groups = {}
    for beat in beats:
        groups.setdefault(beat['channel'], []).append(beat['path'])
    summary, offset, total = {}, 0, len(beats)
    if beats:
        tools = tools or mr.Tools()
    for channel, paths in groups.items():
        if cancelled():
            raise mr.Cancelled()
        entry = summary.setdefault(channel, {'ok': 0, 'errores': []})

        def fail(audio, message, channel=channel, entry=entry):
            entry['errores'].append((mr.beat_name(audio), message))
            log_error(root, channel, audio, message)

        def done(audio, result, channel=channel, entry=entry):
            entry['ok'] += 1
            mark_done(root, channel, audio)

        def step(d, t, text, channel=channel, offset=offset):
            progress(offset + d, total, f'[{channel}] {text}')

        try:
            profile = cp.load(root, channel)
            mr.run_batch(paths, channel, root, output_root, profile, progress=step, cancelled=cancelled,
                         tools=tools, titles=titles, today=today, on_done=done, on_error=fail)
        except (mr.ManualError, cp.ProfileError) as exc:
            for audio in paths:
                fail(audio, str(exc))
        offset += len(paths)
    progress(total, total, 'Listo')
    return summary
