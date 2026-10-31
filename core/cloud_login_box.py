# -*- coding: utf-8 -*-
"""Recuadro «Esta PC» de Conexiones: Dropbox (llavero), GitHub (``gh``) y client_secret.

Es lo único que se conecta por PC; el resto vive en GitHub Secrets. No muestra valores:
los campos password se limpian al terminar. Emite ``changed`` para que el panel refresque.
"""
from PyQt5.QtCore import QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton,
)

from core import cloud_login, gh_status
from core.automation_status import ROOT
from core.cloud_worker import CallWorker, detach
from core.connections_mixin import gh_updates
import ui_theme as theme

_LIGHTS = {cloud_login.OK: (theme.color('success'), 'Conectado'),
           cloud_login.MISSING: (theme.color('danger'), 'Falta'),
           cloud_login.INVALID: (theme.color('warning'), 'Inválido'),
           cloud_login.UNKNOWN: (theme.color('text_muted'), 'Sin llavero (instalá keyring)')}


def light(code, text=None):
    color, default = _LIGHTS.get(code, _LIGHTS[cloud_login.UNKNOWN])
    return f'<span style="color:{color}">●</span> {text or default}'


class CloudLoginBox(QGroupBox):
    changed = pyqtSignal()
    message = pyqtSignal(str, bool)  # texto, es_error

    def __init__(self, parent=None):
        super().__init__('Esta PC', parent)
        self.worker = None
        self._flow = None
        form = theme.form_layout(self)
        self.dropbox_light, self.gh_light, self.google_light = QLabel(), QLabel(), QLabel()
        form.addRow('Dropbox', self.dropbox_light)
        self.dbx_app_key = QLineEdit()
        self.dbx_app_key.setEchoMode(QLineEdit.Password)
        self.dbx_app_key.setPlaceholderText('App key de la app App folder')
        self.dbx_code = QLineEdit()
        self.dbx_code.setEchoMode(QLineEdit.Password)
        self.dbx_code.setPlaceholderText('Código que muestra Dropbox')
        form.addRow('Clave de la app', self.dbx_app_key)
        form.addRow('Código de Dropbox', self.dbx_code)
        row = QHBoxLayout()
        self.dbx_start_button = QPushButton('Autorizar Dropbox')
        self.dbx_start_button.clicked.connect(self.start_dropbox)
        self.dbx_finish_button = QPushButton('Guardar en esta PC')
        self.dbx_finish_button.clicked.connect(self.finish_dropbox)
        self.dbx_worker_button = QPushButton('Subir al robot (GitHub)')
        self.dbx_worker_button.setToolTip('Autorización propia del worker: se sube a GitHub y no '
                                          'se guarda en esta PC. Pedí un código nuevo para esto.')
        self.dbx_worker_button.clicked.connect(self.finish_dropbox_worker)
        self.dbx_forget_button = theme.danger(QPushButton('Desconectar'))
        self.dbx_forget_button.clicked.connect(self.forget_dropbox)
        for button in (self.dbx_start_button, self.dbx_finish_button, self.dbx_worker_button):
            row.addWidget(button)
        row.addStretch(1)
        row.addWidget(self.dbx_forget_button)
        form.addRow('', row)
        gh_row = QHBoxLayout()
        gh_row.addWidget(self.gh_light, 1)
        self.gh_check_button = QPushButton('Revisar')
        self.gh_check_button.clicked.connect(self.check_github)
        gh_row.addWidget(self.gh_check_button)
        form.addRow('GitHub', gh_row)
        g_row = QHBoxLayout()
        g_row.addWidget(self.google_light, 1)
        self.import_secret_button = QPushButton('Importar permiso de Google…')
        self.import_secret_button.setToolTip('El archivo client_secret.json que descargaste de Google Cloud.')
        self.import_secret_button.clicked.connect(self.import_client_secret)
        g_row.addWidget(self.import_secret_button)
        form.addRow('Permiso de Google', g_row)
        gh_updates().updated.connect(self.refresh)
        self.refresh()

    def buttons(self):
        return [self.dbx_start_button, self.dbx_finish_button, self.dbx_worker_button,
                self.dbx_forget_button, self.gh_check_button, self.import_secret_button]

    def refresh(self):
        self.dropbox_light.setText(light(cloud_login.dropbox_status()))
        gh = cloud_login.gh_status()
        self.gh_light.setText(light(gh, {
            cloud_login.OK: 'Conectado (gh)', cloud_login.UNKNOWN: 'Consultando GitHub…',
        }.get(gh, 'Sin sesión: corré «gh auth login» en una terminal')))
        google = cloud_login.client_secret_status()
        self.google_light.setText(light(google, 'En el llavero' if google == cloud_login.OK
                                        else None))
        busy = self.worker is not None
        for button in self.buttons():
            button.setEnabled(not busy)

    def _start(self, fn, fallback, done_text, wait_text):
        if self.worker is not None:
            return
        worker = CallWorker(fn, fallback, self)
        worker.done.connect(lambda _r: self.message.emit(done_text, False))
        worker.failed.connect(lambda text: self.message.emit(text, True))
        worker.finished.connect(self._finished)
        self.worker = worker
        self.refresh()
        self.message.emit(wait_text, False)
        worker.start()

    def _finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.refresh()
        self.changed.emit()

    def stop(self):
        """Al cerrar el panel: suelta el canje de Dropbox en curso sin esperarlo."""
        worker, self.worker = self.worker, None
        detach(worker)

    def start_dropbox(self):
        try:
            self._flow, url = cloud_login.dropbox_start(self.dbx_app_key.text())
        except cloud_login.LoginError as exc:
            self.message.emit(str(exc), True)
            return
        QDesktopServices.openUrl(QUrl(url))
        self.message.emit('Autorizá en el navegador y pegá el código.', False)

    def finish_dropbox(self):
        flow, app_key, code = self._flow, self.dbx_app_key.text(), self.dbx_code.text()
        self.dbx_code.clear()
        if flow is None:
            self.message.emit('Autorizá Dropbox y pegá el código antes de guardar.', True)
            return
        self.dbx_app_key.clear()
        self._flow = None
        self._start(lambda: cloud_login.dropbox_finish(flow, app_key, code),
                    'No se pudo conectar Dropbox.', 'Dropbox conectado en esta PC.',
                    'Canjeando el código de Dropbox…')

    def finish_dropbox_worker(self):
        """Canjea un código y sube ``KIT_DROPBOX_*`` a todos los Environments, sin el llavero.

        Es otra autorización (otro refresh token) que la de esta PC: revocar una no corta la otra
        y una filtración de GitHub no expone el token de esta PC.
        """
        from core import automation_status as status
        flow, app_key, code = self._flow, self.dbx_app_key.text(), self.dbx_code.text()
        self.dbx_code.clear()
        if flow is None:
            self.message.emit('Autorizá Dropbox y pegá el código antes de subir.', True)
            return
        self.dbx_app_key.clear()
        self._flow = None
        self._start(lambda: status.save_worker_dropbox(
                        cloud_login.dropbox_exchange(flow, app_key, code)),
                    'No se pudo subir Dropbox al worker.', 'Dropbox del worker cargado en GitHub.',
                    'Subiendo Dropbox del worker a GitHub…')

    def forget_dropbox(self):
        try:
            cloud_login.dropbox_forget()
            self.message.emit('Dropbox desconectado de esta PC.', False)
        except cloud_login.LoginError as exc:
            self.message.emit(str(exc), True)
        self.refresh()
        self.changed.emit()

    def check_github(self):
        gh_status.default().invalidate()
        self.refresh()
        self.changed.emit()

    def import_client_secret(self):
        path, _ = QFileDialog.getOpenFileName(self, 'client_secret.json de Google',
                                              str(ROOT), 'JSON (*.json)')
        if not path:
            return
        try:
            cloud_login.import_client_secret(path)
            self.message.emit('client_secret guardado en el llavero. El archivo original no se '
                              'tocó: podés borrarlo.', False)
        except cloud_login.LoginError as exc:
            self.message.emit(str(exc), True)
        self.refresh()
