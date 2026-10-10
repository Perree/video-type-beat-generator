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
    images=None,
) -> dict:
    path = f'/kits/{name}'
    return {
        'name': name,
        'dropbox_path': path,
        'loops': loops or [],
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
    rich = _pack('Rich', loops=loops10,
                 images=[_img('cover.png', '/kits/Rich/images/cover.png')])
    out4 = choose([rich], _history(), now, random.Random(99))
    if out4['audio_mode'] != 'assembled':
        print('FAIL: el único modo es assembled', out4['audio_mode'])
        return 1
    n_loops = len(out4['audio_files'])
    if n_loops < 6 or n_loops > 8:
        print('FAIL: debe elegir entre 6 y 8 loops', n_loops)
        return 1
    try:
        choose([rich], _history(), now, random.Random(99), prefer_named_preview=True)
        print('FAIL: prefer_named_preview ya no existe')
        return 1
    except TypeError:
        pass

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

    # Portada automática: un kit sin imágenes es válido y sale sin imagen.
    auto = choose([no_img], _history(), now, random.Random(0), require_image=False)
    if auto['image'] is not None or not auto['audio_files']:
        print('FAIL: sin imágenes y require_image=False', auto)
        return 1

    print('OK smoke_kit_select')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
