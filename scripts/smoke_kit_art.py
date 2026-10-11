#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: kit_art (referencias sin repetir en 30 días, fallback manual, prompt sin nombres propios)."""

import base64
import io
import json
import os
import random
import re
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import dropbox_client, kit_art, kit_cloud, kit_llm, kit_state

# El host de ejemplo tiene que estar permitido para probar el cliente de la API.
os.environ[kit_llm.ENV_HOSTS] = 'img.example'
for _name in kit_cloud.ENV_VARS:
    os.environ.pop(_name, None)

FAILS = []
NOW = datetime(2026, 3, 20, 12, 0, 0)
KEY = 'SMOKE-SECRET-KEY'
KIT = 'Luna Brava'
ROOT_REFS = '/kits/_referencias'
FOLDER = ROOT_REFS + '/reggaeton_house'
REF_NAMES = ['Zafiro_Morales_01.jpg', 'Zafiro_Morales_02.png', 'Tormenta_03.webp',
             'Tormenta_04.jpg']
REFS = [{'name': n, 'path': f'{FOLDER}/{n}'} for n in REF_NAMES]
PROPER_WORDS = ('luna', 'brava', 'zafiro', 'morales', 'tormenta')


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _png(color=(120, 60, 30), size=(64, 48)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


def _ago(days):
    return (NOW - timedelta(days=days)).isoformat(timespec='seconds')


def _fake_client(fail=None):
    calls = []

    def client(prompt, image_paths, cfg):
        calls.append({'prompt': prompt, 'paths': list(image_paths),
                      'ok': all(os.path.exists(p) for p in image_paths),
                      'sizes': [Image.open(p).size for p in image_paths]})
        if fail:
            raise fail
        return _png()
    client.calls = calls
    return client


def _fetch(paths, dest_dir):
    os.makedirs(dest_dir, exist_ok=True)
    out = []
    for path in paths:
        local = os.path.join(dest_dir, os.path.basename(path))
        Image.new('RGB', (3000, 2000), (10, 80, 160)).save(local)
        out.append(local)
    return out


def _check_refs():
    p = [r['path'] for r in REFS]
    used = {p[0]: _ago(5), p[1]: _ago(29), p[2]: _ago(31)}
    sizes = set()
    for seed in range(40):
        chosen, warnings = kit_art.choose_refs(REFS, used, random.Random(seed), now=NOW)
        sizes.add(len(chosen))
        check(set(chosen) <= {p[2], p[3]}, f"eligió una referencia usada hace menos de 30 días (seed {seed})")
        check(not warnings, "warning sin haber relajado la regla")
    check(sizes == {1, 2}, f"debe elegir 1 o 2 referencias, eligió {sorted(sizes)}")
    chosen, _ = kit_art.choose_refs(REFS, {**used, p[2]: _ago(3)}, random.Random(1), now=NOW)
    check(chosen == [p[3]], "con una sola libre debe ir esa sola")
    # Ninguna libre: se relaja con warning y va la más antigua.
    all_used = {p[0]: _ago(5), p[1]: _ago(29), p[2]: _ago(12), p[3]: _ago(1)}
    chosen, warnings = kit_art.choose_refs(REFS, all_used, random.Random(1), now=NOW)
    check(chosen == [p[1]] and len(warnings) == 1, "no relajó con warning hacia la más antigua")
    check(not any(w in warnings[0].lower() for w in PROPER_WORDS), "el warning nombra una referencia")
    try:
        kit_art.choose_refs([], {}, random.Random(1), now=NOW)
        FAILS.append("sin referencias debe fallar")
    except kit_art.KitArtError:
        pass
    # Simulación: 3 videos por semana durante 8 semanas, guardando el uso en el estado.
    state, last, relaxed = {'runs': []}, {}, 0
    many = [f'{FOLDER}/ref_{i:02d}.jpg' for i in range(14)]
    rng = random.Random(7)
    for week in range(8):
        for video in range(3):
            day = NOW + timedelta(days=7 * week + video)
            chosen, warnings = kit_art.choose_refs(many, kit_art.used_refs(state), rng, now=day)
            relaxed += bool(warnings)
            for path in chosen:
                if path in last and not warnings:
                    check((day - last[path]).days >= 30, "repitió una referencia dentro de 30 días")
                last[path] = day
            state['runs'].append({'subido_en': day.isoformat(timespec='seconds'),
                                  'ref_images': chosen})
    check(relaxed > 0, "la simulación debía agotar las referencias al menos una vez")


def _check_prompt():
    kit = {'name': KIT, 'motifs': ['Luna Brava skyline', 'Neon Palms', 'tape hiss 1998!']}
    cfg = {'banned_words': ['Tormenta'],
           'styles': {'Reggaeton House': {'palette': 'Brava blue, warm orange',
                                          'motifs': ['palm silhouettes', 'tormenta sky']}}}
    prompt = kit_art.build_prompt(kit, 'reggaeton_house', cfg)
    low = prompt.lower()
    for word in PROPER_WORDS:
        check(not re.search(r'\b%s\b' % word, low), f"el prompt contiene la palabra {word!r}")
    check('neon palms' in low and 'palm silhouettes' in low and 'warm orange' in low,
          "el prompt perdió la estética configurada")
    check('1998' not in prompt, "el prompt dejó pasar números de un motivo")
    # Ninguna palabra en mayúscula fuera del inicio de oración (no hay nombres propios).
    for sentence in re.split(r'(?<=[.:])\s+', prompt):
        for word in sentence.split()[1:]:
            check(not word[:1].isupper(), f"palabra con mayúscula en el prompt: {word!r}")
    for needle in ('no text', 'no people', 'likeness', 'film grain', 'bokeh'):
        check(needle in low, f"al prompt le falta {needle!r}")
    for genre in ('reggaeton house', 'guitarras melodicas', 'otro genero'):
        low = kit_art.build_prompt(KIT, genre).lower()
        check(not any(re.search(r'\b%s\b' % w, low) for w in PROPER_WORDS),
              f"el prompt de {genre!r} contiene un nombre propio")
    check(kit_art.build_prompt(KIT, 'guitarras melodicas') != kit_art.build_prompt(KIT, 'otro genero'),
          "el género no cambia la estética")


def _check_background(tmp):
    client = _fake_client()
    report = {}
    out = kit_art.background(KIT, 'reggaeton house', REFS, {}, random.Random(3), client,
                             out_dir=os.path.join(tmp, 'bg'), now=NOW, fetch=_fetch, report=report)
    check(os.path.exists(out) and Image.open(out).size == (64, 48), "background no dejó la imagen")
    check(len(client.calls) == 1, "debe haber un solo pedido por video")
    call = client.calls[0]
    check(call['ok'] and 1 <= len(call['paths']) <= 2, "el cliente no recibió 1-2 referencias locales")
    check(all(max(s) <= 1536 for s in call['sizes']), "las referencias no se achicaron")
    check(not any(os.path.exists(p) for p in call['paths']), "las referencias temporales no se borraron")
    check(not any(w in os.path.basename(p).lower() for p in call['paths'] for w in PROPER_WORDS),
          "el archivo enviado conserva el nombre de la referencia")
    check(not any(w in call['prompt'].lower() for w in PROPER_WORDS), "el prompt lleva un nombre propio")
    check(set(report['refs']) <= {r['path'] for r in REFS} and report['prompt'] == call['prompt'],
          "report no informa las referencias usadas")
    try:
        kit_art.background(KIT, 'g', REFS, {}, random.Random(3), lambda *a: b'no es una imagen',
                           out_dir=tmp, now=NOW, fetch=_fetch)
        FAILS.append("una respuesta que no es imagen debe fallar")
    except kit_art.KitArtError:
        pass


class _Store:
    def __init__(self, usage=None):
        self.usage = usage or {}

    def ref_usage(self):
        return self.usage


def _check_for_video(tmp):
    fallback = os.path.join(tmp, 'manual.png')
    Image.new('RGB', (10, 10)).save(fallback)
    real = (dropbox_client.list_folder_entries, dropbox_client.download)
    listed = []

    def list_folder_entries(path='', dbx=None):
        listed.append(path)
        if path != FOLDER:
            raise RuntimeError('not_found ' + path)
        return ([{'name': 'sub', 'path': FOLDER + '/sub', 'is_folder': True},
                 {'name': 'loop.wav', 'path': FOLDER + '/loop.wav', 'is_folder': False}]
                + [dict(r, is_folder=False) for r in REFS])

    def download(dropbox_path, dest_dir, dbx=None):
        return _fetch([dropbox_path], dest_dir)[0]
    dropbox_client.list_folder_entries, dropbox_client.download = list_folder_entries, download
    cfg = {'cover_mode': 'auto', 'art': {'refs_root': ROOT_REFS + '/'},
           'names': {'genre': 'Reggaeton House'}}
    try:
        sent = []
        # Manual (o sin la clave): no se llama a nada.
        for kit_cfg in ({}, {'cover_mode': 'manual', 'art': cfg['art']}, None):
            client = _fake_client()
            got = kit_art.for_video(kit_cfg, KIT, fallback, _Store(), random.Random(1), tmp,
                                    client=client, notify=sent.append, now=NOW)
            check(got == (fallback, []) and not client.calls, "el modo manual llamó a la API")
        check(not listed and not sent, "el modo manual tocó Dropbox o Telegram")
        check([kit_art.mode({'cover_mode': m}) for m in ('manual', 'auto', 'Template', 'otro', '')]
              == ['manual', 'auto', 'template', 'manual', 'manual'], "mode no reconoce los modos")
        # for_cover en manual y auto es for_video más "completa" en falso (pasa por el compositor).
        got = kit_art.for_cover({'cover_mode': 'manual'}, KIT, 'Titulo', fallback, _Store(),
                                random.Random(1), tmp, client=_fake_client(), notify=sent.append,
                                now=NOW)
        check(got == (fallback, [], False) and not listed and not sent,
              "for_cover cambió el modo manual")

        # Auto: fondo generado, sin repetir lo usado hace menos de 30 días.
        p = [r['path'] for r in REFS]
        store = _Store({p[0]: _ago(2), p[1]: _ago(10), p[2]: _ago(20)})
        client = _fake_client()
        path, refs = kit_art.for_video(cfg, KIT, fallback, store, random.Random(1),
                                       os.path.join(tmp, 'auto'), client=client,
                                       notify=sent.append, now=NOW)
        check(path != fallback and os.path.exists(path), "auto no devolvió el fondo generado")
        again = _fake_client()
        got = kit_art.for_cover(cfg, KIT, 'Titulo', fallback, store, random.Random(1),
                                os.path.join(tmp, 'auto2'), client=again, notify=sent.append,
                                now=NOW)
        check(got[1] == refs and got[2] is False and len(again.calls) == 1
              and 'titulo' not in again.calls[0]['prompt'].lower(),
              "for_cover cambió el modo auto (el título no va al prompt del fondo)")
        listed.remove(FOLDER)
        check(refs == [p[3]], f"auto no eligió la única referencia libre: {refs!r}")
        check(listed == [FOLDER] and not sent, "auto no listó la carpeta del género o avisó de más")

        # Rechazo y fallo: cae a manual, avisa una vez y no levanta.
        for fail, word in ((kit_art.KitArtRejected('x ' + KEY), 'rechazado'),
                           (OSError(KEY + ' ' + KIT), 'OSError')):
            sent.clear()
            client = _fake_client(fail)
            got = kit_art.for_video(cfg, KIT, fallback, _Store(), random.Random(1), tmp,
                                    client=client, notify=sent.append, now=NOW)
            check(got == (fallback, []), f"ante {word} no cayó a la imagen manual")
            check(len(client.calls) == 1, f"ante {word} hubo reintentos")
            check(len(sent) == 1 and word in sent[0], f"ante {word} no avisó por Telegram")
            check(sent and KEY not in sent[0] and not any(w in sent[0].lower() for w in PROPER_WORDS),
                  "el aviso expone la clave o un nombre")

        # Carpeta inexistente, género sin config y Telegram caído: también manual, sin levantar.
        def broken(text):
            raise RuntimeError(KEY)
        for kit_cfg in ({'cover_mode': 'auto', 'art': {'refs_root': '/otra', 'genre': 'x'}},
                        {'cover_mode': 'auto', 'art': {'refs_root': ROOT_REFS}},
                        {'cover_mode': 'AUTO'}):
            client = _fake_client()
            got = kit_art.for_video(kit_cfg, KIT, fallback, _Store(), random.Random(1), tmp,
                                    client=client, notify=broken, now=NOW)
            check(got == (fallback, []) and not client.calls, "config incompleta no cayó a manual")
    finally:
        dropbox_client.list_folder_entries, dropbox_client.download = real


def _check_api(tmp):
    ref = os.path.join(tmp, 'Zafiro_Morales_01.png')
    Image.new('RGB', (8, 8)).save(ref)
    cfg = {'base_url': 'https://img.example/v1/', 'model': 'modelo-x', 'size': '512x512'}
    real = urllib.request.urlopen
    seen = []

    class _Resp:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return self.payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def ok(req, timeout=None):
        seen.append(req)
        return _Resp(json.dumps({'data': [{'b64_json': base64.b64encode(_png()).decode()}]}).encode())

    def rejected(req, timeout=None):
        seen.append(req)
        raise urllib.error.HTTPError(req.full_url, 400, KEY + ' moderation', {}, io.BytesIO(KEY.encode()))

    def server_error(req, timeout=None):
        seen.append(req)
        raise urllib.error.HTTPError(req.full_url, 500, KEY, {}, io.BytesIO(b''))

    def boom(req, timeout=None):
        seen.append(req)
        raise OSError(KEY + ' en el texto del error')

    try:
        urllib.request.urlopen = ok
        data = kit_art.api_client('solo estetica', [ref, ref], cfg, key=KEY)
        check(Image.open(io.BytesIO(data)).size == (64, 48), "api_client no devolvió la imagen")
        req = seen[0]
        check(req.full_url == 'https://img.example/v1/images/edits', "URL de edición incorrecta")
        check(req.get_header('Authorization') == 'Bearer ' + KEY, "la clave no va en Authorization")
        body = req.data
        check(b'solo estetica' in body and b'modelo-x' in body and b'512x512' in body,
              "el pedido no lleva prompt, modelo y tamaño")
        check(body.count(b'name="image[]"') == 2, "las referencias no van como entrada de edición")
        check(b'Zafiro' not in body and KEY.encode() not in body,
              "el cuerpo lleva el nombre del archivo o la clave")
        for fake, kind in ((rejected, kit_art.KitArtRejected), (server_error, kit_art.KitArtError),
                           (boom, kit_art.KitArtError)):
            urllib.request.urlopen = fake
            seen.clear()
            try:
                kit_art.api_client('p', [ref], cfg, key=KEY)
                FAILS.append(f"{fake.__name__} no levantó error")
            except kit_art.KitArtError as e:
                check(type(e) is kind, f"{fake.__name__} levantó {type(e).__name__}")
                check(KEY not in str(e) and e.__cause__ is None, "el error de la API expone la clave")
            check(len(seen) == 1, f"{fake.__name__}: hubo reintentos")
        billable = {}
        for code in (400, 401, 429, 500, 503):
            def http_error(req, timeout=None, code=code):
                raise urllib.error.HTTPError(req.full_url, code, KEY, {}, io.BytesIO(b''))
            urllib.request.urlopen = http_error
            try:
                kit_art.api_client('p', [ref], cfg, key=KEY)
            except kit_art.KitArtError as e:
                billable[code] = e.billable
        check(billable == {400: False, 401: False, 429: False, 500: True, 503: True},
              f"qué errores HTTP cuentan como cobrados: {billable}")
        urllib.request.urlopen = boom
        try:
            kit_art.api_client('p', [ref], cfg, key=KEY)
        except kit_art.KitArtError as e:
            check(e.billable is True, "un timeout debe contarse como cobrado")
        urllib.request.urlopen = ok
        seen.clear()
        kit_art.api_client('p', [ref], {**cfg, 'n': 'x', 'input_fidelity': 'high'}, key=KEY)
        check(b'name="n"\r\n\r\n1\r\n' in seen[0].data and b'input_fidelity' in seen[0].data,
              "n inválido debe ser 1 e input_fidelity va solo si se configura")
        check(b'input_fidelity' not in body, "el modo auto manda input_fidelity sin pedirlo")
        seen.clear()
        for bad in ({'base_url': 'http://img.example/v1'}, {'base_url': 'ftp://x'}):
            try:
                kit_art.api_client('p', [ref], bad, key=KEY)
                FAILS.append("base_url sin https aceptada")
            except kit_art.KitArtError as e:
                check(KEY not in str(e), "el error de config expone la clave")
        check(not seen, "con base_url inválida igual se llamó a la red")
        old = os.environ.pop(kit_art.ENV_KEY, None)
        try:
            kit_art.api_client('p', [ref], cfg)
            FAILS.append("sin clave debe fallar")
        except kit_art.KitArtError:
            pass
        finally:
            if old is not None:
                os.environ[kit_art.ENV_KEY] = old
        check(not seen, "sin clave igual se llamó a la red")
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
        pid = kit_state.upsert_pack('/p/a', 'Kit', db_path='/s.json')
        kit_state.record_run(pid, db_path='/s.json', audio_mode='assembled', youtube_id='yt1',
                             subido_en=_ago(40), ref_images=['/r/1.jpg', '/r/2.jpg'])
        kit_state.record_run(pid, db_path='/s.json', audio_mode='assembled', youtube_id='yt2',
                             subido_en=_ago(3), ref_images=['/r/2.jpg'])
        kit_state.record_run(pid, db_path='/s.json', audio_mode='assembled', youtube_id='yt3')
        state = kit_state.load('/s.json')
        check(state['runs'][0].get('ref_images') == ['/r/1.jpg', '/r/2.jpg']
              and state['runs'][0].get('youtube_id') == 'yt1',
              "la corrida no guarda qué referencias usó el video")
        check('ref_images' not in state['runs'][2], "una corrida sin IA no debe guardar referencias")
        usage = kit_art.used_refs(state)
        check(usage == {'/r/1.jpg': _ago(40), '/r/2.jpg': _ago(3)}, f"used_refs devolvió {usage!r}")
        chosen, _ = kit_art.choose_refs(['/r/1.jpg', '/r/2.jpg'], usage, random.Random(0), now=NOW)
        check(chosen == ['/r/1.jpg'], "el uso guardado en el estado no frena la repetición")
    finally:
        kit_cloud.read_json_rev, kit_cloud.write_json = real


def main():
    with tempfile.TemporaryDirectory() as tmp:
        for fn, args in ((_check_refs, ()), (_check_prompt, ()), (_check_background, (tmp,)),
                         (_check_for_video, (tmp,)), (_check_api, (tmp,)), (_check_state, ())):
            try:
                fn(*args)
            except Exception as e:
                FAILS.append(f"{fn.__name__} falló: {type(e).__name__}: {e}")
    if FAILS:
        for msg in FAILS:
            print('FAIL:', msg)
        return 1
    print('OK: smoke_kit_art')
    return 0


if __name__ == '__main__':
    sys.exit(main())
