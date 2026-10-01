# -*- coding: utf-8 -*-
"""Plantilla de descripción de YouTube por canal (guardada en config/app_config.json)."""
import json
import os

CONFIG_FILE = os.path.join('config', 'app_config.json')

DEFAULT_TEMPLATE = (
    "{name} Type Beat | {bpm} BPM | {key}\n"
    "\n"
    "🎧 Compra / Download: {beatstars_url}\n"
    "\n"
    "{socials}\n"
    "\n"
    "Tags: {tags}\n"
    "{hashtags}"
)


class _SafeDict(dict):
    def __missing__(self, key):
        return '{' + key + '}'


def _load(config_path):
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_channel_settings(channel, config_path=None):
    """Devuelve {'template', 'socials', 'hashtags'} del canal (con valores por defecto)."""
    ch = _load(config_path or CONFIG_FILE).get('channels', {}).get(channel, {})
    return {
        'template': ch.get('description_template') or DEFAULT_TEMPLATE,
        'socials': ch.get('socials', ''),
        'hashtags': ch.get('hashtags', ''),
    }


def save_channel_template(channel, template, config_path=None):
    """Guarda la plantilla en el canal indicado (lo crea si no existe)."""
    path = config_path or CONFIG_FILE
    config = _load(path)
    config.setdefault('channels', {}).setdefault(channel, {'groups': ['Principal']})
    config['channels'][channel]['description_template'] = template
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _fmt_bpm(bpm):
    if bpm in (None, ''):
        return ''
    bpm = float(bpm)
    return str(int(bpm)) if bpm == int(bpm) else f"{bpm:.1f}"


def render(template, name, bpm=None, key=None, beatstars_url='', tags='',
           socials='', hashtags=''):
    """Rellena {name} {bpm} {key} {beatstars_url} {tags} {socials} {hashtags}.

    Variables desconocidas se dejan tal cual; sin tags se usa '<name> type beat'.
    """
    values = _SafeDict(
        name=name or '', bpm=_fmt_bpm(bpm), key=key or '',
        beatstars_url=beatstars_url or '',
        tags=tags or (f"{name} type beat" if name else ''),
        socials=socials or '', hashtags=hashtags or '')
    try:
        return template.format_map(values)
    except (ValueError, IndexError, KeyError, AttributeError):
        return template  # llaves mal formadas: mostrar la plantilla sin tocar


def render_for_channel(channel, name, bpm=None, key=None, beatstars_url='', tags='',
                       config_path=None):
    s = get_channel_settings(channel, config_path)
    return render(s['template'], name, bpm, key, beatstars_url, tags,
                  s['socials'], s['hashtags'])
