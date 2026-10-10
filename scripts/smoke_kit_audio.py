#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del audio por duración: tramos de preview y armado con loops, sin red.

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
from core.kit_trim import KitTrimError, silence_points

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


def _pack(loops=(), previews=()):
    return {'name': 'pack', 'dropbox_path': '/kits/pack',
            'loops': [{'name': os.path.basename(p), 'path': p} for p in loops],
            'named_previews': [{'name': os.path.basename(p), 'path': p} for p in previews],
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

    # Preview de 520 s con silencios de 0,6 s cada 20 s.
    silences = [(20.0 * i - 0.6, 20.0 * i) for i in range(1, 26)]

    def sil_520(path, noise_db, min_silence):
        return 520.0, list(silences)

    pack = _pack(previews=['/kits/pack/Preview.wav'])
    plans = []
    for _ in range(3):
        plan = plan_audio(pack, plans, rng, silences_fn=sil_520)
        plans.append(plan)
        ok &= _check(_in_window(plan) and plan['mode'] == 'named_preview',
                     f'tramo de preview fuera de ventana: {plan}')
        seg = plan['segments'][0]
        ok &= _check(seg['end'] == 520.0 or any(abs(seg['end'] - s) < 0.01 for s, _ in silences),
                     f"el corte no cae en un silencio ni en el final: {seg['end']}")
        ok &= _check(not seg.get('fade_in') and not seg.get('fade_out'), 'corte limpio sin fundido')
    ok &= _check(not _overlap(plans), f'tramos solapados: {[p["segments"] for p in plans]}')
    fourth = plan_audio(pack, plans, rng, silences_fn=sil_520)
    ok &= _check(not _overlap(plans + [fourth]), 'el cuarto tramo pisa a los anteriores')
    ok &= _check(fourth['ok'] is False or fourth['short'] or _in_window(fourth),
                 f'cuarto tramo inconsistente: {fourth}')

    # Sin silencios: corte directo, con fundido y aviso, y sin pisarse.
    def sil_none(path, noise_db, min_silence):
        return 400.0, []

    first = plan_audio(pack, [], rng, silences_fn=sil_none)
    second = plan_audio(pack, [first], rng, silences_fn=sil_none)
    ok &= _check(_in_window(first) and _in_window(second), f'sin silencios: {first} {second}')
    ok &= _check(first['segments'][0].get('fade_out') and first['warnings'],
                 'corte directo sin fundido o sin aviso')
    ok &= _check(second['segments'][0].get('fade_in'), 'arranque en corte directo sin fundido')
    ok &= _check(not _overlap([first, second]), 'tramos solapados sin silencios')

    # Bordes de la ventana: preview que dura justo el mínimo o apenas más que el máximo.
    exact = plan_audio(pack, [], rng, silences_fn=lambda p, noise_db, min_silence: (135.0, []))
    ok &= _check(_in_window(exact) and exact['duration'] == 135.0, f'preview de 135 s: {exact}')
    over = plan_audio(pack, [], rng, silences_fn=lambda p, noise_db, min_silence: (195.02, []))
    ok &= _check(_in_window(over), f'preview de 195,02 s: {over}')

    # Loops: 24 de 14,7 s dan dos videos sin repetir; el tercero repite y avisa.
    loops = [f'/kits/pack/L{i:02d}.wav' for i in range(24)]
    loop_pack = _pack(loops=loops)
    plans = []
    for _ in range(3):
        plans.append(plan_audio(loop_pack, plans, rng, end_fn=lambda p, **kw: 14.7))
    ok &= _check(all(_in_window(p) and p['mode'] == 'assembled' for p in plans),
                 f'loops fuera de ventana: {[p["duration"] for p in plans]}')
    for plan in plans:
        paths = [seg['path'] for seg in plan['segments']]
        ok &= _check(len(paths) == len(set(paths)), 'un loop repetido dentro del mismo video')
    ok &= _check(not _overlap(plans[:2]) and not plans[0]['repeated'] and not plans[1]['repeated'],
                 'los dos primeros videos repiten loops')
    ok &= _check(plans[2]['repeated'] and any('repiten' in w for w in plans[2]['warnings']),
                 'el tercer video debía avisar que repite')

    # Loops que no se pueden cortar o demasiado largos: se saltean y se avisa.
    def flaky(path, **kw):
        if path.endswith(('L00.wav', 'L01.wav')):
            raise KitTrimError('sin corte')
        return 250.0 if path.endswith('L02.wav') else 15.0

    plan = plan_audio(loop_pack, [], rng, end_fn=flaky)
    used = {seg['name'] for seg in plan['segments']}
    ok &= _check(_in_window(plan) and not used & {'L00.wav', 'L01.wav', 'L02.wav'},
                 f'loops malos usados: {sorted(used)}')

    # Kit chico: 6 loops dan un video corto con aviso; 2 loops no arman nada.
    small = plan_audio(_pack(loops=loops[:6]), [], rng, end_fn=lambda p, **kw: 15.0)
    ok &= _check(small['ok'] and small['short'] and small['duration'] == 90.0
                 and any('más corto' in w for w in small['warnings']), f'kit chico: {small}')
    tiny = plan_audio(_pack(loops=loops[:2]), [], rng, end_fn=lambda p, **kw: 15.0)
    ok &= _check(tiny['ok'] is False and not tiny['segments'] and tiny['warnings'],
                 f'kit mínimo: {tiny}')
    empty = plan_audio(_pack(), [], rng)
    ok &= _check(empty['ok'] is False and empty['warnings'], f'kit vacío: {empty}')
    ok &= _check('pack' not in ' '.join(small['warnings'] + tiny['warnings']).lower(),
                 'los avisos no llevan el nombre del kit')

    # Preview corta y loops suficientes: se arma con loops.
    mixed = _pack(loops=loops, previews=['/kits/pack/Preview.wav'])
    plan = plan_audio(mixed, [], rng, end_fn=lambda p, **kw: 14.7,
                      silences_fn=lambda p, noise_db, min_silence: (40.0, []))
    ok &= _check(_in_window(plan) and plan['mode'] == 'assembled', f'preview corta: {plan}')

    ok &= _check(settings({'target_min_s': 120}) == {
        'target_min_s': 120.0, 'target_max_s': 195.0, 'short_min_s': 60.0}, 'settings')
    try:
        plan_audio(loop_pack, [], rng, target_min=200, target_max=195)
        ok = _check(False, 'ventana invertida debía fallar')
    except ValueError:
        pass
    return ok


def _real_checks(folder):
    """Lo mismo sobre wav reales: silencedetect y cortes con ffmpeg."""
    ok = True
    rng = random.Random(11)

    # Preview: 26 frases de 19,4 s separadas por 0,6 s de silencio (520 s).
    preview = os.path.join(folder, 'Kit Preview.wav')
    _write_wav(preview, [part for _ in range(26) for part in ((19.4, False), (0.6, True))])
    duration, points = silence_points(preview)
    ok &= _check(abs(duration - 520) < 0.5 and len(points) == 26,
                 f'silence_points: {duration} / {len(points)}')
    ok &= _check(all(0.4 < end - start < 0.8 for start, end in points), f'silencios: {points[:3]}')

    pack = _pack(previews=[preview])
    plans = []
    for index in range(3):
        plan = plan_audio(pack, plans, rng)
        plans.append(plan)
        ok &= _check(_in_window(plan), f'tramo real {index} fuera de ventana: {plan}')
        seg = plan['segments'][0]
        ok &= _check(any(abs(seg['end'] - start) < 0.05 for start, _ in points),
                     f"corte real fuera de un silencio: {seg['end']}")
        wavs = cut_segments(plan, os.path.join(folder, f'cut_preview_{index}'))
        real = sum(_wav_duration(w) for w in wavs)
        ok &= _check(MIN_S <= real <= MAX_S and abs(real - plan['duration']) < 0.01,
                     f"wav de {real:.3f}s contra plan de {plan['duration']}s")
    ok &= _check(not _overlap(plans), 'tramos reales solapados')

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
        ok &= _check(_in_window(plan) and not plan['repeated'], f'loops reales: {plan}')
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
