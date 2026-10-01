#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: tablas de Shorts (long_videos, transcripts, clips) en SQLite temporal."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import shorts_store as store


def main() -> int:
    db = os.path.join(tempfile.mkdtemp(), 'test_shorts.db')

    vid = store.upsert_video('C:/videos/tutorial largo.mp4', 'abc123', db_path=db,
                             duration_s=1800.0, canal='personal')
    if store.upsert_video('D:/otra/ruta.mp4', 'abc123', db_path=db) != vid:
        print("FAIL: dedupe por hash")
        return 1

    words = [{'t0': 0.0, 't1': 0.4, 'w': 'hola'}, {'t0': 0.5, 't1': 0.9, 'w': 'mundo'}]
    store.save_transcript(vid, 'small', 'es', words, db_path=db)
    store.save_transcript(vid, 'small', 'es', words, db_path=db)  # idempotente

    store.replace_clips(vid, [
        {'start': 10.0, 'end': 40.0, 'titulo': 'A', 'puntaje': 0.9},
        {'start': 60.0, 'end': 95.0, 'titulo': 'B', 'puntaje': 0.7},
    ], db_path=db)

    # Reabrir y leer
    video = store.get_video(vid, db_path=db)
    if video['path'] != 'D:/otra/ruta.mp4' or video['estado'] != 'importado':
        print("FAIL: video", video)
        return 1
    if store.get_transcript(vid, 'small', db_path=db) != words:
        print("FAIL: transcript roundtrip")
        return 1
    clips = store.list_clips(vid, db_path=db)
    if [c['titulo'] for c in clips] != ['A', 'B'] or clips[0]['start_modelo'] != 10.0:
        print("FAIL: clips", clips)
        return 1

    # Aprobado sobrevive a replace_clips
    with store.connect(db) as conn:
        conn.execute("UPDATE clips SET estado='aprobado' WHERE id = ?", (clips[0]['id'],))
    store.replace_clips(vid, [{'start': 5.0, 'end': 30.0, 'titulo': 'C'}], db_path=db)
    titles = [c['titulo'] for c in store.list_clips(vid, db_path=db)]
    if titles != ['C', 'A']:
        print("FAIL: replace_clips", titles)
        return 1

    # Borrar el video limpia transcripts y clips (FK ON)
    with store.connect(db) as conn:
        conn.execute("DELETE FROM long_videos WHERE id = ?", (vid,))
        left = conn.execute("SELECT (SELECT COUNT(*) FROM clips) + "
                            "(SELECT COUNT(*) FROM transcripts)").fetchone()[0]
    if left:
        print("FAIL: cascade", left)
        return 1

    print("OK smoke_shorts_schema")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
