#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga con ``gh`` el Environment y los secretos de un canal de Type Beats.

Uso: ``py -3 scripts/beat_secrets_sync.py --channel "ey mat" --slug ey-mat``.

Reutiliza la app y el refresh token de Dropbox de Loopkits (``tokens/dropbox.json`` +
``config/dropbox_app.json``) y el token de YouTube del canal (``tokens/<canal>.json``). Telegram sale de
``tokens/kit_secrets.json`` (``KIT_TELEGRAM_*``), del entorno (``BEAT_TELEGRAM_*``) o de un prompt sin eco.
Cada valor viaja a ``gh`` por stdin: nunca va en un argumento ni se imprime. Crea el Environment
``type-beats-<slug>`` restringido a la rama principal y agrega el slug a la variable ``BEAT_CHANNELS``.
"""
import argparse
import getpass
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts import kit_secrets_sync as kit

DROPBOX_FILE = os.path.join(ROOT, 'tokens', 'dropbox.json')
APP_FILE = os.path.join(ROOT, 'config', 'dropbox_app.json')
TELEGRAM = (('BEAT_TELEGRAM_TOKEN', 'KIT_TELEGRAM_TOKEN', 'Token del bot de Telegram'),
            ('BEAT_TELEGRAM_CHAT_ID', 'KIT_TELEGRAM_CHAT_ID', 'Chat id de Telegram'))


def values_for(channel, yt_token_file=None, env=None, ask=getpass.getpass):
    env = os.environ if env is None else env
    dropbox, app = kit._load_json(DROPBOX_FILE), kit._load_json(APP_FILE)
    shared = kit._load_json(kit.SHARED_FILE)
    values = {'BEAT_CHANNEL_ID': channel,
              'BEAT_DROPBOX_REFRESH_TOKEN': str(dropbox.get('refresh_token') or '').strip(),
              'BEAT_DROPBOX_APP_KEY': str(app.get('app_key') or '').strip(),
              'BEAT_YT_TOKEN_JSON': kit.youtube_token(channel, yt_token_file)}
    for name, kit_name, label in TELEGRAM:
        value = str(env.get(name) or shared.get(kit_name) or '').strip() or ask(f"{label}: ").strip()
        values[name] = value
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise kit.SyncError(f"Faltan valores: {', '.join(missing)}.")
    return values


def add_channel_variable(slug, repo=None, runner=kit._gh):
    """Agrega ``slug`` a la variable ``BEAT_CHANNELS`` (array JSON) sin quitar los existentes."""
    args = ['variable', 'get', 'BEAT_CHANNELS'] + (['--repo', repo] if repo else [])
    try:
        current = subprocess.run(['gh', *args], capture_output=True, text=True).stdout.strip()
        slugs = json.loads(current) if current else []
    except (OSError, ValueError):
        slugs = []
    if not isinstance(slugs, list):
        slugs = []
    if slug not in slugs:
        slugs.append(slug)
    set_args = ['variable', 'set', 'BEAT_CHANNELS'] + (['--repo', repo] if repo else [])
    if runner(set_args, json.dumps(slugs)) != 0:
        raise kit.SyncError("No se pudo guardar la variable BEAT_CHANNELS.")
    return slugs


def main(argv=None, runner=kit._gh):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--channel', required=True, help='Nombre del canal en la app (ej. "ey mat").')
    parser.add_argument('--slug', required=True, help='actions_slug del canal (ej. ey-mat).')
    parser.add_argument('--yt-token-file', help='Token de YouTube (por defecto tokens/<canal>.json).')
    parser.add_argument('--repo', help='owner/repo (por defecto, el de esta carpeta).')
    parser.add_argument('--branch', default='master')
    args = parser.parse_args(argv)
    if not re.fullmatch('[a-z][a-z0-9-]{0,39}', args.slug):
        print("El slug debe ser minúsculas, números y guiones.")
        return 1
    env_name = f'type-beats-{args.slug}'
    try:
        values = values_for(args.channel.strip(), args.yt_token_file)
        if kit.ensure_environment(env_name, args.repo, args.branch, runner):
            print("Environment creado y restringido a la rama.")
        failed = kit.sync(env_name, values, args.repo, runner)
        slugs = add_channel_variable(args.slug, args.repo, runner)
    except kit.SyncError as exc:
        print(exc)
        return 1
    if failed:
        print(f"{len(failed)} secreto(s) no se cargaron.")
        return 1
    print(f"Listo: {len(values)} secreto(s) en {env_name}; BEAT_CHANNELS={slugs}.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
