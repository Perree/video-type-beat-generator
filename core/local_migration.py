# -*- coding: utf-8 -*-
"""Pasa los canales del modo manual viejo a perfiles en la carpeta local (Dropbox). Sin Qt.

Origen (en la carpeta del proyecto): ``config/app_config.json`` (canales, grupos y plantillas),
``images/<canal>/<grupo>`` y ``videos/<canal>/<grupo>``. Cada grupo que no sea «Principal»
queda como canal propio ``<canal> - <grupo>``. Solo copia: nunca borra ni pisa nada.
"""
import json
import os

from core import channel_profile as cp
from core import channel_templates, description

LEGACY_IMAGES, LEGACY_VIDEOS = 'images', 'videos'


def _read_config(repo):
    try:
        with open(os.path.join(repo, 'config', 'app_config.json'), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _files(folder, suffixes):
    if not os.path.isdir(folder):
        return []
    return sorted(os.path.join(folder, n) for n in os.listdir(folder)
                  if n.lower().endswith(suffixes) and os.path.isfile(os.path.join(folder, n)))


def _legacy_groups(repo, config):
    """``{(canal, grupo)}`` de app_config y de las carpetas images/ y videos/."""
    pairs = []
    for name, cfg in (config.get('channels') or {}).items():
        groups = cfg.get('groups') if isinstance(cfg, dict) else None
        for group in (groups if isinstance(groups, list) and groups else ['Principal']):
            pairs.append((name, group))
    for base in (LEGACY_IMAGES, LEGACY_VIDEOS):
        root = os.path.join(repo, base)
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            if not os.path.isdir(os.path.join(root, name)):
                continue
            for group in sorted(os.listdir(os.path.join(root, name))):
                if os.path.isdir(os.path.join(root, name, group)):
                    pairs.append((name, group))
    seen, out = set(), []
    for name, group in pairs:
        key = (name, group.lower())
        if key not in seen:
            seen.add(key)
            out.append((name, group))
    return out


def target_name(channel, group):
    return channel if group.strip().lower() == 'principal' else f'{channel} - {group}'


def plan(repo, local_root):
    """Lista de acciones (sin escribir nada). Cada una: canal destino, fondos, perfil, estado."""
    config = _read_config(repo)
    global_title = config.get('name_template') or channel_templates.DEFAULT_TITLE_TEMPLATE
    actions = []
    for channel, group in _legacy_groups(repo, config):
        target = target_name(channel, group)
        try:
            cp.check_name(target)
        except cp.ProfileError as exc:
            actions.append({'canal': target, 'error': str(exc)})
            continue
        images = _files(os.path.join(repo, LEGACY_IMAGES, channel, group), cp.IMAGE_SUFFIXES)
        videos = _files(os.path.join(repo, LEGACY_VIDEOS, channel, group), cp.VIDEO_SUFFIXES)
        cfg = (config.get('channels') or {}).get(channel) or {}
        settings = description.get_channel_settings(channel, os.path.join(repo, 'config', 'app_config.json'))
        profile = dict(cp.default_profile(target),
                       fondo=cp.MODE_VIDEO if videos and not images else cp.MODE_IMAGE,
                       titulo=channel_templates.get_title_template(cfg, global_title),
                       descripcion=settings['template'], socials=settings['socials'],
                       hashtags=settings['hashtags'])
        exists = os.path.exists(os.path.join(cp.channel_dir(local_root, target), cp.PROFILE_FILE))
        actions.append({'canal': target, 'origen': f'{channel}/{group}', 'imagenes': images,
                        'videos': videos, 'perfil': profile, 'perfil_existe': exists})
    return actions


def apply(actions, local_root):
    """Crea canales y copia fondos que falten. Devuelve ``{canales, archivos, errores}``."""
    created, copied, errors = 0, 0, []
    for action in actions:
        if 'error' in action:
            errors.append(f"{action['canal']}: {action['error']}")
            continue
        name = action['canal']
        if not action['perfil_existe']:
            created += 1
        cp.create(local_root, name, action['perfil'])  # no pisa un perfil que ya exista
        target = os.path.join(cp.channel_dir(local_root, name), cp.BACKGROUNDS_DIR)
        copied += cp.copy_missing(action['imagenes'] + action['videos'], target)
    return {'canales': created, 'archivos': copied, 'errores': errors}


def summary(actions):
    lines = []
    for a in actions:
        if 'error' in a:
            lines.append(f"✗ {a['canal']}: {a['error']}")
            continue
        state = 'ya existe (solo copia fondos que falten)' if a['perfil_existe'] else 'nuevo'
        lines.append(f"• {a['canal']} ← {a['origen']}: {len(a['imagenes'])} imágenes, "
                     f"{len(a['videos'])} videos — {state}")
    return lines
