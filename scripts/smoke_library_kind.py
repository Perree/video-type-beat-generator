#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: import_beat y list_beats separan beat vs loop_kit (SQLite temporal)."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import library


def _dummy_audio(path: str, payload: bytes) -> None:
    with open(path, 'wb') as f:
        f.write(payload)


def main() -> int:
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, 'test_library.db')
    lib_beat = os.path.join(tmp, 'library')
    lib_kit = os.path.join(tmp, 'loop_kits')
    os.makedirs(lib_beat, exist_ok=True)
    os.makedirs(lib_kit, exist_ok=True)

    beat_file = os.path.join(tmp, 'one.wav')
    kit_file = os.path.join(tmp, 'two.wav')
    _dummy_audio(beat_file, b'beat-payload-a')
    _dummy_audio(kit_file, b'loop-kit-payload-b')

    id_beat, created_b = library.import_beat(
        beat_file, kind=library.KIND_BEAT, db_path=db_path, library_dir=lib_beat)
    id_kit, created_k = library.import_beat(
        kit_file, kind=library.KIND_LOOP_KIT, db_path=db_path, library_dir=lib_kit)
    if not created_b or not created_k:
        print("FAIL: imports should be new", created_b, created_k)
        return 1

    beats_only = library.list_beats(kind=library.KIND_BEAT, db_path=db_path)
    kits_only = library.list_beats(kind=library.KIND_LOOP_KIT, db_path=db_path)

    if len(beats_only) != 1 or beats_only[0]['id'] != id_beat:
        print("FAIL: beats list", beats_only)
        return 1
    if len(kits_only) != 1 or kits_only[0]['id'] != id_kit:
        print("FAIL: loop_kits list", kits_only)
        return 1
    if beats_only[0].get('kind') != library.KIND_BEAT:
        print("FAIL: beat kind column", beats_only[0].get('kind'))
        return 1
    if kits_only[0].get('kind') != library.KIND_LOOP_KIT:
        print("FAIL: kit kind column", kits_only[0].get('kind'))
        return 1

    same_src = os.path.join(tmp, 'shared.wav')
    _dummy_audio(same_src, b'same-bytes-for-both-kinds')
    id_b2, created_b2 = library.import_beat(
        same_src, kind=library.KIND_BEAT, db_path=db_path, library_dir=lib_beat)
    id_k2, created_k2 = library.import_beat(
        same_src, kind=library.KIND_LOOP_KIT, db_path=db_path, library_dir=lib_kit)
    if not created_b2 or not created_k2 or id_b2 == id_k2:
        print("FAIL: same hash should create two rows by kind", created_b2, created_k2, id_b2, id_k2)
        return 1
    found_b = library.find_beat_by_path(
        os.path.join(lib_beat, os.path.basename(same_src)),
        db_path=db_path, kind=library.KIND_BEAT)
    found_k = library.find_beat_by_path(
        os.path.join(lib_kit, os.path.basename(same_src)),
        db_path=db_path, kind=library.KIND_LOOP_KIT)
    if not found_b or found_b['id'] != id_b2:
        print("FAIL: find beat by path mixed kinds", found_b)
        return 1
    if not found_k or found_k['id'] != id_k2:
        print("FAIL: find kit by path mixed kinds", found_k)
        return 1

    print("OK smoke_library_kind")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
