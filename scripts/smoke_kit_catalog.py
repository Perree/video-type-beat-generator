#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del catálogo de kits y del marcador {link}. Sin red. Datos ficticios."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import description, kit_catalog, kit_publish
from core.kit_catalog import KitCatalogError

GENRES = ['genre-a', 'genre-b']


def _fail(msg):
    print('FAIL:', msg)
    return 1


def _kit(folder, url='https://example.com/p', genre='genre-a', active=True):
    return {'folder': folder, 'name': f'Name {folder}', 'payhip_url': url,
            'genre': genre, 'active': active}


def _write(tmp, data):
    path = os.path.join(tmp, 'kits.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return path


def _rejects(tmp, data, genres=GENRES):
    try:
        kit_catalog.load(_write(tmp, data), genres)
    except KitCatalogError:
        return True
    return False


def _check_catalog(tmp):
    packs = [{'name': 'ok', 'dropbox_path': '/root/ok'},
             {'name': 'nolink', 'dropbox_path': '/root/nolink'},
             {'name': 'off', 'dropbox_path': '/root/off'}]
    data = [_kit('ok'), _kit('nolink', url=''), _kit('off', active=False),
            _kit('missing')]
    catalog = kit_catalog.load(_write(tmp, data), GENRES)
    if len(catalog) != 4:
        return _fail(f'load devolvió {len(catalog)} entradas')
    got = [k['folder'] for k in kit_catalog.eligible(catalog, packs)]
    if got != ['ok']:
        return _fail(f'elegibles esperados [ok], salió {got}')
    if any(k['folder'] == 'nolink' for k in kit_catalog.eligible(catalog, packs)):
        return _fail('un kit sin link fue elegible')
    if any(k['folder'] == 'missing' for k in kit_catalog.eligible(catalog, packs)):
        return _fail('un kit con carpeta inexistente fue elegible')

    slash = [{'name': 'ok', 'dropbox_path': '/root/ok/'}]
    if not kit_catalog.eligible([_kit('/root/ok')], slash):
        return _fail('una ruta con / final no coincidió')

    for bad in ('http://example.com/p', 'ftp://example.com/p', 'example.com/p',
                'https://', 'https://example.com/a b', 'https://example.com/a\nb'):
        if not _rejects(tmp, [_kit('x', url=bad)]):
            return _fail(f'link no https aceptado: {bad}')
        if kit_catalog.is_valid_link(bad):
            return _fail(f'is_valid_link aceptó {bad}')
    # Catálogo armado en memoria con link malo: eligible igual lo excluye.
    mem = [_kit('ok', url='http://example.com/p')]
    if kit_catalog.eligible(mem, packs):
        return _fail('eligible aceptó un link no https')

    if not _rejects(tmp, [_kit('x', genre='other')]):
        return _fail('género no configurado aceptado')
    if _rejects(tmp, [_kit('x', genre='GENRE-B')]):
        return _fail('género configurado rechazado')
    if not _rejects(tmp, [_kit('x'), _kit('X')]):
        return _fail('carpetas repetidas aceptadas')
    if not _rejects(tmp, {'folder': 'x'}):
        return _fail('un objeto suelto no es una lista válida')
    if kit_catalog.eligible(catalog, []):
        return _fail('sin packs no debe haber elegibles')
    return 0


def _check_link_marker():
    link = 'https://example.com/p?a=1&b={x}'
    base = {'title_template': '{name} Kit'}

    tpl = {**base, 'description_template': 'Get {name}: {link} end', 'link': link}
    _, body, _ = kit_publish._metadata('kits', 'Pack', tpl)
    if body != f'Get Pack: {link} end':
        return _fail(f'{{link}} no se reemplazó bien: {body!r}')

    no_link = {**base, 'description_template': 'Get {name}: {link} end'}
    _, body, _ = kit_publish._metadata('kits', 'Pack', no_link)
    if '{link}' in body:
        return _fail('{link} sin valor quedó literal en la descripción')

    plain = {**base, 'description_template': 'Just {name} here'}
    expected = description.render('Just {name} here', 'Pack', tags='', socials='',
                                  hashtags='')
    for templates in (plain, {**plain, 'link': link}):
        _, body, _ = kit_publish._metadata('kits', 'Pack', templates)
        if body != expected or link in body:
            return _fail(f'plantilla sin {{link}} cambió: {body!r}')
    # Un nombre con "{link}" no activa el reemplazo si la plantilla no lo trae.
    _, body, _ = kit_publish._metadata(
        'kits', '{link}', {**plain, 'link': link})
    if link in body:
        return _fail('el nombre del pack activó el reemplazo de {link}')
    return 0


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        for check in (lambda: _check_catalog(tmp), _check_link_marker):
            code = check()
            if code:
                return code
    print('OK smoke_kit_catalog')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
