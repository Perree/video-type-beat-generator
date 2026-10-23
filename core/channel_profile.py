# -*- coding: utf-8 -*-
"""Perfil de estilo por canal para el modo Manual (local). Sin Qt ni red.

Estructura dentro de la carpeta local (normalmente ``<Dropbox>/TypeBeat Local``)::

    canales/<canal>/perfil.json   estilo: fondo, título, descripción, tags, miniatura
    canales/<canal>/fondos/       imágenes y/o videos stock
    canales/<canal>/miniaturas/   opcional: imágenes para la miniatura
    entrada/<canal>/              beats a generar (los usa la tanda en bulk)
"""
import json
import os
import re
import shutil
from copy import deepcopy

from core import beat_title, description

SCHEMA_VERSION = 1
PROFILE_FILE = 'perfil.json'
CHANNELS_DIR, INPUT_DIR = 'canales', 'entrada'
BACKGROUNDS_DIR, THUMBNAILS_DIR = 'fondos', 'miniaturas'
MODE_IMAGE, MODE_VIDEO = 'image', 'video'
IMAGE_SUFFIXES = ('.jpg', '.jpeg', '.jfif', '.png', '.webp', '.bmp')
VIDEO_SUFFIXES = ('.mp4', '.mov', '.mkv', '.webm', '.avi', '.wmv')
TITLE_MAX = 100        # límite de YouTube
TAGS_MAX = 500         # límite de YouTube (suma de los tags separados por coma)
DESCRIPTION_MAX = 5000
NAME_MAX = 80
DEFAULT_TITLE = '[FREE] {artist} Type Beat - "{name}"'
_BAD_NAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_CONFLICT = re.compile(r'conflicted copy|copia en conflicto|copia con conflicto', re.I)
# Atributos de Windows de un archivo «solo en línea» (Dropbox / OneDrive no lo bajaron).
_ONLINE_ONLY = 0x00400000 | 0x00040000 | 0x00001000  # RECALL_ON_DATA_ACCESS | RECALL_ON_OPEN | OFFLINE


class ProfileError(ValueError):
    """Perfil o nombre inválido; el mensaje es apto para la UI."""


def check_name(name):
    if (not isinstance(name, str) or not name.strip() or name != name.strip()
            or len(name) > NAME_MAX or _BAD_NAME.search(name) or name in ('.', '..')
            or name.endswith('.')):
        raise ProfileError('Nombre de canal inválido (sin \\ / : * ? " < > | y hasta 80 caracteres).')
    return name


def channel_dir(root, name):
    return os.path.join(root, CHANNELS_DIR, check_name(name))


def input_dir(root, name):
    return os.path.join(root, INPUT_DIR, check_name(name))


def default_profile(name):
    return {
        'schema_version': SCHEMA_VERSION,
        'nombre': name,
        'fondo': MODE_IMAGE,
        'titulo': DEFAULT_TITLE,
        'descripcion': description.DEFAULT_TEMPLATE,
        'socials': '',
        'hashtags': '',
        'tags': ['{artist} type beat', '{name} type beat', 'type beat', 'free beat'],
        'miniatura_con_titulo': False,
        'artistas': [],
    }


def _text(data, key, limit):
    value = data.get(key)
    if not isinstance(value, str) or len(value) > limit:
        raise ProfileError(f'Campo inválido en el perfil: {key}.')
    return value


def validate(data, name=None):
    """Copia normalizada del perfil (completa los campos que falten) o ProfileError."""
    if not isinstance(data, dict):
        raise ProfileError('El perfil tiene que ser un objeto JSON.')
    if data.get('schema_version', SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ProfileError('Versión de perfil no soportada.')
    profile = default_profile(name or data.get('nombre') or 'canal')
    profile.update(deepcopy(data))
    profile['schema_version'] = SCHEMA_VERSION
    if name is not None:
        profile['nombre'] = name
    if profile['fondo'] not in (MODE_IMAGE, MODE_VIDEO):
        raise ProfileError('El fondo tiene que ser imagen o video.')
    if not _text(profile, 'titulo', 300).strip():
        raise ProfileError('La plantilla del título está vacía.')
    _text(profile, 'descripcion', DESCRIPTION_MAX)
    _text(profile, 'socials', 2000)
    _text(profile, 'hashtags', 1000)
    tags = profile['tags']
    if not isinstance(tags, list) or any(not isinstance(t, str) or len(t) > 100 for t in tags):
        raise ProfileError('Los tags tienen que ser una lista de textos.')
    profile['tags'] = [t.strip() for t in tags if t.strip()]
    artists = profile['artistas']
    if (not isinstance(artists, list) or len(artists) > 50
            or any(not isinstance(a, str) or len(a) > 60 for a in artists)):
        raise ProfileError('Los artistas tienen que ser una lista de textos (hasta 50).')
    profile['artistas'] = [a.strip() for a in artists if a.strip()]
    if type(profile['miniatura_con_titulo']) is not bool:
        raise ProfileError('Campo inválido en el perfil: miniatura_con_titulo.')
    if 'estilo' in profile:  # opcional: sin estilo, el canal sale como siempre
        from core import style
        try:
            profile['estilo'] = style.validate(profile['estilo'])
        except style.StyleError as exc:
            raise ProfileError(str(exc)) from None
    return profile


def load(root, name):
    """Perfil del canal; uno por defecto si todavía no tiene ``perfil.json``."""
    path = os.path.join(channel_dir(root, name), PROFILE_FILE)
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        return default_profile(name)
    except (OSError, ValueError):
        raise ProfileError(f'No se pudo leer el perfil de {name}.') from None
    return validate(data, name)


def save(root, name, data):
    profile = validate(data, name)
    folder = channel_dir(root, name)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, PROFILE_FILE)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    return profile


def create(root, name, profile=None):
    """Crea las carpetas del canal (fondos, miniaturas, entrada) y su perfil si no existe."""
    folder = channel_dir(root, name)
    for sub in (BACKGROUNDS_DIR, THUMBNAILS_DIR):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    os.makedirs(input_dir(root, name), exist_ok=True)
    if not os.path.exists(os.path.join(folder, PROFILE_FILE)):
        return save(root, name, profile or default_profile(name))
    return load(root, name)


def duplicate(root, source, new):
    """Canal nuevo con el mismo estilo que ``source``; los fondos empiezan vacíos."""
    check_name(new)
    if os.path.exists(channel_dir(root, new)):
        raise ProfileError(f'Ya existe un canal llamado {new}.')
    return create(root, new, dict(load(root, source), nombre=new))


def list_channels(root):
    base = os.path.join(root, CHANNELS_DIR)
    if not os.path.isdir(base):
        return []
    names = []
    for name in os.listdir(base):
        try:
            check_name(name)
        except ProfileError:
            continue
        if os.path.isdir(os.path.join(base, name)):
            names.append(name)
    return sorted(names, key=str.lower)


def conflicts(root, name):
    """Copias en conflicto que dejó Dropbox en la carpeta del canal (para avisar)."""
    folder = channel_dir(root, name)
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder) if _CONFLICT.search(f))


def online_only(path):
    """True si Dropbox todavía no bajó el archivo a esta PC (Windows)."""
    try:
        attrs = getattr(os.stat(path), 'st_file_attributes', 0)
    except OSError:
        return False
    return bool(attrs & _ONLINE_ONLY)


def media(root, name, kind):
    """``(disponibles, solo_en_linea)``: rutas de fondos (``image``/``video``) o ``thumbnail``."""
    if kind == 'thumbnail':
        folder, suffixes = os.path.join(channel_dir(root, name), THUMBNAILS_DIR), IMAGE_SUFFIXES
    else:
        folder = os.path.join(channel_dir(root, name), BACKGROUNDS_DIR)
        suffixes = IMAGE_SUFFIXES if kind == MODE_IMAGE else VIDEO_SUFFIXES
    if not os.path.isdir(folder):
        return [], []
    ready, remote = [], []
    for entry in sorted(os.listdir(folder)):
        path = os.path.join(folder, entry)
        if entry.lower().endswith(suffixes) and os.path.isfile(path):
            (remote if online_only(path) else ready).append(path)
    return ready, remote


def fit_title(title, limit=TITLE_MAX):
    """Corta en la última palabra que entra; nunca pasa ``limit`` caracteres."""
    title = ' '.join(title.split())
    if len(title) <= limit:
        return title
    cut = title[:limit].rsplit(' ', 1)[0].rstrip(' -|,~')
    return cut or title[:limit]


def render_tags(profile, values):
    """Tags del perfil con las variables del beat, sin repetir y hasta 500 caracteres.

    Un tag que usa una variable vacía (p. ej. ``{artist}`` sin artista) se omite.
    """
    out, seen, total = [], set(), 0
    for tag in profile['tags']:
        if any(not str(values.get(n) or '').strip() for n in beat_title.variables_in(tag)):
            continue
        value = ' '.join(beat_title.fill(tag, values).split())
        key = value.lower()
        if not value or key in seen:
            continue
        extra = len(value) + (2 if out else 0)
        if total + extra > TAGS_MAX:
            break
        out.append(value)
        seen.add(key)
        total += extra
    return out


def copy_missing(files, target_dir):
    """Copia sin pisar (mismo nombre y tamaño = ya está). Devuelve cuántos copió."""
    os.makedirs(target_dir, exist_ok=True)
    copied = 0
    for src in files:
        dest = os.path.join(target_dir, os.path.basename(src))
        if os.path.exists(dest):
            continue
        shutil.copy2(src, dest)
        copied += 1
    return copied
