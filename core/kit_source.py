# -*- coding: utf-8 -*-
"""Inventario de loop kits en Dropbox: kits, loops e imágenes.

``dropbox_root`` es la carpeta de la tienda. Se recorren, en orden, las categorías de
``scan_folders`` (subcarpetas directas de la raíz); con la lista vacía los kits cuelgan
directo de la raíz. Un kit es una carpeta con loops en una subcarpeta llamada como alguna
de ``loops_dirs`` (nombre exacto, sin distinguir mayúsculas) o, si no la tiene, en su raíz.
Una carpeta sin loops (un bundle) se recorre hacia adentro hasta ``max_depth`` niveles; ahí
adentro un kit solo cuenta si tiene su subcarpeta de loops.
"""
import os
import re

from core import dropbox_client

DEFAULT_SCAN_FOLDERS = ('Individual Kits', 'Production Suites', 'Genre Bundles', 'free kits')
DEFAULT_LOOPS_DIRS = ('loops',)
DEFAULT_IGNORE_NAMES = ('tag', 'preview')
DEFAULT_MAX_DEPTH = 3
# Subcarpetas de un producto que no son loops melódicos: no se recorren.
SKIP_WORDS = ('drum', 'midi', 'starter', 'vocal', 'phrase', 'stem', 'layer')


def _names(value, default):
    """Lista de textos sin vacíos ni repetidos (sin distinguir mayúsculas)."""
    if value is None:
        value = default
    if isinstance(value, str):
        value = value.split(',')
    out, seen = [], set()
    for item in value or []:
        item = ' '.join(str(item).split())
        if item and item.lower() not in seen:
            seen.add(item.lower())
            out.append(item)
    return out


def scan_settings(kit_cfg=None):
    """Reglas de recorrido desde ``kit_preview`` (con defaults).

    Returns:
        dict ``{scan_folders, loops_dirs, ignore_names, max_depth}``. ``scan_folders`` vacío
        (``[]`` en la config) significa que los kits cuelgan directo de ``dropbox_root``.
    """
    kit_cfg = kit_cfg or {}
    try:
        depth = int(kit_cfg.get('scan_max_depth', DEFAULT_MAX_DEPTH))
    except (TypeError, ValueError):
        depth = DEFAULT_MAX_DEPTH
    return {
        'scan_folders': _names(kit_cfg.get('scan_folders'), DEFAULT_SCAN_FOLDERS),
        'loops_dirs': (_names(kit_cfg.get('loops_dirs'), DEFAULT_LOOPS_DIRS)
                       or list(DEFAULT_LOOPS_DIRS)),
        'ignore_names': _names(kit_cfg.get('ignore_names'), DEFAULT_IGNORE_NAMES),
        'max_depth': max(1, depth),
    }


def _is_ignored(filename, words):
    """True si el nombre trae alguna palabra de ``words`` como palabra suelta.

    Se compara por palabras y no por texto contenido: "tag" no descarta "Vintage".
    """
    tokens = re.split(r'[^a-z0-9]+', os.path.splitext(filename)[0].lower())
    for word in words:
        word = word.lower()
        if any(tok == word or (tok.startswith(word) and tok[len(word):].isdigit())
               for tok in tokens):
            return True
    return False


def _is_skipped_dir(name):
    """True si alguna palabra del nombre empieza con una de SKIP_WORDS ("Drum Loops", "MIDIS")."""
    tokens = re.split(r'[^a-z0-9]+', name.lower())
    return any(tok.startswith(word) for tok in tokens for word in SKIP_WORDS)


def _loops_in(entries, ignore_names):
    """Audios de una carpeta ya listada: sin ignorados y con un solo formato por loop."""
    by_stem = {}
    for entry in entries:
        if entry['is_folder'] or not dropbox_client.is_audio(entry['name']):
            continue
        if _is_ignored(entry['name'], ignore_names):
            continue
        stem = os.path.splitext(entry['name'])[0].lower()
        kept = by_stem.get(stem)
        # El mismo loop en mp3 y wav cuenta una vez: queda el wav.
        if kept is None or (entry['name'].lower().endswith('.wav')
                            and not kept['name'].lower().endswith('.wav')):
            by_stem[stem] = {'name': entry['name'], 'path': entry['path']}
    return sorted(by_stem.values(), key=lambda rec: rec['name'].lower())


def _dropbox_images(images_path, dbx):
    """Lista jpg/png/webp de images/ en Dropbox. source='dropbox'."""
    items = []
    for entry in dropbox_client.list_folder_entries(images_path, dbx=dbx):
        if entry['is_folder'] or not dropbox_client.is_image(entry['name']):
            continue
        items.append({
            'name': entry['name'],
            'path': entry['path'],
            'source': 'dropbox',
        })
    return items


def _local_images(local_images_root, pack_name):
    """Imágenes hechas a mano en local_images_root/<nombre-del-pack>/."""
    if not local_images_root:
        return []
    folder = os.path.join(local_images_root, pack_name)
    if not os.path.isdir(folder):
        return []
    items = []
    for filename in sorted(os.listdir(folder), key=str.lower):
        if dropbox_client.is_image(filename):
            items.append({
                'name': filename,
                'path': os.path.join(folder, filename),
                'source': 'local',
            })
    return items


def _packs_under(folder, category, depth, scan, local_images_root, dbx):
    """Kits de ``folder``: ella misma si tiene loops; si no, lo que haya adentro."""
    entries = dropbox_client.list_folder_entries(folder['path'], dbx=dbx)
    subdirs = [e for e in entries if e['is_folder']]
    loops_keys = {name.lower() for name in scan['loops_dirs']}
    loops = []
    for sub in subdirs:
        if sub['name'].lower() in loops_keys:
            loops = _loops_in(dropbox_client.list_folder_entries(sub['path'], dbx=dbx),
                              scan['ignore_names'])
            if loops:
                break
    # Los loops sueltos en la raíz solo valen en la carpeta del producto: más adentro
    # serían las muestras de un drum kit ("Kicks", "One Shots").
    if not loops and depth == 1:
        loops = _loops_in(entries, scan['ignore_names'])
    if loops:
        images_dir = next((s for s in subdirs if s['name'].lower() == 'images'), None)
        # Si existe images/, no se usa el fallback local aunque esté vacío.
        if images_dir is not None:
            images = _dropbox_images(images_dir['path'], dbx)
        else:
            images = _local_images(local_images_root, folder['name'])
        return [{
            'name': folder['name'],
            'dropbox_path': folder['path'],
            'category': category,
            'loops': loops,
            'images': images,
        }]
    if depth >= scan['max_depth']:
        return []
    packs = []
    for sub in subdirs:
        key = sub['name'].lower()
        if key == 'images' or key in loops_keys or _is_skipped_dir(sub['name']):
            continue
        packs += _packs_under(sub, category, depth + 1, scan, local_images_root, dbx)
    return packs


def list_categories(dropbox_root, dbx=None):
    """Nombres de las subcarpetas de la raíz (sin las que empiezan con ``_``)."""
    return [e['name'] for e in dropbox_client.list_folder_entries(dropbox_root or '', dbx=dbx)
            if e['is_folder'] and not e['name'].startswith('_')]


def list_packs(dropbox_root, local_images_root=None, dbx=None, scan=None):
    """Lista los kits de la tienda con sus loops e imágenes, en orden de recorrido.

    Args:
        dropbox_root: carpeta de Dropbox con las categorías (o con los kits, si
            ``scan_folders`` está vacío).
        local_images_root: si el kit no tiene images/, se leen archivos de
            ``<local_images_root>/<nombre>/``.
        dbx: cliente Dropbox o fake con files_list_folder (smokes).
        scan: salida de ``scan_settings``; por defecto, los defaults.

    Returns:
        Lista de dicts ``{name, dropbox_path, category, loops, images}``.
        loops: ``{name, path}``. images: ``{name, path, source}``. Una categoría que no
        existe en la raíz se saltea.
    """
    scan = scan or scan_settings()
    top = [e for e in dropbox_client.list_folder_entries(dropbox_root or '', dbx=dbx)
           if e['is_folder']]
    packs = []
    if not scan['scan_folders']:
        for folder in top:
            if not folder['name'].startswith('_'):
                packs += _packs_under(folder, '', 1, scan, local_images_root, dbx)
        return packs
    by_name = {folder['name'].lower(): folder for folder in top}
    for wanted in scan['scan_folders']:
        category = by_name.get(wanted.lower())
        if category is None:
            continue
        for folder in dropbox_client.list_folder_entries(category['path'], dbx=dbx):
            if folder['is_folder']:
                packs += _packs_under(folder, category['name'], 1, scan, local_images_root, dbx)
    return packs


def download_pack_files(paths, dest_dir, dbx=None):
    """Descarga cada path de Dropbox a dest_dir. Devuelve las rutas locales."""
    dests = []
    for dropbox_path in paths:
        dests.append(dropbox_client.download(dropbox_path, dest_dir, dbx=dbx))
    return dests
