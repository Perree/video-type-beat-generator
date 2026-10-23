# -*- coding: utf-8 -*-
"""Título por canal (plantilla con {name}) y nombre de archivo seguro."""

DEFAULT_TITLE_TEMPLATE = '[Type] {name} | Free for Profit'


def reserved_filename(value):
    """Windows device names stay reserved even when followed by an extension."""
    stem = value.split('.', 1)[0].rstrip(' ').upper()
    return stem in {'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$'} or (
        len(stem) == 4 and stem[:3] in ('COM', 'LPT') and stem[3] in '123456789¹²³')


def sanitize_filename(s):
    """Elimina caracteres no válidos para nombres de archivo."""
    for c in '\\/:*?"<>|':
        s = s.replace(c, '_')
    s = ''.join('_' if ord(c) < 32 else c for c in s)[:200].strip().rstrip(' .') or 'video'
    return '_' + s if reserved_filename(s) else s


def get_title_template(channel_cfg, global_default=DEFAULT_TITLE_TEMPLATE):
    """Plantilla del canal; si no tiene, la global."""
    return (channel_cfg or {}).get('title_template', '').strip() or global_default or DEFAULT_TITLE_TEMPLATE


def render_title(template, name, channel='', group=''):
    """Título crudo de YouTube (conserva | [ ] etc.)."""
    return template.replace('{name}', name).replace('{channel}', channel).replace('{group}', group)
