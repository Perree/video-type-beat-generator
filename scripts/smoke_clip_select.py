#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: clip_select (prompt, reparación de JSON, validación, snap, reintento). Sin red."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import clip_select as cs
from core import shorts_store as store

FIXTURE = os.path.join(ROOT, 'scripts', 'fixtures', 'transcript_sample.json')
CFG = {'clip_min_s': 20, 'clip_max_s': 60, 'clip_count': 6, 'language': 'es'}


def fail(msg, *extra):
    print("FAIL:", msg, *extra)
    return 1


def cuts_a_word(words, t):
    return any(w['t0'] + 1e-6 < t < w['t1'] - 1e-6 for w in words)


def main() -> int:
    with open(FIXTURE, encoding='utf-8') as f:
        fx = json.load(f)
    words, duration = fx['words'], fx['duration']
    phrases = cs.group_phrases(words)

    # Prompt: solo texto con timestamps, sin rutas
    system, user = cs.build_prompt(words, CFG, duration)
    if '[' not in user or 'Formato de respuesta' not in user or '.mp4' in user or ':\\' in user:
        return fail("prompt")

    # Clip ~25 s que empieza a mitad de la primera palabra y termina a mitad de una palabra
    a = phrases[0][0]
    target_end = a + 25
    mid_word = next(w for w in words if w['t0'] < target_end < w['t1'] or w['t0'] > target_end)
    raw_start = a + 0.2
    raw_end = mid_word['t0'] + (mid_word['t1'] - mid_word['t0']) / 2
    good = {'start': raw_start, 'end': raw_end, 'titulo': 'Tip de mezcla',
            'gancho': 'g', 'motivo': 'm', 'puntaje': 0.9}
    short = {'start': 30.0, 'end': 35.0, 'titulo': 'Muy corto', 'puntaje': 0.8}
    fenced = "Claro, aquí tienes:\n```json\n" + json.dumps({'clips': [good, short]}) + "\n```\nSuerte."

    # 1) Fences markdown se reparan
    data = cs.parse_and_repair(fenced)
    if len(data['clips']) != 2:
        return fail("fences", data)

    # 2) Clip de 5 s se rechaza
    valid, warns = cs.validate_clips(data, duration, CFG)
    if [c['titulo'] for c in valid] != ['Tip de mezcla'] or not warns:
        return fail("validación 5 s", valid, warns)

    # 3) Snap no corta palabras
    snapped = cs.snap_to_words(valid[0], words, CFG)
    if snapped is None:
        return fail("snap devolvió None")
    if cuts_a_word(words, snapped['start']) or cuts_a_word(words, snapped['end']):
        return fail("snap corta una palabra", snapped)
    if abs(snapped['start'] - raw_start) > 0.6 or abs(snapped['end'] - raw_end) > 0.6:
        return fail("snap se movió de más", snapped)
    far = {**valid[0], 'start': phrases[0][0] - 5.0}
    if cs.snap_to_words(far, words, CFG) is not None:
        return fail("snap lejos de toda palabra debía descartarse")

    # 4) JSON roto: error y NO borra clips aprobados; luego un reintento exitoso
    db = os.path.join(tempfile.mkdtemp(), 'smoke_clip_select.db')
    vid = store.upsert_video('x.mp4', 'h1', db_path=db, duration_s=duration)
    store.replace_clips(vid, [{'start': 1.0, 'end': 25.0, 'titulo': 'Aprobado'}], db_path=db)
    with store.connect(db) as conn:
        conn.execute("UPDATE clips SET estado='aprobado'")

    try:
        cs.select_clips(words, vid, CFG, duration, db_path=db,
                        llm_call=lambda s, u: "esto no es json {{{")
        return fail("JSON roto no lanzó error")
    except cs.ClipSelectError:
        pass
    titles = [c['titulo'] for c in store.list_clips(vid, db_path=db)]
    if titles != ['Aprobado']:
        return fail("clips tocados tras fallo", titles)

    calls = []

    def flaky(s, u):
        calls.append(u)
        return "basura" if len(calls) == 1 else fenced

    clips, _ = cs.select_clips(words, vid, CFG, duration, db_path=db, llm_call=flaky)
    if len(calls) != 2 or 'no sirvió' not in calls[1]:
        return fail("reintento", len(calls))
    rows = store.list_clips(vid, db_path=db)
    states = {r['titulo']: r['estado'] for r in rows}
    if states != {'Aprobado': 'aprobado', 'Tip de mezcla': 'propuesto'} or len(clips) != 1:
        return fail("persistencia", states)

    # 5) Sin clave: ClipSelectError claro; export/import manual funciona
    try:
        cs.select_clips(words, vid, {**CFG, 'llm': {'api_key_file': 'no/existe.txt'}},
                        duration, db_path=db)
        return fail("sin clave no lanzó error")
    except cs.ClipSelectError:
        pass
    prompt_path = os.path.join(tempfile.mkdtemp(), 'prompt.txt')
    cs.export_prompt(words, CFG, prompt_path, duration)
    resp_path = os.path.join(os.path.dirname(prompt_path), 'resp.json')
    with open(resp_path, 'w', encoding='utf-8') as f:
        f.write(fenced)
    cs.import_response(resp_path, words, vid, CFG, duration, db_path=db)
    if not os.path.getsize(prompt_path):
        return fail("export_prompt vacío")

    # 6) Poca voz: no se llama al LLM
    try:
        cs.build_prompt(words[:5], CFG)
        return fail("pocas palabras no lanzó error")
    except cs.ClipSelectError:
        pass

    print("OK smoke_clip_select")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
