# -*- coding: utf-8 -*-
"""Tipo de canal (beats | loops): nombres derivados y reglas del registro.

Sin Qt ni red. Solo calcula lo que ya usan los workers: documento de Dropbox, Environment,
secretos, variable de lista y workflow. Las convenciones salen de ``beat_actions`` (Beats) y de
``kit_channel`` / ``kit_cloud`` (Loops); este módulo no inventa nombres nuevos.
"""
import json

from core import beat_actions, kit_channel, kit_cloud

BEATS = 'beats'
LOOPS = 'loops'
TYPES = (BEATS, LOOPS)
SLUG_MAX = 40
# Valor de ``section`` en app_config y en el config del worker de kits (formato que no cambia).
SECTIONS = {'beats': BEATS, 'loop_kits': LOOPS}
SECTION_OF = {BEATS: 'beats', LOOPS: 'loop_kits'}
# Sección de la "Marca personal" dada de baja: se ignora, no es un tipo.
IGNORED_SECTION = 'personal'

BEATS_DOCUMENT = '/type-beats/config.json'
BEATS_LIST = 'BEAT_CHANNELS'
BEATS_WORKFLOW = 'type-beats-daily.yml'
LOOPS_LIST = 'KIT_CHANNELS'
LOOPS_WORKFLOW = 'kit-weekly.yml'


class ChannelKindError(ValueError):
    """Tipo, slug o registro inválido; el mensaje no lleva valores secretos."""


def check_type(tipo):
    if tipo not in TYPES:
        raise ChannelKindError('Tipo de canal inválido: tiene que ser beats o loops.')
    return tipo


def check_slug(slug):
    """Regla común (docs/CLOUD_ONLY_SPIKE.md §7): patrón de kit_channel que además acepta
    ``beat_actions.matrix`` (empieza con letra), ≤ 40 y distinto de ``default``."""
    if type(slug) is not str or not slug or len(slug) > SLUG_MAX or slug == kit_channel.DEFAULT:
        raise ChannelKindError('Slug de canal inválido.')
    try:
        if not kit_channel.valid_slug(slug):
            raise ValueError()
        beat_actions.matrix(json.dumps([slug]))
    except ValueError:
        raise ChannelKindError('Slug de canal inválido.') from None
    return slug


def from_section(section):
    """``section`` legacy (app_config / config de kits) → tipo. ``personal`` → None.

    Ausente o desconocida es un error: nunca se asume Beats.
    """
    if section == IGNORED_SECTION:
        return None
    if section not in SECTIONS:
        raise ChannelKindError('Canal sin tipo definido (section ausente o desconocida).')
    return SECTIONS[section]


def is_loops_section(channel_cfg):
    """True si el canal de un config de kits es de Loops; error si no tiene tipo."""
    section = channel_cfg.get('section') if isinstance(channel_cfg, dict) else None
    return from_section(section) == LOOPS


def spec(tipo, slug, legacy_default=False):
    """Nombres que usan los workers para el canal ``(tipo, slug)``."""
    check_type(tipo)
    check_slug(slug)
    if tipo == BEATS:
        if legacy_default:
            raise ChannelKindError('legacy_default solo existe en Loops.')
        names = beat_actions.secret_names(slug)
        return {'tipo': BEATS, 'slug': slug, 'documents': {'config': BEATS_DOCUMENT},
                'environment': beat_actions.environment(slug),
                'secrets': (names['channel_secret'], names['youtube_secret']),
                'list_variable': BEATS_LIST, 'list_entry': slug, 'workflow': BEATS_WORKFLOW}
    key = kit_channel.DEFAULT if legacy_default else slug
    paths = kit_channel.paths(key, env={})
    return {'tipo': LOOPS, 'slug': slug,
            'documents': {'config': paths.config, 'kits': paths.kits, 'state': paths.state},
            'environment': kit_channel.environment(key),
            'secrets': tuple(kit_cloud.ENV_VARS + kit_cloud.RUNTIME_SECRETS),
            'list_variable': LOOPS_LIST, 'list_entry': key, 'workflow': LOOPS_WORKFLOW}


def _rows(registry):
    rows = registry.get('canales') if isinstance(registry, dict) else None
    if not isinstance(rows, list):
        raise ChannelKindError('El registro de canales no tiene la lista "canales".')
    if any(not isinstance(row, dict) for row in rows):
        raise ChannelKindError('Ficha de canal inválida.')
    return rows


def validate_registry(new, previous=None):
    """Reglas de ``canales.json`` contra la versión anterior (o None si es nuevo)."""
    rows = _rows(new)
    slugs, claves, legacy = set(), set(), 0
    for row in rows:
        tipo, slug = row.get('tipo'), row.get('slug')
        check_type(tipo)
        check_slug(slug)
        if slug in slugs:
            raise ChannelKindError('Slug repetido en el registro (también cuenta entre tipos).')
        slugs.add(slug)
        clave = row.get('clave')
        if type(clave) is not str or not clave.strip() or len(clave) > 200:
            raise ChannelKindError('Clave de canal inválida.')
        if clave in claves:
            raise ChannelKindError('Clave de canal repetida en el registro.')
        claves.add(clave)
        flag = row.get('legacy_default', False)
        if type(flag) is not bool:
            raise ChannelKindError('legacy_default tiene que ser true o false.')
        if flag:
            if tipo != LOOPS:
                raise ChannelKindError('legacy_default solo se permite en Loops.')
            legacy += 1
        elif tipo == LOOPS and kit_channel.slug(clave) != slug:
            # El worker corta si slug(nombre del canal) != slug (kit_channel.check_owner).
            raise ChannelKindError('En Loops el slug tiene que salir de la clave del canal.')
    if legacy > 1:
        raise ChannelKindError('Hay más de un canal con legacy_default.')
    if previous is None:
        return new
    old = _rows(previous)
    by_slug = {row.get('slug'): row for row in old}
    by_clave = {row.get('clave'): row for row in old}
    for row in rows:
        before = by_slug.get(row['slug'])
        if before is not None and (before.get('tipo') != row['tipo']
                                   or before.get('clave') != row['clave']):
            raise ChannelKindError('No se puede cambiar el tipo ni la clave de un canal existente.')
        before = by_clave.get(row['clave'])
        if before is not None and before.get('slug') != row['slug']:
            raise ChannelKindError('No se puede cambiar el slug de un canal existente.')
    return new


def channels_of(registry, tipo):
    """Fichas de ``tipo`` del registro, en orden."""
    check_type(tipo)
    return [row for row in _rows(registry) if row.get('tipo') == tipo]


def find(registry, clave):
    return next((row for row in _rows(registry) if row.get('clave') == clave), None)
