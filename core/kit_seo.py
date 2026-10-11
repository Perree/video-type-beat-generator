# -*- coding: utf-8 -*-
"""SEO de los videos de loop kits: título por ficha de género, capítulos y gancho.

La ficha vive en la config del canal (``kit_preview.seo.<genero>``), no en el repo:
``{phrase, artists[], tags[], title_template, examples[]}``. El título lo arma el código con
esa ficha y el nombre real del kit; ningún texto del título sale de un modelo de lenguaje.
El modelo solo escribe el gancho de la descripción (1 o 2 frases), y si falla o el tope de
gasto no deja, el video sale sin gancho. Solo librería estándar; los avisos no llevan
nombres de kit ni de archivo.
"""
import re
import unicodedata
from functools import partial

DEFAULT_TEMPLATE = '[FREE] {artist} {phrase} - "{name}" | ({tags})'
MARKERS = ('artist', 'artists', 'phrase', 'name', 'tags')
FIELDS = ('phrase', 'artists', 'tags', 'title_template', 'examples')
MAX_ITEMS = 40
MAX_ITEM_LEN = 80
MAX_TEMPLATE = 200
MAX_EXAMPLES = 20
MAX_EXAMPLE_LEN = 150
TITLE_MAX = 100      # límite de YouTube
TITLE_TARGET = 90
PHRASE_WITHIN = 40   # la frase de búsqueda tiene que terminar antes de este carácter
TAGS_PER_TITLE = 4
ARTISTS_PER_TITLE = 3
RECENT_TITLES = 20
MIN_CHAPTERS = 3
MIN_CHAPTER_SEC = 10
MAX_HOOK = 300
_TRIES = 12
_HOOK_TOKENS = 120

_MARKER = re.compile(r'\{(%s)\}' % '|'.join(MARKERS))
_ANY_MARKER = re.compile(r'\{(\w*)\}')
_EMPTY_GROUP = re.compile(r'\(\s*\)|\[\s*\]')
_SENTENCE_END = re.compile(r'(?<=[.!?])\s+')
_LINK = re.compile(r'https?:|www\.|\b[\w-]+\.(?:com|net|org|io|co|ly|gg|me)\b', re.IGNORECASE)
# Un artista solo puede aparecer como referencia de estilo: la fórmula va antes del nombre
# (a lo sumo con otros nombres en el medio) o pegada después ("X-style", "X type").
_STYLE_BEFORE = re.compile(r'inspired by|style of', re.IGNORECASE)
_STYLE_AFTER = re.compile(r'[\s-]*(?:style|type|inspired)\b', re.IGNORECASE)
_STYLE_GAP = 40
# Frases que afirman autoría o participación: el gancho entero se descarta.
_AUTHORSHIP = re.compile(
    r'\b(?:made|used|produced|created|crafted|played|recorded|written|composed|approved|'
    r'endorsed|signed)\s+by\b|\bfeat(?:\.|uring)?(?!\w)|\bft\.|\bofficial\b|\bcollab',
    re.IGNORECASE)
_DIGITS = re.compile(r'\d+')
_NAME_PROBE = 'X'   # nombre mínimo para probar si una ficha puede cumplir las reglas

WARN_CHAPTERS = (f"Un video salió sin capítulos: hacen falta al menos {MIN_CHAPTERS} capítulos de "
                 f"{MIN_CHAPTER_SEC} s o más.")

_HOOK_SYSTEM = (
    "You write the opening lines of YouTube descriptions for free loop kits (sample packs "
    "for music producers). Reply with the text only: 1 or 2 short sentences in English, "
    "plain text. No emojis, no hashtags, no links, no quotes. Never say or imply that an "
    "artist made, used, endorsed or is featured in the kit: an artist may only appear as a "
    "style reference, with the words \"inspired by\" or \"in the style of\". Do not invent "
    "facts such as the number of loops, BPM, keys or file formats.")


class KitSeoError(ValueError):
    """Ficha de SEO mal formada. El mensaje nombra el campo, no su contenido."""


def _fold(text):
    text = unicodedata.normalize('NFKD', str(text or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(text.casefold().replace('_', ' ').split())


def _clean(text):
    """Una línea, sin ``<`` ni ``>`` (YouTube no los admite) ni espacios dobles."""
    return ' '.join(str(text or '').replace('<', '').replace('>', '').split())


def lines(text):
    """Una entrada por línea, para los campos de lista del panel."""
    return [part.strip() for part in str(text or '').splitlines() if part.strip()]


# --- Ficha ---

def _text(value, label, limit):
    if value is None:
        return ''
    if not isinstance(value, str):
        raise KitSeoError(f'{label}: debe ser texto.')
    value = _clean(value)
    if len(value) > limit:
        raise KitSeoError(f'{label}: admite hasta {limit} caracteres.')
    return value


def _list(value, label, max_items=MAX_ITEMS, max_len=MAX_ITEM_LEN):
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise KitSeoError(f'{label}: debe ser una lista.')
    out, seen = [], set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, str):
            raise KitSeoError(f'{label}, línea {index}: debe ser texto.')
        item = _clean(item)
        if len(item) > max_len:
            raise KitSeoError(f'{label}, línea {index}: admite hasta {max_len} caracteres.')
        if item and _fold(item) not in seen:
            seen.add(_fold(item))
            out.append(item)
    if len(out) > max_items:
        raise KitSeoError(f'{label}: admite hasta {max_items} entradas.')
    return out


def is_empty(raw):
    """True si la ficha no trae nada cargado."""
    return not isinstance(raw, dict) or not any(raw.get(key) for key in FIELDS)


def is_blank(raw):
    """True si no hay frase principal: sin frase no hay ficha, aunque haya artistas cargados."""
    if not isinstance(raw, dict):
        return True
    phrase = raw.get('phrase')
    return phrase is None or (isinstance(phrase, str) and not phrase.strip())


def validate(raw, partial=False):
    """Ficha normalizada ``{phrase, artists, tags, title_template, examples}``.

    Con ``partial`` se admite sin frase: es una ficha a medio cargar, que se guarda pero no
    se usa (``load`` la ignora).

    Raises:
        KitSeoError: tipos o largos inválidos, falta la frase, la plantilla no lleva
            ``{name}`` y ``{phrase}`` o usa un marcador desconocido, o la frase no puede
            quedar dentro de los primeros 40 caracteres del título.
    """
    if not isinstance(raw, dict):
        raise KitSeoError('la ficha debe ser un objeto.')
    phrase = _text(raw.get('phrase'), 'frase', MAX_ITEM_LEN)
    if not phrase and not partial:
        raise KitSeoError('falta la frase principal.')
    template = _text(raw.get('title_template'), 'plantilla del título', MAX_TEMPLATE)
    template = template or DEFAULT_TEMPLATE
    found = set(_ANY_MARKER.findall(template))
    if found - set(MARKERS):
        raise KitSeoError('plantilla del título: solo admite {artist}, {artists}, {phrase}, '
                          '{name} y {tags}.')
    if not {'name', 'phrase'} <= found:
        raise KitSeoError('plantilla del título: tiene que llevar {phrase} y {name}.')
    seo = {'phrase': phrase,
           'artists': _list(raw.get('artists'), 'artistas'),
           'tags': _list(raw.get('tags'), 'etiquetas'),
           'title_template': template,
           'examples': _list(raw.get('examples'), 'ejemplos', MAX_EXAMPLES, MAX_EXAMPLE_LEN)}
    if phrase and not _phrase_in_place(_probe(seo, ''), phrase):
        # Ni sin artista entra: ningún video de este género tendría título por SEO.
        raise KitSeoError(f'la frase no queda dentro de los primeros {PHRASE_WITHIN} caracteres '
                          'del título: acortala o ponela antes en la plantilla.')
    return seo


def unfit_artists(seo):
    """Artistas de la ficha que no pueden ir de principal: empujan la frase más allá del 40."""
    return [artist for artist in seo['artists']
            if not _phrase_in_place(_probe(seo, artist), seo['phrase'])]


def to_config(seo):
    """Ficha validada tal como se guarda: sin la plantilla de fábrica ni listas vacías."""
    out = {'phrase': seo['phrase'], 'artists': list(seo['artists']), 'tags': list(seo['tags'])}
    if seo['title_template'] != DEFAULT_TEMPLATE:
        out['title_template'] = seo['title_template']
    if seo['examples']:
        out['examples'] = list(seo['examples'])
    return out


def form(raw):
    """Ficha para mostrar en el panel; tolera una ficha guardada a medias o mal formada."""
    raw = raw if isinstance(raw, dict) else {}

    def text(key):
        return raw[key].strip() if isinstance(raw.get(key), str) else ''

    def items(key):
        value = raw.get(key)
        return [str(v) for v in value if str(v).strip()] if isinstance(value, (list, tuple)) else []
    return {'phrase': text('phrase'), 'artists': items('artists'), 'tags': items('tags'),
            'title_template': text('title_template'), 'examples': items('examples')}


def find_key(table, genre):
    """Clave de ``table`` que corresponde a ``genre`` (sin mayúsculas, tildes ni ``_``)."""
    wanted = _fold(genre)
    if not wanted or not isinstance(table, dict):
        return None
    return next((key for key in table if _fold(key) == wanted), None)


def load(kit_cfg, genre):
    """Ficha validada del género desde ``kit_preview.seo``, o None si no hay.

    Sin ficha el flujo sigue con la plantilla de título del canal, como siempre.

    Raises:
        KitSeoError: hay ficha pero está mal formada.
    """
    table = (kit_cfg or {}).get('seo')
    key = find_key(table, genre)
    if key is None or is_blank(table[key]):
        return None
    return validate(table[key])


def history(state, pack_path):
    """``(variantes ya usadas por el kit, títulos de los últimos videos del canal)``."""
    state = state if isinstance(state, dict) else {}
    pack_id = ((state.get('packs') or {}).get(pack_path) or {}).get('id')
    runs = sorted((r for r in state.get('runs') or []
                   if isinstance(r, dict) and isinstance(r.get('seo'), dict)),
                  key=lambda r: r['id'] if isinstance(r.get('id'), int) else 0)
    used = [r['seo'] for r in runs if pack_id is not None and r.get('pack_id') == pack_id]
    titles = [r['seo']['title'] for r in runs if isinstance(r['seo'].get('title'), str)]
    return used, titles[-RECENT_TITLES:]


# --- Título ---

def _tidy(text):
    text = _EMPTY_GROUP.sub('', text.replace('<', '').replace('>', ''))
    return ' '.join(text.split()).strip(' |-–—,·:')


def _render(template, **values):
    # Una sola pasada: un nombre o un artista con llaves no se vuelve a interpretar.
    return _tidy(_MARKER.sub(lambda m: values[m.group(1)], template))


def _probe(seo, artist):
    """Título más corto posible con ese artista: sin etiquetas y con un nombre mínimo."""
    return _render(seo['title_template'], artist=artist, artists=artist, phrase=seo['phrase'],
                   name=_NAME_PROBE, tags='')


def _variant_key(variant):
    tags = variant.get('tags')
    return (_fold(variant.get('artist')),
            tuple(sorted(_fold(tag) for tag in (tags if isinstance(tags, (list, tuple)) else []))))


def _phrase_in_place(title, phrase):
    at = title.lower().find(phrase.lower())
    return 0 <= at and at + len(phrase) <= PHRASE_WITHIN


def _pick_tags(tags, rng):
    most = min(TAGS_PER_TITLE, len(tags))
    if not most:
        return []
    return rng.sample(tags, rng.randint(max(1, most - 1), most))


def _fit(seo, name, main, others, tags):
    """Título que cumple las reglas con ese artista, o None. Recorta etiquetas, no el nombre."""
    template = seo['title_template']
    tags = list(tags)
    shown = ([main] + others)[:ARTISTS_PER_TITLE] if main else []

    def build():
        return _render(template, artist=main, artists=', '.join(shown), phrase=seo['phrase'],
                       name=name, tags=', '.join(tags))
    title = build()
    while len(title) > TITLE_TARGET and len(tags) > 1:
        tags.pop()
        title = build()
    if len(title) > TITLE_MAX and tags:
        tags.pop()
        title = build()
    while ('{artists}' in template and len(shown) > 1
           and (len(title) > TITLE_MAX or not _phrase_in_place(title, seo['phrase']))):
        shown.pop()
        title = build()
    if len(title) > TITLE_MAX or not _phrase_in_place(title, seo['phrase']):
        return None
    return title, shown, tags


def build_title(seo, name, used_variants, rng, recent_titles=()):
    """Título del video y la variante usada, para comparar después cuál rinde mejor.

    Elige un artista principal que el kit todavía no usó (si ya usó todos, el que hace más
    que no sale) y una mezcla de etiquetas que no repita una variante de ``used_variants``;
    el resto de los artistas va en orden rotado para ``{artists}``. Determinístico con ``rng``.

    Args:
        seo: ficha de ``validate`` / ``load``.
        name: nombre del kit; va completo, nunca se recorta.
        used_variants: variantes ya usadas por ESE kit (del estado), de la más vieja a la última.
        recent_titles: títulos de los últimos videos del canal; no se repite ninguno.

    Returns:
        ``(titulo, variante)``; la variante es ``{artist, artists, tags, phrase, title}``.
        ``(None, None)`` si ningún título cumple las reglas (frase dentro de los primeros
        40 caracteres y 100 como máximo): el llamador usa la plantilla del canal.
    """
    name = _clean(name)
    if not name:
        return None, None
    used = [v for v in used_variants or [] if isinstance(v, dict)]
    used_keys = {_variant_key(v) for v in used}
    used_tags = {key[1] for key in used_keys}
    recent = {_fold(t) for t in list(recent_titles or [])[-RECENT_TITLES:] if t}
    last_use = {_fold(v.get('artist')): i for i, v in enumerate(used)}
    artists = list(seo['artists'])
    rng.shuffle(artists)
    artists.sort(key=lambda a: last_use.get(_fold(a), -1))  # estable: primero los sin usar

    best = None
    # Sin artistas, o si ninguno deja la frase al principio, el título sale sin artista.
    for order, main in enumerate(artists + ['']):
        if not main and best is not None:
            break
        at = artists.index(main) if main else 0
        others = artists[at + 1:] + artists[:at] if main else []
        for _ in range(_TRIES):
            built = _fit(seo, name, main, others, _pick_tags(seo['tags'], rng))
            if built is None:
                break
            title, shown, tags = built
            variant = {'artist': main, 'artists': shown, 'tags': tags,
                       'phrase': seo['phrase'], 'title': title}
            key = _variant_key(variant)
            repeated = key in used_keys or _fold(title) in recent
            rank = (repeated, order, key[1] in used_tags)
            if best is None or rank < best[0]:
                best = (rank, title, variant)
            if rank == (False, order, False):
                break
        if best is not None and not best[0][0] and best[0][1] == order:
            break
    return (best[1], best[2]) if best else (None, None)


# --- Capítulos ---

def _stamp(seconds, hours):
    minutes, secs = divmod(int(seconds), 60)
    if not hours:
        return f"{minutes}:{secs:02d}"
    return f"{minutes // 60}:{minutes % 60:02d}:{secs:02d}"


def chapters(segments):
    """Capítulos ``0:00 Loop 1`` … a partir de los tramos del audio.

    Cada tramo dura ``end - start`` y el video los une sin pausas, así que los tiempos se
    acumulan. Reglas de YouTube: al menos 3 capítulos, el primero en 0:00 y cada uno de 10 s
    o más. Un loop más corto comparte capítulo con el siguiente ("Loops 3-4"), o con el
    anterior si es el último.

    Returns:
        ``(texto, aviso)``. Si no se cumplen las reglas el texto es '' y hay aviso.
    """
    groups, total = [], 0.0   # cada grupo: [inicio, primer loop, último loop]
    for number, seg in enumerate(segments or [], 1):
        try:
            length = float(seg['end']) - float(seg['start'])
        except (KeyError, TypeError, ValueError):
            return '', WARN_CHAPTERS
        if length <= 0:
            return '', WARN_CHAPTERS
        if groups and total - groups[-1][0] < MIN_CHAPTER_SEC:
            groups[-1][2] = number   # el capítulo abierto todavía no llega a 10 s
        else:
            groups.append([int(total), number, number])
        total = round(total + length, 3)   # como kit_audio: sin arrastrar error de float
    if len(groups) > 1 and total - groups[-1][0] < MIN_CHAPTER_SEC:
        short = groups.pop()
        groups[-1][2] = short[2]
    if len(groups) < MIN_CHAPTERS or total - groups[-1][0] < MIN_CHAPTER_SEC:
        return '', WARN_CHAPTERS
    hours = groups[-1][0] >= 3600
    return '\n'.join(
        f"{_stamp(start, hours)} " + (f"Loop {first}" if first == last else f"Loops {first}-{last}")
        for start, first, last in groups), ''


# --- Gancho de la descripción ---

def _hook_prompt(kit_description, genre, seo):
    description = ' '.join(str(kit_description or '').split())[:MAX_HOOK]
    return (f"Genre: {genre or 'not set'}\n"
            f"Search phrase: {seo['phrase']}\n"
            f"Keywords: {', '.join(seo['tags']) or 'none'}\n"
            f"Style references: {', '.join(seo['artists'][:4]) or 'none'}\n"
            f"About the kit: {description or 'no description'}\n"
            "Write the hook.")


def _is_style_reference(text, start, end):
    """True si el nombre en ``text[start:end]`` está presentado como referencia de estilo."""
    if _STYLE_AFTER.match(text, end):
        return True
    sentence = max(text.rfind(mark, 0, start) for mark in '.!?') + 1
    formulas = list(_STYLE_BEFORE.finditer(text, sentence, start))
    # Entre la fórmula y el nombre solo caben otros nombres ("inspired by A, B and C").
    return bool(formulas) and start - formulas[-1].end() <= _STYLE_GAP


def _claims_artist(text, artists):
    """True si nombra a un artista sin dejar claro que es una referencia de estilo."""
    for artist in artists:
        if not artist:
            continue
        # Palabra entera: un artista "Future" no descarta "the future of trap"... salvo
        # que de verdad lo nombre, y entonces tiene que llevar la fórmula.
        pattern = re.compile(r'(?<!\w)' + re.escape(artist) + r'(?!\w)', re.IGNORECASE)
        for found in pattern.finditer(text):
            if artist.islower() or found.group(0) != found.group(0).lower():
                if not _is_style_reference(text, found.start(), found.end()):
                    return True
    return False


def _invents_numbers(text, seo, description):
    """True si el gancho trae cifras que no están en la descripción del kit ni en la ficha."""
    seo = seo or {}
    known = ' '.join([str(description or ''), str(seo.get('phrase') or ''),
                      *(seo.get('tags') or []), *(seo.get('artists') or [])])
    return bool(set(_DIGITS.findall(text)) - set(_DIGITS.findall(known)))


def clean_hook(raw, seo=None, description=None):
    """Gancho listo para la descripción, o '' si no sirve.

    Deja 1 o 2 frases en una línea, sin emojis ni ``<>``. Se descarta entero si trae un
    link, una frase de autoría ("made by", "used by", "feat."…), una cifra que no está en
    la descripción del kit (cantidad de loops, BPM) o si nombra a un artista de la ficha
    sin "inspired by" / "style of" delante o "-style" / "type" detrás.
    """
    if not isinstance(raw, str):
        return ''
    text = ''.join(c for c in raw if ord(c) <= 0xFFFF
                   and unicodedata.category(c) not in ('So', 'Sk', 'Cs', 'Co', 'Cn', 'Cf'))
    text = _clean(text).strip('"\'“”‘’`* ')
    if not text or _LINK.search(text) or '@' in text or '#' in text:
        return ''
    text = ' '.join(_SENTENCE_END.split(text)[:2])
    if len(text) > MAX_HOOK:
        text = _SENTENCE_END.split(text)[0]
    if (len(text) > MAX_HOOK or _AUTHORSHIP.search(text)
            or _invents_numbers(text, seo, description)
            or _claims_artist(text, (seo or {}).get('artists') or [])):
        return ''
    return text


def hook(kit_description, genre, seo, llm_call=None, cfg=None, key=None, budget=None):
    """Gancho de la descripción: una sola llamada de texto, o '' si no se puede.

    Args:
        kit_description: descripción del kit en el catálogo (contexto para el modelo).
        seo: ficha del género (frase, etiquetas y artistas como referencia de estilo).
        llm_call: ``(system, user) -> str`` inyectable; sin él se usa ``kit_llm`` con ``cfg``
            (``base_url``, ``model``, ``key_file``) y ``key``.
        budget: ``kit_spend.Budget`` de la corrida; el costo de texto entra en el tope mensual.

    Nunca levanta: sin modelo configurado, con el tope alcanzado, si el modelo falla o
    devuelve algo que no sirve, el video sale sin gancho.
    """
    try:
        if llm_call is None:
            from core import kit_llm
            cfg = dict(cfg or {})
            if not cfg.get('base_url') or not cfg.get('model'):
                return ''
            # Config o clave inválidas se detectan antes: no hubo llamada, no se cobra.
            kit_llm.check_base_url(cfg['base_url'])
            key = key or kit_llm.read_key(cfg)
            llm_call = partial(kit_llm.call, key=key, cfg={
                **cfg, 'max_tokens': _HOOK_TOKENS, 'temperature': 0.7})
        cost = budget.text_cost() if budget is not None else 0.0
        if budget is not None and budget.blocked(cost):
            return ''
        try:
            raw = llm_call(_HOOK_SYSTEM, _hook_prompt(kit_description, genre, seo))
        except Exception:
            raw = ''  # un fallo dudoso (timeout, 5xx) se cuenta igual como cobrado
        if budget is not None:
            budget.charge(cost)
        return clean_hook(raw, seo, kit_description)
    except Exception:
        return ''
