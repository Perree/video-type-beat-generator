# -*- coding: utf-8 -*-
"""Título por canal (plantilla con {name}) y nombre de archivo seguro."""

DEFAULT_TITLE_TEMPLATE = '[Type] {name} | Free for Profit'


def sanitize_filename(s):
    """Elimina caracteres no válidos para nombres de archivo."""
    for c in '\\/:*?"<>|':
        s = s.replace(c, '_')
    return s[:200].strip() or 'video'


def get_title_template(channel_cfg, global_default=DEFAULT_TITLE_TEMPLATE):
    """Plantilla del canal; si no tiene, la global."""
    return (channel_cfg or {}).get('title_template', '').strip() or global_default or DEFAULT_TITLE_TEMPLATE


def render_title(template, name, channel='', group=''):
    """Título crudo de YouTube (conserva | [ ] etc.)."""
    return template.replace('{name}', name).replace('{channel}', channel).replace('{group}', group)
