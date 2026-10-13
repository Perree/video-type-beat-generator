#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga con ``gh`` los secretos propios de un canal de Type Beats en el Environment compartido.

Uso: ``py -3 scripts/beat_secrets_sync.py --channel "ey mat" --slug ey-mat``.

Dropbox y Telegram ya viven en el Environment ``kit-weekly`` (``KIT_*``) y el workflow de Beats los
reutiliza; aquí solo se suben ``BEAT_CHANNEL_ID`` y ``BEAT_YT_TOKEN_JSON`` (``tokens/<canal>.json``) y se
agrega el slug a la variable ``BEAT_CHANNELS``. Mientras comparta Environment, hay un solo canal de Beats
por Environment. Cada valor viaja a ``gh`` por stdin: nunca va en un argumento ni se imprime.
"""
import argparse
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts import kit_secrets_sync as kit

ENVIRONMENT = 'kit-weekly'  # must match core.beat_actions.ENVIRONMENT


def values_for(channel, yt_token_file=None):
    return {'BEAT_CHANNEL_ID': channel,
            'BEAT_YT_TOKEN_JSON': kit.youtube_token(channel, yt_token_file)}


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
    env_name = ENVIRONMENT
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
