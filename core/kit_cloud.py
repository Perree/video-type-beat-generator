# -*- coding: utf-8 -*-
"""JSON en Dropbox y credenciales efímeras para el worker de loop kits.

No modifica dropbox_client ni youtube: usa sus rutas relativas al cwd, así que el worker
tiene que correr dentro del directorio que devuelve ``bootstrap_credentials``.
Nada de este módulo imprime ni loguea valores de entorno.

Mientras dura ``credentials_dir`` los secretos ``KIT_*`` salen de ``os.environ`` y quedan solo
en memoria (``secret``): los procesos hijos, como ffmpeg, no los heredan.
"""
import contextlib
import json
import os
import shutil
import tempfile

from core import dropbox_client, youtube

# rev=NEW en write_json: crear solo si el archivo todavía no existe.
NEW = object()

ENV_YT_CHANNEL = 'KIT_YT_CHANNEL'
ENV_YT_TOKEN = 'KIT_YT_TOKEN_JSON'
ENV_DROPBOX_TOKEN = 'KIT_DROPBOX_REFRESH_TOKEN'
ENV_DROPBOX_APP_KEY = 'KIT_DROPBOX_APP_KEY'
ENV_VARS = (ENV_YT_CHANNEL, ENV_YT_TOKEN, ENV_DROPBOX_TOKEN, ENV_DROPBOX_APP_KEY)
# Secretos que se leen recién al usarlos (LLM, API de imágenes, Telegram).
RUNTIME_SECRETS = ('KIT_LLM_API_KEY', 'KIT_IMAGE_API_KEY',
                   'KIT_TELEGRAM_TOKEN', 'KIT_TELEGRAM_CHAT_ID',
                   'KIT_NOTION_TOKEN', 'KIT_NOTION_PAGE_ID')
# Token de una app de Dropbox aparte para loop kits (tipo "App folder"), fuera de git.
# Si existe, panel y worker local lo usan en lugar del token general de la app.
WORKER_TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'tokens', 'dropbox_worker.json')
_STASH = {}

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class KitCloudError(Exception):
    pass


class KitCloudEnvError(KitCloudError):
    """Faltan variables de entorno; el mensaje solo trae sus nombres."""


class KitCloudConflict(KitCloudError):
    """El archivo cambió (o ya existe) desde la lectura: releer y reintentar."""


def in_cloud(env=None):
    """True si hay alguna variable ``KIT_*`` de credenciales: el worker corre con secretos."""
    if env is None:
        if _STASH:
            return True
        env = os.environ
    return any((env.get(name) or '').strip() for name in ENV_VARS)


def secret(name, env=None):
    """Valor de un secreto ``KIT_*``: de ``env`` si se pasa; si no, de memoria o del entorno."""
    if env is not None:
        return (env.get(name) or '').strip()
    return (_STASH.get(name) or os.environ.get(name) or '').strip()


def hide_secrets():
    """Saca los secretos ``KIT_*`` de ``os.environ`` y los deja en memoria."""
    for name in ENV_VARS + RUNTIME_SECRETS:
        value = os.environ.pop(name, None)
        if value:
            _STASH[name] = value


def restore_secrets():
    """Deshace ``hide_secrets``."""
    os.environ.update(_STASH)
    _STASH.clear()


def nested_secrets(env=None):
    """Valores sueltos dentro de los secretos JSON (tokens, client_secret).

    GitHub enmascara el secreto entero, no sus campos: el worker registra estos valores
    como máscaras aparte. Nunca se imprimen fuera de ese comando.
    """
    env = os.environ if env is None else env
    found = []
    for name in (ENV_YT_TOKEN, ENV_DROPBOX_TOKEN, ENV_DROPBOX_APP_KEY):
        try:
            data = json.loads(env.get(name) or '')
        except ValueError:
            continue
        for key in ('refresh_token', 'token', 'client_secret', 'app_key'):
            value = data.get(key) if isinstance(data, dict) else None
            if (isinstance(value, str) and len(value) >= 8
                    and not any(c.isspace() for c in value) and value not in found):
                found.append(value)
    return found


def worker_token(path=None):
    """``{refresh_token, app_key}`` de la app de Dropbox del worker, o None si no está."""
    try:
        with open(path or WORKER_TOKEN_FILE, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get('refresh_token') or not data.get('app_key'):
        return None
    return {'refresh_token': data['refresh_token'], 'app_key': data['app_key']}


def client():
    """Cliente de Dropbox para loop kits.

    En el runner (``in_cloud``) sigue el camino de siempre. En el escritorio usa solo el
    llavero de Windows (``core/cloud_login``): ya no lee ``tokens/``.
    """
    if in_cloud():
        return dropbox_client._client()
    from core import cloud_login
    try:
        token = cloud_login.dropbox_credentials()
    except cloud_login.LoginError:
        token = None
    if token is None:
        raise KitCloudError('Dropbox no está conectado en esta PC: conectalo en Conexiones.')
    import dropbox
    return dropbox.Dropbox(oauth2_refresh_token=token['refresh_token'], app_key=token['app_key'])


def _is(exc, tag):
    # El SDK anida el motivo (not_found, conflict) y lo deja en el repr del error;
    # mirar el texto sirve igual para el SDK y para los fakes de los smokes.
    return tag in str(exc) or tag in repr(exc)


def _write_mode(rev):
    from dropbox.files import WriteMode
    if rev is None:
        return WriteMode.overwrite
    if rev is NEW:
        return WriteMode.add
    return WriteMode.update(rev)


def read_json_rev(path, dbx=None):
    """Lee un JSON de Dropbox. Devuelve (data, rev), o (None, None) si no existe.

    Un archivo que existe pero no es JSON válido levanta KitCloudError: nunca se
    devuelve un default que después pise el estado real.
    """
    dbx = dbx or client()
    try:
        meta, resp = dbx.files_download(path)
    except Exception as e:
        if _is(e, 'not_found'):
            return None, None
        raise KitCloudError(f"No se pudo leer '{path}': {e}")
    try:
        raw = resp.content
    finally:
        close = getattr(resp, 'close', None)
        if close:
            close()
    try:
        return json.loads(raw.decode('utf-8')), getattr(meta, 'rev', None)
    except (UnicodeDecodeError, ValueError):
        raise KitCloudError(f"'{path}' no es un JSON válido.")


def read_json(path, default=None, dbx=None):
    """Lee un JSON de Dropbox, o ``default`` si el archivo no existe."""
    data, rev = read_json_rev(path, dbx=dbx)
    return default if rev is None and data is None else data


def write_json(path, data, rev=None, dbx=None):
    """Reemplaza el JSON de ``path`` de forma atómica. Devuelve el rev nuevo.

    Se serializa completo en memoria antes de tocar la red y se sube en un solo commit:
    Dropbox deja la revisión nueva entera o la anterior intacta, nunca un archivo a medias.

    Args:
        rev: None pisa lo que haya; un rev de ``read_json_rev`` solo escribe si nadie
            cambió el archivo; ``NEW`` solo escribe si no existe. Si no se cumple,
            KitCloudConflict.
    """
    try:
        payload = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True).encode('utf-8')
    except (TypeError, ValueError) as e:
        raise KitCloudError(f"Datos no serializables para '{path}': {e}")
    dbx = dbx or client()
    try:
        meta = dbx.files_upload(payload, path, mode=_write_mode(rev), mute=True)
    except Exception as e:
        if rev is not None and _is(e, 'conflict'):
            raise KitCloudConflict(f"'{path}' cambió desde la última lectura.")
        raise KitCloudError(f"No se pudo escribir '{path}': {e}")
    return getattr(meta, 'rev', None)


def _json_object(env, name):
    try:
        data = json.loads(env[name])
    except ValueError:
        data = None
    if not isinstance(data, dict):
        # Solo el nombre de la variable: el valor no va a ningún mensaje.
        raise KitCloudError(f"{name} no es un objeto JSON válido.")
    return data


def _plain_or_field(env, name, field):
    """Acepta el valor suelto o un JSON {field: valor}."""
    raw = env[name].strip()
    if raw.startswith('{'):
        raw = str(_json_object(env, name).get(field) or '').strip()
    if not raw:
        raise KitCloudError(f"{name} no tiene '{field}'.")
    return raw


def _write_private(path, data):
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        json.dump(data, f)


def _inside_repo(path):
    try:
        real = os.path.realpath(path)
        return os.path.commonpath([_REPO_ROOT, real]) == _REPO_ROOT
    except ValueError:  # otra unidad en Windows
        return False


def bootstrap_credentials(env=None):
    """Vuelca las credenciales del entorno a un directorio temporal y devuelve su ruta.

    Crea ``tokens/<canal>.json``, ``tokens/dropbox.json`` y ``config/dropbox_app.json`` con las
    mismas rutas relativas que usan youtube.py y dropbox_client.py: los encuentran si el
    proceso hace ``chdir`` a ese directorio (ver ``credentials_dir``). El ``client_secret.json``
    no se escribe: solo hace falta para conectar un canal, no para subir.
    Directorio 0700, archivos 0600, nunca dentro del repo.
    No imprime nada; los errores nombran la variable, nunca su valor.
    """
    env = os.environ if env is None else env
    missing = [name for name in ENV_VARS if not (env.get(name) or '').strip()]
    if missing:
        raise KitCloudEnvError("Faltan variables de entorno: " + ', '.join(missing))

    channel = env[ENV_YT_CHANNEL].strip()
    files = {
        youtube._token_path(channel): _json_object(env, ENV_YT_TOKEN),
        dropbox_client.TOKEN_FILE: {
            'refresh_token': _plain_or_field(env, ENV_DROPBOX_TOKEN, 'refresh_token')},
        dropbox_client.APP_CONFIG_FILE: {
            'app_key': _plain_or_field(env, ENV_DROPBOX_APP_KEY, 'app_key')},
    }

    run_dir = tempfile.mkdtemp(prefix='kit_run_')
    try:
        if _inside_repo(run_dir):
            raise KitCloudError("El directorio temporal cae dentro del repo; revisar TMP/TEMP.")
        os.chmod(run_dir, 0o700)
        for rel, data in files.items():
            _write_private(os.path.join(run_dir, rel), data)
    except Exception:
        shutil.rmtree(run_dir, ignore_errors=True)
        raise
    return run_dir


@contextlib.contextmanager
def credentials_dir(env=None):
    """Corre el bloque con el cwd en un directorio de credenciales; al salir lo borra.

    Con el entorno real (``env`` None) los secretos salen de ``os.environ`` mientras dura.
    """
    run_dir = bootstrap_credentials(env)
    previous = os.getcwd()
    os.chdir(run_dir)
    if env is None:
        hide_secrets()
    try:
        yield run_dir
    finally:
        if env is None:
            restore_secrets()
        os.chdir(previous)
        shutil.rmtree(run_dir, ignore_errors=True)
