# -*- coding: utf-8 -*-
"""Conexiones de esta PC: Dropbox (refresh token en el llavero de Windows) y GitHub (``gh``).

Nada de esto escribe archivos. Dropbox usa el flujo PKCE sin redirect de la app «App folder»
del worker; el app key y el refresh token quedan en ``keyring`` (servicio ``SERVICE``,
backend WinVaultKeyring = Credential Manager). El resto de los secretos (YouTube, Telegram,
Notion, claves) va directo a GitHub Secrets (``core/gh_status``) y nunca toca el disco.

El ``client_secret.json`` de la app OAuth «Escritorio» de Google también vive en el llavero
(docs/CLOUD_ONLY_SPIKE.md §9.1). Solo se lee de un archivo si el usuario lo importa, o del
fallback ``%APPDATA%\\TypeBeat\\client_secret.json``; nunca se escribe en el repo.
Los mensajes de ``LoginError`` nunca incluyen valores.
"""
import json
import os

from core import gh_status as gh_api, sandbox_guard

OK, MISSING, INVALID, UNKNOWN = 'ok', 'missing', 'invalid', 'unknown'
SERVICE = 'video-type-beat-generator'
DROPBOX_APP_KEY = 'dropbox_app_key'
DROPBOX_REFRESH_TOKEN = 'dropbox_refresh_token'
YOUTUBE_CLIENT_SECRET = 'youtube_client_secret'
GOOGLE_CLIENT_SUFFIX = '.apps.googleusercontent.com'  # todo client_id real de Google termina así
# Credential Manager guarda hasta 2560 bytes en UTF-16: ~1280 caracteres.
MAX_VALUE = 1200
APPDATA_CLIENT_SECRET = os.path.join(
    os.environ.get('APPDATA') or os.path.expanduser('~'), 'TypeBeat', 'client_secret.json')

_backend = None
_test_backend = None  # llavero en memoria que se usa solo si corren tests (core/sandbox_guard)


class LoginError(Exception):
    """Mensaje apto para la UI: sin valores ni rutas de credenciales.

    ``code``: ``missing`` (no está), ``keyring`` (llavero no disponible) o ``invalid``.
    """

    def __init__(self, message, code=INVALID):
        super().__init__(message)
        self.code = code


def set_backend(backend):
    """Reemplaza el módulo ``keyring`` (smokes y tests). Devuelve el anterior."""
    global _backend
    previous, _backend = _backend, backend
    return previous


# Backends que guardan en un archivo (keyrings.alt) o no guardan nada: nunca se usan.
_INSECURE_MODULES = ('keyrings.alt', 'keyring.backends.fail', 'keyring.backends.null')


def _secure_backend(backend):
    """True si el backend es un almacén del sistema (Credential Manager, etc.), no un archivo."""
    parts = getattr(backend, 'backends', None) or [backend]  # ChainerBackend: todos
    for part in parts:
        module = type(part).__module__ or ''
        if module.startswith(_INSECURE_MODULES) or 'Plaintext' in type(part).__name__:
            return False
    return True


def _keyring():
    global _test_backend
    if _backend is not None:
        backend = _backend
    elif sandbox_guard.running_tests():
        if _test_backend is None:
            from core.cloud_fakes import MemoryKeyring
            _test_backend = MemoryKeyring()
        backend = _test_backend  # nunca el llavero real durante los tests
    else:
        try:
            import keyring as backend
        except ImportError:
            raise LoginError('Falta el paquete keyring: instalá requirements.txt.',
                             UNKNOWN) from None
    get_keyring = getattr(backend, 'get_keyring', None)
    if get_keyring is not None:
        try:
            secure = _secure_backend(get_keyring())
        except Exception:
            secure = False
        if not secure:
            raise LoginError('El llavero disponible guarda en un archivo o no es seguro: '
                             'no se usa.', UNKNOWN)
    return backend


def printable(value, limit=512):
    """ASCII visible sin espacios, de 1 a ``limit`` caracteres (formato de claves y tokens)."""
    return (isinstance(value, str) and 0 < len(value) <= limit
            and all(32 < ord(c) < 127 for c in value))


def _get(name):
    backend = _keyring()
    try:
        return backend.get_password(SERVICE, name)
    except Exception:
        raise LoginError('No se pudo leer el llavero de Windows.', UNKNOWN) from None


def _set(name, value):
    if not isinstance(value, str) or not value or len(value) > MAX_VALUE:
        raise LoginError('El valor no entra en el llavero de Windows.')
    backend = _keyring()
    try:
        backend.set_password(SERVICE, name, value)
    except Exception:
        raise LoginError('No se pudo guardar en el llavero de Windows.', UNKNOWN) from None


def _delete(name):
    """Borra la entrada y comprueba que ya no esté: «no existía» no es un error."""
    backend = _keyring()
    try:
        backend.delete_password(SERVICE, name)
    except Exception:
        pass  # puede no existir; lo que importa se comprueba abajo
    if _get(name) is not None:
        raise LoginError('No se pudo borrar del llavero de Windows: revisalo en el '
                         'Administrador de credenciales.', UNKNOWN)


def keyring_status():
    """``ok`` si el llavero responde; ``unknown`` si falta el paquete o el backend."""
    try:
        _get(DROPBOX_APP_KEY)
    except LoginError:
        return UNKNOWN
    return OK


# --- Dropbox ---

def dropbox_start(app_key):
    """Inicia PKCE sin redirect. Devuelve ``(flow, url)``: abrir la URL y pegar el código."""
    app_key = (app_key or '').strip()
    if not printable(app_key, 128):
        raise LoginError('Falta el app key de Dropbox o tiene un formato inválido.')
    try:
        from dropbox import DropboxOAuth2FlowNoRedirect
        flow = DropboxOAuth2FlowNoRedirect(app_key, use_pkce=True, token_access_type='offline')
        return flow, flow.start()
    except Exception:
        raise LoginError('No se pudo iniciar la autorización de Dropbox.') from None


def dropbox_exchange(flow, app_key, code):
    """Canjea el código y devuelve ``{app_key, refresh_token}`` en memoria (no guarda nada)."""
    app_key, code = (app_key or '').strip(), (code or '').strip()
    if flow is None or not printable(app_key, 128) or not printable(code, 512):
        raise LoginError('Autorizá Dropbox y pegá el código antes de guardar.')
    try:
        refresh = flow.finish(code).refresh_token
    except Exception:
        raise LoginError('Código de Dropbox inválido o vencido.') from None
    if not printable(refresh, MAX_VALUE):
        raise LoginError('Dropbox no devolvió un refresh token.')
    return {'app_key': app_key, 'refresh_token': refresh}


def dropbox_finish(flow, app_key, code):
    """Canjea el código y guarda app key + refresh token de **esta PC** en el llavero.

    El worker usa otra autorización (``dropbox_exchange`` → GitHub), nunca este token.
    """
    creds = dropbox_exchange(flow, app_key, code)
    _set(DROPBOX_APP_KEY, creds['app_key'])
    _set(DROPBOX_REFRESH_TOKEN, creds['refresh_token'])


def dropbox_credentials():
    """``{app_key, refresh_token}`` del llavero, o ``None`` si no está conectado."""
    key, token = _get(DROPBOX_APP_KEY), _get(DROPBOX_REFRESH_TOKEN)
    if printable(key, 128) and printable(token, MAX_VALUE):
        return {'app_key': key, 'refresh_token': token}
    return None


def dropbox_status():
    """``ok`` / ``missing`` / ``unknown`` (sin llavero) de Dropbox en esta PC."""
    try:
        return OK if dropbox_credentials() else MISSING
    except LoginError:
        return UNKNOWN


def dropbox_forget():
    """Borra Dropbox del llavero (la app tendrá que volver a autorizarse)."""
    _delete(DROPBOX_REFRESH_TOKEN)
    _delete(DROPBOX_APP_KEY)


# --- GitHub ---

def gh_status(gh=None):
    """``ok`` si ``gh auth status`` tiene sesión; ``missing`` si no o si falta gh."""
    return (gh or gh_api.default()).auth()


# --- client_secret.json de Google (app OAuth «Escritorio») ---

def _check_client_config(data):
    """Dict compacto ``{'installed': {...}}`` listo para InstalledAppFlow, o LoginError."""
    block = data.get('installed') if isinstance(data, dict) else None
    if (not isinstance(block, dict) or not printable(block.get('client_id'), 256)
            or not printable(block.get('client_secret'), 256)):
        raise LoginError('El client_secret.json no es de una app OAuth «Escritorio».')
    if not block['client_id'].endswith(GOOGLE_CLIENT_SUFFIX):
        raise LoginError('Ese client_secret no es de Google Cloud (el client_id no termina en '
                         f'«{GOOGLE_CLIENT_SUFFIX}»). Volvé a importarlo.')
    return data


def import_client_secret(path):
    """Copia al llavero el ``client_secret.json`` elegido. El archivo no se toca."""
    try:
        with open(path, encoding='utf-8') as f:
            data = _check_client_config(json.load(f))
    except LoginError:
        raise
    except (OSError, ValueError):
        raise LoginError('No se pudo leer ese client_secret.json.') from None
    _set(YOUTUBE_CLIENT_SECRET, json.dumps(data, separators=(',', ':')))


def client_secret_config(appdata_file=None):
    """Config OAuth de Google: llavero, si no ``%APPDATA%\\TypeBeat``. LoginError si falta.

    Sin llavero disponible igual se prueba el archivo de %APPDATA% (para eso existe).
    """
    try:
        raw = _get(YOUTUBE_CLIENT_SECRET)
    except LoginError as exc:
        raw, keyring_error = None, exc
    else:
        keyring_error = None
    if raw:
        try:
            return _check_client_config(json.loads(raw))
        except ValueError:
            raise LoginError('El client_secret del llavero está dañado: importalo de nuevo.')                 from None
    path = appdata_file or APPDATA_CLIENT_SECRET
    if os.path.isfile(path):
        try:
            with open(path, encoding='utf-8') as f:
                return _check_client_config(json.load(f))
        except (OSError, ValueError):
            raise LoginError('No se pudo leer el client_secret de %APPDATA%.') from None
    if keyring_error is not None:
        raise keyring_error
    raise LoginError('Falta el client_secret de Google: importalo en Conexiones.', MISSING)


def client_secret_status(appdata_file=None):
    """``ok`` (llavero o %APPDATA%), ``missing``, ``invalid`` o ``unknown`` (sin llavero)."""
    try:
        client_secret_config(appdata_file)
        return OK
    except LoginError as exc:
        return exc.code


def forget_client_secret():
    _delete(YOUTUBE_CLIENT_SECRET)
