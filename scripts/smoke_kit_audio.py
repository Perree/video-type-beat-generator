#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del audio por duración: armado con loops sin repetir y mínimo de loops, sin red.

La lógica se prueba siempre con mediciones falsas. Con ffmpeg en bin/ o PATH se
repite sobre wav generados y se miden los cortes reales; sin ffmpeg esa parte se
salta (SKIP) y sigue exit 0.
"""
import math
import os
import random
import shutil
import struct
import sys
import tempfile
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import dropbox  # noqa: F401
except ImportError:  # kit_source importa el cliente; acá no se usa
    import types
    _stub = types.ModuleType('dropbox')
    _stub.exceptions = types.SimpleNamespace(ApiError=type('ApiError', (Exception,), {}))
    _stub.files = types.SimpleNamespace(FolderMetadata=type('FolderMetadata', (), {}),
                                        FileMetadata=type('FileMetadata', (), {}))
    sys.modules['dropbox'] = _stub

from core.ffmpeg_util import resolve_tool
from core.kit_audio import cut_segments, plan_audio, settings
from core.kit_trim import KitTrimError

RATE = 8000
MIN_S, MAX_S = 135.0, 195.0


def _write_wav(path, parts):
    """parts: lista de (segundos, silencio). Segundos con un decimal como mucho."""
    one_sec = b''.join(struct.pack('<h', int(0.5 * 32767 * math.sin(2 * math.pi * 440 * i / RATE)))
                       for i in range(RATE))
    tone = one_sec * 60
    with wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        for seconds, silent in parts:
            frames = int(round(seconds * RATE))
            w.writeframes(b'\x00\x00' * frames if silent else tone[:frames * 2])


def _wav_duration(path):
    with wave.open(path, 'r') as handle:
        return handle.getnframes() / float(handle.getframerate())


def _check(cond, msg):
    if not cond:
        print('FAIL:', msg)
        return False
    return True


def _pack(loops=()):
    return {'name': 'pack', 'dropbox_path': '/kits/pack',
            'loops': [{'name': os.path.basename(p), 'path': p} for p in loops],
            'images': []}


def _overlap(plans):
    """True si dos tramos del mismo archivo se pisan entre planes distintos."""
    seen = []
    for index, plan in enumerate(plans):
        for seg in plan['segments']:
            for other_index, other in seen:
                if (other_index != index and other['path'] == seg['path']
                        and seg['start'] < other['end'] and other['start'] < seg['end']):
                    return True
            seen.append((index, seg))
    return False


def _in_window(plan):
    return plan['ok'] and not plan['short'] and MIN_S <= plan['duration'] <= MAX_S


def _logic_checks():
    """Reglas de planificación con mediciones inyectadas (sin ffmpeg)."""
    ok = True
    rng = random.Random(3)

    # Loops: 24 de 14,7 s dan dos videos completos; el tercero sale corto con los 4 que
    # quedan, sin repetir ninguno, y el cuarto ya no se arma.
    loops = [f'/kits/pack/L{i:02d}.wav' for i in range(24)]
    loop_pack = _pack(loops=loops)
    plans = []
    for _ in range(3):
        plans.append(plan_audio(loop_pack, plans, rng, end_fn=lambda p, **kw: 14.7))
    ok &= _check(all(_in_window(p) and p['mode'] == 'assembled' for p in plans[:2]),
                 f'loops fuera de ventana: {[p["duration"] for p in plans]}')
    for plan in plans:
        paths = [seg['path'] for seg in plan['segments']]
        ok &= _check(len(paths) == len(set(paths)), 'un loop repetido dentro del mismo video')
    ok &= _check(not _overlap(plans), 'un video repite loops de los anteriores')
    ok &= _check(not plans[0]['exhausted'] and not plans[1]['exhausted'],
                 'con loops de sobra el kit no debía cerrar el ciclo')
    third = plans[2]
    ok &= _check(third['ok'] and third['short'] and len(third['segments']) == 4
                 and third['exhausted'] and any('más corto' in w for w in third['warnings']),
                 f'el tercer video debía salir corto con 4 loops: {third}')
    fourth = plan_audio(loop_pack, plans, rng, end_fn=lambda p, **kw: 14.7)
    ok &= _check(fourth['ok'] is False and not fourth['segments'] and fourth['warnings'],
                 f'sin loops libres no se arma nada: {fourth}')
    ok &= _check(all('repet' not in w and 'repit' not in w
                     for p in plans + [fourth] for w in p['warnings']),
                 'ningún aviso habla de repetir loops')

    # Kit de 13 loops: un video completo (10) deja 3, menos que el mínimo: cierra el ciclo.
    last = plan_audio(_pack(loops=loops[:13]), [], rng, end_fn=lambda p, **kw: 14.7)
    ok &= _check(_in_window(last) and last['exhausted'], f'kit que se queda sin loops: {last}')

    # Loops largos: aunque 3 ya entren en la ventana, el video lleva el mínimo de 4.
    long_plan = plan_audio(loop_pack, [], rng, end_fn=lambda p, **kw: 46.0,
                           trim={'max_preview': 60})
    ok &= _check(_in_window(long_plan) and len(long_plan['segments']) == 4,
                 f'mínimo de loops con previews largas: {long_plan}')

    # Loops que no se pueden cortar o demasiado largos: se saltean y se avisa.
    def flaky(path, **kw):
        if path.endswith(('L00.wav', 'L01.wav')):
            raise KitTrimError('sin corte')
        return 250.0 if path.endswith('L02.wav') else 15.0

    plan = plan_audio(loop_pack, [], rng, end_fn=flaky)
    used = {seg['name'] for seg in plan['segments']}
    ok &= _check(_in_window(plan) and not used & {'L00.wav', 'L01.wav', 'L02.wav'},
                 f'loops malos usados: {sorted(used)}')

    # Kit chico: 4 loops o más dan un video corto con aviso; con 3 no se arma nada.
    small = plan_audio(_pack(loops=loops[:6]), [], rng, end_fn=lambda p, **kw: 15.0)
    ok &= _check(small['ok'] and small['short'] and small['duration'] == 90.0
                 and any('más corto' in w for w in small['warnings']), f'kit chico: {small}')
    four = plan_audio(_pack(loops=loops[:4]), [], rng, end_fn=lambda p, **kw: 10.0)
    ok &= _check(four['ok'] and four['short'] and four['duration'] == 40.0
                 and len(four['segments']) == 4, f'kit de 4 loops: {four}')
    tiny = plan_audio(_pack(loops=loops[:3]), [], rng, end_fn=lambda p, **kw: 15.0)
    ok &= _check(tiny['ok'] is False and not tiny['segments'] and tiny['warnings'],
                 f'kit de 3 loops: {tiny}')
    # 5 loops con 2 que no se pueden cortar: quedan 3 utilizables, no alcanza.
    broken = plan_audio(_pack(loops=loops[:5]), [], rng, end_fn=flaky)
    ok &= _check(broken['ok'] is False, f'kit con loops rotos: {broken}')
    empty = plan_audio(_pack(), [], rng)
    ok &= _check(empty['ok'] is False and empty['warnings'], f'kit vacío: {empty}')
    ok &= _check('pack' not in ' '.join(small['warnings'] + tiny['warnings']).lower(),
                 'los avisos no llevan el nombre del kit')
    # El mínimo y el piso de duración se pueden cambiar por config.
    two = plan_audio(_pack(loops=loops[:2]), [], rng, min_loops=2, end_fn=lambda p, **kw: 15.0)
    ok &= _check(two['ok'] and two['short'], f'min_loops=2: {two}')
    floor = plan_audio(_pack(loops=loops[:6]), [], rng, short_min=100,
                       end_fn=lambda p, **kw: 15.0)
    ok &= _check(floor['ok'] is False, f'short_min=100 con 90 s: {floor}')

    ok &= _check(settings({'target_min_s': 120}) == {
        'target_min_s': 120.0, 'target_max_s': 195.0, 'short_min_s': 0.0, 'min_loops': 4},
        'settings')
    ok &= _check(settings({'min_loops_per_video': 6})['min_loops'] == 6, 'min_loops_per_video')
    try:
        plan_audio(loop_pack, [], rng, target_min=200, target_max=195)
        ok = _check(False, 'ventana invertida debía fallar')
    except ValueError:
        pass
    return ok


def _real_checks(folder):
    """Lo mismo sobre wav reales: corte en el primer silencio con ffmpeg."""
    ok = True
    rng = random.Random(11)

    # Loops: 15 s de tono, 0,5 s de silencio y 3 s de capas que no deben entrar.
    loops = []
    for i in range(24):
        path = os.path.join(folder, f'L{i:02d}.wav')
        _write_wav(path, [(15, False), (0.5, True), (3, False)])
        loops.append(path)
    plans = []
    for index in range(2):
        plan = plan_audio(_pack(loops=loops), plans, rng)
        plans.append(plan)
        ok &= _check(_in_window(plan), f'loops reales: {plan}')
        wavs = cut_segments(plan, os.path.join(folder, f'cut_loops_{index}'))
        ok &= _check(all(14.7 <= _wav_duration(w) <= 15.3 for w in wavs),
                     'un loop cortado incluye audio posterior al silencio')
        real = sum(_wav_duration(w) for w in wavs)
        ok &= _check(MIN_S <= real <= MAX_S, f'video de loops de {real:.3f}s')
    ok &= _check(not _overlap(plans), 'dos videos del mismo kit comparten loops')

    small = plan_audio(_pack(loops=loops[:5]), [], rng)
    ok &= _check(small['ok'] and small['short'] and small['warnings'], f'kit chico real: {small}')
    return ok


def main() -> int:
    os.chdir(ROOT)  # resolve_tool busca bin/ relativo al cwd
    if not _logic_checks():
        return 1
    print('OK reglas de planificación')
    if not resolve_tool('ffmpeg'):
        print('SKIP: sin ffmpeg, no se prueban los cortes reales')
        print('OK')
        return 0
    folder = tempfile.mkdtemp(prefix='smoke_kit_audio_')
    try:
        if not _real_checks(folder):
            return 1
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    print('OK cortes reales')
    print('OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
