#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke de kit_select.choose con packs en memoria y seed fija."""

import os
import random
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.kit_select import KitSelectError, choose


def _loop(name: str, path: str) -> dict:
    return {'name': name, 'path': path}


def _img(name: str, path: str) -> dict:
    return {'name': name, 'path': path, 'source': 'local'}


def _pack(
    name: str,
    loops=None,
    named_previews=None,
    images=None,
) -> dict:
    path = f'/kits/{name}'
    return {
        'name': name,
        'dropbox_path': path,
        'loops': loops or [],
        'named_previews': named_previews or [],
        'images': images or [],
    }


def _history(last_used=None, last_image=None) -> dict:
    return {
        'last_used_by_path': last_used or {},
        'last_image_by_path': last_image or {},
    }


def main() -> int:
    now = datetime(2026, 6, 15, 12, 0, 0)
    t10 = (now - timedelta(days=10)).isoformat(timespec='seconds')
    t5 = (now - timedelta(days=5)).isoformat(timespec='seconds')
    t20 = (now - timedelta(days=20)).isoformat(timespec='seconds')

    free = _pack('Free', loops=[_loop(f'L{i}.wav', f'/kits/Free/L{i}.wav') for i in range(8)],
                 images=[_img('a.png', '/img/a.png')])
    recent = _pack('Recent', loops=[_loop('R.wav', '/kits/Recent/R.wav')],
                   images=[_img('b.png', '/img/b.png')])

    hist = _history(last_used={'/kits/Recent': t10})
    rng = random.Random(42)
    out = choose([free, recent], hist, now, rng, cooldown_days=30)
    if out['pack']['dropbox_path'] != '/kits/Free':
        print('FAIL: pack de 10 días no debe salir si hay otro libre', out['pack']['dropbox_path'])
        return 1

    only_a = _pack('A', loops=[_loop('x.wav', '/kits/A/x.wav')],
                  images=[_img('i.png', '/img/i.png')])
    only_b = _pack('B', loops=[_loop('y.wav', '/kits/B/y.wav')],
                  images=[_img('j.png', '/img/j.png')])
    hist_all = _history(last_used={'/kits/A': t5, '/kits/B': t20})
    rng2 = random.Random(1)
    out2 = choose([only_a, only_b], hist_all, now, rng2, cooldown_days=30)
    if not out2['cooldown_relaxed']:
        print('FAIL: cooldown_relaxed debe ser True')
        return 1
    if out2['pack']['dropbox_path'] != '/kits/B':
        print('FAIL: con todos en cooldown debe salir el más viejo (B=20d)', out2['pack'])
        return 1

    loops10 = [_loop(f'loop{i}.wav', f'/kits/Rich/loop{i}.wav') for i in range(10)]
    rich = _pack(
        'Rich',
        loops=loops10,
        named_previews=[_loop('Preview.wav', '/kits/Rich/Preview.wav')],
        images=[_img('cover.png', '/kits/Rich/images/cover.png')],
    )
    rng3 = random.Random(99)
    out3 = choose([rich], _history(), now, rng3, prefer_named_preview=True)
    if out3['audio_mode'] != 'named_preview':
        print('FAIL: modo named_preview', out3['audio_mode'])
        return 1
    if len(out3['audio_files']) != 1 or out3['audio_files'][0]['name'] != 'Preview.wav':
        print('FAIL: debe ser solo Preview.wav', out3['audio_files'])
        return 1

    rng4 = random.Random(99)
    out4 = choose([rich], _history(), now, rng4, prefer_named_preview=False)
    if out4['audio_mode'] != 'assembled':
        print('FAIL: modo assembled', out4['audio_mode'])
        return 1
    n_loops = len(out4['audio_files'])
    if n_loops < 6 or n_loops > 8:
        print('FAIL: assembled debe tener entre 6 y 8 loops', n_loops)
        return 1
    names = {f['name'] for f in out4['audio_files']}
    if 'Preview.wav' in names:
        print('FAIL: assembled no debe incluir preview', names)
        return 1

    loops_only = _pack(
        'LoopsOnly',
        loops=[_loop(f'L{i}.wav', f'/kits/LoopsOnly/L{i}.wav') for i in range(12)],
        images=[_img('c.png', '/img/c.png')],
    )
    rng5 = random.Random(7)
    out5 = choose([loops_only], _history(), now, rng5, prefer_named_preview=True)
    if out5['audio_mode'] != 'assembled':
        print('FAIL: sin named_previews debe armar', out5['audio_mode'])
        return 1
    if not (6 <= len(out5['audio_files']) <= 8):
        print('FAIL: rango 6-8 sin previews', len(out5['audio_files']))
        return 1

    two_img = _pack(
        'TwoImg',
        loops=[_loop(f'x{i}.wav', f'/kits/TwoImg/x{i}.wav') for i in range(8)],
        images=[
            _img('one.png', '/kits/TwoImg/one.png'),
            _img('two.png', '/kits/TwoImg/two.png'),
        ],
    )
    hist_img = _history(last_image={'/kits/TwoImg': '/kits/TwoImg/one.png'})
    rng6 = random.Random(0)
    first = choose([two_img], hist_img, now, rng6)
    hist_after = _history(last_image={
        '/kits/TwoImg': first['image']['path'],
    })
    second = choose([two_img], hist_after, now, random.Random(0))
    if first['image']['path'] == second['image']['path']:
        print('FAIL: dos choose no deben repetir imagen si hay dos', first, second)
        return 1

    no_img = _pack('NoImg', loops=[_loop('a.wav', '/kits/NoImg/a.wav')], images=[])
    try:
        choose([no_img], _history(), now, random.Random(0))
        print('FAIL: 0 imágenes debe lanzar error')
        return 1
    except KitSelectError:
        pass

    print('OK smoke_kit_select')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
