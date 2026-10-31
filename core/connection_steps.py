# -*- coding: utf-8 -*-
"""Mini asistentes de cada conexión (Dropbox, GitHub, Google, robot, Telegram, Notion, IA, nube).

Cada ``Connection`` dice su estado y arma sus pasos (``core/wizard.py``). Todo se guarda con lo
que ya existía: llavero de Windows (``cloud_login``) y GitHub Secrets (``automation_status``).
Ningún valor se escribe en archivos ni se muestra.
"""
import os
import shutil
import subprocess
import time

from PyQt5.QtCore import QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                             QVBoxLayout, QWidget)

from core import automation_status as status
from core import cloud_login, gh_status
from core.cloud_worker import CallWorker
from core.wizard import WizardPage
import ui_theme as theme

OK, MISSING, UNKNOWN = status.OK, status.MISSING, status.UNKNOWN
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GH_DEFAULT_DIRS = (r'C:\Program Files\GitHub CLI', r'C:\Program Files (x86)\GitHub CLI')
LINKS = {
    'dropbox_apps': 'https://www.dropbox.com/developers/apps',
    'github_cli': 'https://cli.github.com/',
    'google_console': 'https://console.cloud.google.com/apis/credentials',
    'botfather': 'https://t.me/BotFather',
    'notion': 'https://www.notion.so/my-integrations',
}


# --- Utilidades ---


def open_url(url):
    QDesktopServices.openUrl(QUrl(url))


def ensure_gh_on_path():
    """Si GitHub CLI se instaló recién, la app no lo ve en el PATH: se agrega la carpeta típica."""
    if shutil.which('gh'):
        return True
    for folder in GH_DEFAULT_DIRS:
        if os.path.isfile(os.path.join(folder, 'gh.exe')):
            os.environ['PATH'] = folder + os.pathsep + os.environ.get('PATH', '')
            return True
    return False


def open_console(command, title='Type Beat'):
    """Abre una ventana de consola nueva que corre ``command`` (para pasos interactivos)."""
    subprocess.Popen(f'start "{title}" cmd /k {command}', shell=True, cwd=ROOT)  # noqa: S602 - comando fijo


def gh_ready():
    ensure_gh_on_path()
    return status.gh_auth_status() == OK


class Task:
    """Corre una función en segundo plano (``CallWorker``) y avisa al terminar."""

    def __init__(self, owner):
        self.owner = owner
        self.worker = None
        self.message = ''
        self.error = False

    def busy(self):
        return self.worker is not None

    def run(self, fn, fallback, wait_text, on_ok=None):
        if self.worker is not None:
            return
        self.message, self.error = wait_text, False
        worker = CallWorker(fn, fallback, self.owner)

        def ok(result):
            self.message, self.error = 'Listo ✓', False
            if on_ok:
                on_ok(result)

        def failed(text):
            self.message, self.error = text, True
        worker.done.connect(ok)
        worker.failed.connect(failed)
        worker.finished.connect(self._finished)
        self.worker = worker
        worker.start()

    def _finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        gh_status.default().invalidate()


def _page(*items):
    box = QWidget()
    layout = QVBoxLayout(box)
    for item in items:
        if isinstance(item, QHBoxLayout):
            layout.addLayout(item)
        elif isinstance(item, str):
            label = QLabel(item)
            label.setWordWrap(True)
            label.setOpenExternalLinks(True)
            layout.addWidget(label)
        else:
            layout.addWidget(item)
    layout.addStretch(1)
    return box


def _buttons(*pairs):
    row = QHBoxLayout()
    for text, slot in pairs:
        button = QPushButton(text)
        button.clicked.connect(slot)
        row.addWidget(button)
    row.addStretch()
    return row


def _secret_field(placeholder):
    field = QLineEdit()
    field.setEchoMode(QLineEdit.Password)
    field.setPlaceholderText(placeholder)
    return field


def _task_label(task):
    label = QLabel()
    label.setWordWrap(True)

    def refresh():
        color = theme.color('danger' if task.error else 'warning' if task.busy() else 'success')
        label.setText(f'<span style="color:{color}">{task.message}</span>' if task.message else '')
        label.setVisible(bool(task.message))
    label.setVisible(False)
    return label, refresh


def _done_page(connection):
    light = QLabel()

    def refresh():
        code = connection.status()
        light.setText((f'<span style="color:{theme.color("success")}">●</span> Conectado. Ya podés cerrar este '
                       'asistente.') if code == OK else
                      f'<span style="color:{theme.color("danger")}">●</span> Todavía no aparece conectado. '
                      'Si recién lo hiciste, esperá unos segundos.')
    return WizardPage('Listo', '', _page(light), refresh=refresh, next_text='Terminar', can_back=True)


# --- Conexiones ---

class Connection:
    key = ''
    title = ''
    icon = '🔌'
    required = True
    description = ''

    def status(self):
        return UNKNOWN

    def status_text(self):
        return {OK: 'Conectado', MISSING: 'Falta', UNKNOWN: 'Revisando…'}.get(self.status(), 'Falta')

    def pages(self, owner):
        raise NotImplementedError


class DropboxPC(Connection):
    key, title, icon = 'dropbox_pc', 'Dropbox (esta PC)', '📦'
    description = 'Para leer tus canales y fondos desde la app. Una vez por computadora.'

    def status(self):
        return cloud_login.dropbox_status()

    def pages(self, owner):
        state = {'flow': None}
        task = Task(owner)
        try:
            known = (cloud_login.dropbox_credentials() or {}).get('app_key', '')
        except cloud_login.LoginError:
            known = ''
        app_key = _secret_field('App key (algo como «a1b2c3d4e5f6g7h»)')
        app_key.setText(known)
        code = _secret_field('Código que muestra Dropbox después de autorizar')
        task_label, task_refresh = _task_label(task)

        def authorize():
            try:
                state['flow'], url = cloud_login.dropbox_start(app_key.text())
            except cloud_login.LoginError as exc:
                task.message, task.error = str(exc), True
                return
            open_url(url)
            task.message, task.error = 'Se abrió Dropbox: tocá «Permitir» y copiá el código.', False

        def save():
            task.run(lambda: cloud_login.dropbox_finish(state['flow'], app_key.text(), code.text()),
                     'No se pudo conectar Dropbox.', 'Guardando en el llavero de Windows…',
                     lambda _r: owner.wizard_advance())
            return False

        intro = ('La app usa una «app» de Dropbox tuya (tipo <b>App folder</b>). Si ya la tenés, pegá su '
                 '<b>App key</b>. Si no:<ol><li>Abrí la consola de Dropbox (botón de abajo).</li>'
                 '<li>«Create app» → «Scoped access» → «App folder» → poné un nombre.</li>'
                 '<li>En «Permissions» tildá <i>files.content.write</i> y <i>files.content.read</i> → Submit.</li>'
                 '<li>En «Settings» copiá el <b>App key</b>.</li></ol>')
        return [
            WizardPage('App key de Dropbox', '', _page(intro, app_key, _buttons(
                ('Abrir consola de Dropbox', lambda: open_url(LINKS['dropbox_apps'])))),
                ready=lambda: cloud_login.printable(app_key.text().strip(), 128),
                blocker=lambda: 'pegá el App key.'),
            WizardPage('Autorizá esta PC', 'Se abre Dropbox en el navegador: tocá «Permitir» y copiá el código.',
                       _page(_buttons(('🌐 Abrir Dropbox para autorizar', authorize)), code, task_label),
                       refresh=task_refresh, on_next=save, busy=task.busy, next_text='Guardar en esta PC',
                       ready=lambda: state['flow'] is not None and bool(code.text().strip()),
                       blocker=lambda: ('tocá «Abrir Dropbox para autorizar».' if state['flow'] is None
                                        else 'pegá el código que te mostró Dropbox.')),
            _done_page(self),
        ]


class GitHub(Connection):
    key, title, icon = 'github', 'GitHub', '🐙'
    description = 'El robot de la nube vive en GitHub. Necesita la herramienta «GitHub CLI» y tu sesión.'

    def status(self):
        if not ensure_gh_on_path():
            return MISSING
        return status.gh_auth_status()

    def status_text(self):
        if not ensure_gh_on_path():
            return 'Falta instalar GitHub CLI'
        return super().status_text()

    def pages(self, owner):
        def install():
            if QMessageBox.question(owner, 'Instalar GitHub CLI',
                                    'Se abre una ventana que instala GitHub CLI con «winget» (el instalador de '
                                    'Windows). Puede pedirte permiso de administrador. ¿Seguir?',
                                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) == QMessageBox.Yes:
                open_console('winget install --id GitHub.cli -e --accept-source-agreements '
                             '--accept-package-agreements', 'Instalar GitHub CLI')

        def login():
            ensure_gh_on_path()
            gh = shutil.which('gh') or 'gh'
            open_console(f'"{gh}" auth login --hostname github.com --git-protocol https --web',
                         'Iniciar sesión en GitHub')

        def recheck():
            ensure_gh_on_path()
            gh_status.default().invalidate()

        install_text = ('GitHub CLI es una herramienta chica que deja a la app hablar con GitHub (donde vive el '
                        'robot). <b>Opción fácil:</b> «Instalar GitHub CLI» (usa el instalador de Windows). '
                        f'<b>O</b> bajala de <a href="{LINKS["github_cli"]}">cli.github.com</a>. '
                        'Cuando termine, tocá «Ya la instalé».')
        login_text = ('Tocá «Iniciar sesión»: se abre una ventana negra. Respondé con Enter las preguntas, copiá el '
                      'código de 8 letras que muestra y pegalo en la página de GitHub que se abre. Usá la cuenta '
                      'dueña del repositorio <b>Perree/video-type-beat-generator</b>. Esta pantalla se tilda sola.')
        return [
            WizardPage('Instalá GitHub CLI', '', _page(install_text, _buttons(
                ('Instalar GitHub CLI', install), ('Ya la instalé', recheck))),
                ready=ensure_gh_on_path, blocker=lambda: 'falta instalar GitHub CLI.'),
            WizardPage('Iniciá sesión en GitHub', '', _page(login_text, _buttons(
                ('🔑 Iniciar sesión', login), ('Revisar ahora', recheck))),
                ready=lambda: status.gh_auth_status() == OK,
                blocker=lambda: 'iniciá sesión en la ventana que se abre y esperá unos segundos.'),
            _done_page(self),
        ]


class Google(Connection):
    key, title, icon = 'google', 'Google (permiso para YouTube)', '▶'
    description = 'Un permiso de Google Cloud para que la app pueda conectar tus canales de YouTube.'

    def status(self):
        return cloud_login.client_secret_status()

    def pages(self, owner):
        task = Task(owner)
        legacy = os.path.join(ROOT, 'config', 'client_secret.json')
        task_label, task_refresh = _task_label(task)

        def import_file(path):
            if path:
                task.run(lambda: cloud_login.import_client_secret(path), 'No se pudo importar el archivo.',
                         'Guardando en el llavero…')

        def pick():
            path, _ = QFileDialog.getOpenFileName(owner, 'Archivo client_secret descargado de Google',
                                                  os.path.expanduser('~/Downloads'), 'JSON (*.json)')
            import_file(path)

        guide = ('Se hace una sola vez (Google exige hacerlo en su web):<ol>'
                 '<li>Abrí Google Cloud (botón de abajo) y creá un proyecto.</li>'
                 '<li>«APIs y servicios» → «Biblioteca» → <b>YouTube Data API v3</b> → Habilitar.</li>'
                 '<li>«Pantalla de consentimiento»: tipo <b>Externo</b>; agregá tu mail como usuario de prueba y '
                 'pasala a <b>En producción</b> (si no, hay que reconectar cada 7 días).</li>'
                 '<li>«Credenciales» → «Crear credenciales» → «ID de cliente OAuth» → <b>App de escritorio</b> → '
                 'Descargar JSON.</li></ol>')
        buttons = [('Abrir Google Cloud', lambda: open_url(LINKS['google_console'])),
                   ('Elegir el archivo descargado…', pick)]
        if os.path.isfile(legacy):
            buttons.insert(1, ('Usar el que ya tengo en la carpeta config', lambda: import_file(legacy)))
        return [
            WizardPage('Permiso de Google para YouTube', '', _page(guide, _buttons(*buttons), task_label),
                       refresh=task_refresh, busy=task.busy, ready=lambda: self.status() == OK,
                       blocker=lambda: 'elegí el archivo JSON que descargaste de Google.'),
            _done_page(self),
        ]


class DropboxRobot(Connection):
    key, title, icon = 'dropbox_robot', 'Dropbox del robot', '🤖'
    description = 'El robot necesita su propio permiso de Dropbox (distinto del de esta PC).'

    def status(self):
        return status.dropbox_worker_status()

    def pages(self, owner):
        state = {'flow': None}
        task = Task(owner)
        try:
            known = (cloud_login.dropbox_credentials() or {}).get('app_key', '')
        except cloud_login.LoginError:
            known = ''
        app_key = _secret_field('App key de Dropbox (el mismo de esta PC)')
        app_key.setText(known)
        code = _secret_field('Código NUEVO que muestra Dropbox')
        task_label, task_refresh = _task_label(task)

        def authorize():
            try:
                state['flow'], url = cloud_login.dropbox_start(app_key.text())
            except cloud_login.LoginError as exc:
                task.message, task.error = str(exc), True
                return
            open_url(url)
            task.message, task.error = 'Se abrió Dropbox: «Permitir» y copiá el código nuevo.', False

        def upload():
            def work():
                creds = cloud_login.dropbox_exchange(state['flow'], app_key.text(), code.text())
                return status.save_worker_dropbox(creds)
            task.run(work, 'No se pudo subir el permiso a GitHub.', 'Subiendo a GitHub…',
                     lambda _r: owner.wizard_advance())
            return False

        return [
            WizardPage('Permiso de Dropbox para el robot', 'Necesita GitHub conectado. Se pide un código nuevo: así '
                       'el permiso del robot y el de esta PC se pueden quitar por separado.',
                       _page(app_key, _buttons(('🌐 Abrir Dropbox para autorizar', authorize)), code, task_label),
                       refresh=task_refresh, on_next=upload, busy=task.busy, next_text='Subir a GitHub',
                       ready=lambda: gh_ready() and state['flow'] is not None and bool(code.text().strip()),
                       blocker=lambda: ('primero conectá GitHub.' if not gh_ready() else
                                        'tocá «Abrir Dropbox para autorizar».' if state['flow'] is None
                                        else 'pegá el código nuevo.')),
            _done_page(self),
        ]


class _SecretsConnection(Connection):
    """Conexión opcional que se guarda en GitHub Secrets con uno o más campos."""
    fields = ()       # ((clave, placeholder), …)
    intro = ''
    link = None

    def save(self, values):
        raise NotImplementedError

    def test(self, values):
        return None  # sin prueba

    def pages(self, owner):
        task = Task(owner)
        widgets = {key: _secret_field(placeholder) for key, placeholder in self.fields}
        task_label, task_refresh = _task_label(task)

        def values():
            return {key: field.text().strip() for key, field in widgets.items()}

        def save():
            task.run(lambda: self.save(values()), 'No se pudo guardar en GitHub.', 'Guardando en GitHub…',
                     lambda _r: owner.wizard_advance())
            return False

        buttons = []
        if self.link:
            buttons.append((f'Abrir {self.link[0]}', lambda: open_url(self.link[1])))
        if type(self).test is not _SecretsConnection.test:
            buttons.append(('Probar', lambda: task.run(lambda: self.test(values()), 'La prueba falló.',
                                                         'Probando…')))
        items = [self.intro, *widgets.values()]
        if buttons:
            items.append(_buttons(*buttons))
        items.append(task_label)
        return [
            WizardPage(self.title, 'Opcional. Se guarda directo en GitHub (no queda en esta PC).', _page(*items),
                       refresh=task_refresh, on_next=save, busy=task.busy, next_text='Guardar en GitHub',
                       ready=lambda: gh_ready() and all(values().values()),
                       blocker=lambda: 'primero conectá GitHub.' if not gh_ready() else 'completá los campos.'),
            _done_page(self),
        ]


class Telegram(_SecretsConnection):
    key, title, icon, required = 'telegram', 'Telegram (avisos de Loop kits)', '✈', False
    description = 'Te avisa por Telegram cuando el robot de Loop kits publica o falla. Obligatorio para Loop kits.'
    fields = (('KIT_TELEGRAM_TOKEN', 'Token del bot (de @BotFather)'), ('KIT_TELEGRAM_CHAT_ID', 'Chat id'))
    intro = ('<ol><li>En Telegram hablá con <b>@BotFather</b> → /newbot → copiá el <b>token</b>.</li>'
             '<li>Mandale un mensaje a tu bot y abrí <code>api.telegram.org/bot&lt;token&gt;/getUpdates</code>: '
             'el número de «chat → id» es tu <b>chat id</b>.</li></ol>')
    link = ('BotFather', LINKS['botfather'])

    def status(self):
        return status.kit_telegram_status()

    def save(self, values):
        return status.save_kit_keys(values)

    def test(self, values):
        from core import kit_notify
        kit_notify.send('Prueba desde Type Beat Video Generator ✓', env=values)
        return True


class Notion(_SecretsConnection):
    key, title, icon, required = 'notion', 'Notion (informes de tendencias)', '📝', False
    description = 'Opcional: informes de SEO y tendencias en una página de Notion.'
    fields = (('token', 'Token de la integración (secret_…)'), ('page', 'ID o link de la página'))
    intro = ('<ol><li>Creá una integración en Notion y copiá su token.</li>'
             '<li>En la página de informes: «…» → «Conexiones» → agregá la integración, y copiá el link.</li></ol>')
    link = ('Notion', LINKS['notion'])

    def status(self):
        beats, kits = status.beat_notion_status(), status.kit_notion_status()
        return OK if OK in (beats, kits) else MISSING

    def save(self, values):
        from core import kit_notion
        page = kit_notion.page_id(values['page']) or values['page']
        status.save_beat_notion(values['token'], page)
        return status.save_kit_notion(values['token'], page)


class AI(_SecretsConnection):
    key, title, icon, required = 'ai', 'IA para nombres y portadas', '✨', False
    description = 'Opcional: Loop kits puede inventar nombres y portadas con IA.'
    fields = (('KIT_LLM_API_KEY', 'Clave de IA para nombres'), ('KIT_IMAGE_API_KEY', 'Clave de IA para imágenes'))
    intro = 'Pegá las claves de tu proveedor de IA. Si no usás esta función, salteala.'

    def status(self):
        return OK if OK in (status.kit_llm_status(), status.kit_image_status()) else MISSING

    def save(self, values):
        return status.save_kit_keys(values)


class CloudPrep(Connection):
    key, title, icon = 'cloud_prep', 'Preparar la nube (una vez)', '☁'
    description = 'Crea en Dropbox la lista de canales automatizados a partir de tu configuración anterior.'
    # reason: 'dropbox' = no se puede revisar sin Dropbox conectado; 'offline' = no respondió.
    _cache = {'at': 0.0, 'code': UNKNOWN, 'reason': ''}

    def status(self):
        if cloud_login.dropbox_status() != OK:
            return UNKNOWN  # sin Dropbox no se sabe si la lista existe (quizá la creó la otra PC)
        return self._cache['code']

    @classmethod
    def check(cls):
        """Lee Dropbox (lento): llamar en segundo plano. Guarda el resultado por 60 s."""
        if cloud_login.dropbox_status() != OK:
            cls._cache.update(at=0.0, code=UNKNOWN, reason='dropbox')
            return UNKNOWN
        if time.monotonic() - cls._cache['at'] < 60 and cls._cache['code'] != UNKNOWN:
            return cls._cache['code']
        try:
            from core.beat_panel_cloud import local_transport
            from core.cloud_registry import CloudRegistry
            _doc, rev = CloudRegistry(local_transport()).read('canales')
            code, reason = (OK if rev is not None else MISSING), ''
        except Exception:  # noqa: BLE001 - sin red: se reintenta después
            code, reason = UNKNOWN, 'offline'
        cls._cache.update(at=time.monotonic(), code=code, reason=reason)
        return code

    def status_text(self):
        if cloud_login.dropbox_status() != OK:
            return 'Conectá Dropbox para revisar'
        if self.status() == UNKNOWN:
            return 'No se pudo revisar (sin conexión)' if self._cache['reason'] == 'offline' else 'Revisando…'
        return {OK: 'Lista', MISSING: 'Falta'}[self.status()]

    def pages(self, owner):
        task = Task(owner)
        task_label, task_refresh = _task_label(task)
        preview = QLabel()
        preview.setWordWrap(True)
        state = {'docs': None, 'count': 0}

        def prep_problem():
            if cloud_login.dropbox_status() != OK:
                return 'primero conectá Dropbox en esta PC (así se revisa si la lista ya existe).'
            if self.status() == OK:
                return 'la lista ya existe en Dropbox: no hace falta hacer nada.'
            if state['docs'] is None:
                return 'no se pudo leer la configuración anterior (mirá el mensaje).'
            if not state['count']:
                return 'en esta PC no hay canales para pasar: hacelo desde la otra PC.'
            return ''

        def build():
            from scripts import migrate_to_cloud as mig
            try:
                app = mig.read_app(mig.CONFIG_FILE)
                canales, ajustes, report = mig.build(app)
            except Exception as exc:  # noqa: BLE001 - mostrar el motivo
                preview.setText(f'✗ No se pudo leer la configuración anterior: {exc}')
                return
            state['docs'] = (('canales', canales), ('ajustes', ajustes))
            state['count'] = len(report['migrados'])
            lines = [f'• <b>{m["canal"]}</b> ({"Beats" if m["tipo"] == "beats" else "Loop kits"})'
                     for m in report['migrados']]
            if not lines:
                untyped = sum(1 for o in report['omitidos'] if o['motivo'] == 'tipo sin definir')
                preview.setText(
                    '<b>En esta PC no hay canales automatizados para pasar a la nube.</b><br><br>'
                    + (f'Hay {untyped} canales en la configuración de esta PC, pero ninguno está marcado como Beats o '
                       'Loop kits (pasa si esta PC no es la que configuró la automatización). '
                       if untyped else '')
                    + 'Hacé «Preparar la nube» desde la <b>otra PC</b>, la que tiene la automatización configurada. '
                    'Crear acá una lista vacía no sirve y después habría que rehacerla.')
                return
            skipped = [f'• {o["canal"]}: {o["motivo"]}' for o in report['omitidos']]
            preview.setText(f'Se van a crear <b>{len(lines)} canales automatizados</b>:<br>' + '<br>'.join(lines)
                            + ('<br><br>Se omiten:<br>' + '<br>'.join(skipped) if skipped else ''))

        def apply():
            from core.beat_panel_cloud import local_transport
            from scripts import migrate_to_cloud as mig

            def work():
                ok, lines = mig.apply(state['docs'], local_transport())
                CloudPrep._cache['at'] = 0.0
                if not ok:
                    raise status.AutomationError(' '.join(lines))
                return lines
            task.run(work, 'No se pudo escribir en Dropbox.', 'Creando en Dropbox…', lambda _r: owner.wizard_advance())
            return False

        return [
            WizardPage('Preparar la nube', 'Se hace una sola vez. No borra nada: solo crea la lista nueva en '
                       'Dropbox.', _page(preview, task_label), on_enter=build, refresh=task_refresh,
                       on_next=apply, busy=task.busy, next_text='Crear en Dropbox',
                       ready=lambda: not prep_problem(), blocker=prep_problem),
            _done_page(self),
        ]


def all_connections():
    """En el orden en que conviene hacerlas."""
    return [DropboxPC(), GitHub(), Google(), DropboxRobot(), CloudPrep(), Telegram(), Notion(), AI()]
