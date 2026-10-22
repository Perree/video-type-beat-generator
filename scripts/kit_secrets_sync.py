#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Carga con ``gh`` los secretos del Environment de un canal de loop kits.

Uso: ``py -3 scripts/kit_secrets_sync.py --env kit-weekly-<slug> --channel "<canal>"``.

Los secretos compartidos salen de ``--shared-file`` (si se indica), del entorno o, si faltan,
de un prompt sin eco; dejar un prompt vacío no toca ese secreto. El Dropbox de esta PC (llavero)
nunca se copia al worker: el worker tiene su propia autorización. Ya no se lee ``tokens/`` por defecto. El token de YouTube
sale de ``--yt-token-file`` o, si no se indica, del OAuth en memoria (abre el navegador).
Cada valor viaja a ``gh`` por stdin: nunca va en un argumento ni se imprime. Si el
Environment no existe se crea restringido a la rama principal. Ver docs/KIT_WEEKLY.md.

La app llama a ``push_channel`` / ``push_values`` con valores en memoria.
"""
import argparse
import getpass
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_channel

# Archivo heredado: ya no se lee por defecto (solo con --shared-file). Sigue en .gitignore.
SHARED_FILE = os.path.join(ROOT, 'tokens', 'kit_secrets.json')
SHARED = (
    ('KIT_DROPBOX_REFRESH_TOKEN', 'Refresh token de Dropbox'),
    ('KIT_DROPBOX_APP_KEY', 'App key de Dropbox'),
    ('KIT_LLM_API_KEY', 'Clave de OpenAI para los nombres'),
    ('KIT_IMAGE_API_KEY', 'Clave de OpenAI para las portadas'),
    ('KIT_TELEGRAM_TOKEN', 'Token del bot de Telegram'),
    ('KIT_TELEGRAM_CHAT_ID', 'Chat id de Telegram'),
    ('KIT_NOTION_TOKEN', 'Clave de Notion (solo lectura) del informe de tendencias'),
    ('KIT_NOTION_PAGE_ID', 'Id de la página de Notion del informe de tendencias'),
)
_DROPBOX_FIELDS = {'KIT_DROPBOX_REFRESH_TOKEN': 'refresh_token', 'KIT_DROPBOX_APP_KEY': 'app_key'}
# Con --no-prompt no se puede completar por stdin: sin estos nombres el Environment queda roto.
_REQUIRED_NO_PROMPT = (
    'KIT_DROPBOX_REFRESH_TOKEN', 'KIT_DROPBOX_APP_KEY',
    'KIT_TELEGRAM_TOKEN', 'KIT_TELEGRAM_CHAT_ID',
)


class SyncError(Exception):
    """Mensaje apto para la consola: sin valores."""


def _load_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def shared_values(shared_file=None, dropbox_file=None, env=None, ask=getpass.getpass):
    """``{nombre: valor}`` de los secretos compartidos que se pudieron resolver.

    Solo lee archivos que se pasen explícitamente; nunca el llavero de esta PC.
    """
    env = os.environ if env is None else env
    from_file = _load_json(shared_file) if shared_file else {}
    dropbox = _load_json(dropbox_file) if dropbox_file else {}
    values = {}
    for name, label in SHARED:
        value = (from_file.get(name) or dropbox.get(_DROPBOX_FIELDS.get(name, '')) or
                 env.get(name) or '')
        value = str(value).strip() or ask(f"{label} (Enter para no tocarlo): ").strip()
        if value:
            values[name] = value
    return values


def check_token(token_json):
    """Valida un token de YouTube (JSON con refresh_token) y lo devuelve compacto."""
    try:
        data = json.loads(token_json) if isinstance(token_json, str) else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not data.get('refresh_token'):
        raise SyncError("El token de YouTube no es válido: conectá el canal en la app.")
    return json.dumps(data)


def oauth_token():
    """Token de YouTube por OAuth en memoria (abre el navegador); no escribe archivos."""
    from core import youtube
    try:
        return youtube.authorize()[0]
    except youtube.YouTubeError as exc:
        raise SyncError(str(exc)) from None


def youtube_token(channel, token_file=None, ask=input, authorize=None):
    """Token de YouTube del canal (JSON), listo para el secreto.

    ``token_file`` explícito; si no, ``authorize()`` (OAuth en memoria); si no, se pide la ruta.
    """
    if not token_file and authorize is not None:
        return check_token(authorize())
    path = token_file or ask("Ruta al token de YouTube de este canal (.json): ").strip().strip('"')
    if not path or not os.path.isfile(path):
        raise SyncError("El token de YouTube no existe o no es válido: conectá el canal en la app.")
    return check_token(json.dumps(_load_json(path)))


def _gh(args, stdin=None):
    """Corre ``gh`` y devuelve el código de salida; su salida no se muestra."""
    try:
        return subprocess.run(['gh', *args], input=(stdin or '').encode('utf-8'),
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode
    except OSError:
        raise SyncError("No se encontró gh (GitHub CLI).") from None


def ensure_environment(env_name, repo=None, branch='master', runner=_gh):
    """Crea el Environment si no existe, limitado a ``branch``. Uno que ya existe no se toca."""
    base = f"repos/{repo or '{owner}/{repo}'}/environments/{env_name}"
    if runner(['api', base]) == 0:
        return False
    body = {'deployment_branch_policy': {'protected_branches': False,
                                         'custom_branch_policies': True}}
    if runner(['api', '--method', 'PUT', base, '--input', '-'], json.dumps(body)) != 0:
        raise SyncError("No se pudo crear el Environment (¿gh auth login? ¿permisos de admin?).")
    if runner(['api', '--method', 'POST', base + '/deployment-branch-policies', '--input', '-'],
              json.dumps({'name': branch})) != 0:
        raise SyncError("El Environment se creó, pero no quedó restringido a la rama: "
                        "hacelo a mano en Settings > Environments.")
    return True


def sync(env_name, values, repo=None, runner=_gh, out=print):
    """Sube ``values`` como secretos del Environment. Devuelve los nombres que fallaron."""
    failed = []
    for name, value in values.items():
        args = ['secret', 'set', name, '--env', env_name] + (['--repo', repo] if repo else [])
        ok = runner(args, value) == 0
        out(f"{name}: {'ok' if ok else 'falló'}")
        if not ok:
            failed.append(name)
    return failed


def check_channel_env(env_name, channel, default_channel=None):
    """El token de un canal solo va a ``kit-weekly-<slug del canal>`` o, si es el canal por
    defecto, a ``kit-weekly``. ``default_channel`` (si se conoce) es el dueño de ``kit-weekly``:
    el worker no controla el dueño de ese Environment, así que se controla acá.
    """
    own = kit_channel.environment(kit_channel.slug(channel))
    if env_name not in (kit_channel.ENV_PREFIX, own):
        raise SyncError("Ese Environment no es el de este canal: usá kit-weekly (canal por "
                        "defecto) o kit-weekly-<slug del canal>.")
    if (env_name == kit_channel.ENV_PREFIX and env_name != own and default_channel is not None
            and channel != default_channel):
        raise SyncError(f"kit-weekly es del canal por defecto «{default_channel}», no de "
                        f"«{channel}»: no se tocaron sus secretos.")


def push_values(env_name, values, repo=None, branch='master', runner=_gh, out=print):
    """Sube ``values`` (en memoria) al Environment, creándolo si falta. SyncError si algo falla."""
    if ensure_environment(env_name, repo, branch, runner):
        out("Environment creado y restringido a la rama.")
    failed = sync(env_name, values, repo, runner, out)
    if failed:
        raise SyncError(f"{len(failed)} secreto(s) no se cargaron: " + ', '.join(failed))
    return sorted(values)


def push_channel(env_name, channel, token_json=None, extra=None, repo=None, branch='master',
                 runner=_gh, out=print, default_channel=None):
    """Canal de kits desde la app: ``KIT_YT_CHANNEL`` (+ token y ``extra`` si vienen).

    Para ``kit-weekly`` exige ``default_channel``: sin saber de quién es, no se escribe.
    """
    channel = (channel or '').strip()
    if not channel:
        raise SyncError("Falta el nombre del canal.")
    if env_name == kit_channel.ENV_PREFIX and default_channel is None:
        raise SyncError("No se sabe cuál es el canal por defecto de kit-weekly: recargá desde "
                        "Dropbox y reintentá.")
    check_channel_env(env_name, channel, default_channel)
    values = dict(extra or {})
    values['KIT_YT_CHANNEL'] = channel
    if token_json is not None:
        values['KIT_YT_TOKEN_JSON'] = check_token(token_json)
    return push_values(env_name, values, repo, branch, runner, out)


def main(argv=None, runner=_gh):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--env', required=True, help='Environment: kit-weekly o kit-weekly-<slug>.')
    parser.add_argument('--channel', help='Nombre del canal, tal como figura en la app.')
    parser.add_argument('--yt-token-file',
                        help='Token de YouTube (.json). Sin esto se autoriza por OAuth en memoria.')
    parser.add_argument('--shared-file', help='JSON con secretos compartidos (fuera de git).')
    parser.add_argument('--repo', help='owner/repo (por defecto, el de esta carpeta).')
    parser.add_argument('--branch', default='master', help='Rama que puede usar el Environment.')
    parser.add_argument('--default-channel',
                        help='Canal dueño de kit-weekly; si se indica, otro canal no puede usarlo.')
    parser.add_argument('--no-prompt', action='store_true',
                        help='No pedir secretos por stdin (para la UI; Enter equivale a omitir).')
    args = parser.parse_args(argv)
    ask_shared = (lambda _label: '') if args.no_prompt else getpass.getpass
    ask_path = (lambda _label: '') if args.no_prompt else input

    try:
        channel = (args.channel or ('' if args.no_prompt else input("Nombre del canal: "))).strip()
        if not channel:
            raise SyncError("Falta el nombre del canal.")
        check_channel_env(args.env, channel, args.default_channel)
        values = shared_values(args.shared_file, ask=ask_shared)
        values['KIT_YT_CHANNEL'] = channel
        values['KIT_YT_TOKEN_JSON'] = youtube_token(
            channel, args.yt_token_file, ask=ask_path,
            authorize=None if args.no_prompt else oauth_token)
        if args.no_prompt:
            missing = [name for name in _REQUIRED_NO_PROMPT if not values.get(name)]
            if missing:
                raise SyncError('Faltan secretos obligatorios: ' + ', '.join(missing)
                                + '. Completá Conexiones y repetí.')
        if ensure_environment(args.env, args.repo, args.branch, runner):
            print("Environment creado y restringido a la rama.")
        failed = sync(args.env, values, args.repo, runner)
    except (SyncError, kit_channel.KitChannelError) as exc:
        print(exc)
        return 1
    except EOFError:
        # Sin stdin (p. ej. lanzado desde la UI) no se puede pedir un secreto por prompt.
        print('Falta un secreto o el token de YouTube: cargalo en la app y repetí.')
        return 1
    if failed:
        print(f"{len(failed)} secreto(s) no se cargaron.")
        return 1
    print(f"Listo: {len(values)} secreto(s) cargados.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
