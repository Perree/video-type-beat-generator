# -*- coding: utf-8 -*-
"""Registro de la app en Dropbox: ``/automatizacion/canales.json`` y ``ajustes.json``.

Reusa el transporte de ``beat_cloud`` (CAS por ``rev``, ``decode_document``). Los workers no
leen estos documentos: el escritorio proyecta lo que necesitan a sus propios archivos.
Nunca guarda secretos. ``canales.json`` pasa por ``channel_kind.validate_registry`` antes de
cada escritura.
"""
from copy import deepcopy
import json

from core import channel_kind, cloud_merge, dropbox_layout
from core.beat_cloud import BeatCloud, CloudError, Conflict, Missing, decode_document

ROOT = dropbox_layout.REGISTRY_DIR
PATHS = {'canales': ROOT + '/canales.json', 'ajustes': ROOT + '/ajustes.json'}
NAMESPACE = 'automatizacion'
VERSION = 1
MAX_CHANNELS = 100
TEMPLATE_KEYS = ('title_template', 'description_template', 'socials', 'hashtags', 'link')
_ROW_KEYS = {'slug', 'tipo', 'clave', 'nombre', 'activo', 'legacy_default', 'plantillas',
             'creado'}


class RegistryError(ValueError):
    """Documento del registro inválido; el mensaje es apto para la UI."""


def empty(kind):
    if kind == 'canales':
        return {'schema_version': VERSION, 'namespace': NAMESPACE, 'canales': []}
    if kind == 'ajustes':
        return {'schema_version': VERSION, 'namespace': NAMESPACE}
    raise ValueError('invalid_kind')


def _text(value, limit, field, required=True):
    if type(value) is not str or len(value) > limit or (required and not value.strip()):
        raise RegistryError(f'Campo inválido en el registro: {field}.')
    return value


def _templates(raw):
    if not isinstance(raw, dict):
        raise RegistryError('Plantillas inválidas en el registro.')
    out = {}
    for key, value in raw.items():
        if key in TEMPLATE_KEYS:
            out[key] = _text(value, 20000, 'plantillas.' + key, required=False)
        elif key == 'tags':
            if (not isinstance(value, list) or len(value) > 100
                    or any(type(v) is not str or len(v) > 100 for v in value)):
                raise RegistryError('Tags inválidos en las plantillas.')
            out[key] = list(value)
        else:
            raise RegistryError('Campo desconocido en las plantillas.')
    return out


def normalize(kind, document):
    """Valida forma y tipos; devuelve una copia. ``canales`` además pasa por channel_kind."""
    if not isinstance(document, dict):
        raise RegistryError('El documento del registro tiene que ser un objeto.')
    doc = deepcopy(document)
    if doc.get('namespace', NAMESPACE) != NAMESPACE:
        raise RegistryError('El documento no es del registro de automatización.')
    if doc.get('schema_version', VERSION) != VERSION:
        raise RegistryError('Versión del registro no soportada.')
    doc.update(schema_version=VERSION, namespace=NAMESPACE)
    if kind == 'ajustes':
        return doc
    if kind != 'canales':
        raise ValueError('invalid_kind')
    rows = doc.setdefault('canales', [])
    if not isinstance(rows, list) or len(rows) > MAX_CHANNELS:
        raise RegistryError('La lista de canales es inválida o tiene más de 100 canales.')
    for row in rows:
        if not isinstance(row, dict) or set(row) - _ROW_KEYS:
            raise RegistryError('Ficha de canal con campos desconocidos.')
        row.setdefault('nombre', row.get('clave'))
        row.setdefault('activo', True)
        row.setdefault('legacy_default', False)
        _text(row.get('nombre'), 200, 'nombre')
        if type(row['activo']) is not bool:
            raise RegistryError('Campo inválido en el registro: activo.')
        if 'plantillas' in row:
            row['plantillas'] = _templates(row['plantillas'])
        if 'creado' in row:
            _text(row['creado'], 40, 'creado')
    try:
        channel_kind.validate_registry(doc)
    except channel_kind.ChannelKindError as exc:
        raise RegistryError(str(exc)) from None
    return doc


def payload(document):
    data = json.dumps(document, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')
    if len(data) > 1024 * 1024:
        raise RegistryError('El registro supera 1 MB.')
    return data


class CloudRegistry:
    def __init__(self, transport, retries=1, sleep=None):
        self.transport = transport
        self._cloud = BeatCloud(transport, retries=retries,
                                **({} if sleep is None else {'sleep': sleep}))

    def read(self, kind):
        """``(documento, rev)``; si no existe, el documento vacío y rev None."""
        path = PATHS[kind]
        try:
            data, rev = self._cloud._retry(lambda: self.transport.read(path))
        except Missing:
            return empty(kind), None
        try:
            return normalize(kind, decode_document(data)), rev
        except RegistryError:
            raise
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise CloudError('invalid_registry_document') from None

    def write(self, kind, document, rev, previous=None):
        """CAS: ``rev`` None crea solo si no existe. ``previous`` = lo leído con ese rev."""
        doc = normalize(kind, document)  # ya valida las reglas sin versión anterior
        if kind == 'canales' and previous is not None:
            try:
                channel_kind.validate_registry(doc, normalize(kind, previous))
            except channel_kind.ChannelKindError as exc:
                raise RegistryError(str(exc)) from None
        data = payload(doc)
        return self._cloud._retry(lambda: self.transport.write(PATHS[kind], data, rev))

    def save(self, kind, mine, base, rev):
        """Escribe ``mine``; ante Conflict fusiona por campo con lo releído y reintenta.

        Returns:
            ``(documento_guardado, rev)``. Levanta ``cloud_merge.MergeConflict`` con choques.
        """
        state = {'previous': base if rev is not None else None}

        def read():
            doc, new_rev = self.read(kind)
            state['previous'] = doc if new_rev is not None else None
            return doc, new_rev

        def write(doc, current):
            return self.write(kind, doc, current, state['previous'])

        return cloud_merge.save_merged(read, write, base, mine, rev, (Conflict,),
                                       prepare=lambda doc: normalize(kind, doc))


def templates_by_key(registry, tipo):
    """``{clave: plantillas}`` de los canales de ``tipo`` (para apply_channel_templates)."""
    return {row['clave']: dict(row.get('plantillas') or {})
            for row in channel_kind.channels_of(registry, tipo)}


def new_channel(tipo, slug, clave, nombre=None, now=None):
    """Ficha nueva (sin escribir). Para canales nuevos, ``clave = slug`` salvo que se pase otra."""
    from datetime import datetime, timezone
    channel_kind.check_type(tipo)
    channel_kind.check_slug(slug)
    stamp = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
    return {'slug': slug, 'tipo': tipo, 'clave': clave, 'nombre': nombre or clave,
            'activo': True, 'legacy_default': False, 'plantillas': {}, 'creado': stamp}


# --- Mismo registro con el cliente de Dropbox de loop kits (kit_cloud) ---

def read_with_dbx(kind, dbx):
    """Como ``CloudRegistry.read`` pero con ``kit_cloud`` (cliente del panel de kits)."""
    from core import kit_cloud
    data, rev = kit_cloud.read_json_rev(PATHS[kind], dbx=dbx)
    return (empty(kind), None) if rev is None and data is None else (normalize(kind, data), rev)


def save_with_dbx(kind, mine, base, rev, dbx):
    """Como ``CloudRegistry.save`` (CAS + merge por campo) con ``kit_cloud``."""
    from core import kit_cloud
    state = {'previous': base if rev is not None else None}

    def read():
        doc, new_rev = read_with_dbx(kind, dbx)
        state['previous'] = doc if new_rev is not None else None
        return doc, new_rev

    def write(doc, current):
        if kind == 'canales' and state['previous'] is not None:
            try:
                channel_kind.validate_registry(doc, normalize(kind, state['previous']))
            except channel_kind.ChannelKindError as exc:
                raise RegistryError(str(exc)) from None
        payload(doc)
        return kit_cloud.write_json(PATHS[kind], doc, rev=current or kit_cloud.NEW, dbx=dbx)

    return cloud_merge.save_merged(read, write, base, mine, rev, (kit_cloud.KitCloudConflict,),
                                   prepare=lambda doc: normalize(kind, doc))
