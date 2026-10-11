# -*- coding: utf-8 -*-
"""Nombres cortos para los videos de loop kits y link con seguimiento por video.

``propose`` devuelve opciones (modo manual); ``pick`` elige la primera válida (modo
automático). ``llm_call(system, user) -> str`` es inyectable; sin él se usa ``kit_llm``
con ``cfg`` / ``key``.
"""
import re
import unicodedata
import urllib.parse
import uuid
from functools import partial

from core import kit_cloud, kit_llm

MAX_WORDS = 2
MAX_LEN = 24
MAX_DESCRIPTION = 200
_EXTRA = 3  # se piden algunos de más para compensar los que se descartan
_PREFIX = re.compile(r'^\s*(?:[-*•]+|\d+\s*[.):-])\s*')
_VALID = re.compile(r"^[^\W_]+(?:[ '-][^\W_]+)?$", re.UNICODE)

_SYSTEM = (
    "Eres un curador de nombres para videos de loop kits de producción musical. "
    "Respondes solo con la lista pedida, un nombre por línea, sin numerar ni explicar.")


def _norm(name):
    text = unicodedata.normalize('NFKD', name)
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(text.casefold().split())


def _clean(line):
    line = _PREFIX.sub('', line.strip())
    return line.strip(' \t"\'“”‘’`*.,;:').strip()


def _valid_shape(name):
    return (bool(name) and len(name) <= MAX_LEN and len(name.split()) <= MAX_WORDS
            and bool(_VALID.match(name)))


def clean_description(text):
    """Descripción del kit en una línea y con tope de largo (vacía si no es texto)."""
    return ' '.join(text.split())[:MAX_DESCRIPTION] if isinstance(text, str) else ''


def _prompt(kit, genre, used, count, description=None):
    avoid = ', '.join(sorted({u for u in used if u}))
    context = clean_description(description)
    return (
        f"Propone {count} nombres de 1 o 2 palabras para un video de loops del género "
        f"\"{genre}\". Deben sonar coherentes con ese género, ser fáciles de recordar y "
        f"distintos entre sí. No uses el nombre \"{kit}\" ni estos ya usados: "
        f"{avoid or 'ninguno'}. Un nombre por línea."
        + (f" Contexto del kit, para que los nombres se relacionen con él: {context}"
           if context else ''))


def propose(kit, genre, used_names, n=5, llm_call=None, cfg=None, key=None, description=None):
    """Hasta ``n`` nombres válidos, sin repetir los usados ni el del propio kit.

    Descarta vacíos, de más de 2 palabras, con símbolos y duplicados (sin distinguir
    mayúsculas ni tildes). Puede devolver menos de ``n`` si el LLM no alcanza.
    ``description`` (1-2 líneas sobre el kit) va al LLM como contexto.
    """
    if n < 1:
        return []
    used = list(used_names or [])
    if llm_call is None:
        llm_call = partial(kit_llm.call, cfg=cfg, key=key)
    raw = llm_call(_SYSTEM, _prompt(kit, genre, used, n + _EXTRA, description))
    seen = {_norm(u) for u in used if u}
    seen.add(_norm(kit or ''))
    names = []
    for line in str(raw or '').splitlines():
        name = _clean(line)
        if not _valid_shape(name):
            continue
        key_ = _norm(name)
        if key_ in seen:
            continue
        seen.add(key_)
        names.append(name)
        if len(names) == n:
            break
    return names


def pick(kit, genre, used_names, llm_call=None, cfg=None, key=None, description=None):
    """Modo automático: la primera opción válida, o None si no hay ninguna."""
    options = propose(kit, genre, used_names, n=1, llm_call=llm_call, cfg=cfg, key=key,
                      description=description)
    return options[0] if options else None


def new_tracking_id():
    """Id corto y único por video para ``utm_content`` (el youtube_id no existe aún al subir)."""
    return uuid.uuid4().hex[:12]


def track_link(url, content_id, source='youtube'):
    """Agrega ``utm_source`` y ``utm_content`` conservando query y fragmento previos.

    Si el link ya traía alguno de los dos, se reemplaza: cada uno queda una sola vez.
    Link vacío o sin id → se devuelve sin cambios.
    """
    url = (url or '').strip()
    if not url or not content_id:
        return url
    parts = urllib.parse.urlsplit(url)
    pairs = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
             if k not in ('utm_source', 'utm_content')]
    pairs += [('utm_source', source), ('utm_content', str(content_id))]
    query = urllib.parse.urlencode(pairs)
    return urllib.parse.urlunsplit(parts._replace(query=query))


ENV_LLM_KEY = 'KIT_LLM_API_KEY'


def for_pack(pack_name, pack_path, names_cfg, store, llm_call=None, key=None, description=None):
    """Nombre del video para un kit, o ``(None, [])`` si no aplica o el LLM falla.

    ``description`` es la descripción del kit en el catálogo: contexto para el LLM.

    ``names_cfg`` es ``kit_preview.names`` (``genre`` obligatorio, más ``base_url``, ``model`` y
    ``key_file``); la clave sale de ``key``, de ``KIT_LLM_API_KEY`` o de ``key_file``. Los usados del
    ciclo salen de ``store.get_cycle`` si el store lo tiene. Un fallo nunca corta la subida: el
    llamador usa el nombre del pack. Devuelve ``(nombre, usados)``; no se imprime ningún nombre.
    """
    if not names_cfg or names_cfg.get('enabled', True) is False:
        return None, []
    genre = str(names_cfg.get('genre') or '').strip()
    if not genre:
        return None, []
    get_cycle = getattr(store, 'get_cycle', None)
    used = list(get_cycle(pack_path).get('used_names') or []) if get_cycle else []
    try:
        # Tampoco se repite el nombre de un video de otro kit, si el store los conoce.
        others = getattr(store, 'used_video_names', None)
        name = pick(pack_name, genre, used + list(others() if others else []),
                    llm_call=llm_call, cfg=names_cfg,
                    key=key or kit_cloud.secret(ENV_LLM_KEY) or None, description=description)
    except Exception as exc:
        print(f"Nombre de video no generado ({type(exc).__name__}); se usa el del pack.")
        return None, used
    return name, used


def remember(store, pack_path, used, name):
    """Guarda ``name`` entre los usados del ciclo del kit. Un fallo no corta nada."""
    update_cycle = getattr(store, 'update_cycle', None)
    if not name or update_cycle is None:
        return
    try:
        update_cycle(pack_path, used_names=list(used) + [name])
    except Exception as exc:
        print(f"No se guardó el nombre usado ({type(exc).__name__}).")
