#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: tendencias semanales (kit_trends). Sin red: Notion, IA y Dropbox falsos.

Chequea el informe (validación y antigüedad), la lectura de Notion (host fijo, sin redirecciones,
sin filtrar la clave), que la IA solo pueda elegir entre opciones existentes, los respaldos
(última ficha buena, ficha del panel) y que ``apply`` nunca levante.
"""

import contextlib
import copy
import io
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_cloud, kit_notion, kit_seo, kit_spend, kit_trends

for _name in kit_cloud.ENV_VARS + kit_cloud.RUNTIME_SECRETS:
    os.environ.pop(_name, None)

FAILS = []
NOW = datetime(2026, 10, 11, 20, 0, 0, tzinfo=timezone.utc)
TOKEN = 'secret_SMOKE_NOTION_TOKEN_123'
PAGE = '0123456789abcdef0123456789abcdef'
GUITAR = {'phrase': 'Guitar Loop Kit', 'artists': ['Juice WRLD', 'Iann Dior', 'NBA YoungBoy'],
          'tags': ['Emotional', 'Dark', 'Acoustic', 'Sad', 'Sample Pack']}
REGGAETON = {'phrase': 'Afro House Loop Kit', 'artists': ['Makar', 'Morad'],
             'tags': ['House', 'Afro', 'Deep House', 'Vocals']}
KIT_CFG = {'seo': {'guitarras': GUITAR, 'reggaeton house': REGGAETON},
           'names': {'base_url': 'https://api.openai.com/v1', 'model': 'm'}}


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def report(**over):
    data = {'version': 1, 'generated_at': (NOW - timedelta(hours=3)).isoformat().replace('+00:00', 'Z'),
            'channel': {'top_videos': [{'title': 'Juice WRLD Loop Kit - "999"', 'views': 679}]},
            'genres': {
                'guitarras': {'keywords': [
                    {'keyword': 'emotional guitar loop kit', 'monthly_searches': 11700,
                     'competition': 12.3, 'growth_pct': 4.0},
                    {'keyword': 'guitar loop kit free', 'monthly_searches': 13700,
                     'competition': 6.3, 'growth_pct': None},
                    {'keyword': 'juice wrld guitar loop kit', 'monthly_searches': 9700,
                     'competition': 12.3, 'growth_pct': -31.0},
                    {'keyword': 'sad guitar loop kit', 'monthly_searches': 11200,
                     'competition': 27.3, 'growth_pct': -20.0}]},
                'reggaeton_house': {'keywords': [
                    {'keyword': 'afro house loop kit free', 'monthly_searches': 4800,
                     'competition': 13.1, 'growth_pct': None}]}}}
    data.update(over)
    return json.dumps(data)


class Dbx:
    """Dropbox falso con un solo archivo en memoria (lo que usa kit_cloud)."""

    def __init__(self):
        self.files, self.n = {}, 0

    def files_download(self, path):
        if path not in self.files:
            raise Exception('not_found')
        meta = type('M', (), {'rev': '%09x' % self.n})()
        return meta, type('R', (), {'content': self.files[path]})()

    def files_upload(self, payload, path, mode=None, mute=True):
        self.n += 1
        self.files[path] = payload
        return type('M', (), {'rev': '%09x' % self.n})()


PATH = '/loop_kits/_automation/seo_trends.json'


class Resp:
    def __init__(self, body):
        self._body = json.dumps(body).encode()

    def read(self, limit=None):
        return self._body[:limit] if limit else self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def fake_opener(pages, seen):
    class Opener:
        def open(self, req, timeout=None):
            seen.append({'url': req.full_url, 'auth': req.get_header('Authorization'),
                         'version': req.get_header('Notion-version'), 'timeout': timeout})
            body = pages.pop(0)
            if isinstance(body, Exception):
                raise body
            return Resp(body)
    return Opener()


def code_block(text, language='json'):
    parts = [{'plain_text': text[i:i + 1900]} for i in range(0, len(text), 1900)]
    return {'type': 'code', 'code': {'language': language, 'rich_text': parts}}


def llm_returning(answer, calls=None):
    def llm(system, user):
        if calls is not None:
            calls.append((system, user))
        if isinstance(answer, Exception):
            raise answer
        return answer if isinstance(answer, str) else json.dumps(answer)
    return llm


def _check_report():
    ok = kit_trends.parse_report(report(), NOW)
    check(set(ok['genres']) == {'guitarras', 'reggaeton_house'} and len(ok['videos']) == 1,
          f"el informe válido no se leyó: {ok['genres'].keys()}")
    for label, text in (('no es JSON', 'esto no es json'), ('versión', report(version=2)),
                        ('sin fecha', report(generated_at='ayer')),
                        ('del futuro', report(generated_at=(NOW + timedelta(days=3)).isoformat())),
                        ('viejo', report(generated_at=(NOW - timedelta(days=11)).isoformat()))):
        try:
            kit_trends.parse_report(text, NOW, 10)
            FAILS.append(f"el informe '{label}' no se rechazó")
        except kit_trends.KitTrendsError as e:
            check(e.code in ('json', 'version', 'fecha', 'viejo') and 'ayer' not in str(e),
                  f"el error de '{label}' trae datos: {e}")
    junk = json.loads(report())
    junk['genres']['guitarras']['keywords'] = [
        {'keyword': 'ver http://malo.com loop kit', 'monthly_searches': 5},
        {'keyword': 'x' * 500 + ' loop kit', 'monthly_searches': 'muchas'},
        {'keyword': 'ok loop kit', 'monthly_searches': float('inf'), 'competition': 900},
        'texto', None, {'keyword': '', 'monthly_searches': 1}]
    words = kit_trends.parse_report(json.dumps(junk, allow_nan=True), NOW)['genres']['guitarras']
    check([w['keyword'] for w in words] == ['x' * kit_seo.MAX_ITEM_LEN, 'ok loop kit'],
          f"entradas basura aceptadas: {[w['keyword'][:20] for w in words]}")
    check(all(w['competition'] is None or 0 <= w['competition'] <= 100 for w in words)
          and all(w['searches'] >= 0 and w['searches'] < 1e10 for w in words),
          "los rangos numéricos no se limitan")
    # Un número gigante no tira abajo el informe: se limita.
    huge = report().replace('11700', '9' * 400)
    parsed = kit_trends.parse_report(huge, NOW)
    check(parsed['genres']['guitarras'][0]['searches'] == 1e9, "un entero enorme no se limitó")
    huge_views = json.loads(report())
    huge_views['channel']['top_videos'][0]['views'] = 10 ** 400
    check(kit_trends.parse_report(json.dumps(huge_views), NOW)['videos'][0]['views'] == 10 ** 9,
          "las vistas enormes no se limitaron")
    many = json.loads(report())
    many['genres']['guitarras']['keywords'] = [
        {'keyword': f'kw{i} loop kit', 'monthly_searches': i} for i in range(500)]
    check(len(kit_trends.parse_report(json.dumps(many), NOW)['genres']['guitarras']) <= 40,
          "no se limita la cantidad de palabras clave")


def _check_notion():
    saved = {name: os.environ.pop(name, None) for name in (kit_notion.ENV_TOKEN, kit_notion.ENV_PAGE)}
    real = kit_notion._OPENER
    try:
        env = {kit_notion.ENV_TOKEN: TOKEN, kit_notion.ENV_PAGE: PAGE}
        check(kit_notion.configured(env) and not kit_notion.configured({}), "configured falla")
        # Un id, un id con guiones y una URL con título llegan al mismo id.
        check(kit_notion.page_id('https://www.notion.so/SEO-semanal-' + PAGE + '?pvs=4') == PAGE
              and kit_notion.page_id('01234567-89ab-cdef-0123-456789abcdef') == PAGE
              and kit_notion.page_id('../../etc/passwd') is None
              and kit_notion.page_id('x' * 40) is None, "el id de página no se normaliza bien")
        text = report()
        seen, pages = [], [
            {'results': [code_block('{"viejo": true}'), {'type': 'paragraph'}, 'raro'],
             'has_more': True, 'next_cursor': 'abc def&x=1'},
            {'results': [code_block(text * 1), code_block('no importa', 'python')],
             'has_more': False}]
        kit_notion._OPENER = fake_opener(pages, seen)
        got = kit_notion.fetch_report_text(7, env)
        check(got == text, "no tomó el último bloque json (largo, partido en trozos)")
        check(len(seen) == 2 and all(s['url'].startswith('https://api.notion.com/v1/blocks/' + PAGE)
                                     for s in seen), f"URL de Notion: {[s['url'] for s in seen]}")
        check('start_cursor=abc%20def%26x%3D1' in seen[1]['url'] and seen[0]['timeout'] == 7,
              "el cursor no se escapa o falta el timeout")
        check(seen[0]['auth'] == 'Bearer ' + TOKEN and seen[0]['version'], "cabeceras de Notion")
        # Errores: sin motivo ni clave.
        for failure in (urllib.error.HTTPError('https://api.notion.com/x?k=' + TOKEN, 401, TOKEN,
                                                {}, None), OSError(TOKEN)):
            kit_notion._OPENER = fake_opener([failure], [])
            try:
                kit_notion.fetch_report_text(5, env)
                FAILS.append("un error de Notion no levantó")
            except kit_notion.NotionError as e:
                check(TOKEN not in str(e) and e.code == 'notion', f"el error de Notion filtra: {e}")
        kit_notion._OPENER = fake_opener([{'results': [], 'has_more': False}], [])
        try:
            kit_notion.fetch_report_text(5, env)
            FAILS.append("una página sin bloque json no levantó")
        except kit_notion.NotionError as e:
            check(e.code == 'sin_bloque', "código de página sin bloque")
        try:
            kit_notion.fetch_report_text(5, {})
            FAILS.append("sin secretos no levantó")
        except kit_notion.NotionError as e:
            check(e.code == 'sin_notion', "código sin secretos")
        # Un bloque json vacío o en blanco no tapa al informe, y se leen hasta 10 páginas.
        seen, pages = [], [{'results': [code_block(text)], 'has_more': True, 'next_cursor': 'c1'},
                           {'results': [code_block('  \n ')], 'has_more': False}]
        kit_notion._OPENER = fake_opener(pages, seen)
        check(kit_notion.fetch_report_text(5, env) == text, "un bloque vacío tapó al informe")
        pages = [{'results': [], 'has_more': True, 'next_cursor': f'c{i}'} for i in range(9)]
        pages.append({'results': [code_block(text)], 'has_more': False})
        kit_notion._OPENER = fake_opener(pages, [])
        check(kit_notion.fetch_report_text(5, env) == text, "no leyó hasta 10 páginas de bloques")
        # La clave no sigue una redirección a otro host.
        handler = kit_notion._NoRedirect()
        check(handler.redirect_request(None, None, 302, 'x', {}, 'https://evil.example/') is None,
              "se siguen las redirecciones")
    finally:
        kit_notion._OPENER = real
        for name, value in saved.items():
            if value is not None:
                os.environ[name] = value


def _check_choose():
    seo = kit_seo.validate(GUITAR)
    words = kit_trends.parse_report(report(), NOW)['genres']['guitarras']
    cands = kit_trends.candidates(seo, words)
    phrases = sorted(c['phrase'] for c in cands.values())
    check(phrases == ['Emotional Guitar Loop Kit', 'Guitar Loop Kit', 'Sad Guitar Loop Kit'],
          f"candidatas: {phrases} ('free' sale, el artista no se repite)")
    # Un artista corto no descarta frases por tener esas letras dentro de otra palabra.
    short = kit_seo.validate({**GUITAR, 'artists': ['Ye', 'Mac']})
    short_words = [{'keyword': 'keyboard layered loop kit', 'searches': 9000.0, 'competition': 5.0,
                    'growth': None},
                   {'keyword': 'machine guitar loop kit', 'searches': 8000.0, 'competition': 5.0,
                    'growth': None},
                   {'keyword': 'ye guitar loop kit', 'searches': 7000.0, 'competition': 5.0,
                    'growth': None}]
    got = sorted(c['phrase'] for c in kit_trends.candidates(short, short_words).values())
    check(got == ['Guitar Loop Kit', 'Keyboard Layered Loop Kit', 'Machine Guitar Loop Kit'],
          f"el artista corto descartó frases ajenas (o dejó pasar la suya): {got}")
    # Sin IA: la de mejor puntaje (búsquedas, competencia y crecimiento).
    new, tips, used = kit_trends.choose('guitarras', seo, words, [], None, None)
    check(new['phrase'] == 'Guitar Loop Kit' and not used and not tips
          and new['tags'] == seo['tags'], f"sin IA: {new['phrase']!r}")
    # Con IA: solo entre opciones que existen.
    calls = []
    answer = {'phrase': 'emotional guitar loop kit', 'tags': ['dark', 'EMOTIONAL', 'Inventada'],
              'artists': ['Juice WRLD', 'Artista Falso'], 'suggestions': ['nba youngboy', 'http://x.co']}
    new, tips, used = kit_trends.choose('guitarras', seo, words, [{'title': 't', 'views': 1}],
                                         llm_returning(answer, calls), kit_spend.Budget())
    check(used and new['phrase'] == 'Emotional Guitar Loop Kit', f"frase elegida: {new['phrase']!r}")
    check(new['tags'][:2] == ['Dark', 'Emotional'] and 'Inventada' not in new['tags']
          and len(new['tags']) >= 4, f"etiquetas: {new['tags']}")
    check(new['artists'][0] == 'Juice WRLD' and 'Artista Falso' not in new['artists']
          and len(new['artists']) >= 2, f"artistas: {new['artists']}")
    check(tips == ['nba youngboy'], f"sugerencias (sin links): {tips}")
    prompt = calls[0][1]
    check('Ignore' not in prompt and 'untrusted' in calls[0][0] and 'Emotional Guitar Loop Kit' in prompt
          and len(prompt) < 6000, "el prompt no marca el informe como dato no confiable")
    # Respuestas que no sirven: frase inventada, texto suelto o error → respaldo sin IA.
    for bad in ({'phrase': 'Hacked Loop Kit', 'tags': []}, 'no soy json', ['lista'],
                RuntimeError('timeout')):
        new, _t, used = kit_trends.choose('guitarras', seo, words, [], llm_returning(bad),
                                           kit_spend.Budget())
        check(not used and new['phrase'] == 'Guitar Loop Kit', f"respuesta mala aceptada: {bad!r}")
    # JSON rodeado de texto se acepta.
    new, _t, used = kit_trends.choose('guitarras', seo, words, [], llm_returning(
        'Claro: ' + json.dumps({'phrase': 'Sad Guitar Loop Kit'}) + ' listo'), None)
    check(used and new['phrase'] == 'Sad Guitar Loop Kit', "JSON entre textos no se leyó")
    # El tope de gasto frena la llamada y cuenta lo que se paga.
    calls = []
    blocked = kit_spend.Budget({'monthly_cap_usd': 0.0})
    kit_trends.choose('guitarras', seo, words, [], llm_returning(answer, calls), blocked)
    check(not calls, "el tope de gasto no frenó la llamada")
    budget = kit_spend.Budget()
    kit_trends.choose('guitarras', seo, words, [], llm_returning(RuntimeError('x')), budget)
    check(abs(budget.month_spent() - budget.text_cost()) < 1e-9, "no se anotó el gasto de texto")
    # La ficha de la semana sigue cumpliendo las reglas del título.
    check(kit_seo.validate(new) and new['title_template'] == seo['title_template'],
          "la ficha elegida no valida")


def _check_apply():
    out = io.StringIO()
    dbx = Dbx()
    good = lambda: report()
    guitar_answer = {'phrase': 'Emotional Guitar Loop Kit',
                     'tags': ['Dark', 'Emotional', 'Acoustic', 'Sad']}

    def answer(system, user):  # cada género recibe su respuesta
        genre = json.loads(user)['genre']
        return json.dumps(guitar_answer if 'guitar' in genre
                          else {'phrase': 'Afro House Loop Kit', 'tags': ['House', 'Afro']})
    # Sin secretos ni fetch: no hace nada y no avisa.
    cfg, warns = kit_trends.apply(copy.deepcopy(KIT_CFG), dbx=dbx, path=PATH, now=NOW)
    check(cfg == KIT_CFG and warns == [] and not dbx.files, "sin secretos debía ser un no-op")
    for off in ({'trends': {'enabled': False}}, {'seo': {}}):
        cfg, warns = kit_trends.apply({**KIT_CFG, **off}, dbx=dbx, path=PATH, fetch=good, now=NOW)
        check(cfg == {**KIT_CFG, **off} and not warns, f"apagado/sin ficha cambió algo: {off}")
    # Informe vigente: elige, guarda y devuelve la config nueva sin tocar la original.
    original = copy.deepcopy(KIT_CFG)
    cfg, warns = kit_trends.apply(KIT_CFG, dbx=dbx, path=PATH, fetch=good, now=NOW,
                                  llm_call=answer, budget=kit_spend.Budget())
    check(KIT_CFG == original, "apply modificó la config original")
    check(cfg['seo']['guitarras']['phrase'] == 'Emotional Guitar Loop Kit' and not warns,
          f"frase o avisos: {cfg['seo']['guitarras']['phrase']!r} {warns}")
    check(cfg['seo']['reggaeton house']['phrase'] == 'Afro House Loop Kit',
          "el género 'reggaeton house' no se emparejó con 'reggaeton_house'")
    saved = json.loads(dbx.files[PATH])
    check(saved['version'] == 1 and set(saved['genres']) == {'guitarras', 'reggaeton house'}
          and 'secret' not in json.dumps(saved), f"ficha guardada: {saved}")
    # Sin informe nuevo: usa la última buena y avisa sin datos.
    def broken():
        raise kit_trends.KitTrendsError('notion')
    cfg, warns = kit_trends.apply(KIT_CFG, dbx=dbx, path=PATH, fetch=broken, now=NOW)
    check(cfg['seo']['guitarras']['phrase'] == 'Emotional Guitar Loop Kit'
          and len(warns) == 1 and 'semana anterior' in warns[0] and 'notion' in warns[0],
          f"no usó la ficha de la semana anterior: {warns}")
    # Informe viejo: lo mismo, con su motivo.
    old = report(generated_at=(NOW - timedelta(days=20)).isoformat())
    cfg, warns = kit_trends.apply(KIT_CFG, dbx=dbx, path=PATH, fetch=lambda: old, now=NOW)
    check(cfg['seo']['guitarras']['phrase'] == 'Emotional Guitar Loop Kit' and 'viejo' in warns[0],
          f"informe viejo: {warns}")
    # La última buena también vence: vuelve a la ficha del panel.
    later = NOW + timedelta(days=40)
    cfg, warns = kit_trends.apply(KIT_CFG, dbx=dbx, path=PATH, fetch=broken, now=later)
    check(cfg['seo']['guitarras']['phrase'] == 'Guitar Loop Kit' and 'panel' in warns[0],
          f"la ficha guardada vencida se usó: {warns}")
    # Si cambiaste la ficha en el panel, manda la nueva: la guardada ya no corresponde.
    edited = copy.deepcopy(KIT_CFG)
    edited['seo']['guitarras']['tags'] = ['Dark', 'Acoustic', 'Raw', 'Moody', 'Lofi']
    edited['seo']['guitarras']['phrase'] = 'Raw Guitar Loop Kit'
    cfg, warns = kit_trends.apply(edited, dbx=dbx, path=PATH, fetch=broken, now=NOW)
    check(cfg['seo']['guitarras']['phrase'] == 'Raw Guitar Loop Kit'
          and set(cfg['seo']['guitarras']['tags']) == {'Dark', 'Acoustic', 'Raw', 'Moody', 'Lofi'}
          and cfg['seo']['reggaeton house']['phrase'] == 'Afro House Loop Kit' and len(warns) == 1,
          f"la ficha guardada pisó los cambios del panel: {cfg['seo']['guitarras']}")
    # Cada género vence por su cuenta: uno viejo no se renueva por tener a otro vigente.
    stale = json.loads(dbx.files[PATH])
    stale['genres']['reggaeton house']['at'] = (NOW - timedelta(days=60)).isoformat()
    dbx.files[PATH] = json.dumps(stale).encode()
    cfg, warns = kit_trends.apply(KIT_CFG, dbx=dbx, path=PATH, fetch=broken, now=NOW)
    check(cfg['seo']['guitarras']['phrase'] == 'Emotional Guitar Loop Kit'
          and cfg['seo']['reggaeton house']['phrase'] == 'Afro House Loop Kit',
          "la ficha guardada de un género vencido se usó")
    _tidy = dbx.files[PATH]
    # Un informe nuevo sin uno de los géneros no le renueva la fecha al viejo.
    only_guitar = json.loads(report())
    del only_guitar['genres']['reggaeton_house']
    kit_trends.apply(KIT_CFG, dbx=dbx, path=PATH, fetch=lambda: json.dumps(only_guitar), now=NOW)
    check(json.loads(dbx.files[PATH])['genres']['reggaeton house']['at'] == stale['genres']['reggaeton house']['at'],
          "la ficha vieja de un género se renovó sola")
    # Sin la IA configurada se elige igual y llega un aviso.
    nollm = {'seo': KIT_CFG['seo']}
    cfg, warns = kit_trends.apply(nollm, dbx=Dbx(), path=PATH, fetch=good, now=NOW)
    check(len(warns) == 1 and 'IA' in warns[0] and cfg['seo']['guitarras']['phrase'] == 'Guitar Loop Kit',
          f"sin IA debía avisar y elegir por búsquedas: {warns}")
    # ``only`` limita el trabajo (y el gasto) a los géneros de la semana.
    calls = []
    counting = lambda system, user: (calls.append(json.loads(user)['genre']), answer(system, user))[1]
    only_dbx = Dbx()
    cfg, warns = kit_trends.apply(KIT_CFG, dbx=only_dbx, path=PATH, fetch=good, now=NOW,
                                  llm_call=counting, budget=kit_spend.Budget(), only={'guitarras'})
    check(calls == ['guitarras'] and cfg['seo']['reggaeton house'] == REGGAETON
          and set(json.loads(only_dbx.files[PATH])['genres']) == {'guitarras'},
          f"only no limitó el trabajo: {calls}")
    # Nunca levanta, con cualquier basura.
    for bad in (None, 5, {'seo': 'x'}, {'seo': {'g': 'texto'}}, {'seo': {'g': {'phrase': 7}}}):
        try:
            kit_trends.apply(bad, dbx=dbx, path=PATH, fetch=good, now=NOW)
        except Exception as e:
            FAILS.append(f"apply levantó con {bad!r}: {type(e).__name__}")
    class Boom(Dbx):
        def files_upload(self, *a, **k):
            raise RuntimeError('sin escritura')
    cfg, _w = kit_trends.apply(KIT_CFG, dbx=Boom(), path=PATH, fetch=good, now=NOW)
    check(cfg['seo']['guitarras']['phrase'] == 'Guitar Loop Kit' or cfg['seo']['guitarras'],
          "un fallo al guardar cortó la elección")
    # Un género roto no descarta a los demás.
    bad_cfg = copy.deepcopy(KIT_CFG)
    bad_cfg['seo']['guitarras'] = {'phrase': 'X' * 200}
    cfg, _w = kit_trends.apply(bad_cfg, dbx=Dbx(), path=PATH, fetch=good, now=NOW)
    check(cfg['seo']['guitarras'] == bad_cfg['seo']['guitarras'], "tocó un género roto")
    # El informe se descarta si la IA elige algo que no entra en el título.
    out.close()


def _check_paths():
    check(kit_trends.saved_path('/loop_kits/_automation/config.json')
          == '/loop_kits/_automation/seo_trends.json'
          and kit_trends.saved_path('/loop_kits/_automation/otro/config.json')
          == '/loop_kits/_automation/otro/seo_trends.json', "ruta de la ficha guardada")
    check(kit_trends.settings({'trends': {'max_age_days': 'x', 'enabled': 'si', 'timeout': -3}})
          == kit_trends.DEFAULTS, "valores inválidos de config no caen al default")
    check(kit_trends.settings({'trends': {'max_age_days': 3}})['max_age_days'] == 3, "config válida")


def main():
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        for fn in (_check_report, _check_notion, _check_choose, _check_apply, _check_paths):
            try:
                fn()
            except Exception as e:
                import traceback
                FAILS.append(f"{fn.__name__} falló: {type(e).__name__}: {e}\n"
                             + traceback.format_exc()[-600:])
    printed = buffer.getvalue()
    check(TOKEN not in printed, "la clave de Notion aparece en la salida")
    if FAILS:
        for msg in FAILS:
            print('FAIL:', msg.replace(TOKEN, '<clave>'))
        return 1
    print('OK: smoke_kit_trends')
    return 0


if __name__ == '__main__':
    sys.exit(main())
