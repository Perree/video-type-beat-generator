# -*- coding: utf-8 -*-
"""Varios canales de loop kits: slug, rutas por canal, día de corrida y prefijo de avisos.

Cada canal tiene su config, su catálogo y su estado en Dropbox. El canal por defecto (el
primero) conserva las rutas de siempre; los demás cuelgan de una subcarpeta con su slug dentro
de las mismas carpetas. Las rutas salen solo del slug del canal que corre: no hay forma de
pedir las de otro. Solo usa la librería estándar (el job ``plan`` del workflow lo importa sin
instalar dependencias).
"""
import hashlib
import json
import os
import posixpath
import re
import unicodedata
from collections import namedtuple

DEFAULT = 'default'
ENV_AUTOMATION = 'KIT_AUTOMATION'
ENV_PREFIX = 'kit-weekly'
# Mismos valores por defecto que kit_settings / kit_state (el smoke compara que coincidan).
_DEFAULT_CONFIG = '/loop_kits/_automation/config.json'
_DEFAULT_KITS = '/loop_kits/_automation/kits.json'
_DEFAULT_STATE = '/loop_kits_state/state.json'
_SLUG_RE = re.compile(r'[a-z0-9]+(?:-[a-z0-9]+)*\Z')
_SLUG_MAX = 40
_DAYS = ('lun', 'mar', 'mie', 'jue', 'vie', 'sab', 'dom')
FIRST_WEEKDAY = 6  # el primer canal corre el domingo, como hasta ahora

Paths = namedtuple('Paths', 'slug config kits state is_default')


class KitChannelError(ValueError):
    """Canal o calendario inválido; el mensaje no lleva nombres de canal."""


def slug(channel):
    """Identificador estable del canal: minúsculas, sin tildes, ``a-z0-9`` y guiones.

    Un nombre sin ninguna letra o número latino usa un hash corto, también estable.
    """
    text = unicodedata.normalize('NFKD', str(channel or '').strip())
    text = ''.join(c for c in text if not unicodedata.combining(c)).lower()
    out = re.sub(r'[^a-z0-9]+', '-', text).strip('-')[:_SLUG_MAX].strip('-')
    if not out and text:
        out = 'canal-' + hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]
    return out


def is_default(key):
    return not str(key or '').strip() or str(key).strip().lower() == DEFAULT


def _check(key):
    key = str(key or '').strip().lower()
    if not _SLUG_RE.match(key) or len(key) > _SLUG_MAX:
        raise KitChannelError("Slug de canal inválido.")
    return key


def default_paths(env=None):
    """Rutas de hoy; ``KIT_CONFIG_PATH`` / ``KIT_CATALOG_PATH`` / ``KIT_STATE_PATH`` mandan."""
    env = os.environ if env is None else env
    return Paths(DEFAULT, env.get('KIT_CONFIG_PATH') or _DEFAULT_CONFIG,
                 env.get('KIT_CATALOG_PATH') or _DEFAULT_KITS,
                 env.get('KIT_STATE_PATH') or _DEFAULT_STATE, True)


def _sub(path, key):
    return posixpath.join(posixpath.dirname(path), key, posixpath.basename(path))


def paths(key=None, env=None):
    """Rutas de config, catálogo y estado del canal ``key`` (slug; vacío o ``default``)."""
    base = default_paths(env)
    if is_default(key):
        return base
    key = _check(key)
    return Paths(key, _sub(base.config, key), _sub(base.kits, key), _sub(base.state, key), False)


def for_channel(channel, env=None):
    """Rutas a partir del nombre del canal."""
    key = slug(channel)
    if not key or key == DEFAULT:
        raise KitChannelError("El nombre del canal no sirve para una automatización.")
    return paths(key, env)


def environment(key=None):
    """Environment de GitHub del canal: ``kit-weekly`` o ``kit-weekly-<slug>``."""
    return ENV_PREFIX if is_default(key) else f'{ENV_PREFIX}-{_check(key)}'


def check_owner(channel_paths, channel, token_channel=None):
    """Corta si la config (o el token de YouTube) no son del canal de estas rutas.

    El canal por defecto no se controla: se comporta como antes.
    """
    if channel_paths is None or channel_paths.is_default:
        return
    if slug(channel) != channel_paths.slug:
        raise KitChannelError("La config no corresponde a este canal.")
    if token_channel is not None and slug(token_channel) != channel_paths.slug:
        raise KitChannelError("El token de YouTube de este Environment es de otro canal.")


# --- Avisos ---

def prefixed(label, text):
    return f"[{label}] {text}" if label else text


class Prefixed:
    """Notificador que antepone el nombre del canal a cada mensaje."""

    def __init__(self, notifier, label):
        self._notifier, self._label = notifier, label

    def send(self, text, photo=None):
        if photo is None:
            return self._notifier.send(prefixed(self._label, text))
        return self._notifier.send(prefixed(self._label, text), photo)


# --- Día de corrida de cada canal ---

def _weekday(text):
    text = text.strip().lower()
    if text in _DAYS:
        return _DAYS.index(text)
    if text.isdigit() and int(text) <= 6:
        return int(text)
    raise KitChannelError("Día inválido en KIT_CHANNELS (0-6 con lunes = 0, o lun..dom).")


def parse_schedule(text):
    """``KIT_CHANNELS`` (``slug[=dia]`` separados por coma) a ``[(slug, weekday)]``.

    Vacío: solo el canal por defecto. Sin día, un canal por día en el orden de la lista
    empezando por el domingo. Día: 0-6 (lunes = 0) o ``lun..dom``.
    """
    out, seen = [], set()
    for i, part in enumerate(p for p in str(text or '').split(',') if p.strip()):
        name, _, day = part.partition('=')
        key = DEFAULT if is_default(name) else _check(name)
        if key in seen:
            raise KitChannelError("Canal repetido en KIT_CHANNELS.")
        seen.add(key)
        out.append((key, _weekday(day) if day.strip() else (FIRST_WEEKDAY + i) % 7))
    return out or [(DEFAULT, FIRST_WEEKDAY)]


def matrix(text, weekday, only=None):
    """Canales que corren: los del día ``weekday``, o solo ``only`` (corrida manual).

    Returns:
        lista de ``{channel, suffix}``; ``suffix`` completa el nombre del Environment.
    """
    schedule = parse_schedule(text)
    if only is not None and str(only).strip():
        key = DEFAULT if is_default(only) else _check(only)
        if key not in dict(schedule):
            raise KitChannelError("Ese canal no está en KIT_CHANNELS.")
        chosen = [key]
    else:
        chosen = [key for key, day in schedule if day == weekday]
    return [{'channel': key, 'suffix': environment(key)[len(ENV_PREFIX):]} for key in chosen]


def matrix_json(text, weekday, only=None):
    return json.dumps(matrix(text, weekday, only), separators=(',', ':'))
