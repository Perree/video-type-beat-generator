# -*- coding: utf-8 -*-
"""Pestaña Conexiones del panel de Loop kits: semáforos, secretos SHARED y sync.

Mixin de ``LoopKitPanel``. El estado vive en ``core/automation_status.py``; acá solo hay
widgets y handlers. La UI nunca muestra valores de secretos: los campos password se
limpian al guardar. Solo se escriben claves SHARED conocidas.
"""
import json
import os
import re
import sys

from PyQt5.QtCore import QProcess, QUrl
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
)

from core import automation_status as status
from core.automation_status import ROOT, AutomationError
from core.upload_worker import ConnectChannelWorker

SYNC_SCRIPT = 'scripts/kit_secrets_sync.py'
_LIGHTS = {status.OK: ('●', '#2e9e4f', 'Listo'), status.MISSING: ('●', '#c0392b', 'Falta'),
           status.INVALID: ('●', '#d98e04', 'Inválido'), status.UNKNOWN: ('●', '#888888', 'Desconocido')}
_MAX_LOG = 4000


def sanitize_log(text):
    """Deja solo texto imprimible, sin secuencias largas parecidas a tokens, y con tope de tamaño."""
    text = ''.join(c for c in text if c == '\n' or 32 <= ord(c) < 127 or ord(c) > 159)
    text = re.sub(r'[A-Za-z0-9_\-./+=]{40,}', '[oculto]', text)
    return text[:_MAX_LOG]


class KitConnectionsForm:
    def _build_connections(self, layout):
        """Construye la pestaña Conexiones dentro de ``layout``."""
        self.conn_process = None
        self.conn_worker = None
        self._dbx_flow = None
        form = QFormLayout()
        self.light_labels = {}
        for key, title in (('youtube', 'YouTube'), ('dropbox', 'Dropbox worker'),
                           ('telegram', 'Telegram'), ('notion', 'Notion Kits'),
                           ('llm', 'LLM (nombres)'), ('image', 'Imágenes (portadas)'),
                           ('gh', 'GitHub CLI')):
            self.light_labels[key] = QLabel()
            form.addRow(title + ':', self.light_labels[key])
        layout.addLayout(form)

        self.telegram = QLabel('')
        self.telegram.setWordWrap(True)
        layout.addWidget(self.telegram)

        self.connect_youtube_button = QPushButton('Conectar YouTube')
        self.connect_youtube_button.clicked.connect(self.connect_youtube)
        layout.addWidget(self.connect_youtube_button)

        dbx = QFormLayout()
        self.dbx_app_key = QLineEdit()
        self.dbx_app_key.setEchoMode(QLineEdit.Password)
        self.dbx_app_key.setPlaceholderText('App key de la app App folder')
        self.dbx_code = QLineEdit()
        self.dbx_code.setEchoMode(QLineEdit.Password)
        self.dbx_code.setPlaceholderText('Código que muestra Dropbox')
        dbx.addRow('App key de Dropbox:', self.dbx_app_key)
        dbx.addRow('Código de Dropbox:', self.dbx_code)
        layout.addLayout(dbx)
        dbx_row = QHBoxLayout()
        self.dbx_start_button = QPushButton('Autorizar Dropbox worker')
        self.dbx_start_button.clicked.connect(self.start_dropbox_worker)
        self.dbx_finish_button = QPushButton('Guardar código de Dropbox')
        self.dbx_finish_button.clicked.connect(self.finish_dropbox_worker)
        dbx_row.addWidget(self.dbx_start_button)
        dbx_row.addWidget(self.dbx_finish_button)
        layout.addLayout(dbx_row)

        tg = QFormLayout()
        self.tg_token = QLineEdit()
        self.tg_token.setEchoMode(QLineEdit.Password)
        self.tg_token.setPlaceholderText('Token del bot')
        self.tg_chat = QLineEdit()
        self.tg_chat.setPlaceholderText('Chat id')
        tg.addRow('Token de Telegram:', self.tg_token)
        tg.addRow('Chat id de Telegram:', self.tg_chat)
        layout.addLayout(tg)
        tg_row = QHBoxLayout()
        self.save_telegram_button = QPushButton('Guardar Telegram')
        self.save_telegram_button.clicked.connect(self.save_telegram)
        self.test_telegram_button = QPushButton('Probar mensaje')
        self.test_telegram_button.clicked.connect(self.test_telegram)
        tg_row.addWidget(self.save_telegram_button)
        tg_row.addWidget(self.test_telegram_button)
        layout.addLayout(tg_row)

        notion = QFormLayout()
        self.kit_notion_token = QLineEdit()
        self.kit_notion_token.setEchoMode(QLineEdit.Password)
        self.kit_notion_token.setPlaceholderText('Token de la integración de Notion')
        self.kit_notion_page = QLineEdit()
        self.kit_notion_page.setPlaceholderText('ID o URL de la página de Notion')
        notion.addRow('Token de Notion:', self.kit_notion_token)
        notion.addRow('Página de Notion:', self.kit_notion_page)
        layout.addLayout(notion)
        self.save_kit_notion_button = QPushButton('Guardar Notion')
        self.save_kit_notion_button.clicked.connect(self.save_kit_notion)
        layout.addWidget(self.save_kit_notion_button)

        keys = QFormLayout()
        self.llm_key = QLineEdit()
        self.llm_key.setEchoMode(QLineEdit.Password)
        self.llm_key.setPlaceholderText('Presente o ausente: no se muestra el valor')
        self.image_key = QLineEdit()
        self.image_key.setEchoMode(QLineEdit.Password)
        self.image_key.setPlaceholderText('Presente o ausente: no se muestra el valor')
        keys.addRow('Clave LLM:', self.llm_key)
        keys.addRow('Clave de imágenes:', self.image_key)
        layout.addLayout(keys)
        self.save_keys_button = QPushButton('Guardar claves LLM / imagen')
        self.save_keys_button.clicked.connect(self.save_llm_image)
        layout.addWidget(self.save_keys_button)

        self.sync_button = QPushButton('Sincronizar secretos del canal')
        self.sync_button.clicked.connect(self.sync_kit_secrets)
        layout.addWidget(self.sync_button)

        layout.addWidget(QLabel('Checklist de preparación'))
        self.checklist = QLabel()
        self.checklist.setWordWrap(True)
        layout.addWidget(self.checklist)
        self.conn_log = QPlainTextEdit()
        self.conn_log.setReadOnly(True)
        self.conn_log.setMaximumHeight(110)
        layout.addWidget(self.conn_log)
        layout.addStretch()

    def _conn_channel_name(self):
        """Nombre del canal de YouTube elegido en la pestaña Canal."""
        return (self.channel.currentText() or '').strip() if hasattr(self, 'channel') else ''

    def _conn_slug(self):
        """Slug de automatización del selector superior (vacío = canal por defecto)."""
        return self.automation.currentData() if hasattr(self, 'automation') else ''

    def _set_light(self, key, code):
        symbol, color, text = _LIGHTS.get(code, _LIGHTS[status.UNKNOWN])
        self.light_labels[key].setText(f'<span style="color:{color}">{symbol}</span> {text}')

    def refresh_connections(self, *_):
        """Recalcula semáforos y checklist (sin leer el contenido de ningún secreto)."""
        if not getattr(self, 'light_labels', None):
            return
        channel = self._conn_channel_name()
        slug = self._conn_slug()
        self._set_light('youtube', status.youtube_token_status(channel))
        self._set_light('dropbox', status.dropbox_worker_status())
        self._set_light('telegram', status.kit_telegram_status())
        self._set_light('notion', status.kit_notion_status())
        self._set_light('llm', status.kit_llm_status())
        self._set_light('image', status.kit_image_status())
        self._set_light('gh', status.gh_available())
        items = status.readiness_kits(channel, slug)
        self.checklist.setText('<br>'.join(
            ('✔ ' if i['ok'] else '✘ ') + i['label'] for i in items))
        if hasattr(self, 'refresh_publish_readiness'):
            self.refresh_publish_readiness()
        self.refresh_telegram()
        busy = self.conn_worker is not None
        self.connect_youtube_button.setEnabled(bool(channel) and not busy)
        tg_ok = status.kit_telegram_status() == status.OK
        self.test_telegram_button.setEnabled(tg_ok and self._task is None)

    def refresh_telegram(self):
        """Texto de estado de Telegram: configurado o no, nunca el token."""
        ok = status.kit_telegram_status() == status.OK
        self.telegram.setText(
            'Configurado en esta PC.' if ok else
            'No configurado en esta PC (el worker usa los secretos de GitHub).')

    def connect_youtube(self):
        """Abre el OAuth de YouTube del canal elegido en un hilo."""
        channel = self._conn_channel_name()
        if not channel or self.conn_worker is not None:
            return
        self.connect_youtube_button.setEnabled(False)
        self.conn_worker = ConnectChannelWorker(channel, self)
        self.conn_worker.finished_ok.connect(lambda *_: self._youtube_done('YouTube conectado.'))
        self.conn_worker.failed.connect(lambda *_: self._youtube_done('No se pudo conectar YouTube.'))
        self.conn_worker.finished.connect(self._youtube_finished)
        self.conn_worker.start()
        self._say('Esperando la autorización en el navegador…')

    def _youtube_done(self, message):
        self._say(message)  # el error del SDK no se muestra: puede incluir datos sensibles

    def _youtube_finished(self):
        worker, self.conn_worker = self.conn_worker, None
        worker.deleteLater()
        self.refresh_connections()

    def start_dropbox_worker(self):
        """Abre el flujo PKCE de ``kit_dropbox_auth`` (misma app App folder)."""
        from core import dropbox_client
        app_key = self.dbx_app_key.text().strip()
        if not app_key:
            self._say('Falta el app key de Dropbox.', error=True)
            return
        try:
            flow, url = dropbox_client.start_auth(app_key)
        except Exception:
            self._say('No se pudo iniciar Dropbox. Revisá el app key.', error=True)
            return
        self._dbx_flow = flow
        QDesktopServices.openUrl(QUrl(url))
        self._say('Autorizá en el navegador y pegá el código.')

    def finish_dropbox_worker(self):
        """Canjea el código y guarda ``tokens/dropbox_worker.json`` (sin imprimir tokens)."""
        from core import dropbox_client, kit_cloud
        flow, app_key = self._dbx_flow, self.dbx_app_key.text().strip()
        code = self.dbx_code.text().strip()
        if flow is None or not app_key or not code:
            self._say('Autorizá Dropbox y pegá el código antes de guardar.', error=True)
            return

        def work():
            # Misma escritura que scripts/kit_dropbox_auth.save_token, en hilo para no congelar.
            dropbox_client.finish_auth(flow, code, token_file=kit_cloud.WORKER_TOKEN_FILE)
            path = kit_cloud.WORKER_TOKEN_FILE
            with open(path, encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or not data.get('refresh_token'):
                raise AutomationError('Dropbox no devolvió un refresh token.')
            data['app_key'] = app_key
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f)

        def done(_):
            self.dbx_app_key.clear()
            self.dbx_code.clear()
            self._dbx_flow = None
            self._say('Dropbox worker conectado.')
            self.refresh_connections()

        self._run(work, done, 'Canjeando el código de Dropbox…')

    def save_telegram(self):
        """Guarda token y chat de Telegram en kit_secrets.json y limpia los campos."""
        try:
            status.save_kit_keys({
                'KIT_TELEGRAM_TOKEN': self.tg_token.text(),
                'KIT_TELEGRAM_CHAT_ID': self.tg_chat.text(),
            })
            message = 'Telegram guardado. Sincronizá los secretos para enviarlo a Actions.'
            err = False
        except AutomationError as exc:
            message, err = str(exc), True
        self.tg_token.clear()
        self.tg_chat.clear()
        self._say(message, error=err)
        self.refresh_connections()

    def test_telegram(self):
        """Manda un mensaje fijo; las credenciales van solo a kit_notify, no a la UI."""
        from core import kit_notify
        if status.kit_telegram_status() != status.OK:
            self._say('Configurá Telegram antes de probar.', error=True)
            return
        env = {**os.environ, **status.read_kit_secrets()}

        def work():
            kit_notify.send('Prueba desde el panel de Loop kits.', env=env)
            return True

        self._run(work, lambda _: self._say('Mensaje de prueba enviado.'),
                  'Enviando prueba de Telegram…')

    def save_kit_notion(self):
        """Guarda Notion Kits y limpia los campos."""
        try:
            status.save_kit_notion(self.kit_notion_token.text(), self.kit_notion_page.text())
            message, err = ('Notion guardado. Sincronizá los secretos para enviarlo a Actions.',
                            False)
        except AutomationError as exc:
            message, err = str(exc), True
        self.kit_notion_token.clear()
        self.kit_notion_page.clear()
        self._say(message, error=err)
        self.refresh_connections()

    def save_llm_image(self):
        """Guarda solo las claves LLM/imagen que el usuario acaba de escribir."""
        updates = {'KIT_LLM_API_KEY': self.llm_key.text(),
                   'KIT_IMAGE_API_KEY': self.image_key.text()}
        try:
            status.save_kit_keys(updates)
            message, err = 'Claves guardadas. Sincronizá los secretos para Actions.', False
        except AutomationError as exc:
            message, err = str(exc), True
        self.llm_key.clear()
        self.image_key.clear()
        self._say(message, error=err)
        self.refresh_connections()

    def sync_kit_secrets(self):
        """Lanza kit_secrets_sync.py con QProcess (lista de args, sin shell)."""
        if self.conn_process is not None:
            return
        channel = self._conn_channel_name()
        env_name = status.kit_env_name(self._conn_slug())
        if not env_name:
            self._say('El canal no tiene un Environment válido.', error=True)
            return
        blockers = status.kit_sync_blockers(channel, self._conn_slug())
        if blockers:
            self._say('Antes de sincronizar: ' + '; '.join(blockers), error=True)
            return
        proc = QProcess(self)
        proc.setWorkingDirectory(str(ROOT))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._sync_output)
        proc.finished.connect(self._sync_finished)
        proc.errorOccurred.connect(self._sync_error)
        self.conn_process = proc
        self._sync_key = self._conn_slug() or ''  # clave de flags del asistente de alta
        self.sync_button.setEnabled(False)
        self.conn_log.clear()
        proc.start(sys.executable, [SYNC_SCRIPT, '--env', env_name, '--channel', channel,
                                    '--no-prompt'])
        proc.closeWriteChannel()
        self._say('Sincronizando secretos…')

    def _sync_output(self):
        if self.conn_process is None:
            return
        data = bytes(self.conn_process.readAllStandardOutput()).decode('utf-8', 'replace')
        self.conn_log.appendPlainText(sanitize_log(data).rstrip())

    def _sync_error(self, error):
        if error == QProcess.FailedToStart and self.conn_process is not None:
            self.conn_log.appendPlainText('No se pudo iniciar el proceso de sincronización.')
            self._sync_finished(-1)

    def _sync_finished(self, code, *_):
        proc, self.conn_process = self.conn_process, None
        if proc is None:
            return
        proc.deleteLater()
        self.sync_button.setEnabled(True)
        if code == 0:
            self.pilot_flag_set(getattr(self, '_sync_key', ''), 'secrets')
        self._say('Secretos sincronizados.' if code == 0 else
                  'Falló la sincronización; revisá el log.', error=code != 0)
        self.refresh_connections()
