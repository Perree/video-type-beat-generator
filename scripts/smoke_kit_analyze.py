#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del análisis de packs: packs y wav de stdlib, sin Dropbox ni red.

Sin ffmpeg en bin/ ni PATH, la parte de corte real se salta (SKIP) y sigue exit 0.
"""
import json
import math
import os
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
except ImportError:  # el SDK no hace falta: el listado usa un fake
    import types
    _stub = types.ModuleType('dropbox')
    _stub.exceptions = types.SimpleNamespace(ApiError=type('ApiError', (Exception,), {}))
    _stub.files = types.SimpleNamespace(FolderMetadata=type('FolderMetadata', (), {}),
                                        FileMetadata=type('FileMetadata', (), {}))
    sys.modules['dropbox'] = _stub

from core import kit_source
from core.ffmpeg_util import resolve_tool
from core.kit_analyze import analyze_pack, plan_videos, split_segments
from scripts.analyze_kits import analyze_all, format_table

RATE = 8000


class _Entry:
    def __init__(self, name, path, is_folder=False):
        self.name = name
        self.path_lower = path
        self.path = path
        self.is_folder = is_folder
        self.size = 0 if is_folder else 1


class _Result:
    def __init__(self, entries):
        self.entries = entries
        self.has_more = False
        self.cursor = None


class FakeDbx:
    def __init__(self, tree):
        self.tree = tree

    def files_list_folder(self, path):
        return _Result(self.tree[path or ''])

    def files_list_folder_continue(self, cursor):
        raise AssertionError('sin paginado')


def _write_wav(path, parts):
    """parts: lista de (segundos, silencio)."""
    one_sec = b''.join(struct.pack('<h', int(0.5 * 32767 * math.sin(2 * math.pi * 440 * i / RATE)))
                       for i in range(RATE))
    with wave.open(path, 'w') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        for seconds, silent in parts:
            w.writeframes((b'\x00\x00' * RATE if silent else one_sec) * int(seconds))


def _check(cond, msg):
    if not cond:
        print('FAIL:', msg)
        return False
    return True


def main() -> int:
    ok = True
    # Lógica pura de armado de videos.
    ok &= _check(split_segments(100, 45) == [45, 45, 10], 'split_segments')
    ok &= _check(plan_videos([12] * 12)['videos'] == 1, '12 x 12s = 1 video')
    ok &= _check(plan_videos([12] * 11)['videos'] == 0, '11 x 12s no alcanza 135')
    long_plan = plan_videos([100, 50])
    ok &= _check(long_plan['videos'] == 1 and long_plan['split_loops'] == 2
                 and all(135 <= s <= 195 for s in long_plan['video_secs']), f'tramos {long_plan}')
    ok &= _check(plan_videos([None, 0, 140])['videos'] == 1, 'ignora None/0')
    if not ok:
        return 1

    workdir = tempfile.mkdtemp(prefix='smoke_kit_analyze_')
    scratch = tempfile.mkdtemp(prefix='smoke_kit_scratch_')
    remote = os.path.join(workdir, 'remote')
    os.makedirs(remote)
    try:
        tree = {'/kits': [_Entry('Pack X', '/kits/x', True), _Entry('Pack Y', '/kits/y', True)],
                '/kits/x': [], '/kits/y': []}
        for i in range(12):  # 12 s de tono + 1 s de silencio + 4 s que se descartan
            name = f'L{i:02d}.wav'
            _write_wav(os.path.join(remote, f'x_{name}'), [(12, False), (1, True), (4, False)])
            tree['/kits/x'].append(_Entry(name, f'/kits/x/{name}'.lower()))
        _write_wav(os.path.join(remote, 'x_Preview.wav'), [(30, False)])
        tree['/kits/x'].append(_Entry('Preview.wav', '/kits/x/preview.wav'))
        _write_wav(os.path.join(remote, 'y_Solo.wav'), [(8, False), (1, True), (2, False)])
        tree['/kits/y'].append(_Entry('Solo.wav', '/kits/y/solo.wav'))

        def fake_download(paths, dest_dir, dbx=None):
            out = []
            for p in paths:
                parts = p.strip('/').split('/')  # kits/<x|y>/<archivo>
                src = next(os.path.join(remote, f) for f in os.listdir(remote)
                           if f.lower() == f'{parts[1]}_{parts[2]}'.lower())
                os.makedirs(dest_dir, exist_ok=True)
                dest = os.path.join(dest_dir, os.path.basename(p))
                shutil.copyfile(src, dest)
                out.append(dest)
            return out

        packs = kit_source.list_packs('/kits', dbx=FakeDbx(tree),
                                      scan=kit_source.scan_settings({'scan_folders': []}))
        if not resolve_tool('ffmpeg'):
            print('SKIP: sin ffmpeg, no se prueba el corte real')
            print('OK')
            return 0

        import tempfile as tf
        tf.tempdir = scratch  # el temp del análisis cae acá y tiene que quedar vacío

        def run(pack, dbx=None, max_loops=None):
            return analyze_pack(pack, dbx=dbx, max_loops=max_loops, download_fn=fake_download)

        results = analyze_all(packs, analyze_fn=run)
        by = {r['label']: r for r in results}
        x = by['pack-01']
        ok &= _check(x['loops_total'] == 12 and 'preview_file' not in x, f'pack-01 {x}')
        ok &= _check(all(abs(s - 12) < 0.5 for s in x['loop_preview_secs']), x['loop_preview_secs'])
        ok &= _check(x['videos']['videos'] == 1 and x['errors'] == 0, f"videos {x['videos']}")
        y = by['pack-02']
        ok &= _check(y['loops_total'] == 1, f'pack-02 {y}')
        ok &= _check('name' not in x, 'sin nombres por defecto')

        limited = analyze_all(packs, pack_filter='pack-01', max_loops=3, analyze_fn=run)
        ok &= _check(len(limited) == 1 and limited[0]['loops_analyzed'] == 3
                     and limited[0]['loops_total'] == 12, 'max-loops / --pack')
        ok &= _check(os.listdir(scratch) == [], f'temp sin borrar: {os.listdir(scratch)}')

        table = format_table(results)
        ok &= _check('pack-01' in table and 'Pack X' not in table and workdir not in table, 'tabla')
        out = os.path.join(workdir, 'analysis.json')
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({'packs': results}, f)
        ok &= _check('Pack X' not in open(out, encoding='utf-8').read(), 'JSON sin nombres')
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
        shutil.rmtree(scratch, ignore_errors=True)
    if ok:
        print('OK')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
