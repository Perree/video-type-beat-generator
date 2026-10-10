# -*- coding: utf-8 -*-
"""Inventario de loop kits en Dropbox: packs, loops, preview nombrada e imágenes.

Un pack es una subcarpeta directa de dropbox_root. No se recorre stems/ ni layers/.
"""
import os

from core import dropbox_client

SKIP_SUBDIRS = frozenset({'stems', 'layers'})


def _is_named_preview(filename):
    """True si el nombre del audio contiene 'preview' (sin importar mayúsculas)."""
    return 'preview' in filename.lower()


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


def _pack_from_folder(folder, local_images_root, dbx):
    """Clasifica loops, preview nombrada e imágenes de un pack (solo raíz + images/)."""
    name = folder['name']
    path = folder['path']
    loops = []
    named_previews = []
    images_dir_path = None
    for entry in dropbox_client.list_folder_entries(path, dbx=dbx):
        if entry['is_folder']:
            folder_key = entry['name'].lower()
            if folder_key in SKIP_SUBDIRS:
                continue
            if folder_key == 'images' and images_dir_path is None:
                images_dir_path = entry['path']
            continue
        if not dropbox_client.is_audio(entry['name']):
            continue
        rec = {'name': entry['name'], 'path': entry['path']}
        if _is_named_preview(entry['name']):
            named_previews.append(rec)
        else:
            loops.append(rec)
    # Si existe images/, no se usa el fallback local aunque esté vacío.
    if images_dir_path is not None:
        images = _dropbox_images(images_dir_path, dbx)
    else:
        images = _local_images(local_images_root, name)
    return {
        'name': name,
        'dropbox_path': path,
        'loops': loops,
        'named_previews': named_previews,
        'images': images,
    }


def list_packs(dropbox_root, local_images_root=None, dbx=None):
    """Lista packs (subcarpetas de dropbox_root) con loops, previews e imágenes.

    Args:
        dropbox_root: carpeta de Dropbox que contiene un directorio por pack.
        local_images_root: si el pack no tiene images/, se leen archivos de
            ``<local_images_root>/<nombre>/``.
        dbx: cliente Dropbox o fake con files_list_folder (smokes).

    Returns:
        Lista de dicts ``{name, dropbox_path, loops, named_previews, images}``.
        loops/named_previews: ``{name, path}``. images: ``{name, path, source}``.
    """
    packs = []
    for item in dropbox_client.list_folder_entries(dropbox_root or '', dbx=dbx):
        if not item['is_folder']:
            continue
        packs.append(_pack_from_folder(item, local_images_root, dbx))
    return packs


def download_pack_files(paths, dest_dir, dbx=None):
    """Descarga cada path de Dropbox a dest_dir. Devuelve las rutas locales."""
    dests = []
    for dropbox_path in paths:
        dests.append(dropbox_client.download(dropbox_path, dest_dir, dbx=dbx))
    return dests
