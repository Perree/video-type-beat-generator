# -*- coding: utf-8 -*-
"""Detección de kits para el panel de loop kits (sin Qt).

Recorre la carpeta de la tienda con las reglas de ``kit_source`` y arma filas para la
tabla de kits: sin link ni género, para que el usuario las complete. Solo lee Dropbox.
"""
import re

from core import kit_catalog, kit_cloud, kit_source

# Sufijo que dejan Dropbox y el explorador al duplicar una carpeta: "Nombre (1)".
_COPY_SUFFIX = re.compile(r'\s\(\d+\)$')


def is_copy(name):
    """True si el nombre termina en " (N)": una copia duplicada de otra carpeta."""
    return bool(_COPY_SUFFIX.search(str(name or '').strip()))


def categories(dropbox_root, dbx=None):
    """Subcarpetas de la raíz, para armar las casillas de categorías."""
    return kit_source.list_categories(dropbox_root, dbx=dbx or kit_cloud.client())


def rows_from_packs(packs):
    """Filas de catálogo para los kits encontrados, en el orden del recorrido.

    ``folder`` es el nombre de la carpeta; si dos kits se llaman igual, su ruta completa.
    Una carpeta duplicada (nombre terminado en " (N)") queda con ``active`` en False.
    """
    counts = {}
    for pack in packs:
        key = kit_catalog._norm(pack['name'])
        counts[key] = counts.get(key, 0) + 1
    rows = []
    for pack in packs:
        unique = counts[kit_catalog._norm(pack['name'])] == 1
        rows.append({'folder': pack['name'] if unique else pack['dropbox_path'],
                     'name': pack['name'], 'payhip_url': '', 'genre': '',
                     'active': not is_copy(pack['name']),
                     'loops': len(pack.get('loops') or [])})
    return rows


def detect(dropbox_root, scan=None, dbx=None):
    """Kits de la tienda como filas ``{folder, name, payhip_url, genre, active, loops}``."""
    packs = kit_source.list_packs(dropbox_root, dbx=dbx or kit_cloud.client(),
                                  scan=scan or kit_source.scan_settings())
    return rows_from_packs(packs)


def merge(existing, detected):
    """Suma a ``existing`` los kits detectados que todavía no están en la tabla.

    Las filas que ya estaban no se tocan (conservan link, género y activo). Una fila
    coincide con un kit por ``folder``, sea el nombre de la carpeta o su ruta.

    Returns:
        ``(filas, cantidad_de_nuevas)``.
    """
    rows = [dict(row) for row in existing or []]
    known = {kit_catalog._norm(row.get('folder')) for row in rows}
    added = 0
    for row in detected or []:
        if kit_catalog._norm(row['folder']) in known or kit_catalog._norm(row['name']) in known:
            continue
        rows.append({k: row[k] for k in ('folder', 'name', 'payhip_url', 'genre', 'active')})
        known.add(kit_catalog._norm(row['folder']))
        added += 1
    return rows, added
