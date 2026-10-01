# -*- coding: utf-8 -*-
"""Cliente de Dropbox (SDK oficial) con OAuth PKCE y refresh token.

Solo hace falta el "App key" de una app de Dropbox (sin app secret, gracias a PKCE).
Va en config/dropbox_app.json -> {"app_key": "..."} (no versionado). El refresh token queda
en tokens/dropbox.json (no versionado). Ver docs/DROPBOX_SETUP.md.
"""
import json
import os

APP_CONFIG_FILE = os.path.join('config', 'dropbox_app.json')
TOKEN_FILE = os.path.join('tokens', 'dropbox.json')
AUDIO_EXTENSIONS = ('.mp3', '.wav')


class DropboxError(Exception):
    pass


def is_audio(name):
    return name.lower().endswith(AUDIO_EXTENSIONS)


def load_app_key(config_file=None):
    path = config_file or APP_CONFIG_FILE
    if not os.path.exists(path):
        raise DropboxError(f"Falta {path} con {{\"app_key\": \"...\"}}. Ver docs/DROPBOX_SETUP.md.")
    with open(path, encoding='utf-8') as f:
        key = (json.load(f).get('app_key') or '').strip()
    if not key:
        raise DropboxError(f"{path} no tiene 'app_key'.")
    return key


def is_connected(token_file=None):
    return os.path.exists(token_file or TOKEN_FILE)


def disconnect(token_file=None):
    path = token_file or TOKEN_FILE
    if os.path.exists(path):
        os.remove(path)


def start_auth(app_key=None):
    """Inicia el flujo PKCE. Devuelve (flow, url): abrir la URL, el usuario copia el código."""
    from dropbox import DropboxOAuth2FlowNoRedirect
    flow = DropboxOAuth2FlowNoRedirect(app_key or load_app_key(), use_pkce=True,
                                       token_access_type='offline')
    return flow, flow.start()


def finish_auth(flow, code, token_file=None):
    """Canjea el código pegado por el usuario y guarda el refresh token."""
    try:
        result = flow.finish(code.strip())
    except Exception as e:
        raise DropboxError(f"Código inválido o vencido: {e}")
    path = token_file or TOKEN_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'refresh_token': result.refresh_token}, f)


def _client(app_key=None, token_file=None):
    import dropbox
    path = token_file or TOKEN_FILE
    if not os.path.exists(path):
        raise DropboxError("Dropbox no está conectado.")
    with open(path, encoding='utf-8') as f:
        refresh = json.load(f).get('refresh_token')
    return dropbox.Dropbox(oauth2_refresh_token=refresh, app_key=app_key or load_app_key())


def list_folder(path='', dbx=None):
    """Lista una carpeta ('' = raíz). Devuelve [{'name','path','is_folder','size'}] con carpetas
    primero y solo archivos de audio (mp3/wav)."""
    import dropbox
    dbx = dbx or _client()
    try:
        res = dbx.files_list_folder(path)
        entries = list(res.entries)
        while res.has_more:
            res = dbx.files_list_folder_continue(res.cursor)
            entries.extend(res.entries)
    except dropbox.exceptions.ApiError as e:
        raise DropboxError(f"No se pudo listar '{path or '/'}': {e}")
    items = []
    for e in entries:
        if isinstance(e, dropbox.files.FolderMetadata):
            items.append({'name': e.name, 'path': e.path_lower, 'is_folder': True, 'size': 0})
        elif isinstance(e, dropbox.files.FileMetadata) and is_audio(e.name):
            items.append({'name': e.name, 'path': e.path_lower, 'is_folder': False, 'size': e.size})
    return sorted(items, key=lambda i: (not i['is_folder'], i['name'].lower()))


def download(dropbox_path, dest_dir, dbx=None):
    """Descarga un archivo a dest_dir y devuelve la ruta local."""
    import dropbox
    dbx = dbx or _client()
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(dropbox_path))
    try:
        dbx.files_download_to_file(dest, dropbox_path)
    except dropbox.exceptions.ApiError as e:
        raise DropboxError(f"No se pudo descargar '{dropbox_path}': {e}")
    return dest


def import_files(dropbox_paths, dbx=None, progress=None, kind='beat'):
    """Descarga cada archivo a un temporal, lo importa a la biblioteca (dedupe por hash) y
    devuelve (nuevos, duplicados, errores)."""
    import tempfile
    from core import library
    dbx = dbx or _client()
    nuevos = duplicados = 0
    errores = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, p in enumerate(dropbox_paths):
            if progress:
                progress(i, len(dropbox_paths), os.path.basename(p))
            try:
                local = download(p, tmp, dbx)
                _, creado = library.import_beat(local, kind=kind)
                nuevos += creado
                duplicados += not creado
                os.remove(local)
            except Exception as e:
                errores.append(f"{os.path.basename(p)}: {e}")
    return nuevos, duplicados, errores
