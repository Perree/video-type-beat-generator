#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: kit_names (propose/pick/track_link), kit_llm sin red y video_name en el estado."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_cloud, kit_llm, kit_names, kit_state

# El host de ejemplo tiene que estar permitido para llegar al fallo de red simulado.
os.environ[kit_llm.ENV_HOSTS] = 'x.example'
for _name in kit_cloud.ENV_VARS:
    os.environ.pop(_name, None)

FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _fake(text):
    calls = []

    def llm(system, user):
        calls.append(user)
        return text
    llm.calls = calls
    return llm


def _check_propose():
    raw = "\n".join([
        "1. Sol Dorado", "- Brisa", "", "   ", "sol dorado", "SOL  DORADO",
        "Brisa.", "\"Nube\"", "Kit Alfa", "Uno Dos Tres", "Fuego!!", "Ámbar", "Ambar",
        "Costa Azul", "Reflejo", "Marea",
    ])
    llm = _fake(raw)
    got = kit_names.propose('Kit Alfa', 'reggaeton house', ['Brisa'], n=5, llm_call=llm)
    check(got == ['Sol Dorado', 'Nube', 'Ámbar', 'Costa Azul', 'Reflejo'],
          f"propose devolvió {got!r}")
    check(len(llm.calls) == 1 and 'reggaeton house' in llm.calls[0], "el prompt no lleva el género")
    check('Brisa' in llm.calls[0], "el prompt no lista los nombres usados")
    check(kit_names.propose('K', 'g', [], n=3, llm_call=_fake("A\nB")) == ['A', 'B'],
          "devolver menos de n debe ser válido")
    check(kit_names.propose('K', 'g', [], llm_call=_fake("\n \n")) == [], "respuesta vacía")
    check(kit_names.propose('K', 'g', [], n=0, llm_call=_fake("A")) == [], "n=0")
    check(kit_names.pick('Kit Alfa', 'g', ['Sol Dorado'],
                         llm_call=_fake("sol dorado\nKit Alfa\nBrisa")) == 'Brisa',
          "pick no eligió la primera válida")
    check(kit_names.pick('K', 'g', [], llm_call=_fake("")) is None, "pick sin opciones")


def _check_link():
    t = kit_names.track_link
    one = t('https://shop.example/p/abc', 'v1')
    check(one == 'https://shop.example/p/abc?utm_source=youtube&utm_content=v1', f"link simple {one!r}")
    two = t('https://shop.example/p/abc?ref=x&a=1#top', 'v1')
    check(two == 'https://shop.example/p/abc?ref=x&a=1&utm_source=youtube&utm_content=v1#top',
          f"link con query {two!r}")
    again = t(two, 'v2')
    check(again.count('utm_source=') == 1 and again.count('utm_content=') == 1
          and 'utm_content=v2' in again and 'ref=x' in again, f"doble pasada {again!r}")
    check(t('', 'v1') == '' and t('https://x.example/p', '') == 'https://x.example/p',
          "link o id vacío debe quedar igual")
    ids = {kit_names.new_tracking_id() for _ in range(50)}
    check(len(ids) == 50, "tracking ids repetidos")


def _check_llm():
    for cfg in ({}, {'base_url': 'http://x.example', 'model': 'm'}):
        try:
            kit_llm.call('s', 'u', cfg, key='SMOKE-SECRET-KEY')
            FAILS.append("cfg inválida no levantó error")
        except kit_llm.KitLlmError as e:
            check('SMOKE-SECRET-KEY' not in str(e), "el error expone la clave")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'k.txt')
        try:
            kit_llm.read_key({'key_file': path})
            FAILS.append("archivo de clave inexistente no levantó error")
        except kit_llm.KitLlmError as e:
            check(path not in str(e), "el error expone la ruta de la clave")
        with open(path, 'w', encoding='utf-8') as f:
            f.write('  SMOKE-SECRET-KEY \n')
        check(kit_llm.read_key({'key_file': path}) == 'SMOKE-SECRET-KEY', "read_key")
    # Fallo de red simulado: el mensaje no debe traer la clave.
    import urllib.request
    real = urllib.request.urlopen

    def boom(*a, **k):
        raise OSError('SMOKE-SECRET-KEY en el texto del error')
    urllib.request.urlopen = boom
    try:
        kit_llm.call('s', 'u', {'base_url': 'https://x.example/v1', 'model': 'm'},
                     key='SMOKE-SECRET-KEY')
        FAILS.append("un fallo de red no levantó error")
    except kit_llm.KitLlmError as e:
        check('SMOKE-SECRET-KEY' not in str(e), "el error de red expone la clave")
    finally:
        urllib.request.urlopen = real


def _check_state():
    store = {}

    def read_json_rev(path, dbx=None):
        return (json.loads(store[path]), 'rev') if path in store else (None, None)

    def write_json(path, data, rev=None, dbx=None):
        store[path] = json.dumps(data)
        return 'rev'
    real = (kit_cloud.read_json_rev, kit_cloud.write_json)
    kit_cloud.read_json_rev, kit_cloud.write_json = read_json_rev, write_json
    try:
        pid = kit_state.upsert_pack('/p/a', 'Kit Alfa', db_path='/s.json')
        kit_state.record_run(pid, db_path='/s.json', audio_mode='assembled',
                             youtube_id='yt123', video_name='Sol Dorado', tracking_id='t1',
                             basura='x')
        run = kit_state.load('/s.json')['runs'][0]
        check(run.get('video_name') == 'Sol Dorado' and run.get('youtube_id') == 'yt123'
              and run.get('tracking_id') == 't1' and run['pack_id'] == pid,
              "la corrida no guarda nombre, youtube_id y kit")
        check('basura' not in run, "campo desconocido se coló en la corrida")
    finally:
        kit_cloud.read_json_rev, kit_cloud.write_json = real


def main():
    for fn in (_check_propose, _check_link, _check_llm, _check_state):
        try:
            fn()
        except Exception as e:
            FAILS.append(f"{fn.__name__} falló: {type(e).__name__}: {e}")
    if FAILS:
        for msg in FAILS:
            print('FAIL:', msg)
        return 1
    print('OK: smoke_kit_names')
    return 0


if __name__ == '__main__':
    sys.exit(main())
