#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: editar start_s/end_s no pisa start_modelo ni end_modelo."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import shorts_store as store


def main() -> int:
    db = os.path.join(tempfile.mkdtemp(), "test_clip_edit.db")
    vid = store.upsert_video(
        "C:/videos/tutorial.mp4", "hash-edit", db_path=db, duration_s=600.0)
    store.replace_clips(vid, [
        {"start": 10.0, "end": 40.0, "titulo": "Original", "puntaje": 0.8},
    ], db_path=db)
    clip = store.list_clips(vid, db_path=db)[0]
    modelo_ini = clip["start_modelo"]
    modelo_fin = clip["end_modelo"]
    if modelo_ini != 10.0 or modelo_fin != 40.0:
        print("FAIL: el modelo no quedó con el corte original", clip)
        return 1

    # start_modelo/end_modelo en kwargs tienen que ignorarse.
    store.update_clip(
        clip["id"], db_path=db,
        start_s=12.5, end_s=42.0, titulo="Editado",
        start_modelo=0.0, end_modelo=1.0,
    )
    again = store.get_clip(clip["id"], db_path=db)
    if again["start_s"] != 12.5 or again["end_s"] != 42.0 or again["titulo"] != "Editado":
        print("FAIL: no se guardó la edición", again)
        return 1
    if again["start_modelo"] != modelo_ini or again["end_modelo"] != modelo_fin:
        print("FAIL: se pisó el corte del modelo", again)
        return 1

    store.update_clip(clip["id"], db_path=db, estado="rechazado")
    left = store.list_clips(vid, db_path=db)
    if len(left) != 1 or left[0]["estado"] != "rechazado":
        print("FAIL: rechazar no debe borrar la fila", left)
        return 1
    if left[0]["start_modelo"] != modelo_ini:
        print("FAIL: rechazar pisó start_modelo", left[0])
        return 1

    print("OK smoke_clip_edit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
