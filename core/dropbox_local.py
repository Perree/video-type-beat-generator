# -*- coding: utf-8 -*-
"""Carpeta local de Dropbox (la que sincroniza la app de escritorio). Sin red ni API.

El modo Manual guarda perfiles y fondos en ``<Dropbox>/TypeBeat Local`` para que las dos PCs
vean lo mismo. Cada PC solo recuerda dónde está esa carpeta.
"""
import json
import os

LOCAL_DIRNAME = 'TypeBeat Local'


def _info_files(env=None):
    env = os.environ if env is None else env
    for var in ('LOCALAPPDATA', 'APPDATA'):
        base = env.get(var)
        if base:
            yield os.path.join(base, 'Dropbox', 'info.json')


def find_dropbox(env=None, home=None):
    """Carpeta de Dropbox de esta PC, o None.

    1) ``info.json`` de la app de Dropbox (cuenta personal, si no la de empresa);
    2) ``~/Dropbox`` si existe.
    """
    for path in _info_files(env):
        try:
            with open(path, encoding='utf-8') as f:
                info = json.load(f)
        except (OSError, ValueError):
            continue
        for account in ('personal', 'business'):
            folder = (info.get(account) or {}).get('path') if isinstance(info, dict) else None
            if isinstance(folder, str) and os.path.isdir(folder):
                return folder
    fallback = os.path.join(home or os.path.expanduser('~'), 'Dropbox')
    return fallback if os.path.isdir(fallback) else None


def default_local_root(env=None, home=None):
    """Carpeta local de canales dentro de Dropbox, o None sin Dropbox.

    Primero la carpeta única de la app (``<Dropbox>/Soft Projects/Type Beat Generator/contenido``)
    si esta PC ya la tiene sincronizada; si no, ``<Dropbox>/TypeBeat Local`` como antes.
    """
    from core import dropbox_layout
    dropbox = find_dropbox(env, home)
    if not dropbox:
        return None
    unified = os.path.join(dropbox, *dropbox_layout.CONTENT.strip('/').split('/'))
    if os.path.isdir(os.path.join(unified, 'canales')):
        return unified
    return os.path.join(dropbox, LOCAL_DIRNAME)
