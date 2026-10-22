#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga con ``gh`` los secretos propios de un canal de Type Beats en el Environment existente.

Uso: ``py -3 scripts/beat_secrets_sync.py --channel "ey mat" --slug ey-mat``.

Cada canal usa secretos BEAT_CHANNEL_ID_<SLUG> y BEAT_YT_TOKEN_JSON_<SLUG>
en kit-weekly. Dropbox y Telegram conservan sus secretos KIT_* existentes.
El script no modifica los secretos KIT_* ni la conexión anterior de Beats.
El token de YouTube sale de ``--yt-token-file`` o, si no se indica, del OAuth en memoria
(abre el navegador); ``--skip-youtube`` no lo toca. Ya no se lee ``tokens/`` por defecto.
Notion Beats se carga desde Conexiones (va directo a Secrets).
Cada valor viaja a gh por stdin: nunca va en un argumento ni se imprime.
La app llama a ``push_channel`` con el token en memoria.
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

from core.beat_actions import environment, matrix, secret_names


def values_for(channel, yt_token_file=None, *, slug, token_json=None, youtube=True):
    """Secretos del canal. El token: ``token_json`` en memoria, archivo explícito u OAuth."""
    names = secret_names(slug)
    values = {names['channel_secret']: channel}
    if token_json is not None:
        values[names['youtube_secret']] = kit.check_token(token_json)
    elif youtube:
        values[names['youtube_secret']] = kit.youtube_token(
            channel, yt_token_file, authorize=kit.oauth_token)
    return values


def _read_gh(args):
    result = subprocess.run(['gh', *args], capture_output=True, text=True)
    return result.returncode, result.stdout


def add_channel_variable(slug, repo=None, runner=kit._gh, reader=None):
    """Agrega ``slug`` a la variable ``BEAT_CHANNELS`` (array JSON) sin quitar los existentes.

    ``reader(args) -> (código, stdout)`` lee la variable (por defecto ``gh`` directo).
    """
    args = ['variable', 'get', 'BEAT_CHANNELS'] + (['--repo', repo] if repo else [])
    try:
        code, out = (reader or _read_gh)(args)
        if code != 0:
            raise kit.SyncError('No se pudo leer BEAT_CHANNELS; creala como [] si no existe.')
        current = out.strip()
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


def push_channel(channel, slug, token_json=None, extra=None, repo=None, runner=kit._gh,
                 out=print, reader=None):
    """Desde la app: secretos del canal (token en memoria si viene) y ``BEAT_CHANNELS``.

    Levanta ``kit.SyncError`` (sin valores). ``BEAT_CHANNELS`` solo cambia si todo subió.
    """
    channel = (channel or '').strip()
    if not channel:
        raise kit.SyncError('Falta el nombre del canal.')
    try:
        env_name = environment(slug)
    except ValueError:
        raise kit.SyncError('El canal necesita un actions_slug válido.') from None
    values = values_for(channel, slug=slug, token_json=token_json, youtube=False)
    values.update(extra or {})
    kit.push_values(env_name, values, repo, 'master', runner, out)
    return add_channel_variable(slug, repo, runner, reader)


def main(argv=None, runner=kit._gh):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--channel', required=True, help='Nombre del canal en la app (ej. "ey mat").')
    parser.add_argument('--slug', required=True, help='actions_slug del canal (ej. ey-mat).')
    parser.add_argument('--yt-token-file',
                        help='Token de YouTube (.json). Sin esto se autoriza por OAuth en memoria.')
    parser.add_argument('--skip-youtube', action='store_true',
                        help='No tocar BEAT_YT_TOKEN_JSON_<SLUG> (ya cargado).')
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
        values = values_for(args.channel.strip(), args.yt_token_file, slug=args.slug,
                            youtube=not args.skip_youtube)
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
    except EOFError:
        # Sin stdin (p. ej. lanzado desde la UI) no se puede pedir una ruta por prompt.
        print('Falta el token de YouTube del canal: conectalo en la app.')
        return 1
    print(f"Listo: {len(values)} secreto(s) en {env_name}; BEAT_CHANNELS={slugs}.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
