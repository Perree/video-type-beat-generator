#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: kit_packs/kit_runs en SQLite temporal (upsert, cooldown, schema 2x)."""

import os
import sys
import tempfile
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_store as store


def main() -> int:
    db = os.path.join(tempfile.mkdtemp(), 'test_kits.db')

    store.ensure_schema(store.connect(db))
    store.ensure_schema(store.connect(db))

    path_a = '/kits/Pack A'
    id1 = store.upsert_pack(path_a, 'Pack A', db_path=db)
    id2 = store.upsert_pack(path_a, 'Pack A v2', db_path=db)
    if id1 != id2:
        print("FAIL: upsert duplicó el path", id1, id2)
        return 1
    with store.connect(db) as conn:
        n = conn.execute("SELECT COUNT(*) FROM kit_packs").fetchone()[0]
        nombre = conn.execute(
            "SELECT nombre FROM kit_packs WHERE id = ?", (id1,)).fetchone()[0]
    if n != 1 or nombre != 'Pack A v2':
        print("FAIL: upsert count/nombre", n, nombre)
        return 1

    path_10 = '/kits/Used10'
    path_40 = '/kits/Used40'
    id_10 = store.upsert_pack(path_10, 'Used10', db_path=db)
    id_40 = store.upsert_pack(path_40, 'Used40', db_path=db)
    now = datetime.now()
    t10 = (now - timedelta(days=10)).isoformat(timespec='seconds')
    t40 = (now - timedelta(days=40)).isoformat(timespec='seconds')
    with store.connect(db) as conn:
        conn.execute(
            "UPDATE kit_packs SET last_used_at = ? WHERE id = ?", (t10, id_10))
        conn.execute(
            "UPDATE kit_packs SET last_used_at = ? WHERE id = ?", (t40, id_40))

    recent = store.recent_pack_paths(30, db_path=db)
    if path_10 in recent:
        print("FAIL: pack de 10 días no debe estar en recent_pack_paths(30)", recent)
        return 1
    if path_40 not in recent:
        print("FAIL: pack de 40 días debe estar en recent_pack_paths(30)", recent)
        return 1

    run_id = store.record_run(
        id_40, db_path=db, audio_mode='assembled', canal='kits',
        loops_json=['a.wav', 'b.wav'], image_path='img/one.png',
        estado='rendered')
    if not run_id:
        print("FAIL: record_run id")
        return 1
    if store.last_run_at(id_40, db_path=db) is None:
        print("FAIL: last_run_at")
        return 1
    imgs = store.recent_images(id_40, limit=2, db_path=db)
    if imgs != ['img/one.png']:
        print("FAIL: recent_images", imgs)
        return 1
    other = store.upsert_pack('/kits/Other', 'Other', db_path=db)
    with store.connect(db) as conn:
        other_used = conn.execute(
            "SELECT last_used_at FROM kit_packs WHERE id = ?", (other,)
        ).fetchone()[0]
        used40 = conn.execute(
            "SELECT last_used_at FROM kit_packs WHERE id = ?", (id_40,)
        ).fetchone()[0]
    if other_used is not None:
        print("FAIL: record_run pisó last_used_at de otro pack")
        return 1
    if used40 is None:
        print("FAIL: last_used_at del pack de la corrida vacío")
        return 1

    print("OK smoke_kit_schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
