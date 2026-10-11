#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: portada por plantilla + fondo (kit_template_art) y tope de gasto (kit_spend).

Sin red: cliente de imágenes, verificación y Dropbox falsos. Datos ficticios.
"""

import contextlib
import io
import json
import os
import random
import re
import sys
import tempfile
import urllib.request
from datetime import datetime, timedelta

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import (kit_art, kit_catalog, kit_cloud, kit_cover, kit_llm, kit_names, kit_settings,
                  kit_spend, kit_state, kit_template_art)

os.environ[kit_llm.ENV_HOSTS] = 'img.example'
for _name in kit_cloud.ENV_VARS:
    os.environ.pop(_name, None)

FAILS = []
NOW = datetime(2026, 3, 20, 12, 0, 0)
KEY = 'SMOKE-SECRET-KEY-77'
TITLE = 'Noche  Rara #7 (vol. 2)'
GENRE = 'Genero Smoke'
REFS_ROOT = '/kits/_referencias'
FOLDER = REFS_ROOT + '/genero_smoke'
MODEL = FOLDER + '/modelo.png'
BG_NAMES = ['Persona_Famosa_01.jfif', 'Persona_Famosa_02.jpg', 'calle_03.webp', 'calle_04.png']
BGS = [{'name': n, 'path': f'{FOLDER}/fondos/{n.lower()}'} for n in BG_NAMES]
PRIVATE = ('persona', 'famosa', 'noche', 'rara')
OUT = io.StringIO()   # todo lo que imprimen los módulos


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _png(color=(120, 60, 30), size=(96, 96)):
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'PNG')
    return buf.getvalue()


def _ago(days):
    return (NOW - timedelta(days=days)).isoformat(timespec='seconds')


def _fetch(paths, dest_dir):
    """Descarga falsa: el .jfif y el .jpg llegan como JPEG, el resto como PNG o WEBP."""
    os.makedirs(dest_dir, exist_ok=True)
    out = []
    for path in paths:
        local = os.path.join(dest_dir, os.path.basename(path))
        fmt = {'.jfif': 'JPEG', '.jpg': 'JPEG', '.webp': 'WEBP'}.get(
            os.path.splitext(path)[1].lower(), 'PNG')
        Image.new('RGB', (2400, 1800), (10, 80, 160)).save(local, fmt)
        out.append(local)
    return out


def _client(fail=None, fail_from=1):
    """Cliente de imágenes falso; ``fail`` se levanta desde la llamada ``fail_from``."""
    calls = []

    def client(prompt, image_paths, cfg):
        calls.append({'prompt': prompt, 'names': [os.path.basename(p) for p in image_paths],
                      'formats': [Image.open(p).format for p in image_paths],
                      'sizes': [Image.open(p).size for p in image_paths], 'cfg': dict(cfg)})
        if fail and len(calls) >= fail_from:
            raise fail
        return _png((len(calls) * 40 % 255, 60, 30))
    client.calls = calls
    return client


def _verifier(*answers):
    """Verificación falsa: devuelve ``answers`` en orden (la última se repite)."""
    calls = []

    def verify(path, cfg):
        calls.append(os.path.exists(path))
        answer = answers[min(len(calls), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer
    verify.calls = calls
    return verify


class _Store:
    """Estado mínimo en memoria con el gasto del mes y el uso de los fondos."""

    def __init__(self, usage=None, spent=0.0, fail_write=False):
        self.usage = usage or {}
        self.state = {}
        self.fail_write = fail_write
        if spent:
            kit_spend.record(self.state, kit_spend.month_key(NOW), spent)

    def ref_usage(self):
        return self.usage

    def spend_month(self, month):
        return kit_spend.spent(self.state, month)

    def add_spend(self, month, usd, images=0, verifications=0):
        if self.fail_write:
            raise RuntimeError(KEY)
        return kit_spend.record(self.state, month, usd, images, verifications)


def _budget(store=None, **cfg):
    return kit_spend.Budget({**kit_spend.DEFAULTS, **cfg}, store, NOW)


# --- Fondo sin repetir en 30 días ---

def _check_background():
    p = [b['path'] for b in BGS]
    used = {p[0]: _ago(3), p[1]: _ago(29), p[2]: _ago(31)}
    for seed in range(30):
        client, report = _client(), {}
        with tempfile.TemporaryDirectory() as tmp:
            kit_template_art.cover(TITLE, MODEL, BGS, used, random.Random(seed), client,
                                   out_dir=tmp, now=NOW, fetch=_fetch, report=report,
                                   budget=_budget(), verify=_verifier(TITLE))
        check(len(report['refs']) == 1 and report['refs'][0] in (p[2], p[3]),
              f"eligió un fondo usado hace menos de 30 días (seed {seed})")
        check(not report['warnings'], "warning sin haber relajado la regla")
    # Todos usados: se relaja con warning hacia el más antiguo.
    report = {}
    with tempfile.TemporaryDirectory() as tmp:
        kit_template_art.cover(TITLE, MODEL, BGS, {**used, p[2]: _ago(9), p[3]: _ago(1)},
                               random.Random(1), _client(), out_dir=tmp, now=NOW, fetch=_fetch,
                               report=report, budget=_budget(), verify=_verifier(TITLE))
    check(report['refs'] == [p[1]] and len(report['warnings']) == 1,
          "sin fondos libres no relajó con warning hacia el más antiguo")
    check(not any(w in report['warnings'][0].lower() for w in PRIVATE),
          "el warning nombra un fondo")
    # Simulación con el estado: 3 videos por semana, 8 semanas, 10 fondos.
    state, last, relaxed = {'runs': []}, {}, 0
    many = [{'name': f'f{i}.jpg', 'path': f'{FOLDER}/fondos/f{i:02d}.jpg'} for i in range(10)]
    rng = random.Random(5)
    for week in range(8):
        for video in range(3):
            day, report = NOW + timedelta(days=7 * week + video), {}
            with tempfile.TemporaryDirectory() as tmp:
                kit_template_art.cover(TITLE, MODEL, many, kit_art.used_refs(state), rng,
                                       _client(), out_dir=tmp, now=day, fetch=_fetch,
                                       report=report, budget=_budget(max_images_per_run=99),
                                       verify=_verifier(TITLE))
            path = report['refs'][0]
            relaxed += bool(report['warnings'])
            if path in last and not report['warnings']:
                check((day - last[path]).days >= 30, "repitió un fondo dentro de 30 días")
            last[path] = day
            state['runs'].append({'subido_en': day.isoformat(timespec='seconds'),
                                  'ref_images': report['refs']})
    check(relaxed > 0, "la simulación debía agotar los fondos al menos una vez")


# --- Prompt y pedido ---

def _check_prompt(tmp):
    default = kit_template_art.DEFAULT_PROMPT
    check(default.count(kit_template_art.MARKER) == 1, "el prompt por defecto no trae {titulo}")
    for sentence in re.split(r'(?<=[.:])\s+', default.replace(kit_template_art.MARKER, 'x')):
        for word in sentence.split()[1:]:
            check(not word[:1].isupper(),
                  f"palabra con mayúscula (¿nombre propio?) en el prompt: {word!r}")
    low = default.lower()
    for needle in ('imagen 1', 'imagen 2', 'tipografía', 'código de barras', 'exacto',
                   'marcas de agua', 'cuadrada'):
        check(needle in low, f"al prompt por defecto le falta {needle!r}")

    client, report = _client(), {}
    out = kit_template_art.cover(TITLE, MODEL, BGS, {}, random.Random(2), client,
                                 out_dir=os.path.join(tmp, 'ok'), now=NOW, fetch=_fetch,
                                 report=report, budget=_budget(), verify=_verifier(TITLE))
    call = client.calls[0]
    check(len(client.calls) == 1, "un título bien leído no debe reintentar")
    check(TITLE in call['prompt'] and call['prompt'] == default.replace('{titulo}', TITLE),
          "el título no llegó al prompt sin cambios")
    check(call['names'] == ['img0.png', 'img1.png'] and call['formats'] == ['PNG', 'PNG'],
          f"no se mandaron dos PNG con nombre genérico: {call['names']} {call['formats']}")
    check(all(max(s) <= 1536 for s in call['sizes']), "las imágenes no se achicaron")
    cfg = call['cfg']
    check((cfg['model'], cfg['size'], cfg['quality'], cfg['input_fidelity'], cfg['n'])
          == ('gpt-image-1', '1024x1024', 'high', 'high', 1), "parámetros por defecto distintos")
    check(os.path.exists(out) and Image.open(out).size == (96, 96), "no quedó la portada")
    check(report['verified'] is True and not report['retried'], "report sin la verificación")

    # Prompt de la config: con marcador se reemplaza; sin marcador el título va al final.
    custom = {'prompt': 'Portada nueva. Titulo: {titulo}. Fin {otra}.', 'quality': 'medium'}
    client = _client()
    kit_template_art.cover(TITLE, MODEL, BGS, {}, random.Random(2), client, cfg=custom,
                           out_dir=os.path.join(tmp, 'c'), now=NOW, fetch=_fetch,
                           budget=_budget(), verify=_verifier(TITLE))
    check(client.calls[0]['prompt'] == f'Portada nueva. Titulo: {TITLE}. Fin {{otra}}.'
          and client.calls[0]['cfg']['quality'] == 'medium',
          "el prompt o los parámetros de la config no se respetan")
    check(kit_template_art.render_prompt('Sin marcador', TITLE).endswith(f'"{TITLE}"'),
          "sin marcador el título no se agrega")
    try:
        kit_template_art.render_prompt(None, '  ')
        FAILS.append("un título vacío debe fallar")
    except kit_art.KitArtError:
        pass
    check(kit_template_art.titles_match('Noche Rara #7', ' "noche  RARA#7" '),
          "la comparación distingue mayúsculas o espacios")
    check(not kit_template_art.titles_match('Noche Rara #7', 'Noche Rara 8')
          and not kit_template_art.titles_match('Noche Rara', '')
          and not kit_template_art.titles_match('Noche Rara', 'Noche Rora'),
          "la comparación acepta un título distinto")
    # Acentos, signos y "&" no justifican otra imagen (que se cobra).
    check(kit_template_art.titles_match('Café 24/7', 'CAFE 24 7')
          and kit_template_art.titles_match('Nuit & Fog', 'Nuit and Fog')
          and kit_template_art.titles_match('Noche Rara #7', 'Noche Rara 7')
          and kit_template_art.titles_match('¡Ñandú!', 'nandu')
          and kit_template_art.titles_match('???', '? ? ?') and not
          kit_template_art.titles_match('???', '!!!'),
          "la comparación se frena por acentos, signos o '&'")


# --- Reintentos ---

def _check_retries(tmp):
    def run(client, verify, budget=None, name='r'):
        report = {}
        budget = budget or _budget()
        try:
            out = kit_template_art.cover(
                TITLE, MODEL, BGS, {}, random.Random(4), client,
                out_dir=os.path.join(tmp, name), now=NOW, fetch=_fetch, report=report,
                budget=budget, verify=verify)
        except Exception as exc:  # el cliente falso puede levantar cualquier cosa
            return exc, report, budget
        return out, report, budget

    # Título distinto: un reintento y nada más, aunque vuelva a salir mal.
    client, verify = _client(), _verifier('Noche Rora #7 (vol. 2)')
    out, report, budget = run(client, verify)
    check(len(client.calls) == 2 and len(verify.calls) == 2,
          f"ante un título distinto hubo {len(client.calls)} pedidos (deben ser 2)")
    check(isinstance(out, str) and os.path.exists(out) and report['verified'] is False
          and report['retried'], "tras el reintento fallido no se usó la imagen")
    check(abs(budget.month_spent() - (2 * 0.25 + 2 * 0.01)) < 1e-6 and budget.images == 2,
          f"el gasto del reintento no se anotó: {budget.month_spent()}")
    # El reintento sale bien.
    client, verify = _client(), _verifier('otro titulo', TITLE.upper())
    out, report, _b = run(client, verify)
    check(len(client.calls) == 2 and report['verified'] is True, "el reintento bueno no se aceptó")
    # El reintento falla en la API: queda la primera imagen, sin más pedidos.
    client = _client(OSError(KEY), fail_from=2)
    out, report, _b = run(client, _verifier('otro titulo'))
    check(len(client.calls) == 2 and isinstance(out, str) and report['verified'] is False,
          "un error en el reintento debe dejar la primera imagen")
    # La verificación no responde: se usa la imagen, sin reintento.
    client = _client()
    out, report, _b = run(client, _verifier(OSError(KEY)))
    check(len(client.calls) == 1 and report['verified'] is None and isinstance(out, str),
          "si no se puede verificar no se reintenta")
    # Verificación apagada: ni se llama.
    client, verify, report = _client(), _verifier('otro'), {}
    kit_template_art.cover(TITLE, MODEL, BGS, {}, random.Random(4), client,
                           cfg={'verify': {'enabled': False}}, out_dir=os.path.join(tmp, 'v'),
                           now=NOW, fetch=_fetch, report=report, budget=_budget(), verify=verify)
    check(len(client.calls) == 1 and not verify.calls, "la verificación apagada igual se llamó")

    # Error de la API: ningún reintento. El rechazo no se cobra; un fallo dudoso sí.
    for fail, charged in ((kit_art.KitArtRejected('x ' + KEY), 0.0),
                          (kit_art.KitArtError('5xx ' + KEY), 0.25), (OSError(KEY), 0.25)):
        client, verify = _client(fail), _verifier(TITLE)
        out, _r, budget = run(client, verify)
        check(isinstance(out, Exception), "un error de la API debe salir como error")
        check(len(client.calls) == 1 and not verify.calls,
              f"ante {type(fail).__name__} hubo reintentos")
        check(abs(budget.month_spent() - charged) < 1e-6,
              f"gasto anotado ante {type(fail).__name__}: {budget.month_spent()}")
    # Respuesta que no es una imagen: error, cobrada y sin reintento.
    calls = []
    out, _r, budget = run(lambda *a: calls.append(1) or b'no es una imagen', _verifier(TITLE))
    check(isinstance(out, kit_art.KitArtError) and len(calls) == 1
          and abs(budget.month_spent() - 0.25) < 1e-6, "una respuesta inválida se manejó mal")
    # El reintento también respeta el tope: sin presupuesto queda la primera imagen.
    client = _client()
    out, report, _b = run(client, _verifier('otro'), _budget(max_images_per_run=1))
    check(len(client.calls) == 1 and isinstance(out, str) and report['verified'] is False,
          "el reintento pasó por encima del máximo por corrida")


# --- Tope de gasto ---

def _check_spend():
    cfg = kit_spend.settings({})
    check(cfg['monthly_cap_usd'] == 10.0 and cfg['max_images_per_run'] == 6,
          f"defaults del tope: {cfg}")
    bad = kit_spend.settings({'spend': {'monthly_cap_usd': 'x', 'max_images_per_run': -3,
                                        'image_cost_usd': 0.5}})
    check(bad['monthly_cap_usd'] == 10.0 and bad['max_images_per_run'] == 6
          and bad['image_cost_usd'] == 0.5, "valores inválidos del tope no caen al default")
    check(kit_spend.check(9.75, 10, 0.25) and not kit_spend.check(9.76, 10, 0.25)
          and kit_spend.check(0, 0) and not kit_spend.check(0, 0, 0.01), "check no corta en el tope")
    state = {}
    kit_spend.record(state, '2026-03', 0.25, images=1)
    kit_spend.record(state, '2026-03', 0.01, verifications=1)
    kit_spend.record(state, '2026-04', 0.25, images=1)
    check(state['spend']['2026-03'] == {'usd': 0.26, 'images': 1, 'verifications': 1}
          and kit_spend.spent(state, '2026-04') == 0.25 and kit_spend.spent(state, '2026-05') == 0,
          f"el contador no separa los meses: {state}")
    check(kit_spend.month_key(datetime(2026, 12, 31, 23, 59)) == '2026-12', "clave del mes")
    line = kit_spend.summary_line(state, datetime(2026, 3, 9), cap=10)
    check('2026-03' in line and '0.26' in line and '10.00' in line, f"resumen del gasto: {line}")

    # Máximo por corrida y tope del mes.
    budget = _budget(_Store(), max_images_per_run=2)
    for _ in range(2):
        check(budget.blocked(budget.image_cost(), images=1) is None, "bloqueó antes del máximo")
        budget.charge(budget.image_cost(), images=1)
    check(budget.blocked(budget.image_cost(), images=1) == kit_spend.REASON_RUN,
          "no cortó en el máximo por corrida")
    budget = _budget(_Store(spent=9.80))
    check(budget.blocked(budget.image_cost(), images=1) == kit_spend.REASON_MONTH
          and budget.blocked(budget.verify_cost()) is None, "no cortó en el tope mensual")
    store = _Store(spent=9.5)
    budget = _budget(store)
    budget.charge(0.25, images=1)
    check(abs(store.spend_month(budget.month) - 9.75) < 1e-6 and budget.month_spent() == 9.75,
          "el gasto no quedó guardado en el estado")
    # Un mes nuevo arranca en cero aunque el anterior haya llegado al tope.
    later = kit_spend.Budget(kit_spend.DEFAULTS, _Store(spent=10), NOW + timedelta(days=31))
    check(later.blocked(later.image_cost(), images=1) is None, "el tope no se reinicia con el mes")
    # Si el gasto no se puede guardar o leer, no se autoriza otra llamada.
    budget = _budget(_Store(fail_write=True))
    budget.charge(0.25, images=1)
    check(budget.broken and budget.blocked(0.25, images=1) == kit_spend.REASON_STATE,
          "sin poder guardar el gasto igual autoriza")

    class _NoRead:
        def spend_month(self, month):
            raise RuntimeError(KEY)

        def add_spend(self, *a, **k):
            return None
    check(_budget(_NoRead()).blocked(0.25, images=1) == kit_spend.REASON_STATE,
          "sin poder leer el gasto igual autoriza")

    # Estado en Dropbox (falso): el gasto se suma por mes y no pisa lo demás.
    files = {}
    real = (kit_cloud.read_json_rev, kit_cloud.write_json)
    kit_cloud.read_json_rev = lambda path, dbx=None: (
        (json.loads(files[path]), 'rev') if path in files else (None, None))
    kit_cloud.write_json = lambda path, data, rev=None, dbx=None: files.update(
        {path: json.dumps(data)}) or 'rev'
    try:
        pid = kit_state.upsert_pack('/p/a', 'Kit', db_path='/s.json')
        kit_state.add_spend('2026-03', 0.25, db_path='/s.json', images=1)
        kit_state.add_spend('2026-03', 0.01, db_path='/s.json', verifications=1)
        kit_state.record_run(pid, db_path='/s.json', audio_mode='assembled', youtube_id='y')
        check(kit_state.get_spend('2026-03', db_path='/s.json')
              == {'usd': 0.26, 'images': 1, 'verifications': 1}
              and kit_state.get_spend('2026-04', db_path='/s.json')['usd'] == 0,
              "kit_state no guarda el gasto por mes")
        state = kit_state.load('/s.json')
        check(len(state['runs']) == 1 and '/p/a' in state['packs'], "el gasto pisó el estado")
        lines = kit_settings.last_state_lines(state, now=datetime(2026, 3, 9), cap=10)
        check(any('0.26' in ln and '10.00' in ln for ln in lines),
              "'Ver último estado' no muestra el gasto del mes")
    finally:
        kit_cloud.read_json_rev, kit_cloud.write_json = real


# --- Entrada del worker ---

def _check_for_video(tmp):
    fallback = os.path.join(tmp, 'manual.png')
    Image.new('RGB', (10, 10)).save(fallback)
    listed = []

    def list_folder(folder, dbx=None):
        listed.append(folder)
        if folder == FOLDER:
            return [{'name': 'fondos', 'path': FOLDER + '/fondos', 'is_folder': True},
                    {'name': 'Modelo.jfif', 'path': FOLDER + '/modelo.jfif', 'is_folder': False},
                    {'name': 'Modelo.PNG', 'path': MODEL, 'is_folder': False},
                    {'name': 'otra.png', 'path': FOLDER + '/otra.png', 'is_folder': False}]
        if folder == FOLDER + '/fondos':
            return ([dict(b, is_folder=False) for b in BGS]
                    + [{'name': 'notas.txt', 'path': folder + '/notas.txt', 'is_folder': False},
                       {'name': 'viejos', 'path': folder + '/viejos', 'is_folder': True}])
        raise RuntimeError('not_found ' + folder)

    real = (kit_template_art.list_folder, kit_template_art.kit_source.download_pack_files)
    kit_template_art.list_folder = list_folder
    kit_template_art.kit_source.download_pack_files = lambda paths, dest, dbx=None: _fetch(
        paths, dest)
    cfg = {'cover_mode': 'template', 'art': {'refs_root': REFS_ROOT + '/', 'genre': GENRE},
           'spend': {'max_images_per_run': 2}}
    p = [b['path'] for b in BGS]
    try:
        model, backgrounds = kit_template_art.find_assets(REFS_ROOT, GENRE)
        check(model == MODEL and [b['path'] for b in backgrounds] == p,
              "no encontró modelo.png y los fondos (incluido el .jfif)")

        def run(store, client, verify, budget=None, sent=None, kit_cfg=cfg, name='w'):
            return kit_art.for_cover(
                kit_cfg, 'Kit Privado', TITLE, fallback, store, random.Random(1),
                os.path.join(tmp, name), client=client, notify=(sent if sent is not None
                                                                 else []).append,
                now=NOW, budget=budget, verify=verify)

        # Camino feliz: portada completa, el fondo libre y el gasto guardado.
        sent, client = [], _client()
        store = _Store({p[0]: _ago(2), p[1]: _ago(10), p[2]: _ago(20)})
        path, refs, complete = run(store, client, _verifier(TITLE), sent=sent)
        check(complete and path != fallback and os.path.exists(path), "no devolvió la portada")
        check(refs == [p[3]], f"no eligió el único fondo libre: {refs!r}")
        check(not sent, "avisó sin motivo")
        check(abs(store.spend_month('2026-03') - 0.26) < 1e-6, "el gasto no llegó al estado")
        check('Kit Privado' not in client.calls[0]['prompt'], "el nombre del kit entró al prompt")
        frame, thumb = kit_cover.frame_for_video(
            {'frame': {'size': [320, 180]}}, path, os.path.join(tmp, 'frame'))
        check(Image.open(frame).size == (320, 180) and os.path.exists(thumb),
              "la portada completa no se pudo llevar al cuadro 16:9")

        # Tope por corrida: el tercer video ya no genera, cae a manual y avisa una sola vez.
        sent, client, store = [], _client(), _Store()
        budget = kit_spend.Budget(kit_spend.settings(cfg), store, NOW)
        results = [run(store, client, _verifier(TITLE), budget, sent, name=f't{i}')
                   for i in range(4)]
        check([r[2] for r in results] == [True, True, False, False] and len(client.calls) == 2,
              f"el máximo por corrida no cortó la generación: {len(client.calls)} pedidos")
        check(results[2][:2] == (fallback, []), "al llegar al tope no pasó a manual")
        check(len(sent) == 1 and 'máximo' in sent[0], f"aviso del tope: {sent!r}")
        # Tope mensual ya alcanzado en el estado: ni un pedido.
        sent, client, store = [], _client(), _Store(spent=9.9)
        got = run(store, client, _verifier(TITLE), sent=sent)
        check(got == (fallback, [], False) and not client.calls,
              "con el tope mensual alcanzado igual se generó")
        check(len(sent) == 1 and 'tope' in sent[0] and store.spend_month('2026-03') == 9.9,
              "el tope mensual no avisó o sumó gasto")

        # Error y rechazo de la API: manual, un aviso y ningún reintento.
        for fail, word in ((kit_art.KitArtRejected('x ' + KEY), 'rechazado'),
                           (OSError(KEY + ' Kit Privado'), 'OSError')):
            sent, client = [], _client(fail)
            got = run(_Store(), client, _verifier(TITLE), sent=sent)
            check(got == (fallback, [], False), f"ante {word} no cayó a manual")
            check(len(client.calls) == 1, f"ante {word} hubo reintentos")
            check(len(sent) == 1 and word in sent[0], f"ante {word} no avisó")

        # Título distinto dos veces: se usa igual y el aviso lleva la portada.
        photos, sent, client = [], [], _client()

        def notify(text, photo=None):
            sent.append(text)
            photos.append(photo)
        got = kit_art.for_cover(cfg, 'Kit Privado', TITLE, fallback, _Store(), random.Random(1),
                                os.path.join(tmp, 'rev'), client=client, notify=notify,
                                now=NOW, verify=_verifier('Otro Titulo'))
        check(got[2] and got[0] != fallback and len(client.calls) == 2,
              "con el título mal dos veces no se usó la imagen o hubo más de un reintento")
        check(len(sent) == 1 and 'revisala' in sent[0] and photos == [got[0]],
              "el aviso de revisión no salió con la portada")

        # El reintento no se pudo hacer (tope): el aviso lo dice, no afirma que hubo uno.
        sent, client = [], _client()
        one = {**cfg, 'spend': {'max_images_per_run': 1}}
        got = kit_art.for_cover(one, 'Kit Privado', TITLE, fallback, _Store(), random.Random(1),
                                os.path.join(tmp, 'rev2'), client=client,
                                notify=lambda text, photo=None: sent.append(text),
                                now=NOW, verify=_verifier('Otro Titulo'))
        check(got[2] and len(client.calls) == 1 and len(sent) == 1
              and 'no se pudo hacer' in sent[0] and 'incluso' not in sent[0],
              f"el aviso del reintento fallido no dice la causa: {sent!r}")

        # Un TypeError de adentro del notificador no manda el aviso dos veces.
        tries = []

        def flaky(text, photo=None):
            tries.append(photo)
            raise TypeError('de adentro')
        kit_art.for_cover(cfg, 'Kit Privado', TITLE, fallback, _Store(), random.Random(1),
                          os.path.join(tmp, 'rev3'), client=_client(), notify=flaky, now=NOW,
                          verify=_verifier('Otro Titulo'))
        check(len(tries) == 1, f"el aviso se mandó {len(tries)} veces")
        # Un notificador que solo recibe texto sigue funcionando (sin foto).
        texts = []
        kit_art.for_cover(cfg, 'Kit Privado', TITLE, fallback, _Store(), random.Random(1),
                          os.path.join(tmp, 'rev4'), client=_client(), notify=texts.append,
                          now=NOW, verify=_verifier('Otro Titulo'))
        check(len(texts) == 1 and 'revisala' in texts[0], "un notificador de solo texto falló")

        # Config incompleta, carpeta inexistente o Telegram caído: manual, sin levantar.
        def broken(text, photo=None):
            raise RuntimeError(KEY)
        for kit_cfg in ({'cover_mode': 'template'},
                        {'cover_mode': 'template', 'art': {'refs_root': '/otra', 'genre': 'x'}},
                        {'cover_mode': 'TEMPLATE', 'art': {'refs_root': REFS_ROOT}}):
            client = _client()
            got = kit_art.for_cover(kit_cfg, 'Kit Privado', TITLE, fallback, _Store(),
                                    random.Random(1), tmp, client=client, notify=broken, now=NOW)
            check(got == (fallback, [], False) and not client.calls,
                  "una config incompleta no cayó a manual")

        # Manual y auto siguen igual: for_cover delega en for_video y nunca marca "completa".
        listed.clear()
        for kit_cfg in ({}, {'cover_mode': 'manual', 'art': cfg['art']}, None):
            client, sent = _client(), []
            got = kit_art.for_cover(kit_cfg, 'Kit Privado', TITLE, fallback, _Store(),
                                    random.Random(1), tmp, client=client, notify=sent.append,
                                    now=NOW)
            check(got == (fallback, [], False) and not client.calls and not sent,
                  "el modo manual cambió")
        check(not listed, "el modo manual tocó Dropbox")
        check(kit_art.for_video(cfg, 'Kit Privado', fallback, _Store(), random.Random(1), tmp,
                                client=_client(), now=NOW) == (fallback, []),
              "for_video (modo auto) no debe generar en modo template")
        check(kit_art.generates(cfg) and kit_art.generates({'cover_mode': 'auto'})
              and not kit_art.generates({'cover_mode': 'manual'}) and not kit_art.generates({}),
              "generates no distingue los modos")
    finally:
        kit_template_art.list_folder, kit_template_art.kit_source.download_pack_files = real


# --- Clientes reales contra un urlopen falso ---

def _check_api(tmp):
    imgs = []
    for i in range(2):
        imgs.append(os.path.join(tmp, f'Persona_Famosa_{i}.png'))
        Image.new('RGB', (8, 8)).save(imgs[-1])
    cover = os.path.join(tmp, 'cover.png')
    Image.new('RGB', (2000, 2000)).save(cover)
    real = urllib.request.urlopen
    seen = []

    class _Resp:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake(req, timeout=None):
        seen.append(req)
        if req.full_url.endswith('/images/edits'):
            import base64
            return _Resp({'data': [{'b64_json': base64.b64encode(_png()).decode()}]})
        return _Resp({'choices': [{'message': {'content': ' "Noche Rara" '}}]})

    def boom(req, timeout=None):
        seen.append(req)
        raise OSError(KEY + ' en el texto del error')

    cfg = {**kit_template_art.DEFAULTS, 'base_url': 'https://img.example/v1'}
    try:
        urllib.request.urlopen = fake
        kit_art.api_client('p {titulo}', imgs, cfg, key=KEY)
        body = seen[0].data
        for field, value in (('quality', 'high'), ('input_fidelity', 'high'),
                             ('size', '1024x1024'), ('model', 'gpt-image-1'), ('n', '1')):
            check(f'name="{field}"\r\n\r\n{value}\r\n'.encode() in body,
                  f"el pedido no lleva {field}={value}")
        check(body.count(b'name="image[]"') == 2 and b'filename="ref0.png"' in body
              and b'Persona' not in body and KEY.encode() not in body,
              "el multipart lleva el nombre del archivo o la clave, o no trae 2 imágenes")
        # El modo auto no manda input_fidelity (su comportamiento no cambia).
        seen.clear()
        kit_art.api_client('p', imgs[:1], {'base_url': cfg['base_url']}, key=KEY)
        check(b'input_fidelity' not in seen[0].data, "el modo auto ahora manda input_fidelity")

        # Verificación con visión.
        seen.clear()
        vcfg = kit_template_art.verify_settings(cfg)
        check(vcfg['same_host'] and vcfg['base_url'] == cfg['base_url'], "verify_settings")
        text = kit_template_art.vision_client(cover, vcfg, key=KEY)
        check(kit_template_art.titles_match('noche rara', text), "vision_client no leyó el título")
        req = seen[0]
        check(req.full_url == 'https://img.example/v1/chat/completions'
              and req.get_header('Authorization') == 'Bearer ' + KEY
              and KEY.encode() not in req.data and b'image_url' in req.data
              and len(req.data) < 200000, "pedido de verificación mal armado")
        other = kit_template_art.verify_settings(
            {**cfg, 'verify': {'base_url': 'https://otro.example/v1'}})
        check(not other['same_host'] and not other.get('key_file'),
              "la clave de imágenes podría viajar a otro host")
        urllib.request.urlopen = boom
        for call in (lambda: kit_template_art.vision_client(cover, vcfg, key=KEY),
                     lambda: kit_art.api_client('p', imgs, cfg, key=KEY)):
            try:
                call()
                FAILS.append("un fallo de red no levantó error")
            except kit_art.KitArtError as e:
                check(KEY not in str(e) and e.__cause__ is None, "el error expone la clave")
        # Sin clave o con un host no permitido: error de config, nada sale a la red.
        seen.clear()
        for call in (lambda: kit_template_art.vision_client(cover, vcfg),
                     lambda: kit_template_art.vision_client(cover, other, key=KEY),
                     lambda: kit_art.api_client('p', imgs, cfg)):
            try:
                call()
                FAILS.append("sin clave o con host no permitido debe fallar")
            except kit_art.KitArtConfig as e:
                check(e.billable is False and KEY not in str(e), "error de config mal marcado")
        check(not seen, "un error de config igual llamó a la red")
    finally:
        urllib.request.urlopen = real


# --- Descripción del kit ---

def _check_description():
    kit = {'folder': 'f', 'name': 'N', 'payhip_url': 'https://example.com/p', 'genre': 'g'}
    plain = kit_catalog.validate([kit])[0]
    check('description' not in plain, "una entrada sin descripción cambió de forma")
    out = kit_catalog.validate([{**kit, 'description': '  guitarras  tristes\n de noche '}])[0]
    check(out['description'] == 'guitarras tristes de noche', "la descripción no se normaliza")
    for bad in ('x' * 201, 5, ['a']):
        try:
            kit_catalog.validate([{**kit, 'description': bad}])
            FAILS.append(f"descripción inválida aceptada: {type(bad).__name__}")
        except kit_catalog.KitCatalogError as e:
            check('entrada 1' in str(e) and 'xxx' not in str(e), "el error cita la descripción")
    check(kit_catalog.validate([{**kit, 'description': 'x' * 200}])[0]['description'],
          "200 caracteres deben entrar")
    rows = kit_settings.validate_kits([{**kit, 'description': 'melodías oscuras'}], ['g'])
    check(rows[0]['description'] == 'melodías oscuras', "kit_settings pierde la descripción")
    try:
        kit_settings.validate_kits([{**kit, 'description': 'x' * 300}], ['g'])
        FAILS.append("kit_settings aceptó una descripción larga")
    except kit_settings.SettingsError as e:
        check('Kit 1' in str(e), "el error de descripción no nombra la fila")

    prompts = []

    def llm(system, user):
        prompts.append(user)
        return 'Bruma\nCeniza'
    name = kit_names.pick('N', 'g', [], llm_call=llm, description='melodías\noscuras de piano')
    check(name == 'Bruma' and 'melodías oscuras de piano' in prompts[0],
          "la descripción no llega al modelo de lenguaje")
    kit_names.pick('N', 'g', [], llm_call=llm)
    check('Contexto' not in prompts[1], "sin descripción el prompt de nombres cambió")

    class _S:
        def get_cycle(self, path):
            return {'used_names': []}
    got = kit_names.for_pack('N', '/p', {'genre': 'g'}, _S(), llm_call=llm, description='uno dos')
    check(got[0] == 'Bruma' and 'uno dos' in prompts[2], "for_pack no pasa la descripción")

    # Ajustes del panel: modo, prompt y topes.
    good = {'channel': 'c', 'genres': ['g'], 'refs_root': '/refs', 'cover_mode': 'template',
            'slots': [{'weekday': 0, 'hour': 18, 'minute': 0}]}
    default = kit_settings.default_prompt()
    out = kit_settings.validate_settings({**good, 'art_prompt': default, 'monthly_cap_usd': 7.5,
                                          'max_images_per_run': 4})
    new = kit_settings.apply_to_config({'kit_preview': {'art': {'prompt': 'viejo {titulo}',
                                                                'model': 'm'}}}, out)
    kp = new['kit_preview']
    check(kp['cover_mode'] == 'template' and 'prompt' not in kp['art'] and kp['art']['model'] == 'm'
          and kp['spend'] == {'monthly_cap_usd': 7.5, 'max_images_per_run': 4},
          f"ajustes de plantilla mal guardados: {kp}")
    out = kit_settings.validate_settings({**good, 'art_prompt': ' Hola {titulo} '})
    kp = kit_settings.apply_to_config({'kit_preview': {'spend': {'image_cost_usd': 0.3}}},
                                      out)['kit_preview']
    check(kp['art']['prompt'] == 'Hola {titulo}' and kp['spend'] == {'image_cost_usd': 0.3},
          "el prompt propio no se guarda o se pisaron los costos")
    form = kit_settings.form_from_config({'kit_preview': kp | {'cover_mode': 'template'}})
    check(form['cover_mode'] == 'template' and form['art_prompt'] == 'Hola {titulo}'
          and form['monthly_cap_usd'] == 10.0 and form['max_images_per_run'] == 6,
          "el formulario no carga el modo plantilla")
    check(kit_settings.form_from_config({})['art_prompt'] == default,
          "sin prompt en la config el formulario no muestra el de fábrica")
    # Sin {titulo} se guarda: el worker agrega el título al final.
    check(kit_settings.validate_settings({**good, 'art_prompt': 'sin marcador'})['art_prompt']
          == 'sin marcador', "un prompt sin {titulo} debe poder guardarse")
    for bad in ({'art_prompt': '{titulo}' + 'x' * 4000},
                {'monthly_cap_usd': -1}, {'monthly_cap_usd': 'x'}, {'max_images_per_run': 999},
                {'refs_root': ''}):
        try:
            kit_settings.validate_settings({**good, **bad})
            FAILS.append(f"ajuste inválido aceptado: {list(bad)}")
        except kit_settings.SettingsError:
            pass
    check('art_prompt' not in kit_settings.validate_settings(good),
          "un formulario sin prompt no debe tocar el guardado")


def _check_auto_budget(tmp):
    """El tope de gasto también corta el modo auto (fondo con IA)."""
    fallback = os.path.join(tmp, 'manual_auto.png')
    Image.new('RGB', (10, 10)).save(fallback)
    cfg = {'cover_mode': 'auto', 'art': {'refs_root': REFS_ROOT, 'genre': GENRE},
           'spend': {'max_images_per_run': 2}}
    real = (kit_art.list_refs, kit_art.kit_source.download_pack_files)
    kit_art.list_refs = lambda root, genre, dbx=None: BGS
    kit_art.kit_source.download_pack_files = lambda paths, dest, dbx=None: _fetch(paths, dest)
    try:
        sent, client, store = [], _client(), _Store()
        budget = kit_spend.Budget(kit_spend.settings(cfg), store, NOW)
        results = [kit_art.for_video(cfg, 'Kit Privado', fallback, store, random.Random(i),
                                     os.path.join(tmp, f'auto{i}'), client=client,
                                     notify=sent.append, now=NOW, budget=budget)
                   for i in range(4)]
        check(len(client.calls) == 2 and results[0][0] != fallback and results[1][0] != fallback
              and results[2] == (fallback, []) and results[3] == (fallback, []),
              f"el máximo por corrida no cortó el modo auto: {len(client.calls)} pedidos")
        check(len(sent) == 1 and 'máximo' in sent[0], f"aviso del tope en auto: {sent!r}")
        check(abs(store.spend_month(budget.month) - 0.5) < 1e-6,
              "el gasto del modo auto no llegó al estado")
        # Sin budget propio usa el estado del store: con el tope mensual alcanzado no genera.
        sent, client, store = [], _client(), _Store(spent=9.9)
        got = kit_art.for_video(cfg, 'Kit Privado', fallback, store, random.Random(1),
                                os.path.join(tmp, 'auto_m'), client=client, notify=sent.append,
                                now=NOW)
        check(got == (fallback, []) and not client.calls and len(sent) == 1,
              "con el tope mensual alcanzado el modo auto igual generó")
        # Un error dudoso de la API en auto también se cobra; un rechazo, no.
        for fail, charged in ((kit_art.KitArtRejected('x'), 0.0), (OSError('x'), 0.25)):
            store = _Store()
            budget = kit_spend.Budget(kit_spend.settings(cfg), store, NOW)
            kit_art.for_video(cfg, 'Kit Privado', fallback, store, random.Random(1),
                              os.path.join(tmp, 'auto_e'), client=_client(fail),
                              notify=lambda t: None, now=NOW, budget=budget)
            check(abs(budget.month_spent() - charged) < 1e-6,
                  f"gasto en auto ante {type(fail).__name__}: {budget.month_spent()}")
    finally:
        kit_art.list_refs, kit_art.kit_source.download_pack_files = real


def main():
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(OUT):
        for fn, args in ((_check_background, ()), (_check_prompt, (tmp,)),
                         (_check_retries, (tmp,)), (_check_spend, ()),
                         (_check_for_video, (tmp,)), (_check_api, (tmp,)),
                         (_check_description, ()), (_check_auto_budget, (tmp,))):
            try:
                fn(*args)
            except Exception as e:
                FAILS.append(f"{fn.__name__} falló: {type(e).__name__}: {e}")
    printed = OUT.getvalue()
    check(KEY not in printed, "la clave aparece en la salida")
    check(not any(w in printed.lower() for w in PRIVATE + ('kit privado',)),
          "la salida nombra un título, un kit o un fondo")
    if FAILS:
        for msg in FAILS:
            print('FAIL:', msg.replace(KEY, '<clave>'))
        return 1
    print('OK: smoke_kit_template_art')
    return 0


if __name__ == '__main__':
    sys.exit(main())
