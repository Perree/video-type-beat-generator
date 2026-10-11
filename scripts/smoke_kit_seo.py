#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del SEO de loop kits: ficha, título, capítulos, gancho y cantidad de videos.

Sin red: Dropbox, YouTube, render, Telegram y LLM son fakes. Datos ficticios.
"""

import contextlib
import io
import json
import os
import random
import sys
import tempfile
from datetime import timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, 'scripts')):
    if p not in sys.path:
        sys.path.insert(0, p)

from smoke_kit_state import FakeDropbox  # también instala el doble de dropbox.files si falta
import smoke_kit_weekly as wk

from core import kit_publish, kit_seo, kit_settings, kit_source, kit_spend, kit_state, youtube
import run_kit_weekly

NOW = wk.NOW  # miércoles 10:00, hora de Buenos Aires
GENRE = 'genero smoke'
PHRASE = 'Guitar Loop Kit'
ARTISTS = ['Artist Uno', 'Second Act', 'The Third', 'Cuatro']
TAGS = ['Emotional', 'Dark', 'Acoustic', 'Sad', 'RnB', 'Afro', 'Sample Pack']
FICHA = {'phrase': PHRASE, 'artists': ARTISTS, 'tags': TAGS}
HOOK_TEXT = 'Dark, emotional guitar loops inspired by Artist Uno. Free to download!'
TEMPLATES = {'title_template': '{name} | canal smoke',
             'description_template': '{hook}\n\nDescarga {name}: {link}\n\n{chapters}\n\nfin',
             'link': 'https://shop.example/p'}

_failed = []


def check(cond, msg):
    if not cond:
        _failed.append(msg)
        print('FAIL:', msg)


def _raises(fn, *args):
    try:
        fn(*args)
    except kit_seo.KitSeoError:
        return True
    return False


def _rules_ok(title, name=None):
    at = title.lower().find(PHRASE.lower())
    return (len(title) <= kit_seo.TITLE_MAX and 0 <= at
            and at + len(PHRASE) <= kit_seo.PHRASE_WITHIN and '<' not in title
            and '>' not in title and '  ' not in title and (name is None or name in title))


# --- Ficha ---

def _check_ficha():
    seo = kit_seo.validate({**FICHA, 'artists': ARTISTS + [' artist  uno ', '']})
    check(seo['artists'] == ARTISTS and seo['tags'] == TAGS and seo['examples'] == []
          and seo['title_template'] == kit_seo.DEFAULT_TEMPLATE,
          'la ficha se normaliza (sin vacíos ni repetidos) y usa la plantilla de fábrica')
    for label, bad in (
            ('sin frase', {**FICHA, 'phrase': ' '}),
            ('41 artistas', {**FICHA, 'artists': [f'a{i}' for i in range(41)]}),
            ('etiqueta de 81 caracteres', {**FICHA, 'tags': ['x' * 81]}),
            ('artistas que no son lista', {**FICHA, 'artists': 'uno, dos'}),
            ('artista que no es texto', {**FICHA, 'artists': [3]}),
            ('frase que no es texto', {**FICHA, 'phrase': ['x']}),
            ('marcador desconocido', {**FICHA, 'title_template': '{phrase} {name} {artista}'}),
            ('plantilla sin nombre', {**FICHA, 'title_template': '{phrase} ({tags})'}),
            ('no es un objeto', ['x'])):
        check(_raises(kit_seo.validate, bad), f'ficha inválida rechazada: {label}')
    check(kit_seo.validate({**FICHA, 'tags': ['x' * 80], 'artists': ['a'] * 60})['artists'] == ['a'],
          'los límites son 40 entradas distintas de hasta 80 caracteres')

    cfg = {'seo': {'Genero_Smoke': FICHA, 'vacio': {'phrase': '', 'artists': []},
                   'roto': {'phrase': PHRASE, 'artists': 'x'}}}
    check(kit_seo.load({}, GENRE) is None and kit_seo.load({'seo': 'x'}, GENRE) is None
          and kit_seo.load(cfg, 'otro genero') is None and kit_seo.load(cfg, '') is None,
          'sin ficha para el género devuelve None')
    check(kit_seo.load(cfg, 'vacio') is None, 'una ficha vacía no cuenta como ficha')
    check((kit_seo.load(cfg, GENRE) or {}).get('phrase') == PHRASE,
          'el género se busca sin distinguir mayúsculas ni guiones bajos')
    check(_raises(kit_seo.load, cfg, 'roto'), 'una ficha mal formada se informa, no se usa')
    half = {'phrase': ' ', 'artists': ARTISTS}
    check(kit_seo.is_blank(half) and not kit_seo.is_empty(half)
          and kit_seo.load({'seo': {GENRE: half}}, GENRE) is None
          and kit_seo.validate(half, partial=True)['artists'] == ARTISTS,
          'sin frase no hay ficha, aunque haya artistas cargados')
    check(_raises(kit_seo.validate, {**FICHA, 'phrase': 'Una frase de busqueda demasiado larga'}),
          'una frase que no entra en los primeros 40 caracteres se rechaza al guardar')
    long_artist = 'Artista De Nombre Largo'
    check(kit_seo.unfit_artists(kit_seo.validate({**FICHA, 'artists': ARTISTS + [long_artist]}))
          == [long_artist], 'se informa qué artistas no dejan la frase al principio')


# --- Título ---

def _check_title():
    seo = kit_seo.validate(FICHA)
    names = ['NOVA', 'BRISA', 'N' * 40, 'Con  espacios   dobles', 'Raro <b> {tags} {name}']
    for seed in range(40):
        for name in names:
            title, variant = kit_seo.build_title(seo, name, [], random.Random(seed))
            clean = ' '.join(name.replace('<', '').replace('>', '').split())
            if not (title and _rules_ok(title, clean)):
                check(False, f'título fuera de regla (seed {seed}): {len(title or "")} caracteres')
                return
            if variant['title'] != title or variant['phrase'] != PHRASE \
                    or variant['artist'] not in ARTISTS or not set(variant['tags']) <= set(TAGS):
                check(False, f'variante inconsistente (seed {seed})')
                return
    one = kit_seo.build_title(seo, 'NOVA', [], random.Random(7))
    check(one == kit_seo.build_title(seo, 'NOVA', [], random.Random(7)),
          'el título es determinístico con el rng')
    check(one[0].startswith(f'[FREE] {one[1]["artist"]} {PHRASE} - "NOVA" | ('),
          'la plantilla de fábrica arma artista, frase, nombre y etiquetas')
    title, _v = kit_seo.build_title(seo, '{tags} y {artist}', [], random.Random(1))
    check('"{tags} y {artist}"' in title, 'un nombre con llaves queda literal')

    # Nombre largo: se recortan etiquetas, nunca el nombre ni la frase.
    long_name = 'L' * 52
    title, variant = kit_seo.build_title(seo, long_name, [], random.Random(3))
    check(title and _rules_ok(title, long_name) and len(variant['tags']) < 3,
          'con un nombre largo se recortan las etiquetas')
    check(kit_seo.build_title(seo, 'L' * 95, [], random.Random(3)) == (None, None),
          'si no entra en 100 caracteres no hay título de SEO (no se corta el nombre)')

    # Ciclo de un kit: ninguna variante se repite y el artista principal rota.
    used, rng = [], random.Random(11)
    for _ in range(12):
        title, variant = kit_seo.build_title(seo, 'NOVA', used, rng, [v['title'] for v in used])
        key = kit_seo._variant_key(variant)
        if key in {kit_seo._variant_key(v) for v in used} or title in {v['title'] for v in used}:
            check(False, f'variante repetida en el video {len(used) + 1} del kit')
            break
        used.append(variant)
    check(len({v['artist'] for v in used[:4]}) == 4,
          'los primeros videos de un kit usan artistas principales distintos')
    check(used[4]['artist'] == used[0]['artist'],
          'agotados los artistas vuelve el que hace más que no sale')

    # Sin títulos repetidos de los últimos videos del canal.
    first, _v = kit_seo.build_title(seo, 'NOVA', [], random.Random(5))
    again, _v = kit_seo.build_title(seo, 'NOVA', [], random.Random(5), [first])
    check(again and again != first, 'no repite un título reciente del canal')

    # {artists}: principal primero y el resto rotado.
    multi = kit_seo.validate({**FICHA, 'title_template': '{phrase} "{name}" {artists} ({tags})'})
    title, variant = kit_seo.build_title(multi, 'NOVA', [], random.Random(2))
    check(variant['artists'][0] == variant['artist'] and len(variant['artists']) > 1
          and ', '.join(variant['artists']) in title and _rules_ok(title, 'NOVA'),
          '{artists} lleva al principal primero')

    # Un artista que empuja la frase más allá del carácter 40 no se usa.
    far = kit_seo.validate({**FICHA, 'artists': ['Un artista de nombre larguisimo ' * 2]})
    title, variant = kit_seo.build_title(far, 'NOVA', [], random.Random(2))
    check(title and _rules_ok(title, 'NOVA') and variant['artist'] == '',
          'sin artista que deje la frase al principio, el título sale sin artista')
    front = kit_seo.validate({**FICHA, 'title_template': '{artists} {phrase} "{name}" ({tags})'})
    title, variant = kit_seo.build_title(front, 'NOVA', [], random.Random(2))
    check(title and _rules_ok(title, 'NOVA') and 1 <= len(variant['artists']) < 3
          and variant['artist'], '{artists} se acorta para que la frase quede al principio')
    odd = [{'artist': 'Artist Uno', 'tags': 7, 'title': 3}, {'artist': None}, 'x']
    check(kit_seo.build_title(seo, 'NOVA', odd, random.Random(2))[0],
          'una variante guardada con forma rara no rompe el título')
    state = {'packs': {'/p': {'id': 1}}, 'runs': [
        'x', {'id': None, 'pack_id': 1, 'seo': {'artist': 'A', 'title': 5}},
        {'id': 2, 'pack_id': 1, 'seo': {'artist': 'B', 'title': 'T'}}, {'id': 3, 'seo': 'x'}]}
    used_v, recent = kit_seo.history(state, '/p')
    check(len(used_v) == 2 and recent == ['T'], 'el historial tolera corridas con datos raros')
    bare = kit_seo.validate({'phrase': PHRASE})
    check(kit_seo.build_title(bare, 'NOVA', [], random.Random(2))[0] == f'[FREE] {PHRASE} - "NOVA"',
          'una ficha con solo la frase no deja paréntesis ni separadores sueltos')
    late = kit_seo.validate({**FICHA, 'title_template': '"{name}" de regalo para vos: {phrase}'})
    check(kit_seo.build_title(late, 'N' * 30, [], random.Random(2)) == (None, None),
          'una plantilla que deja la frase lejos no da título de SEO')


# --- Capítulos ---

def _segs(*lengths, start=0.0):
    return [{'name': f'SECRETO {i} 120bpm Cmin.wav', 'path': f'/x/{i}.wav',
             'start': start, 'end': start + length} for i, length in enumerate(lengths)]


def _check_chapters():
    text, warn = kit_seo.chapters(_segs(28, 28, 28, 28, 28))
    check(text == '0:00 Loop 1\n0:28 Loop 2\n0:56 Loop 3\n1:24 Loop 4\n1:52 Loop 5' and not warn,
          f'capítulos acumulados en m:ss: {text!r}')
    check('SECRETO' not in text and 'bpm' not in text.lower(),
          'los capítulos no llevan nombres de archivo ni BPM')
    check(kit_seo.chapters(_segs(20.5, 30.25, 15, start=4.0))[0]
          == '0:00 Loop 1\n0:20 Loop 2\n0:50 Loop 3', 'cada tramo dura end - start')
    check(kit_seo.chapters(_segs(1900, 1900, 1900))[0]
          == '0:00:00 Loop 1\n0:31:40 Loop 2\n1:03:20 Loop 3', 'h:mm:ss si pasa de una hora')
    for label, segs in (('dos loops', _segs(60, 60)), ('un loop de 9,5 s', _segs(30, 9.5, 30)),
                        ('último de 9 s', _segs(30, 30, 9)), ('sin tramos', []),
                        ('tramo sin datos', [{'start': 0}] * 3),
                        ('tramo de duración cero', _segs(30, 0, 30))):
        text, warn = kit_seo.chapters(segs)
        check(text == '' and warn, f'capítulos omitidos con aviso: {label}')
    check(kit_seo.chapters(_segs(10, 10, 10))[0].count('\n') == 2,
          'tres loops de 10 s justos son válidos')
    check(kit_seo.chapters(_segs(30, 6, 30, 30))[0]
          == '0:00 Loop 1\n0:30 Loops 2-3\n1:06 Loop 4',
          'un loop de menos de 10 s comparte capítulo con el siguiente')
    check(kit_seo.chapters(_segs(30, 30, 30, 4))[0] == '0:00 Loop 1\n0:30 Loop 2\n1:00 Loops 3-4',
          'un último loop corto se suma al capítulo anterior')
    check(kit_seo.chapters(_segs(10.7, 10.1, 10.2, 12))[0].splitlines()[3] == '0:31 Loop 4',
          'la suma de duraciones no arrastra error de coma flotante')


# --- Gancho ---

class SpendStore:
    """Lo mínimo que ``kit_spend.Budget`` usa de un store."""

    def __init__(self, spent=0.0):
        self.spent = spent

    def spend_month(self, month):
        return self.spent

    def add_spend(self, month, usd, images=0, verifications=0):
        self.spent = round(self.spent + usd, 4)


def _budget(store, **cfg):
    return kit_spend.Budget(kit_spend.settings({'spend': cfg}), store, NOW)


def _check_hook():
    seo = kit_seo.validate(FICHA)
    calls = []

    def llm(system, user):
        calls.append((system, user))
        return f'  "{HOOK_TEXT}"  '

    store = SpendStore()
    out = kit_seo.hook('guitarras tristes', GENRE, seo, llm_call=llm, budget=_budget(store))
    check(out == HOOK_TEXT and len(calls) == 1, f'el gancho sale limpio en una sola llamada: {out!r}')
    system, user = calls[0]
    check('inspired by' in system and 'guitarras tristes' in user and PHRASE in user
          and 'Emotional' in user and GENRE in user,
          'el prompt lleva la descripción, el género y las palabras clave de la ficha')
    check(store.spent == 0.01, f'la llamada de texto cuenta en el gasto del mes: {store.spent}')
    check(kit_spend.settings({})['text_cost_usd'] == 0.01
          and kit_spend.settings({'spend': {'text_cost_usd': 0.02}})['text_cost_usd'] == 0.02,
          'text_cost_usd es configurable (default 0.01)')
    store = SpendStore()
    kit_seo.hook('x', GENRE, seo, llm_call=llm, budget=_budget(store, text_cost_usd=0.02))
    check(store.spent == 0.02, 'se cobra el costo de texto configurado')

    # Tope del mes: ni llama ni cobra.
    calls.clear()
    store = SpendStore(spent=9.995)
    check(kit_seo.hook('x', GENRE, seo, llm_call=llm, budget=_budget(store)) == ''
          and not calls and store.spent == 9.995, 'con el tope alcanzado no se llama al modelo')
    check(kit_seo.hook('x', GENRE, seo, llm_call=llm,
                       budget=_budget(SpendStore(9.98))) == HOOK_TEXT,
          'justo por debajo del tope todavía se genera')

    def boom(system, user):
        raise RuntimeError('sin red')

    store = SpendStore()
    check(kit_seo.hook('x', GENRE, seo, llm_call=boom, budget=_budget(store)) == '',
          'un fallo del modelo devuelve vacío sin levantar')
    check(store.spent == 0.01, 'un fallo dudoso se cuenta como cobrado')

    class BrokenStore(SpendStore):
        def spend_month(self, month):
            raise OSError('estado caido')
    calls.clear()
    check(kit_seo.hook('x', GENRE, seo, llm_call=llm, budget=_budget(BrokenStore())) == ''
          and not calls, 'si el gasto no se puede leer no se llama al modelo')
    check(kit_seo.hook('x', GENRE, seo) == '' and kit_seo.hook('x', GENRE, seo, cfg={}) == '',
          'sin modelo configurado no hay gancho ni llamada')
    check(kit_seo.hook('x', GENRE, seo, llm_call=llm) == HOOK_TEXT, 'sin budget (corrida local) funciona')

    for label, raw in (('vacío', '   '), ('no es texto', None),
                       ('link', 'Great loops, get them at https://x.example now.'),
                       ('dominio', 'Great loops at shop.com for you.'),
                       ('hashtag', 'Great loops #free for you.'),
                       ('afirmación falsa', 'These loops were made by Artist Uno himself.'),
                       ('artista sin "inspired by"', 'Guitar loops. Second Act would love them.'),
                       ('palabra de estilo lejos del artista',
                        'Loops loved by Artist Uno, inspired melodies for you.'),
                       ('"type" suelto no alcanza', 'This type of kit was built for Second Act.'),
                       ('autoría de alguien fuera de la ficha', 'Dark loops made by Someone Else.'),
                       ('featuring', 'Dark guitar loops feat. a famous singer.'),
                       ('la fórmula en otra frase', 'Loops inspired by the night. Cuatro is here.'),
                       ('cifras inventadas', 'Dark guitar loops with 50 melodies at 140 BPM.')):
        check(kit_seo.clean_hook(raw, seo) == '', f'gancho descartado: {label}')
    cleaned = kit_seo.clean_hook('Sad <b>loops</b> \U0001F525 for you. Second one! Third one.', seo)
    check(cleaned == 'Sad bloops/b for you. Second one!',
          f'sin emojis, sin < > y hasta dos frases: {cleaned!r}')
    for ok in ('Loops in the style of Second Act and inspired by Cuatro.',
               'Melodies inspired by Artist Uno, Second Act and The Third.',
               'Sad Cuatro-type guitars and Artist Uno style melodies.'):
        check(kit_seo.clean_hook(ok, seo) == ok, f'una referencia de estilo sí se admite: {ok}')
    word = kit_seo.validate({**FICHA, 'artists': ['Future', 'Uno']})
    check(kit_seo.clean_hook('The future of sad guitars, unorthodox and raw.', word),
          'un artista que también es una palabra común no descarta el gancho')
    check(kit_seo.clean_hook('Sad guitars that Future would pick.', word) == '',
          'pero nombrado como artista necesita la fórmula')
    check(kit_seo.clean_hook('Dark guitars with 12 loops.', seo, 'trae 12 loops de guitarra')
          and kit_seo.clean_hook('Dark guitars with 13 loops.', seo, 'trae 12 loops') == '',
          'una cifra solo pasa si está en la descripción del kit')


# --- Marcadores de la descripción ---

def _check_publish():
    plain = {'title_template': '{name} | canal', 'link': 'https://shop.example/p',
             'description_template': 'Kit {name}\n\n\n{link}\n\nTags: {tags}'}
    base = kit_publish._metadata('canal', 'Pack', plain)
    check(base == kit_publish._metadata('canal', 'Pack', plain, None, None),
          'sin los argumentos nuevos el resultado es idéntico')
    check(base == kit_publish._metadata('canal', 'Pack', plain, None,
                                        {'hook': 'GANCHO', 'chapters': '0:00 Loop 1'}),
          'sin marcadores en la plantilla la descripción no cambia')
    check(base == kit_publish._metadata('canal', 'Pack', plain, None, {'hook': '', 'chapters': ''}),
          'sin marcadores y sin contenido tampoco cambia (ni los saltos de línea)')
    title, body, _tags = kit_publish._metadata(
        'canal', 'Pack', plain, 'Titulo armado | [FREE]', {'hook': 'GANCHO'})
    check(title == 'Titulo armado | [FREE]' and body == base[1], 'el título dado se usa tal cual')

    marked = dict(plain, description_template='{hook}\n\nKit {name}: {link}\n\n{chapters}\n\nfin')
    _t, body, _tags = kit_publish._metadata(
        'canal', 'Pack', marked, None, {'hook': 'GANCHO {chapters}', 'chapters': '0:00 Loop 1'})
    check(body == 'GANCHO {chapters}\n\nKit Pack: https://shop.example/p\n\n0:00 Loop 1\n\nfin',
          f'{{hook}} y {{chapters}} se reemplazan en una sola pasada: {body!r}')
    _t, body, _tags = kit_publish._metadata('canal', 'Pack', marked, None,
                                            {'hook': '', 'chapters': ''})
    check(body == 'Kit Pack: https://shop.example/p\n\nfin',
          f'un marcador sin contenido no deja huecos: {body!r}')
    _t, body, _tags = kit_publish._metadata(
        'canal', '{hook} {link}', marked, None, {'hook': 'GANCHO', 'chapters': 'CAPS'})
    check(body == 'GANCHO\n\nKit {hook} {link}: https://shop.example/p\n\nCAPS\n\nfin',
          f'un nombre de kit con marcadores queda literal: {body!r}')
    spaced = dict(plain, description_template='A {name}\n\n\n\nB\n{hook}\nC\r\n\r\n{chapters}')
    _t, body, _tags = kit_publish._metadata('canal', 'Pack', spaced, None,
                                            {'hook': '', 'chapters': ''})
    check(body == 'A Pack\n\n\n\nB\nC', f'quitar un marcador vacío no toca otros saltos: {body!r}')
    check(kit_publish.desc_markers(marked) == {'hook', 'chapters'}
          and kit_publish.desc_markers(plain) == set() and kit_publish.desc_markers(None) == set(),
          'desc_markers dice qué marcadores trae la plantilla del canal')
    _t, body, _tags = kit_publish._metadata('canal', 'Pack', marked)
    check('{hook}' in body and '{chapters}' in body,
          'sin desc_vars los marcadores quedan como estaban (comportamiento anterior)')


# --- Config del panel (sin Qt) ---

def _check_settings():
    good = {'channel': '', 'genres': [GENRE, 'otro'], 'refs_root': '', 'cover_mode': 'manual',
            'slots': [{'weekday': 0, 'hour': 18, 'minute': 0}]}
    plain = kit_settings.validate_settings(good)
    check('seo' not in plain and 'vary_name' not in plain,
          'sin campos de SEO en el formulario no se toca nada')
    base = {'kit_preview': {'seo': {'viejo': FICHA}, 'names': {'model': 'm'}}}
    check(kit_settings.apply_to_config(base, plain)['kit_preview']['seo'] == {'viejo': FICHA},
          'guardar sin campos de SEO conserva las fichas')

    form = {**good, 'vary_name': True, 'seo': {
        GENRE: {**FICHA, 'title_template': '', 'examples': ['  Un   ejemplo ']},
        'otro': {'phrase': '', 'artists': [], 'tags': [], 'title_template': '', 'examples': []}}}
    out = kit_settings.validate_settings(form)
    check(out['seo'] == {GENRE: {**FICHA, 'examples': ['Un ejemplo']}} and out['vary_name'] is True,
          f"la ficha se guarda normalizada y la vacía se descarta: {out.get('seo')}")
    kp = kit_settings.apply_to_config(base, out)['kit_preview']
    check(kp['seo'] == out['seo'] and kp['names'] == {'model': 'm', 'vary_name': True},
          'la ficha y "variar el nombre" van a kit_preview')
    check(kit_seo.load(kp, GENRE)['title_template'] == kit_seo.DEFAULT_TEMPLATE,
          'el worker lee la ficha guardada por el panel')
    back = kit_settings.form_from_config({'kit_preview': kp})
    check(back['vary_name'] is True and back['seo'][GENRE]['artists'] == ARTISTS
          and back['seo'][GENRE]['examples'] == ['Un ejemplo'], 'el formulario vuelve a cargar la ficha')
    empty = kit_settings.validate_settings({**good, 'seo': {}, 'vary_name': False})
    kp = kit_settings.apply_to_config(base, empty)['kit_preview']
    check('seo' not in kp and kp['names']['vary_name'] is False, 'sin fichas la clave se quita')
    for label, bad in (('ficha mal formada', {'seo': {GENRE: {**FICHA, 'artists': ['x' * 81]}}}),
                       ('fichas que no son un objeto', {'seo': ['x']})):
        try:
            kit_settings.validate_settings({**good, **bad})
            check(False, f'ajustes de SEO inválidos aceptados: {label}')
        except kit_settings.SettingsError as exc:
            check('x' * 81 not in str(exc), 'el error no repite el contenido de la ficha')
    try:
        kit_settings.apply_to_config({'kit_preview': {}}, out)
        check(False, 'variar el nombre sin modelo de texto debía rechazarse')
    except kit_settings.SettingsError:
        pass
    # Ficha a medias de un género de la lista: se guarda como está y el worker no la usa.
    half = {'phrase': '', 'artists': ['Uno'], 'tags': [], 'title_template': '', 'examples': []}
    out_half = kit_settings.validate_settings({**good, 'seo': {GENRE: half}})
    check(out_half['seo'] == {GENRE: {'phrase': '', 'artists': ['Uno'], 'tags': []}}
          and kit_seo.load(out_half, GENRE) is None, 'una ficha sin frase no traba el guardado')
    # Género que ya no está en la lista: la ficha válida se conserva, la rota se descarta.
    orphans = kit_settings.validate_settings({**good, 'seo': {
        'quitado': FICHA, 'roto': {'phrase': PHRASE, 'artists': ['x' * 81]}}})
    check(list(orphans['seo']) == ['quitado'],
          'una ficha huérfana y rota no traba el guardado')
    long_artist = 'Artista De Nombre Largo'
    notes = kit_settings.seo_notes({GENRE: {**FICHA, 'artists': ARTISTS + [long_artist]},
                                    'otro': half})
    check(len(notes) == 1 and long_artist in notes[0] and '1 artista' in notes[0]
          and not kit_settings.seo_notes({GENRE: FICHA}),
          f'el panel avisa qué artistas no entran: {notes}')
    blob = json.dumps(kit_settings.apply_to_config(base, out))
    check('key' not in blob.lower() and 'token' not in blob.lower(),
          'la config de SEO no agrega claves ni tokens')


# --- Worker completo (fakes) ---

class Uploads:
    items = []


def _fake_upload(channel, video, title, description='', tags=None, thumbnail=None,
                 privacy='private', publish_at=None, **_k):
    Uploads.items.append({'title': title, 'description': description})
    vid = f'vid{len(Uploads.items):03d}'
    return {'youtube_id': vid, 'url': f'https://youtu.be/{vid}', 'privacy': privacy,
            'thumbnail_error': ''}


def _real_name(pack_name):
    return f'Real {pack_name[-1]}'


def _dropbox(packs):
    dbx = FakeDropbox()
    catalog = [{'folder': p['name'], 'name': _real_name(p['name']), 'genre': GENRE, 'active': True,
                'payhip_url': 'https://shop.example/p', 'description': 'guitarras tristes'}
               for p in packs]
    dbx.files[kit_settings.KITS_PATH] = ('0000000000c1', json.dumps(catalog).encode())
    return dbx


def _config(**extra):
    return {'kit_preview': {'dropbox_root': '/smoke', 'genres': [GENRE], **extra}}


def _run(dbx, config, llm=None, now=NOW, packs=None, dry_run=False, out_dir=None,
         templates=None):
    Uploads.items = []
    tg = wk.FakeTelegram()
    hooks = {'list_packs_fn': (lambda *_a, **_k: packs) if packs else wk._packs,
             'render_fn': wk._fake_render, 'cut_fn': wk._fake_cut,
             'end_fn': lambda path, **_k: 28.0}
    if llm:
        hooks['llm_call'] = llm
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = run_kit_weekly.run_weekly(
            app_config=config, channel='canal-smoke', channel_templates=dict(templates or TEMPLATES),
            dbx=dbx, dry_run=dry_run, now=now, seed=1, notifier=tg, hooks=hooks,
            output_dir=out_dir)
    return code, list(Uploads.items), tg, buf.getvalue()


def _check_worker(out_dir):
    packs = wk._packs()
    calls = []

    def llm(system, user):
        calls.append(system)
        if 'curador' in system:  # kit_names
            return 'Costa Azul\nNimbo\nDelta'
        return HOOK_TEXT

    # 1) Sin ficha: título de la plantilla del canal, sin gancho, capítulos ni llamadas.
    dbx = _dropbox(packs)
    code, plain, _tg, _log = _run(dbx, _config(), llm, out_dir=out_dir)
    check(code == 0 and len(plain) == 3 and not calls, f'sin ficha: code={code} subidas={len(plain)}')
    check(all(u['title'].startswith('Real ') and u['title'].endswith(' | canal smoke')
              for u in plain), 'sin ficha el título sale de la plantilla del canal')
    check(all('Loop 1' not in u['description'] and '{' not in u['description'] for u in plain),
          'sin ficha la descripción no lleva capítulos ni marcadores sueltos')
    check(not any('seo' in r for r in kit_state.load(dbx=dbx)['runs']),
          'sin ficha no se guarda ninguna variante')
    dbx_other = _dropbox(packs)
    _c, other, _tg, _log = _run(dbx_other, _config(seo={'otro genero': FICHA}), llm, out_dir=out_dir)
    check([u['title'] for u in other] == [u['title'] for u in plain] and not calls,
          'la ficha de otro género no cambia nada')

    # 2) Con ficha: título por SEO con el nombre real, gancho, capítulos y variante guardada.
    names = {'base_url': 'https://llm.example/v1', 'model': 'm'}
    dbx = _dropbox(packs)
    code, ups, tg, log = _run(dbx, _config(seo={GENRE: FICHA}, names=names), llm, out_dir=out_dir)
    state = kit_state.load(dbx=dbx)
    check(code == 0 and len(ups) == 3, f'con ficha: code={code} subidas={len(ups)}')
    check(all(_rules_ok(u['title']) and '"Real ' in u['title'] for u in ups),
          f"con ficha el título cumple las reglas y lleva el nombre real: {[u['title'] for u in ups]}")
    check(all(u['description'].startswith(HOOK_TEXT + '\n\nDescarga Real ')
              and '\n\n0:00 Loop 1\n0:28 Loop 2\n' in u['description']
              and u['description'].endswith('\n\nfin') and 'utm_content=' in u['description']
              for u in ups), 'la descripción lleva gancho, link y capítulos')
    check(len(calls) == 3 and all('curador' not in c for c in calls),
          f'una llamada de texto por video y ninguna para el nombre: {len(calls)}')
    seos = [r.get('seo') for r in state['runs']]
    check(all(s and s['phrase'] == PHRASE and s['artist'] in ARTISTS and s['tags']
              and s['title'] == u['title'] for s, u in zip(seos, ups)),
          'cada corrida guarda su variante (artista, etiquetas, frase) junto al youtube_id')
    check(not any(r.get('video_name') for r in state['runs']),
          'con ficha no se guarda un nombre inventado')
    month = kit_spend.month_entry(state, kit_spend.month_key(NOW))
    check(month['usd'] == 0.03, f'el gasto de texto de la corrida queda en el mes: {month}')
    check(not any(name in log + ''.join(tg.sent) for name in wk.PACK_NAMES),
          'ni el log ni el aviso nombran un kit')

    # 3) El modelo falla: los videos salen igual, sin gancho y con capítulos.
    def boom(system, user):
        raise RuntimeError('sin red')
    dbx = _dropbox(packs)
    code, ups, _tg, _log = _run(dbx, _config(seo={GENRE: FICHA}, names=names), boom,
                                out_dir=out_dir)
    check(code == 0 and len(ups) == 3 and all(
        u['description'].startswith('Descarga Real ') and '0:00 Loop 1' in u['description']
        and _rules_ok(u['title']) for u in ups), 'el fallo del LLM no corta el video')

    # 4) Tope del mes en cero: sin llamadas, con título.
    calls.clear()
    dbx = _dropbox(packs)
    code, ups, _tg, _log = _run(
        dbx, _config(seo={GENRE: FICHA}, names=names, spend={'monthly_cap_usd': 0}), llm,
        out_dir=out_dir)
    check(code == 0 and len(ups) == 3 and not calls and all(_rules_ok(u['title']) for u in ups),
          'con el tope alcanzado el video sale sin gancho, nunca sin título')
    check(any('sin gancho' in t and 'tope de gasto' in t for t in _tg.sent),
          f'el tope que frena el gancho se avisa: {_tg.sent}')

    # 4b) Plantilla de descripción sin marcadores: ni llamada paga ni aviso de capítulos.
    calls.clear()
    bare = {'title_template': '{name} | canal smoke', 'description_template': 'Kit {name}',
            'link': 'https://shop.example/p'}
    dbx = _dropbox(packs)
    code, ups, tg, _log = _run(dbx, _config(seo={GENRE: FICHA}, names=names), llm,
                               out_dir=out_dir, templates=bare)
    month = kit_spend.month_entry(kit_state.load(dbx=dbx), kit_spend.month_key(NOW))
    check(code == 0 and len(ups) == 3 and not calls and month['usd'] == 0
          and all(_rules_ok(u['title']) and u['description'].startswith('Kit Real ') for u in ups),
          f'sin {{hook}} en la plantilla no se paga el gancho: {len(calls)} llamadas, {month}')
    check(not any('capítulos' in t or 'gancho' in t for t in tg.sent),
          'sin marcadores no hay avisos de gancho ni de capítulos')

    # 4c) Un fallo al armar el SEO no descarta el video ya renderizado.
    real_build = kit_seo.build_title

    def broken(*_a, **_k):
        raise TypeError('estado raro')
    kit_seo.build_title = broken
    try:
        dbx = _dropbox(packs)
        code, ups, tg, _log = _run(dbx, _config(seo={GENRE: FICHA}, names=names), llm,
                                   out_dir=out_dir)
    finally:
        kit_seo.build_title = real_build
    check(code == 0 and len(ups) == 3 and wk.Counters.renders >= 3
          and all(u['title'].endswith(' | canal smoke') for u in ups)
          and any('No se pudo armar el SEO' in t for t in tg.sent),
          'un fallo del SEO deja el video con la plantilla del canal y avisa')
    check(len(kit_state.load(dbx=dbx)['runs']) == 3, 'y ningún kit se saltea por eso')

    # 5) Ficha mal formada: aviso y plantilla del canal, la corrida no se corta.
    dbx = _dropbox(packs)
    code, ups, tg, _log = _run(dbx, _config(seo={GENRE: {'phrase': PHRASE, 'tags': 'x'}}), llm,
                               out_dir=out_dir)
    check(code == 0 and len(ups) == 3 and all(u['title'].endswith(' | canal smoke') for u in ups)
          and any('ficha de SEO' in t for t in tg.sent), 'una ficha mal formada avisa y no corta')

    # 6) "Variar también el nombre": nombre de una palabra dentro del título por SEO.
    calls.clear()
    dbx = _dropbox(packs)
    one = [{'weekday': 2, 'hour': 18, 'minute': 0}]
    code, ups, _tg, _log = _run(
        dbx, _config(seo={GENRE: FICHA}, names={**names, 'vary_name': True}, slots=one), llm,
        out_dir=out_dir)
    run = kit_state.load(dbx=dbx)['runs'][0]
    check(code == 0 and len(ups) == 1 and '"Nimbo"' in ups[0]['title']
          and run.get('video_name') == 'Nimbo' and _rules_ok(ups[0]['title']),
          f"vary_name usa un nombre de una palabra: {[u['title'] for u in ups]}")
    month = kit_spend.month_entry(kit_state.load(dbx=dbx), kit_spend.month_key(NOW))
    check(month['usd'] == 0.02 and len(calls) == 2,
          f'el nombre y el gancho cuentan como gasto de texto: {month}')
    calls.clear()
    dbx = _dropbox(packs)
    code, ups, tg, _log = _run(
        dbx, _config(seo={GENRE: FICHA}, names={**names, 'vary_name': True}, slots=one,
                     spend={'monthly_cap_usd': 0}), llm, out_dir=out_dir)
    check(code == 0 and len(ups) == 1 and not calls and '"Real ' in ups[0]['title']
          and any('sin nombre generado' in t and 'tope de gasto' in t for t in tg.sent),
          'con el tope alcanzado tampoco se llama al modelo para el nombre')

    # 7) Un solo horario configurado: un solo video (y un solo slot en el dry-run).
    dbx = _dropbox(packs)
    code, ups, _tg, _log = _run(dbx, _config(slots=one), out_dir=out_dir)
    check(code == 0 and len(ups) == 1 and len(kit_state.load(dbx=dbx)['runs']) == 1,
          f'con un horario configurado sale un solo video: {len(ups)}')
    dbx = _dropbox(packs)
    code, ups, tg, _log = _run(dbx, _config(slots=one), dry_run=True, out_dir=out_dir)
    check(code == 0 and not ups and '1 kit(s) distintos elegidos para 1 slots' in tg.sent[0],
          f'el dry-run con un horario elige un kit: {tg.sent}')
    two = one + [{'weekday': 4, 'hour': 18, 'minute': 0}]
    code, ups, _tg, _log = _run(_dropbox(packs), _config(slots=two), out_dir=out_dir)
    check(len(ups) == 2, 'con dos horarios salen dos videos')
    four = two + [{'weekday': 0, 'hour': 18, 'minute': 0}, {'weekday': 1, 'hour': 18, 'minute': 0}]
    code, ups, _tg, _log = _run(_dropbox(packs), _config(slots=four), out_dir=out_dir)
    check(len(ups) == 3, 'el máximo sigue siendo 3 videos por corrida')

    # 8) Ciclo de un kit: tres videos del mismo kit, tres variantes distintas.
    solo = packs[:1]
    dbx = _dropbox(solo)
    cfg = _config(seo={GENRE: FICHA}, slots=one)
    titles = []
    for week in range(3):
        code, ups, _tg, _log = _run(dbx, cfg, now=NOW + timedelta(days=8 * week), packs=solo,
                                    out_dir=out_dir)
        titles += [u['title'] for u in ups]
    seos = [r['seo'] for r in kit_state.load(dbx=dbx)['runs']]
    check(len(titles) == 3 and len(set(titles)) == 3
          and len({kit_seo._variant_key(s) for s in seos}) == 3
          and len({s['artist'] for s in seos}) == 3,
          f'el ciclo de un kit no repite variante ni artista principal: {len(set(titles))}')


def main() -> int:
    real_download, real_upload = kit_source.download_pack_files, youtube.upload
    kit_source.download_pack_files = wk._fake_download
    youtube.upload = _fake_upload
    try:
        _check_ficha()
        _check_title()
        _check_chapters()
        _check_hook()
        _check_publish()
        _check_settings()
        with tempfile.TemporaryDirectory() as out_dir:
            _check_worker(out_dir)
    finally:
        kit_source.download_pack_files, youtube.upload = real_download, real_upload
    if _failed:
        print(f'{len(_failed)} chequeo(s) fallaron.')
        return 1
    print('OK: smoke_kit_seo')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
