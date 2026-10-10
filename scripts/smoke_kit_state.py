#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: kit_cloud/kit_state con Dropbox falso en memoria (escritura atómica, lock, secretos)."""

import contextlib
import io
import json
import os
import stat
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import dropbox_client, kit_cloud, kit_state, youtube

try:
    import dropbox.files  # noqa: F401  (con el SDK instalado se prueba el WriteMode real)
except ImportError:
    import types

    class _WriteMode:
        """Doble mínimo de dropbox.files.WriteMode para correr sin el SDK."""

        def __init__(self, tag, rev=None):
            self._tag, self._rev = tag, rev

        @classmethod
        def update(cls, rev):
            return cls('update', rev)

        def is_add(self):
            return self._tag == 'add'

        def is_update(self):
            return self._tag == 'update'

        def get_update(self):
            return self._rev

    _WriteMode.add = _WriteMode('add')
    _WriteMode.overwrite = _WriteMode('overwrite')
    _files = types.ModuleType('dropbox.files')
    _files.WriteMode = _WriteMode
    _pkg = types.ModuleType('dropbox')
    _pkg.files = _files
    sys.modules.update({'dropbox': _pkg, 'dropbox.files': _files})

STATE = '/smoke/state.json'
SECRETS = {
    'client': 'SMOKE-CLIENT-SECRET-9f1c',
    'yt': 'SMOKE-YT-REFRESH-77aa',
    'dbx': 'SMOKE-DBX-REFRESH-42bd',
    'key': 'SMOKE-APP-KEY-c0de',
}


class _Meta:
    def __init__(self, rev):
        self.rev = rev


class _Resp:
    def __init__(self, content):
        self.content = content


class FakeDropbox:
    """files_download/files_upload en memoria, con rev y modos como el SDK."""

    def __init__(self):
        self.files = {}
        self.uploads = 0
        self.fail_next_upload = False
        self.before_upload = None

    def files_download(self, path):
        if path not in self.files:
            raise LookupError('path/not_found/')
        rev, content = self.files[path]
        return _Meta(rev), _Resp(content)

    def files_upload(self, data, path, mode=None, mute=False):
        if self.before_upload:
            hook, self.before_upload = self.before_upload, None
            hook()
        self.uploads += 1
        if self.fail_next_upload:
            self.fail_next_upload = False
            raise ConnectionError('corte de red simulado')
        current = self.files.get(path)
        if mode.is_add() and current:
            raise RuntimeError('path/conflict/file/')
        if mode.is_update() and (not current or current[0] != mode.get_update()):
            raise RuntimeError('path/conflict/file/')
        rev = f"{self.uploads:012x}"  # el SDK valida rev: 9+ caracteres hex
        self.files[path] = (rev, bytes(data))
        return _Meta(rev)


def _check_atomic(dbx):
    path = '/smoke/data.json'
    if kit_cloud.read_json(path, default={'vacio': True}, dbx=dbx) != {'vacio': True}:
        return "read_json no devolvió el default"
    rev1 = kit_cloud.write_json(path, {'v': 1}, dbx=dbx)
    before = dbx.files[path]

    dbx.fail_next_upload = True
    try:
        kit_cloud.write_json(path, {'v': 2}, dbx=dbx)
        return "una subida fallida no levantó error"
    except kit_cloud.KitCloudError:
        pass
    if dbx.files[path] != before:
        return "una subida fallida cambió el archivo"

    uploads = dbx.uploads
    try:
        kit_cloud.write_json(path, {'v': object()}, dbx=dbx)
        return "datos no serializables no levantaron error"
    except kit_cloud.KitCloudError:
        pass
    if dbx.uploads != uploads or dbx.files[path] != before:
        return "datos no serializables llegaron a Dropbox"

    kit_cloud.write_json(path, {'v': 3}, rev=rev1, dbx=dbx)
    try:
        kit_cloud.write_json(path, {'v': 4}, rev=rev1, dbx=dbx)
        return "un rev viejo no dio conflicto"
    except kit_cloud.KitCloudConflict:
        pass
    try:
        kit_cloud.write_json(path, {'v': 5}, rev=kit_cloud.NEW, dbx=dbx)
        return "NEW pisó un archivo existente"
    except kit_cloud.KitCloudConflict:
        pass
    if kit_cloud.read_json(path, dbx=dbx) != {'v': 3}:
        return "el contenido final no es el de la última escritura válida"
    if list(dbx.files) != [path]:
        return f"quedaron archivos de más: {sorted(dbx.files)}"

    dbx.files['/smoke/roto.json'] = ('revx', b'{"a": ')
    try:
        kit_cloud.read_json('/smoke/roto.json', default={}, dbx=dbx)
        return "un JSON roto se leyó como default"
    except kit_cloud.KitCloudError:
        pass
    del dbx.files['/smoke/roto.json']
    return None


def _check_lock(dbx):
    kw = {'db_path': STATE, 'dbx': dbx}
    t0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    kit_state.acquire_lock('run-a', ttl_sec=600, now=t0, **kw)
    try:
        kit_state.acquire_lock('run-b', ttl_sec=600, now=t0 + timedelta(seconds=599), **kw)
        return "un segundo lock vigente no se rechazó"
    except kit_state.KitLockError:
        pass
    if kit_state.load(**kw)['lock']['owner'] != 'run-a':
        return "el rechazo cambió el dueño del lock"
    if kit_state.release_lock('run-b', **kw):
        return "release_lock liberó un lock ajeno"

    kit_state.acquire_lock('run-b', ttl_sec=600, now=t0 + timedelta(seconds=601), **kw)
    if kit_state.load(**kw)['lock']['owner'] != 'run-b':
        return "un lock vencido no se pudo tomar"
    if not kit_state.release_lock('run-b', **kw) or kit_state.load(**kw)['lock']:
        return "release_lock no liberó el lock propio"

    # Dos corridas leen "sin lock" a la vez: la que escribe segunda tiene que perder.
    def rival():
        kit_state.acquire_lock('run-c', ttl_sec=600, now=t0, **kw)
    dbx.before_upload = rival
    try:
        kit_state.acquire_lock('run-d', ttl_sec=600, now=t0, **kw)
        return "dos corridas simultáneas tomaron el lock"
    except kit_state.KitLockError:
        pass
    if kit_state.load(**kw)['lock']['owner'] != 'run-c':
        return "la carrera dejó el lock en el dueño equivocado"
    kit_state.release_lock('run-c', **kw)
    return None


def _check_store_api(dbx):
    kw = {'db_path': STATE, 'dbx': dbx}
    a = kit_state.upsert_pack('/kits/A', 'A', **kw)
    if kit_state.upsert_pack('/kits/A', 'A v2', **kw) != a:
        return "upsert_pack duplicó el path"
    b = kit_state.upsert_pack('/kits/B', 'B', **kw)
    packs = kit_state.load(**kw)['packs']
    if len(packs) != 2 or packs['/kits/A']['nombre'] != 'A v2':
        return "upsert_pack count/nombre"

    try:
        kit_state.record_run(a, audio_mode='otro', **kw)
        return "record_run aceptó un audio_mode inválido"
    except ValueError:
        pass
    kit_state.record_run(a, audio_mode='assembled', image_path='img/1.png',
                         loops_json=['x.wav'], estado='rendered', **kw)
    kit_state.record_run(a, audio_mode='assembled', image_path='img/2.png',
                         publish_at='2026-01-02T15:00:00Z', estado='scheduled', **kw)
    kit_state.record_run(a, audio_mode='named_preview',
                         publish_at='2026-01-03T15:00:00Z', estado='private_pending', **kw)

    history = kit_state.selection_history(**kw)
    if history['last_image_by_path'] != {'/kits/A': 'img/2.png'}:
        return f"last_image_by_path {history['last_image_by_path']}"
    if set(history['last_used_by_path']) != {'/kits/A'}:
        return "record_run tocó last_used_at de otro pack"
    if not kit_state.has_scheduled_run('2026-01-02T15:00:00Z', **kw):
        return "has_scheduled_run no vio la corrida programada"
    if kit_state.has_scheduled_run('2026-01-03T15:00:00Z', **kw) \
            or kit_state.has_scheduled_run(None, **kw):
        return "has_scheduled_run dio True de más"

    cycle = kit_state.update_cycle(
        '/kits/B', cycle_videos=3, rest_until='2026-02-01T00:00:00',
        used_names=['uno', 'dos', 'uno'], used_ref_images=['ref/a.png'], **kw)
    if cycle != kit_state.get_cycle('/kits/B', **kw) or cycle['used_names'] != ['uno', 'dos'] \
            or cycle['cycle_videos'] != 3 or cycle['used_ref_images'] != ['ref/a.png']:
        return f"ciclo {cycle}"
    if kit_state.get_cycle('/kits/A', **kw)['cycle_videos'] != 0:
        return "update_cycle tocó otro kit"
    try:
        kit_state.update_cycle('/kits/B', otro=1, **kw)
        return "update_cycle aceptó un campo desconocido"
    except ValueError:
        pass
    if kit_state.load(**kw)['packs']['/kits/B']['id'] != b:
        return "el id del pack cambió"
    return None


def _check_bootstrap():
    env = {
        # Ya no se pide ni se escribe: aunque venga en el entorno, no llega al disco.
        'KIT_YT_CLIENT_SECRET_JSON': json.dumps(
            {'installed': {'client_id': 'x', 'client_secret': SECRETS['client']}}),
        kit_cloud.ENV_YT_CHANNEL: 'smoke canal',
        kit_cloud.ENV_YT_TOKEN: json.dumps({'refresh_token': SECRETS['yt']}),
        kit_cloud.ENV_DROPBOX_TOKEN: SECRETS['dbx'],
        kit_cloud.ENV_DROPBOX_APP_KEY: json.dumps({'app_key': SECRETS['key']}),
    }
    for broken in ({k: v for k, v in env.items() if k != kit_cloud.ENV_DROPBOX_TOKEN},
                   {**env, kit_cloud.ENV_YT_TOKEN: SECRETS['yt'] + '{'}):
        try:
            kit_cloud.bootstrap_credentials(broken)
            return "bootstrap aceptó un entorno incompleto o inválido"
        except kit_cloud.KitCloudError as e:
            print(f"error esperado: {e}")

    cwd = os.getcwd()
    with kit_cloud.credentials_dir(env) as run_dir:
        real = os.path.realpath(run_dir)
        if not real.startswith(os.path.realpath(tempfile.gettempdir())) \
                or real.startswith(os.path.realpath(ROOT)):
            return "las credenciales no quedaron en un directorio temporal"
        if not youtube.is_connected('smoke canal') or not dropbox_client.is_connected():
            return "youtube/dropbox_client no encuentran los tokens desde el cwd"
        if dropbox_client.load_app_key() != SECRETS['key']:
            return "dropbox_client no lee el app_key"
        if os.path.exists(youtube.CLIENT_SECRET_FILE):
            return "client_secret.json no hace falta en el runner y se escribió igual"
        with open(dropbox_client.TOKEN_FILE, encoding='utf-8') as f:
            if json.load(f) != {'refresh_token': SECRETS['dbx']}:
                return "tokens/dropbox.json no coincide"
        written = sorted(
            os.path.relpath(os.path.join(base, name), run_dir).replace(os.sep, '/')
            for base, _, names in os.walk(run_dir) for name in names)
        if written != ['config/dropbox_app.json', 'tokens/dropbox.json',
                       'tokens/smoke canal.json']:
            return f"archivos inesperados: {written}"
        if os.name == 'posix':
            modes = [stat.S_IMODE(os.stat(run_dir).st_mode)] + [
                stat.S_IMODE(os.stat(os.path.join(run_dir, w)).st_mode) for w in written]
            if modes[0] != 0o700 or any(m != 0o600 for m in modes[1:]):
                return f"permisos demasiado abiertos: {[oct(m) for m in modes]}"
        print(f"credenciales listas en {len(written)} archivos")
    if os.getcwd() != cwd or os.path.exists(run_dir):
        return "credentials_dir no restauró el cwd o no borró el directorio"
    return None


def main() -> int:
    dbx = FakeDropbox()
    out = io.StringIO()
    failure = None
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        for check in (lambda: _check_atomic(dbx), lambda: _check_lock(dbx),
                      lambda: _check_store_api(dbx), _check_bootstrap):
            failure = check()
            if failure:
                break
    captured = out.getvalue()
    stored = b''.join(content for _, content in dbx.files.values()).decode('utf-8')
    if any(secret in captured or secret in stored for secret in SECRETS.values()):
        print("FAIL: un secreto apareció en la salida o en el estado")
        return 1
    sys.stdout.write(captured)
    if failure:
        print("FAIL:", failure)
        return 1
    print("OK smoke_kit_state")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
