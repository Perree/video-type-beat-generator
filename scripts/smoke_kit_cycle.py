#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del ciclo por kit: 3 videos, descanso de 30 días, separación y semana. Sin red.

Simula semanas completas (elegir kits, planificar audio con mediciones falsas y
guardar el estado en memoria) y revisa las reglas sobre lo que quedó guardado.
"""
import os
import random
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import dropbox  # noqa: F401
except ImportError:  # kit_audio importa kit_source; acá no se usa Dropbox
    import types
    _stub = types.ModuleType('dropbox')
    _stub.exceptions = types.SimpleNamespace(ApiError=type('ApiError', (Exception,), {}))
    _stub.files = types.SimpleNamespace(FolderMetadata=type('FolderMetadata', (), {}),
                                        FileMetadata=type('FileMetadata', (), {}))
    sys.modules['dropbox'] = _stub

from core import kit_cycle
from core.kit_audio import plan_audio

START = datetime(2026, 1, 4, 23, 5, 0)  # domingo


def _check(cond, msg):
    if not cond:
        print('FAIL:', msg)
        return False
    return True


def _pack(name, loops=30):
    path = f'/kits/{name}'
    return {
        'name': name,
        'dropbox_path': path,
        'loops': [{'name': f'L{i:02d}.wav', 'path': f'{path}/L{i:02d}.wav'} for i in range(loops)],
        'images': [{'name': 'a.png', 'path': f'{path}/a.png', 'source': 'local'}],
    }


def _empty_state():
    return {'packs': {}, 'runs': [], 'next_run_id': 1}


def _record(state, pack, plan, when, cfg):
    """Lo que hace el worker al subir un video: corrida, last_used_at y ciclo."""
    saved = state['packs'].setdefault(pack['dropbox_path'], {
        'id': len(state['packs']) + 1, 'nombre': pack['name'], 'last_used_at': None, 'cycle': {}})
    cycle = kit_cycle.advance(saved['cycle'], when, cfg,
                              close=plan['short'] or plan['exhausted'],
                              last_used_at=saved['last_used_at'])
    state['runs'].append({
        'id': state['next_run_id'], 'pack_id': saved['id'], 'estado': 'uploaded',
        'audio_mode': plan['mode'], 'loops_json': plan['segments'],
        'subido_en': when.isoformat(timespec='seconds')})
    state['next_run_id'] += 1
    saved['last_used_at'] = when.isoformat(timespec='seconds')
    saved['cycle'] = {**saved['cycle'], **cycle}
    return cycle


def _overlap(first, second):
    return any(a['path'] == b['path'] and a['start'] < b['end'] and b['start'] < a['end']
               for a in first for b in second)


def _unit_checks():
    ok = True
    cfg = kit_cycle.settings()
    ok &= _check(cfg == {'cycle_max_videos': 3, 'cycle_rest_days': 30, 'kit_min_gap_days': 7,
                         'kits_per_week': 3}, f'defaults {cfg}')
    ok &= _check(kit_cycle.settings({'cycle_rest_days': 45})['cycle_rest_days'] == 45, 'config')

    cycle = {}
    when = START
    for expected in (1, 2):
        cycle = kit_cycle.advance(cycle, when, cfg)
        ok &= _check(cycle == {'cycle_videos': expected, 'rest_until': None}, f'video {expected}')
        when += timedelta(days=7)
    third_at = when
    cycle = kit_cycle.advance(cycle, third_at, cfg)
    rest_until = datetime.fromisoformat(cycle['rest_until'])
    ok &= _check(cycle['cycle_videos'] == 3 and rest_until == third_at + timedelta(days=30),
                 f'el tercer video debía cerrar el ciclo: {cycle}')

    last = third_at.isoformat()
    for days, eligible, reason in ((7, False, 'resting'), (29, False, 'resting'),
                                   (30, True, 'ok'), (45, True, 'ok')):
        st = kit_cycle.status(cycle, last, third_at + timedelta(days=days), cfg)
        ok &= _check(st['eligible'] is eligible and st['reason'] == reason,
                     f'día {days} del descanso: {st}')
    try:
        kit_cycle.advance(cycle, third_at + timedelta(days=10), cfg)
        ok = _check(False, 'sumar un video en descanso debía fallar')
    except kit_cycle.KitCycleError:
        pass
    fresh = kit_cycle.advance(cycle, third_at + timedelta(days=30), cfg)
    ok &= _check(fresh == {'cycle_videos': 1, 'rest_until': None}, f'ciclo nuevo: {fresh}')

    # Separación de 7 días por fecha: la corrida siguiente puede caer minutos antes.
    used = START.isoformat()
    ok &= _check(kit_cycle.status({'cycle_videos': 1}, used, START + timedelta(days=6), cfg)
                 ['reason'] == 'gap', 'a los 6 días todavía no')
    early = START + timedelta(days=7) - timedelta(minutes=20)
    ok &= _check(kit_cycle.status({'cycle_videos': 1}, used, early, cfg)['eligible'],
                 'la corrida semanal adelantada unos minutos debe poder usar el kit')
    ok &= _check(kit_cycle.status({}, None, START, cfg)['eligible'], 'kit nunca usado')

    # Ciclo lleno sin rest_until (estado a medio guardar): descansa desde el último uso.
    broken = kit_cycle.status({'cycle_videos': 3, 'rest_until': None}, used,
                              START + timedelta(days=10), cfg)
    ok &= _check(broken['reason'] == 'resting', f'ciclo lleno sin descanso: {broken}')

    # Kit chico: close cierra el ciclo con el primer video.
    closed = kit_cycle.advance({}, START, cfg, close=True)
    ok &= _check(closed['cycle_videos'] == 1 and closed['rest_until'], f'close: {closed}')

    # Fechas con zona y loops_json como texto (kit_store) no rompen.
    aware = '2026-01-04T23:05:00+00:00'
    ok &= _check(kit_cycle.status({'rest_until': aware}, aware, START, cfg)['reason']
                 in ('ok', 'resting', 'gap'), 'fecha con zona')
    state = {'packs': {'/kits/a': {'id': 1, 'cycle': {'cycle_videos': 1}}},
             'runs': [{'id': 1, 'pack_id': 1, 'estado': 'uploaded',
                       'loops_json': '[{"path": "/kits/a/x.wav", "start": 0, "end": 5}]'},
                      {'id': 2, 'pack_id': 1, 'estado': 'error', 'loops_json': [{'path': 'no'}]}]}
    segs = kit_cycle.used_segments(state, '/kits/a', START, cfg)
    ok &= _check([s['path'] for s in segs] == ['/kits/a/x.wav'], f'used_segments: {segs}')
    ok &= _check(kit_cycle.used_segments(state, '/kits/otro', START, cfg) == [], 'kit sin estado')
    return ok


def _simulation_checks():
    """20 semanas con 12 kits: reglas del ciclo y del audio sobre el estado guardado."""
    ok = True
    cfg = kit_cycle.settings()
    rng = random.Random(5)
    packs = [_pack(f'K{i:02d}') for i in range(11)] + [_pack('Chico', loops=6)]
    by_path = {p['dropbox_path']: p for p in packs}
    state = _empty_state()
    history = {'last_used_by_path': {}, 'last_image_by_path': {}}
    uses = {}      # path -> [(fecha, plan)]
    warned_small = False
    short_weeks = 0

    for week in range(20):
        # La corrida no cae siempre a la misma hora.
        now = START + timedelta(days=7 * week, minutes=rng.randint(-30, 30))
        picked = kit_cycle.pick_week(packs, state, history, now, rng, cfg)
        paths = [s['pack']['dropbox_path'] for s in picked['selections']]
        ok &= _check(len(paths) == len(set(paths)), f'semana {week}: kits repetidos')
        # Con rotación pareja los 12 kits cierran el ciclo casi juntos: una semana puede
        # salir incompleta (y avisar), pero nunca con menos kits de los que están libres.
        free = len(kit_cycle.eligible_packs(packs, state, now, cfg))
        ok &= _check(len(paths) == min(3, free),
                     f'semana {week}: {len(paths)} kits con {free} libres ({picked["warnings"]})')
        ok &= _check(len(paths) == 3 or picked['warnings'], f'semana {week}: incompleta sin aviso')
        short_weeks += len(paths) < 3
        for path in paths:
            pack = by_path[path]
            before = kit_cycle.used_segments(state, path, now, cfg)
            plan = plan_audio(pack, before, rng, end_fn=lambda p, **kw: 14.7)
            ok &= _check(plan['ok'], f'semana {week}: sin audio')
            if pack['name'] == 'Chico':
                ok &= _check(plan['short'] and plan['warnings'], 'el kit chico debía avisar')
                warned_small = True
            else:
                ok &= _check(not plan['short'] and 135 <= plan['duration'] <= 195,
                             f"semana {week}: duración {plan['duration']}")
                ok &= _check(not _overlap(plan['segments'], before),
                             f'semana {week}: tramos repetidos dentro del ciclo')
            _record(state, pack, plan, now, cfg)
            uses.setdefault(path, []).append((now, plan))

    ok &= _check(warned_small, 'el kit chico nunca salió')
    ok &= _check(short_weeks <= 2, f'{short_weeks} semanas incompletas de 20')
    for path, items in uses.items():
        small = by_path[path]['name'] == 'Chico'
        limit = 1 if small else cfg['cycle_max_videos']
        in_cycle = 0
        for index, (when, _plan) in enumerate(items):
            if index:
                days = (when.date() - items[index - 1][0].date()).days
                ok &= _check(days >= cfg['kit_min_gap_days'], f'separación de {days} días')
                if in_cycle == limit:
                    ok &= _check(days >= cfg['cycle_rest_days'],
                                 f'descanso de solo {days} días tras cerrar el ciclo')
                    in_cycle = 0
            in_cycle += 1
            ok &= _check(in_cycle <= limit, 'más videos que el máximo del ciclo')
    ok &= _check(any(len(items) > 3 for items in uses.values()),
                 'ningún kit llegó a empezar un ciclo nuevo')

    # Con pocos kits libres la semana sale incompleta y avisa, sin romper las reglas.
    few = [_pack('A'), _pack('B')]
    out = kit_cycle.pick_week(few, _empty_state(), history, START, rng, cfg)
    ok &= _check(len(out['selections']) == 2 and out['warnings'], f'pocos kits: {out["warnings"]}')
    ok &= _check('A' not in ' '.join(out['warnings']).split(), 'avisos sin nombres de kit')
    no_img = dict(_pack('SinImg'), images=[])
    out = kit_cycle.pick_week([no_img], _empty_state(), history, START, rng, cfg)
    ok &= _check(out['selections'] == [] and len(out['warnings']) == 2, f'sin imágenes: {out}')
    # Con portada automática el kit sin imágenes entra, sin imagen elegida.
    out = kit_cycle.pick_week([no_img], _empty_state(), history, START, rng, cfg,
                              require_images=False)
    ok &= _check(len(out['selections']) == 1 and out['selections'][0]['image'] is None,
                 f'sin imágenes con portada auto: {out}')
    # keep_order: entre kits sin usar manda el orden de la lista, no el azar.
    ordered = [_pack(f'O{i}') for i in range(6)]
    for seed in range(5):
        out = kit_cycle.pick_week(ordered, _empty_state(), history, START, random.Random(seed),
                                  cfg, keep_order=True)
        ok &= _check([s['pack']['name'] for s in out['selections']] == ['O0', 'O1', 'O2'],
                     f'keep_order con semilla {seed}')
    return ok


def main() -> int:
    if not _unit_checks():
        return 1
    print('OK reglas del ciclo')
    if not _simulation_checks():
        return 1
    print('OK simulación de 20 semanas')
    print('OK')
    return 0


if __name__ == '__main__':
    sys.exit(main())
