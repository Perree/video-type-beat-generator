# -*- coding: utf-8 -*-
"""Administrar canales de Loop kits: activo/pausado, día de publicación y quitar. Sin Qt.

Qué kits publica el robot y qué día lo decide la variable del repo ``KIT_CHANNELS``
(``slug=dia`` separados por coma; ver ``core/kit_channel.parse_schedule``). Se lee y escribe
con la sesión de ``gh`` (``core/gh_status``). Quitar un canal lo saca de esa lista y del índice
del panel (``channels.json`` en Dropbox); sus kits, su config y sus secretos no se borran, así
que se puede volver a crear igual.
"""
from core import gh_status, kit_channel, kit_cloud, kit_channel_setup
from core import automation_status as status

VARIABLE = 'KIT_CHANNELS'
DEFAULT = kit_channel.DEFAULT
_WRITE_ATTEMPTS = 4


class KitManageError(Exception):
    """Mensaje apto para la UI."""


def key_of(slug):
    """Slug del selector ('' = canal por defecto) → clave de ``KIT_CHANNELS``."""
    return DEFAULT if kit_channel.is_default(slug) else slug


def read_schedule(gh=None):
    """``{clave: día}`` de los canales activos, o ``None`` si todavía no se puede saber.

    Sin sesión de GitHub (o mientras se consulta en segundo plano) devuelve None.
    """
    client = gh or gh_status.default()
    if client.auth() != status.OK:
        return None
    raw = client.variable(VARIABLE)
    if raw is None and client.pending():
        return None
    try:
        return dict(kit_channel.parse_schedule(raw or ''))
    except kit_channel.KitChannelError:
        return None


def format_schedule(schedule):
    """``{clave: día}`` → texto de ``KIT_CHANNELS`` (``-`` si no queda ninguno activo)."""
    if not schedule:
        return kit_channel.NONE
    keys = sorted(schedule, key=lambda k: (k != DEFAULT, k))
    return ','.join(f'{key}={schedule[key]}' for key in keys)


def apply_changes(schedule, changes):
    """Aplica ``{clave: {'active': bool, 'day': int} | 'remove'}`` a una copia de ``schedule``."""
    out = dict(schedule)
    for key, change in changes.items():
        if change == 'remove' or not change.get('active', True):
            out.pop(key, None)
        else:
            day = change.get('day', out.get(key, kit_channel.FIRST_WEEKDAY))
            if not isinstance(day, int) or not 0 <= day <= 6:
                raise KitManageError('Día de publicación inválido.')
            out[key] = day
    return out


def write_schedule(schedule, gh=None):
    client = gh or gh_status.default()
    if client.auth() != status.OK:
        raise KitManageError('GitHub no está conectado: conectalo en Conexiones.')
    text = format_schedule(schedule)
    kit_channel.parse_schedule(text)  # nunca se escribe algo que el robot no entienda
    if not client.set_variable(VARIABLE, text):
        raise KitManageError('No se pudo guardar en GitHub. Probá de nuevo.')
    return text


def remove_from_index(slug, dbx=None):
    """Saca el canal del índice del panel (``channels.json``) por CAS. El canal por defecto no está."""
    if kit_channel.is_default(slug):
        raise KitManageError('El canal por defecto es la base de Loop kits: se puede pausar, no quitar.')
    path = kit_channel_setup.registry_path()
    for _ in range(_WRITE_ATTEMPTS):
        data, rev = kit_cloud.read_json_rev(path, dbx=dbx)
        rows = kit_channel_setup._entries(data)
        kept = [row for row in rows if row['slug'] != slug]
        if len(kept) == len(rows):
            return False
        try:
            kit_cloud.write_json(path, {'channels': kept}, rev=rev, dbx=dbx)
        except kit_cloud.KitCloudConflict:
            continue
        return True
    raise KitManageError('No se pudo quitar del índice (otra PC lo estaba cambiando). Probá de nuevo.')


def save(changes, gh=None, dbx=None):
    """Guarda cambios de kits: primero la lista del robot (lo que importa), después el índice."""
    current = read_schedule(gh)
    if current is None:
        raise KitManageError('No se pudo leer la lista de canales de GitHub. Revisá la conexión.')
    new = apply_changes(current, changes)
    text = write_schedule(new, gh) if new != current else format_schedule(current)
    removed = []
    for key, change in changes.items():
        if change == 'remove':
            remove_from_index(key, dbx)
            removed.append(key)
    return {'kit_channels': text, 'removed': removed}
