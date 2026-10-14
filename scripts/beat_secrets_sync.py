#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga con ``gh`` los secretos propios de un canal de Type Beats en el Environment propio del canal.

Uso: ``py -3 scripts/beat_secrets_sync.py --channel "ey mat" --slug ey-mat``.

Cada canal usa type-beats-<slug> con su propia autorización de YouTube.
Configurar Dropbox y Telegram como secretos BEAT_* en ese Environment.
Todos los canales comparten la misma app de Dropbox y estado.
Cada valor viaja a gh por stdin: nunca va en un argumento ni se imprime.
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

from core.beat_actions import environment, matrix


def values_for(channel, yt_token_file=None):
    return {'BEAT_CHANNEL_ID': channel,
            'BEAT_YT_TOKEN_JSON': kit.youtube_token(channel, yt_token_file)}


def add_channel_variable(slug, repo=None, runner=kit._gh):
    """Agrega ``slug`` a la variable ``BEAT_CHANNELS`` (array JSON) sin quitar los existentes."""
    args = ['variable', 'get', 'BEAT_CHANNELS'] + (['--repo', repo] if repo else [])
    try:
        result = subprocess.run(['gh', *args], capture_output=True, text=True)
        if result.returncode != 0:
            raise kit.SyncError('No se pudo leer BEAT_CHANNELS; creala como [] si no existe.')
        current = result.stdout.strip()
        slugs = json.loads(current) if current else []
    except (OSError, ValueError):
        raise kit.SyncError('No se pudo leer BEAT_CHANNELS; no se modificó la lista.') from None
    if slugs != []:
        try:
            matrix(json.dumps(slugs))
        except ValueError:
            raise kit.SyncError('BEAT_CHANNELS no es una lista válida; no se modificó.') from None
    if slug not in slugs:
        slugs.append(slug)
    try:
        matrix(json.dumps(slugs))
    except ValueError:
        raise kit.SyncError('La lista resultante de canales no es válida.') from None
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
    if args.branch != 'master':
        print('Beats requiere la rama master.')
        return 1
    env_name = environment(args.slug)
    try:
        values = values_for(args.channel.strip(), args.yt_token_file)
        if kit.ensure_environment(env_name, args.repo, args.branch, runner):
            print("Environment creado y restringido a la rama.")
        failed = kit.sync(env_name, values, args.repo, runner)
        if failed:
            print(f'{len(failed)} secreto(s) no se cargaron; BEAT_CHANNELS no cambió.')
            return 1
        slugs = add_channel_variable(args.slug, args.repo, runner)
    except kit.SyncError as exc:
        print(exc)
        return 1
    print(f"Listo: {len(values)} secreto(s) en {env_name}; BEAT_CHANNELS={slugs}.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
