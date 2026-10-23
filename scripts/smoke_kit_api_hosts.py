#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: la config no decide a dónde va una clave ni de qué archivo sale (kit_llm / kit_art)."""

import os
import sys
import tempfile
import urllib.request

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_http
from core import kit_art, kit_cloud, kit_llm, kit_names

FAILS = []
KEY = 'SMOKE-SECRET-KEY'
_ENV = (kit_llm.ENV_HOSTS, kit_art.ENV_KEY, kit_names.ENV_LLM_KEY, *kit_cloud.ENV_VARS)


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _rejects(fn, exc, msg):
    try:
        fn()
        FAILS.append(msg)
    except exc as e:
        check(KEY not in str(e) and 'evil' not in str(e), f"{msg}: el error expone datos")


def _check_hosts():
    ok = kit_llm.check_base_url
    check(ok('https://api.openai.com/v1/') == 'https://api.openai.com/v1', "host fijo rechazado")
    check(ok('https://API.OpenAI.com:443/v1') == 'https://API.OpenAI.com:443/v1',
          "mayúsculas o puerto 443 rechazados")
    for bad in ('https://evil.example/v1', 'http://api.openai.com/v1',
                'https://api.openai.com.evil.example/v1', 'https://api.openai.com@evil.example/v1',
                'https://api.openai.com\\@evil.example/v1', 'https://evil.example#api.openai.com',
                'https://api.openai.com:8443/v1', 'https://api.openai.com /v1', 'https://', '', None):
        _rejects(lambda: ok(bad), kit_llm.KitLlmError, f"base_url aceptada: {bad!r}")
    # La lista solo se amplía desde el entorno.
    env = {kit_llm.ENV_HOSTS: ' Otro.Example , ,llm.example'}
    check(ok('https://otro.example/v1', env=env) == 'https://otro.example/v1'
          and ok('https://llm.example', env=env) and ok('https://api.openai.com/v1', env=env),
          "KIT_API_HOSTS no amplía la lista")
    _rejects(lambda: ok('https://evil.example/v1', env=env), kit_llm.KitLlmError,
             "host fuera de KIT_API_HOSTS aceptado")


def _check_no_network(tmp):
    """Con un host no permitido la clave no sale: ni LLM ni API de imágenes llaman a la red."""
    seen = []
    real = kit_http.open_request

    def spy(req, timeout=None):
        seen.append(req)
        raise OSError('sin red')
    ref = os.path.join(tmp, 'ref.png')
    Image.new('RGB', (8, 8)).save(ref)
    kit_http.open_request = spy
    try:
        _rejects(lambda: kit_llm.call('s', 'u', {'base_url': 'https://evil.example/v1',
                                                 'model': 'm'}, key=KEY),
                 kit_llm.KitLlmError, "el LLM aceptó un host no permitido")
        _rejects(lambda: kit_art.api_client('p', [ref], {'base_url': 'https://evil.example/v1'},
                                            key=KEY),
                 kit_art.KitArtError, "la API de imágenes aceptó un host no permitido")
        # Con la clave en el entorno y la config apuntando a otro host, for_pack cae al nombre
        # del pack sin mandar nada.
        os.environ[kit_names.ENV_LLM_KEY] = KEY
        name, _ = kit_names.for_pack('Kit', '/p/kit', {
            'genre': 'soul', 'base_url': 'https://evil.example/v1', 'model': 'm'}, store=None)
        check(name is None, "for_pack devolvió un nombre con un host no permitido")
        check(not seen, "con host no permitido igual se llamó a la red")
    finally:
        kit_http.open_request = real
        os.environ.pop(kit_names.ENV_LLM_KEY, None)


def _check_key_file(tmp):
    path = os.path.join(tmp, 'token.json')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(KEY + '\n')
    check(kit_llm.read_key({'key_file': path}) == KEY, "key_file local no se leyó")
    check(not kit_cloud.in_cloud(), "in_cloud sin variables")
    os.environ[kit_cloud.ENV_DROPBOX_TOKEN] = 'x'
    try:
        check(kit_cloud.in_cloud(), "in_cloud no detecta las variables KIT_*")
        # En la nube key_file no se lee: ni para el LLM ni para la API de imágenes.
        _rejects(lambda: kit_llm.read_key({'key_file': path}), kit_llm.KitLlmError,
                 "key_file leído en la nube")
        _rejects(lambda: kit_art._read_key({'key_file': path}), kit_art.KitArtError,
                 "key_file de imágenes leído en la nube")
        os.environ[kit_art.ENV_KEY] = KEY
        check(kit_art._read_key({'key_file': path}) == KEY, "la clave del entorno no se usa")
    finally:
        os.environ.pop(kit_cloud.ENV_DROPBOX_TOKEN, None)
        os.environ.pop(kit_art.ENV_KEY, None)


def main():
    saved = {name: os.environ.pop(name) for name in _ENV if name in os.environ}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for fn, args in ((_check_hosts, ()), (_check_no_network, (tmp,)),
                             (_check_key_file, (tmp,))):
                try:
                    fn(*args)
                except Exception as e:
                    FAILS.append(f"{fn.__name__} falló: {type(e).__name__}: {e}")
    finally:
        os.environ.update(saved)
    if FAILS:
        for msg in FAILS:
            print('FAIL:', msg)
        return 1
    print('OK: smoke_kit_api_hosts')
    return 0


if __name__ == '__main__':
    sys.exit(main())
