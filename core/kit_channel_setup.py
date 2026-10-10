# -*- coding: utf-8 -*-
"""Alta de la automatización de un canal de loop kits (sin Qt).

Guarda en Dropbox la config mínima del canal nuevo y lo anota en un índice
(``channels.json``, junto a la config del canal por defecto) que solo usa el panel para
armar el selector. El worker no lee el índice: cada corrida conoce solo su propio canal.
"""
import posixpath

from core import kit_channel, kit_cloud
from core.kit_publish import DEFAULT_SLOTS

SECTION = 'loop_kits'
_REGISTRY_NAME = 'channels.json'
# Lo único que se copia de un canal ya configurado en esta PC: sus plantillas.
_CHANNEL_KEYS = ('title_template', 'description_template', 'tags', 'socials', 'hashtags', 'link')
_SCAN_KEYS = ('scan_folders', 'loops_dirs', 'ignore_names', 'scan_max_depth')
_WRITE_ATTEMPTS = 4


class ChannelSetupError(ValueError):
    """Alta inválida; el mensaje es apto para mostrar al usuario."""


def registry_path(env=None):
    return posixpath.join(posixpath.dirname(kit_channel.default_paths(env).config), _REGISTRY_NAME)


def _entries(data):
    rows = data.get('channels') if isinstance(data, dict) else None
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and row.get('name') and row.get('slug'):
            out.append({'name': str(row['name']), 'slug': str(row['slug'])})
    return out


def load_registry(dbx=None):
    """Canales con automatización propia: ``[{name, slug}]`` (sin el canal por defecto)."""
    return _entries(kit_cloud.read_json(registry_path(), dbx=dbx))


def loop_kit_channels(*configs):
    """Nombres de los canales de la sección Loop kits en las configs dadas, sin repetir."""
    names = []
    for config in configs:
        for name, data in ((config or {}).get('channels') or {}).items():
            if isinstance(data, dict) and data.get('section') == SECTION and name not in names:
                names.append(name)
    return names


def minimal_config(name, base_config=None, local_config=None):
    """Config mínima del worker para un canal nuevo.

    De la config del canal por defecto solo se heredan la carpeta de kits (con sus reglas
    de recorrido) y los géneros; las
    plantillas del canal salen de la config local si el canal ya existe en la app. Marca,
    portada y claves de API no se copian: se cargan después para este canal.
    """
    base_kit = (base_config or {}).get('kit_preview') or {}
    channel = {'section': SECTION}
    for source in (base_config, local_config):
        known = ((source or {}).get('channels') or {}).get(name)
        if isinstance(known, dict):
            channel.update({k: known[k] for k in _CHANNEL_KEYS if k in known})
    kit = {'channel': name, 'slots': [dict(s) for s in DEFAULT_SLOTS],
           'genres': list(base_kit.get('genres') or [])}
    if base_kit.get('dropbox_root'):
        kit['dropbox_root'] = base_kit['dropbox_root']
    for key in _SCAN_KEYS:
        if key in base_kit:
            kit[key] = base_kit[key]
    return {'channels': {name: channel}, 'kit_preview': kit}


def _register(name, key, dbx):
    path = registry_path()
    for _ in range(_WRITE_ATTEMPTS):
        data, rev = kit_cloud.read_json_rev(path, dbx=dbx)
        rows = _entries(data)
        if {'name': name, 'slug': key} in rows:
            return
        rows = [r for r in rows if r['slug'] != key] + [{'name': name, 'slug': key}]
        try:
            kit_cloud.write_json(path, {'channels': rows},
                                 rev=rev if rev else kit_cloud.NEW, dbx=dbx)
        except kit_cloud.KitCloudConflict:
            continue
        return
    raise ChannelSetupError("No se pudo anotar el canal en el índice; probá de nuevo.")


def create(name, base_config=None, local_config=None, dbx=None):
    """Crea la automatización de ``name`` y devuelve sus rutas. Nunca pisa una existente."""
    name = str(name or '').strip()
    if not name:
        raise ChannelSetupError("Elegí el canal de la automatización nueva.")
    try:
        paths = kit_channel.for_channel(name)
    except kit_channel.KitChannelError as exc:
        raise ChannelSetupError(str(exc)) from None
    if any(r['slug'] == paths.slug and r['name'] != name for r in load_registry(dbx)):
        raise ChannelSetupError("Ya hay otro canal con un nombre equivalente.")
    if kit_cloud.read_json_rev(paths.config, dbx=dbx)[0] is None:
        try:
            kit_cloud.write_json(paths.config, minimal_config(name, base_config, local_config),
                                 rev=kit_cloud.NEW, dbx=dbx)
        except kit_cloud.KitCloudConflict:
            pass  # la creó otro en el medio: se usa la que quedó
    _register(name, paths.slug, dbx)
    return paths
