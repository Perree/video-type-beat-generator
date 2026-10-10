# -*- coding: utf-8 -*-
"""Catálogo de loop kits (``kits.json``): qué kits se pueden promocionar.

Cada entrada es ``{folder, name, payhip_url, genre, active}``. Un kit es
elegible solo si está activo, tiene un link https y su carpeta existe entre los
packs de Dropbox. Los mensajes de error usan el número de entrada, nunca el
nombre ni el link, para no filtrar datos en logs.
"""
import json
from urllib.parse import urlparse


class KitCatalogError(ValueError):
    """kits.json inválido."""


def is_valid_link(url):
    """True si ``url`` es un link https con host."""
    if not isinstance(url, str) or not url.strip():
        return False
    url = url.strip()
    # Espacios o saltos de línea dentro del link romperían la descripción.
    if any(ch.isspace() or ord(ch) < 32 for ch in url):
        return False
    try:
        parsed = urlparse(url)
    except ValueError:  # p. ej. un corchete sin cerrar
        return False
    return parsed.scheme == 'https' and bool(parsed.hostname)


def configured_genres(app_config):
    """Géneros permitidos desde ``app_config['kit_preview']['genres']`` (o None)."""
    genres = ((app_config or {}).get('kit_preview') or {}).get('genres')
    return list(genres) if genres else None


def _norm(value):
    return str(value or '').strip().rstrip('/').lower()


def _validate_entry(index, raw, genres):
    where = f'kits.json entrada {index}'
    if not isinstance(raw, dict):
        raise KitCatalogError(f'{where}: debe ser un objeto.')
    folder = str(raw.get('folder') or '').strip()
    name = str(raw.get('name') or '').strip()
    if not folder or not name:
        raise KitCatalogError(f'{where}: faltan folder o name.')
    url = raw.get('payhip_url')
    url = url.strip() if isinstance(url, str) else ''
    # Sin link es válido (el kit queda no elegible); con link tiene que ser https.
    if url and not is_valid_link(url):
        raise KitCatalogError(f'{where}: payhip_url debe ser un link https.')
    genre = str(raw.get('genre') or '').strip()
    if genres is not None and _norm(genre) not in {_norm(g) for g in genres}:
        raise KitCatalogError(f'{where}: genre no está entre los configurados.')
    active = raw.get('active', True)
    if not isinstance(active, bool):
        raise KitCatalogError(f'{where}: active debe ser true o false.')
    return {'folder': folder, 'name': name, 'payhip_url': url,
            'genre': genre, 'active': active}


def load(path, genres=None):
    """Lee y valida ``kits.json``.

    Args:
        path: ruta del archivo (lista de ``{folder, name, payhip_url, genre, active}``).
        genres: géneros configurados. Si se pasa, ``genre`` debe ser uno de ellos.

    Returns:
        Lista de dicts normalizados.

    Raises:
        KitCatalogError: archivo ilegible, no es lista, entrada mal formada,
            link no https, género no configurado o carpetas repetidas.
    """
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        raise KitCatalogError('No se pudo leer kits.json.') from None
    return validate(data, genres)


def validate(data, genres=None):
    """Valida una lista ya en memoria con las mismas reglas que ``load``.

    Returns:
        Lista de dicts normalizados.

    Raises:
        KitCatalogError: igual que ``load`` (los mensajes nombran la entrada por número).
    """
    if not isinstance(data, list):
        raise KitCatalogError('kits.json debe ser una lista.')
    catalog = [_validate_entry(i, raw, genres) for i, raw in enumerate(data, 1)]
    seen = set()
    for i, kit in enumerate(catalog, 1):
        key = _norm(kit['folder'])
        if key in seen:
            raise KitCatalogError(f'kits.json entrada {i}: folder repetido.')
        seen.add(key)
    return catalog


def eligible(catalog, packs):
    """Kits activos, con link https y carpeta presente entre ``packs``.

    Args:
        catalog: salida de ``load``.
        packs: salida de ``kit_source.list_packs`` (``name`` y ``dropbox_path``).

    Returns:
        Sublista de ``catalog`` (mismo orden). ``folder`` se compara con el
        nombre del pack o con su ``dropbox_path``, sin distinguir mayúsculas.
    """
    present = set()
    for pack in packs or []:
        present.add(_norm(pack.get('name')))
        present.add(_norm(pack.get('dropbox_path')))
    present.discard('')
    return [
        kit for kit in catalog or []
        if kit.get('active') is True
        and is_valid_link(kit.get('payhip_url'))
        and _norm(kit.get('folder')) in present
    ]
