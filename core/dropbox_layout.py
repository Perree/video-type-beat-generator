# -*- coding: utf-8 -*-
"""Dónde vive todo en Dropbox: una sola carpeta para la app. Sin Qt ni red.

    /Soft Projects/Type Beat Generator/
      datos/        lo que usa el programa (JSONs): automatizacion, beats, loop_kits (+ estado)
      contenido/    lo que agrega el usuario: canales/<canal>/{fondos,miniaturas}, entrada,
                    loop_kits/referencias
      _archivo/     copias viejas

Antes estas carpetas estaban sueltas en la raíz de Dropbox. ``translate`` cambia las rutas
viejas que hayan quedado guardadas adentro de los JSON (config, estado, historial) por las
nuevas, así nada se rompe aunque un documento todavía no se haya vuelto a guardar.
La raíz se puede cambiar con la variable de entorno ``TYPEBEAT_DROPBOX_ROOT``.
"""
import os

ROOT = (os.environ.get('TYPEBEAT_DROPBOX_ROOT') or '/Soft Projects/Type Beat Generator').rstrip('/')
DATA = ROOT + '/datos'
CONTENT = ROOT + '/contenido'
ARCHIVE = ROOT + '/_archivo'

REGISTRY_DIR = DATA + '/automatizacion'
BEATS_DIR = DATA + '/beats'
KITS_DIR = DATA + '/loop_kits'
KITS_STATE_DIR = KITS_DIR + '/estado'
KITS_REFS_DIR = CONTENT + '/loop_kits/referencias'
CHANNELS_DIR = CONTENT + '/canales'

KITS_CONFIG = KITS_DIR + '/config.json'
KITS_CATALOG = KITS_DIR + '/kits.json'
KITS_STATE = KITS_STATE_DIR + '/state.json'

# Rutas de antes → rutas de ahora (las más largas primero: «ey mat thumbnails» antes que «ey mat»).
MOVES = (
    ('/AudioVisual Stuff/Type Beats - STUFF/ey mat thumbnails', CHANNELS_DIR + '/ey mat/miniaturas'),
    ('/AudioVisual Stuff/Type Beats - STUFF/ey mat', CHANNELS_DIR + '/ey mat/fondos'),
    ('/loop_kits/_referencias', KITS_REFS_DIR),
    ('/loop_kits/_automation', KITS_DIR),
    ('/loop_kits_state', KITS_STATE_DIR),
    ('/automatizacion', REGISTRY_DIR),
    ('/type-beats', BEATS_DIR),
)


def beats_document(kind):
    """``config`` / ``state`` de Beats."""
    return f'{BEATS_DIR}/{kind}.json'


def translate_path(value):
    """Ruta vieja → nueva (respeta si venía en minúsculas, como guarda el estado). Otra cosa: igual."""
    if not isinstance(value, str) or not value.startswith('/'):
        return value
    lower = value.lower()
    for old, new in MOVES:
        low_old = old.lower()
        if lower == low_old or lower.startswith(low_old + '/'):
            rest = value[len(old):]
            # El estado guarda rutas en minúsculas (path_lower de Dropbox) y las compara así.
            prefix = new.lower() if value == lower else new
            return prefix + rest
    return value


def translate(document):
    """Copia del documento JSON con todas las rutas viejas cambiadas por las nuevas."""
    if isinstance(document, dict):
        return {translate_path(k) if isinstance(k, str) else k: translate(v) for k, v in document.items()}
    if isinstance(document, list):
        return [translate(v) for v in document]
    return translate_path(document)
