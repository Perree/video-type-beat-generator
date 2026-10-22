#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke offline de credenciales solo-nube: llavero (Dropbox, client_secret) + GitHub Secrets.

Uso: ``py -3 scripts/smoke_cloud_credentials.py``. ``gh`` y ``keyring`` son dobles en memoria
(``core/cloud_fakes``); Dropbox y Google se simulan. Comprueba que:
- no se crea ni modifica ningún archivo en ``tokens/`` ni ``config/`` (ni se abre ninguno);
- todo secreto viaja a ``gh`` por stdin y nunca como argumento;
- ningún valor aparece en stdout/stderr, en logs ni en mensajes de excepción;
- el estado sale de ``gh secret list``/``gh variable get`` con caché de ~60 s.
"""
import builtins
import contextlib
import io
import json
import logging
import os
import sys
import tempfile
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import automation_status as st, cloud_login, gh_status, kit_cloud, youtube
from core.cloud_fakes import FakeGhRun, MemoryKeyring

S = {
    'dbx_key': 'SMOKEdbxAPPKEY77', 'dbx_refresh': 'SMOKE-dbx-refresh-0123456789abcdef',
    'yt_refresh': 'SMOKE-yt-refresh-1q2w3e4r', 'yt_access': 'SMOKE-yt-access-9o8i7u',
    'client_secret': 'SMOKE-google-client-secret-55', 'tg': 'SMOKE-tg-token-4242',
    'notion': 'SMOKE_notion_token_abcdef', 'llm': 'SMOKE-llm-key-3141', 'code': 'SMOKE-dbx-code-27',
    'dbx_worker': 'SMOKE-dbx-worker-refresh-77aa', 'auth_code': 'SMOKE-google-auth-code-91',
}
REPO = 'Perree/video-type-beat-generator'
REGISTRY = {'canales': [
    {'slug': 'ey-mat', 'tipo': 'beats', 'clave': 'ey mat'},
    {'slug': 'canal-smoke', 'tipo': 'beats', 'clave': 'Canal Smoke'},
    {'slug': 'wyresounds', 'tipo': 'loops', 'clave': 'WyreSounds', 'legacy_default': True},
]}
PAGE = 'a' * 32
SLUG, CHANNEL = 'canal-smoke', 'Canal Smoke'
_failed = []


def check(cond, msg):
    if not cond:
        _failed.append(msg)
        print('FAIL:', msg)


def snapshot():
    """``{ruta relativa: (tamaño, mtime)}`` de tokens/ y config/ (no lee contenidos)."""
    out = {}
    for base in ('tokens', 'config'):
        top = os.path.join(ROOT, base)
        for folder, _dirs, files in os.walk(top):
            for name in files:
                path = os.path.join(folder, name)
                info = os.stat(path)
                out[os.path.relpath(path, ROOT)] = (info.st_size, info.st_mtime_ns)
    return out


class OpenGuard:
    """Registra cualquier apertura dentro de tokens/ o config/ del repo.

    Cubre ``builtins.open``, ``io.open`` (lo usa ``pathlib``: ``read_text``/``read_bytes``)
    y ``os.open`` (bajo nivel).
    """

    def __init__(self):
        self.hits = []
        self._open, self._io_open, self._os_open = builtins.open, io.open, os.open
        self.roots = [os.path.realpath(os.path.join(ROOT, d)) for d in ('tokens', 'config')]

    def _note(self, file):
        if isinstance(file, (str, bytes, os.PathLike)):
            path = os.path.realpath(os.fsdecode(file))
            if any(path == r or path.startswith(r + os.sep) for r in self.roots):
                self.hits.append(os.path.relpath(path, ROOT))

    def builtin(self, file, *args, **kwargs):
        self._note(file)
        return self._open(file, *args, **kwargs)

    def io(self, file, *args, **kwargs):
        self._note(file)
        return self._io_open(file, *args, **kwargs)

    def os(self, path, *args, **kwargs):
        self._note(path)
        return self._os_open(path, *args, **kwargs)

    @contextlib.contextmanager
    def active(self):
        with patch('builtins.open', self.builtin), patch('io.open', self.io), \
                patch('os.open', self.os):
            yield

    def self_test(self):
        """El guard tiene que ver una lectura por pathlib (sin tocar archivos reales)."""
        from pathlib import Path
        probe = Path(ROOT) / 'config' / 'no-existe-smoke.json'
        try:
            probe.read_text(encoding='utf-8')
        except OSError:
            pass
        name = os.path.relpath(probe, ROOT)
        seen = name in self.hits
        self.hits = [h for h in self.hits if h != name]
        return seen


class Records(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


class FakeCreds:
    refresh_token = S['yt_refresh']

    def to_json(self):
        return json.dumps({'token': S['yt_access'], 'refresh_token': S['yt_refresh'],
                           'client_id': 'id.apps', 'client_secret': S['client_secret']})


class FakeFlow:
    def run_local_server(self, **_kw):
        # Lo mismo que hace el servidor local real al recibir el redirect.
        logging.getLogger('google_auth_oauthlib.flow').info(
            '"GET /?code=%s HTTP/1.1" 200 -', S['auth_code'])
        return FakeCreds()


class FakeService:
    def channels(self):
        return self

    def list(self, **_kw):
        return self

    def execute(self):
        return {'items': [{'id': 'UCsmoke', 'snippet': {'title': CHANNEL}}]}


class DbxResult:
    refresh_token = S['dbx_refresh']


class DbxFlow:
    def __init__(self, fail=False):
        self.fail = fail

    def finish(self, code):
        if self.fail:
            raise RuntimeError('boom ' + code + ' ' + S['dbx_refresh'])
        return DbxResult()


class BadKeyring(MemoryKeyring):
    def set_password(self, service, name, value):
        raise RuntimeError('backend roto con ' + value)


class DeadKeyring(MemoryKeyring):
    def get_password(self, service, name):
        raise RuntimeError('sin backend')


def errors_clean(exc, label):
    """Mensaje, repr y traceback impreso (lo que llega a un log) sin valores."""
    import traceback
    text = f'{exc} {exc!r} ' + ''.join(traceback.format_exception(exc))
    check(not any(v in text for v in S.values()), f'{label}: la excepción expone un secreto')
    check(exc.__cause__ is None and (exc.__context__ is None or exc.__suppress_context__),
          f'{label}: la excepción encadena el error original')


def check_dropbox(fake, keyring):
    with patch('dropbox.DropboxOAuth2FlowNoRedirect') as cls:
        cls.return_value.start.return_value = 'https://www.dropbox.com/oauth2/authorize?x'
        flow, url = cloud_login.dropbox_start(S['dbx_key'])
        check(url.startswith('https://') and cls.call_args.kwargs.get('use_pkce') is True,
              'Dropbox: el flujo no es PKCE')
    try:
        cloud_login.dropbox_finish(DbxFlow(fail=True), S['dbx_key'], S['code'])
        check(False, 'Dropbox: un código inválido no falló')
    except cloud_login.LoginError as exc:
        errors_clean(exc, 'Dropbox finish')
    check(cloud_login.dropbox_status() == st.MISSING, 'Dropbox: quedó algo tras un fallo')
    cloud_login.dropbox_finish(DbxFlow(), S['dbx_key'], ' ' + S['code'] + ' ')
    check(keyring.store.get((cloud_login.SERVICE, cloud_login.DROPBOX_REFRESH_TOKEN))
          == S['dbx_refresh'], 'Dropbox: el refresh token no quedó en el llavero')
    check(cloud_login.dropbox_status() == st.OK, 'Dropbox: el estado no es ok')

    from core.beat_panel_cloud import local_transport
    with patch('dropbox.Dropbox', return_value='client') as factory:
        check(local_transport().client == 'client'
              and factory.call_args.kwargs['oauth2_refresh_token'] == S['dbx_refresh'],
              'local_transport no usa el llavero')
        kit_cloud.client()
        check(factory.call_args.kwargs['oauth2_refresh_token'] == S['dbx_refresh'],
              'kit_cloud.client no usa el llavero en el escritorio')
    previous = cloud_login.set_backend(MemoryKeyring())
    try:
        env = {'BEAT_DROPBOX_APP_KEY': S['dbx_key'], 'BEAT_DROPBOX_REFRESH_TOKEN': S['dbx_refresh']}
        with patch.dict(os.environ, env), patch('dropbox.Dropbox', return_value='env') as factory:
            check(local_transport().client == 'env', 'local_transport: falta el fallback BEAT_*')
        with patch.dict(os.environ, {}, clear=True):
            try:
                local_transport()
                check(False, 'local_transport sin credenciales no falló')
            except Exception as exc:  # noqa: BLE001
                errors_clean(exc, 'local_transport')
        cloud_login.set_backend(BadKeyring())
        try:
            cloud_login.dropbox_finish(DbxFlow(), S['dbx_key'], S['code'])
            check(False, 'llavero roto no falló')
        except cloud_login.LoginError as exc:
            errors_clean(exc, 'llavero roto')
    finally:
        cloud_login.set_backend(previous)


def check_client_secret(tmp):
    check(cloud_login.client_secret_status(os.path.join(tmp, 'no.json')) == st.MISSING,
          'client_secret: sin importar debería faltar')
    path = os.path.join(tmp, 'client_secret.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'installed': {'client_id': 'id.apps', 'client_secret': S['client_secret'],
                                 'redirect_uris': ['http://localhost']}}, f)
    cloud_login.import_client_secret(path)
    check(os.path.exists(path), 'client_secret: se borró el archivo importado')
    check(cloud_login.client_secret_config()['installed']['client_secret'] == S['client_secret'],
          'client_secret: no quedó en el llavero')
    bad = os.path.join(tmp, 'bad.json')
    with open(bad, 'w', encoding='utf-8') as f:
        json.dump({'web': {'client_secret': S['client_secret']}}, f)
    try:
        cloud_login.import_client_secret(bad)
        check(False, 'client_secret de tipo web aceptado')
    except cloud_login.LoginError as exc:
        errors_clean(exc, 'client_secret inválido')


def check_youtube(fake, gh):
    from core.beat_connections_form import push_beat_channel
    from core.kit_connections_form import push_kit_channel
    from scripts.kit_secrets_sync import SyncError
    with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config',
               return_value=FakeFlow()) as from_config, \
            patch.object(youtube, '_service', return_value=FakeService()):
        token_json, title, channel_id = youtube.authorize()
    check(title == CHANNEL and channel_id == 'UCsmoke'
          and from_config.call_args.args[0]['installed']['client_secret'] == S['client_secret'],
          'YouTube: no usó el client_secret del llavero o no devolvió la identidad')
    check(logging.getLogger('google_auth_oauthlib.flow').getEffectiveLevel() >= logging.WARNING,
          'YouTube: el logger del OAuth sigue en INFO (registra ?code=)')
    with patch('google_auth_oauthlib.flow.InstalledAppFlow.from_client_config',
               side_effect=RuntimeError('google ' + S['client_secret'])):
        try:
            youtube.authorize()
            check(False, 'YouTube: un fallo de OAuth no falló')
        except youtube.YouTubeError as exc:
            errors_clean(exc, 'YouTube authorize')

    rows = [{'id': 'ey mat', 'actions_slug': 'ey-mat'}, {'id': CHANNEL, 'actions_slug': SLUG}]
    lines = []
    slugs = push_beat_channel(CHANNEL, SLUG, token_json, log=lines.extend,
                              config_channels=rows, registry=REGISTRY)
    check(slugs == ['ey-mat', SLUG], f'Beats: BEAT_CHANNELS no se actualizó ({slugs})')
    names = st.beat_secret_names(SLUG)
    check(S['yt_refresh'] in (fake.value('kit-weekly', names[1]) or '')
          and fake.value('kit-weekly', names[0]) == CHANNEL, 'Beats: secretos del canal')
    check(fake.value('kit-weekly', 'KIT_DROPBOX_REFRESH_TOKEN') is None,
          'Beats: se copió el Dropbox de esta PC al worker')
    check(st.beat_youtube_status(SLUG) == st.OK and st.beat_listed_status(SLUG) == st.OK,
          'Beats: el estado no refleja lo subido')

    # Slug de otro canal: ni el config ni el registro dejan pisar BEAT_*_EY_MAT.
    sets_before = len([c for c in fake.calls if c[0][:2] == ['secret', 'set']])
    cases = (
        ('Nuevo', 'ey-mat', rows + [{'id': 'Nuevo', 'actions_slug': 'ey-mat'}], None),
        ('Nuevo', 'ey-mat', [{'id': 'Nuevo', 'actions_slug': 'ey-mat'}], REGISTRY),
        (CHANNEL, 'otro-slug', [{'id': CHANNEL, 'actions_slug': 'otro-slug'}], REGISTRY),
    )
    for channel, slug, config_rows, registry in cases:
        try:
            push_beat_channel(channel, slug, token_json, config_channels=config_rows,
                              registry=registry)
            check(False, f'Beats: se aceptó el slug {slug} para {channel}')
        except st.AutomationError as exc:
            errors_clean(exc, 'slug ajeno')
    check(len([c for c in fake.calls if c[0][:2] == ['secret', 'set']]) == sets_before,
          'Beats: un slug ajeno llegó a escribir secretos')

    env = st.kit_env_name('canal-smoke')
    push_kit_channel(env, 'canal smoke', token_json, log=lines.extend, default_channel='WyreSounds')
    check(env in fake.envs and S['yt_refresh'] in fake.value(env, 'KIT_YT_TOKEN_JSON')
          and fake.value(env, 'KIT_DROPBOX_APP_KEY') is None,
          'Kits: Environment o token no se cargaron, o se copió el Dropbox de esta PC')
    default = st.kit_default_channel(REGISTRY)
    check(default == 'WyreSounds', f'Kits: canal por defecto mal resuelto ({default})')
    check(st.kit_default_channel(None, {'kit_preview': {'channel': 'WyreSounds'}}) == 'WyreSounds',
          'Kits: sin registro no se usa el canal del config guardado')
    before = fake.value('kit-weekly', 'KIT_YT_TOKEN_JSON')
    for channel, owner in (('canal smoke', 'WyreSounds'), ('WyreSounds', None)):
        try:
            push_kit_channel('kit-weekly', channel, token_json, default_channel=owner)
            check(False, f'Kits: kit-weekly aceptó a {channel} (dueño {owner})')
        except SyncError as exc:
            errors_clean(exc, 'kit-weekly ajeno')
    check(fake.value('kit-weekly', 'KIT_YT_TOKEN_JSON') == before,
          'Kits: se pisó el token del canal por defecto')
    push_kit_channel('kit-weekly', 'WyreSounds', token_json, default_channel='WyreSounds')
    check(S['yt_refresh'] in (fake.value('kit-weekly', 'KIT_YT_TOKEN_JSON') or ''),
          'Kits: el canal por defecto no pudo cargar su token')
    print('\n'.join(lines))

def check_shared(fake, gh):
    envs = st.save_kit_keys({'KIT_TELEGRAM_TOKEN': S['tg'], 'KIT_TELEGRAM_CHAT_ID': '-1001',
                             'KIT_LLM_API_KEY': S['llm']})
    check(envs == ['kit-weekly', 'kit-weekly-canal-smoke'],
          f'compartidos: no fueron a todos los Environments ({envs})')
    check(all(fake.value(e, 'KIT_TELEGRAM_TOKEN') == S['tg'] for e in envs),
          'compartidos: valor distinto en algún Environment')
    st.save_beat_notion(S['notion'], PAGE)
    code, text = st.secrets_badge(st.NOTION_KEYS)
    check(code == st.OK and text.startswith('cargado ✓ (2026-10-18)'), f'badge: {text}')
    check(st.kit_telegram_status('kit-weekly-canal-smoke') == st.OK, 'Telegram por Environment')
    for bad in ({'NO_PERMITIDA': S['llm']}, {'KIT_NOTION_PAGE_ID': S['notion']}):
        try:
            st.save_kit_keys(bad)
            check(False, 'compartidos: clave inválida aceptada')
        except st.AutomationError as exc:
            errors_clean(exc, 'compartidos inválidos')
    fake.fail_set.add('KIT_IMAGE_API_KEY')
    try:
        st.save_kit_keys({'KIT_IMAGE_API_KEY': S['llm']})
        check(False, 'compartidos: un gh fallido no falló')
    except st.AutomationError as exc:
        errors_clean(exc, 'gh secret set fallido')
        check('KIT_IMAGE_API_KEY' in str(exc), 'el error no nombra el secreto que falló')
    fake.fail_set.clear()

    from core.cloud_worker import CallWorker
    seen = []
    worker = CallWorker(lambda: (_ for _ in ()).throw(RuntimeError(S['tg'])), 'Falló.')
    worker.failed.connect(seen.append)
    worker.run()
    check(seen == ['Falló.'], 'CallWorker mostró el texto de un error ajeno')


def check_confirmation(fake):
    """OAuth → confirmar cuenta → subir: nada se escribe si no coincide o no se confirma."""
    import time
    from PyQt5.QtWidgets import QApplication, QPlainTextEdit, QWidget
    from core.connections_mixin import ConnectionsMixin
    app = QApplication.instance() or QApplication([])

    class Box:
        def stop(self):
            pass

    class Host(QWidget, ConnectionsMixin):
        def __init__(self, answer):
            super().__init__()
            self.answer, self.said, self.asked = answer, [], []
            self.conn_log, self.login_box = QPlainTextEdit(), Box()
            self._init_connections()

        def refresh_connections(self, *_):
            pass

        def _conn_say(self, text, error=False):
            self.said.append(text)

        def _confirm_youtube(self, channel, title):
            self.asked.append((channel, title))
            return self.answer

    def run(answer, expected):
        pushed = []
        host = Host(answer)
        authorized = (FakeCreds().to_json(), CHANNEL, 'UCsmoke')
        with patch.object(youtube, 'authorize', return_value=authorized):
            host._youtube_two_steps(CHANNEL, expected, lambda token: pushed.append(token),
                                    lambda title: host.said.append('subido ' + title))
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and (host.conn_worker is not None
                                                   or host._conn_after is not None):
                app.processEvents()
        host.stop_connections()
        return host, pushed

    host, pushed = run(False, None)
    check(host.asked == [(CHANNEL, CHANNEL)] and not pushed,
          'YouTube: se subió el token sin confirmar la cuenta')
    host, pushed = run(True, 'UCotro')
    check(not host.asked and not pushed and any('otro canal' in t for t in host.said),
          'YouTube: se subió el token de una cuenta distinta a la esperada')
    host, pushed = run(True, 'UCsmoke')
    check(len(pushed) == 1 and S['yt_refresh'] in pushed[0],
          'YouTube: confirmado y correcto no se subió')


def check_hardening(fake, tmp):
    """Llavero inseguro, borrado verificado, Dropbox propio del worker y repo fijo."""

    class Plain:  # se hace pasar por keyrings.alt.file.PlaintextKeyring
        pass
    Plain.__module__, Plain.__name__ = 'keyrings.alt.file', 'PlaintextKeyring'

    class PlainModule(MemoryKeyring):
        def get_keyring(self):
            return Plain()

    previous = cloud_login.set_backend(PlainModule())
    try:
        try:
            cloud_login.dropbox_finish(DbxFlow(), S['dbx_key'], S['code'])
            check(False, 'llavero en archivo aceptado')
        except cloud_login.LoginError as exc:
            check(exc.code == st.UNKNOWN, 'llavero en archivo: código de error')
        check(cloud_login.dropbox_status() == st.UNKNOWN, 'llavero en archivo: estado')
    finally:
        cloud_login.set_backend(previous)

    class Sticky(MemoryKeyring):
        def delete_password(self, service, name):
            raise RuntimeError('acceso denegado')

    sticky = Sticky()
    sticky.set_password(cloud_login.SERVICE, cloud_login.DROPBOX_REFRESH_TOKEN, S['dbx_refresh'])
    previous = cloud_login.set_backend(sticky)
    try:
        try:
            cloud_login.dropbox_forget()
            check(False, 'Desconectar dijo que borró algo que sigue en el llavero')
        except cloud_login.LoginError as exc:
            errors_clean(exc, 'borrado fallido')
    finally:
        cloud_login.set_backend(previous)
    empty = MemoryKeyring()
    previous = cloud_login.set_backend(empty)
    try:
        cloud_login.dropbox_forget()  # no existía: no es error
    finally:
        cloud_login.set_backend(previous)

    class WorkerResult:
        refresh_token = S['dbx_worker']

    class WorkerFlow:
        def finish(self, code):
            return WorkerResult()

    pc_before = cloud_login.dropbox_credentials()
    creds = cloud_login.dropbox_exchange(WorkerFlow(), S['dbx_key'], S['code'])
    envs = st.save_worker_dropbox(creds)
    check(all(fake.value(e, 'KIT_DROPBOX_REFRESH_TOKEN') == S['dbx_worker'] for e in envs)
          and 'kit-weekly' in envs, 'Dropbox del worker no llegó a todos los Environments')
    check(cloud_login.dropbox_credentials() == pc_before,
          'Dropbox del worker tocó el llavero de esta PC')
    check(S['dbx_refresh'] not in [fake.value(e, 'KIT_DROPBOX_REFRESH_TOKEN') for e in fake.envs],
          'el token de Dropbox de esta PC terminó en GitHub')


def check_review_fixes(fake, tmp):
    """Regresiones de la revisión: %APPDATA%, Environments, hilos y caché."""
    import threading
    import time
    def no_envs(args, stdin=None):
        return (1, '') if args[:1] == ['api'] else fake(args, stdin)
    try:
        st.save_kit_keys({'KIT_LLM_API_KEY': S['llm']}, gh_status.GhStatus(run=no_envs))
        check(False, 'se guardó sin poder listar los Environments')
    except st.AutomationError as exc:
        errors_clean(exc, 'Environments sin listar')

    appdata = os.path.join(tmp, 'appdata_client_secret.json')
    with open(appdata, 'w', encoding='utf-8') as f:
        json.dump({'installed': {'client_id': 'id.apps', 'client_secret': S['client_secret']}}, f)
    previous = cloud_login.set_backend(DeadKeyring())
    try:
        check(cloud_login.client_secret_config(appdata)['installed']['client_id'] == 'id.apps',
              'sin llavero no se usó el client_secret de %APPDATA%')
        check(cloud_login.client_secret_status(os.path.join(tmp, 'no.json')) == st.UNKNOWN,
              'sin llavero ni archivo el estado no es unknown')
    finally:
        cloud_login.set_backend(previous)

    calls = []
    slow = gh_status.GhStatus(run=lambda a, i=None: (calls.append(a), (0, '[]'))[1],
                              allow_background=True)
    done = threading.Event()
    slow.enable_background(done.set)
    first = slow.secrets('kit-weekly')
    check(first is None and done.wait(5) and slow.secrets('kit-weekly') == {},
          'la lectura en el hilo principal no fue en segundo plano')
    check(len(calls) == 1, 'la carga en segundo plano se repitió')

    from core.cloud_worker import CallWorker, detach
    gate = threading.Event()
    worker = CallWorker(lambda: gate.wait(10), 'x')
    worker.start()
    start = time.monotonic()
    detach(worker)
    check(time.monotonic() - start < 1, 'soltar un hilo en curso bloqueó el cierre')
    gate.set()
    worker.wait(5)
    detach(None)  # purga el hilo ya terminado


def check_cache(fake):
    clock = [0.0]
    gh = gh_status.GhStatus(run=fake, clock=lambda: clock[0], repo=REPO)
    count = lambda: sum(1 for a, _ in fake.calls if a[:2] == ['secret', 'list'])  # noqa: E731
    start = count()
    st.secrets_state(st.NOTION_KEYS, gh=gh)
    st.secrets_state(st.KIT_DROPBOX_KEYS, gh=gh)
    check(count() - start == 1, 'caché: se listó dos veces dentro de 60 s')
    clock[0] = 61
    st.secrets_state(st.NOTION_KEYS, gh=gh)
    check(count() - start == 2, 'caché: no se renovó pasados 60 s')
    gh.set_secret('BEAT_NOTION_TOKEN', S['notion'])
    st.secrets_state(st.NOTION_KEYS, gh=gh)
    check(count() - start == 3, 'caché: una escritura no la invalidó')
    flaky = FakeGhRun(logged_in=False)
    retry = gh_status.GhStatus(run=flaky, clock=lambda: clock[0])
    check(retry.auth() == st.MISSING, 'sin sesión no da missing')
    flaky.logged_in = True
    clock[0] += 6
    check(retry.auth() == st.OK, 'un fallo quedó en caché más de 5 s (tras gh auth login)')
    off = gh_status.GhStatus(run=FakeGhRun(logged_in=False))
    check(st.secrets_state(st.NOTION_KEYS, gh=off) == st.UNKNOWN
          and st.gh_auth_status(off) == st.MISSING, 'sin sesión de gh el estado no es unknown')


def check_cli(fake, gh, tmp):
    from scripts import beat_secrets_sync, kit_secrets_sync
    token = os.path.join(tmp, 'yt.json')
    with open(token, 'w', encoding='utf-8') as f:
        f.write(FakeCreds().to_json())
    with patch.object(beat_secrets_sync, '_read_gh', gh.read):
        code = beat_secrets_sync.main(['--channel', 'cli', '--slug', 'cli', '--yt-token-file',
                                       token, '--repo', REPO], runner=gh.runner)
    check(code == 0 and S['yt_refresh'] in fake.value('kit-weekly', 'BEAT_YT_TOKEN_JSON_CLI'),
          'CLI de Beats: --yt-token-file dejó de funcionar')
    ci_env = {'KIT_TELEGRAM_TOKEN': S['tg'], 'KIT_TELEGRAM_CHAT_ID': '-1001',
              'KIT_DROPBOX_REFRESH_TOKEN': S['dbx_worker'], 'KIT_DROPBOX_APP_KEY': S['dbx_key']}
    with patch.dict(os.environ, ci_env):
        code = kit_secrets_sync.main(['--env', 'kit-weekly', '--channel', 'cli', '--no-prompt',
                                      '--yt-token-file', token, '--repo', REPO], runner=gh.runner)
    check(code == 0 and fake.value('kit-weekly', 'KIT_DROPBOX_REFRESH_TOKEN') == S['dbx_worker'],
          'CLI de Kits: no tomó Dropbox del entorno')
    with patch.dict(os.environ, {'KIT_TELEGRAM_TOKEN': S['tg'], 'KIT_TELEGRAM_CHAT_ID': '-1001'}):
        code = kit_secrets_sync.main(['--env', 'kit-weekly', '--channel', 'cli', '--no-prompt',
                                      '--yt-token-file', token, '--repo', REPO], runner=gh.runner)
    check(code == 1, 'CLI de Kits: usó el Dropbox del llavero de esta PC')
    code = kit_secrets_sync.main(['--env', 'kit-weekly', '--channel', 'cli', '--no-prompt',
                                  '--yt-token-file', token, '--repo', REPO,
                                  '--default-channel', 'WyreSounds'], runner=gh.runner)
    check(code == 1, 'CLI de Kits: --default-channel no protege kit-weekly')


def main():
    before = snapshot()
    guard = OpenGuard()
    with guard.active():
        check(guard.self_test(), 'el guard no detecta lecturas por pathlib')
    records = Records()
    logging.getLogger().addHandler(records)
    logging.getLogger().setLevel(logging.DEBUG)
    fake = FakeGhRun(variables={'BEAT_CHANNELS': '["ey-mat"]'})
    gh = gh_status.GhStatus(run=fake, repo=REPO)
    previous_gh = gh_status.set_default(gh)
    keyring = MemoryKeyring()
    previous_kr = cloud_login.set_backend(keyring)
    out, err = io.StringIO(), io.StringIO()
    saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith(('KIT_', 'BEAT_'))}
    try:
        with tempfile.TemporaryDirectory() as tmp, guard.active(), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            check_dropbox(fake, keyring)
            check_client_secret(tmp)
            check_youtube(fake, gh)
            check_shared(fake, gh)
            check_cache(fake)
            check_cli(fake, gh, tmp)
            check_review_fixes(fake, tmp)
            check_confirmation(fake)
            check_hardening(fake, tmp)
    finally:
        os.environ.update(saved)
        gh_status.set_default(previous_gh)
        cloud_login.set_backend(previous_kr)
        logging.getLogger().removeHandler(records)

    check(snapshot() == before, 'se creó o modificó un archivo en tokens/ o config/')
    check(not guard.hits, f'se abrieron archivos de tokens/ o config/: {sorted(set(guard.hits))}')
    values = list(S.values())
    check(not any(v in json.dumps([a for a, _ in fake.calls]) for v in values),
          'un secreto viajó como argumento de gh')
    sets = [(a, i) for a, i in fake.calls if a[:2] in (['secret', 'set'], ['variable', 'set'])]
    check(sets and all(i for _a, i in sets), 'un secreto se subió sin stdin')
    reads = [a for a, i in fake.calls if a[:2] in (['secret', 'list'], ['variable', 'get'])]
    check(all(i is None for a, i in fake.calls if a in reads), 'una lectura mandó stdin')
    pinned = [a for a, _ in fake.calls if a[:1] in (['secret'], ['variable'], ['api'])]
    check(pinned and all(('--repo' in a and a[a.index('--repo') + 1] == REPO)
                         or any(str(x).startswith('repos/' + REPO) for x in a) for a in pinned),
          'una llamada a gh no fijó el repo (podría ir a un fork o a otro remoto)')
    blob = out.getvalue() + err.getvalue() + '\n'.join(records.lines)
    check(not any(v in blob for v in values), 'un secreto apareció en la salida o en los logs')
    sys.stdout.write(out.getvalue())
    if _failed:
        print(f'smoke_cloud_credentials: {len(_failed)} fallas')
        return 1
    print('smoke_cloud_credentials: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
