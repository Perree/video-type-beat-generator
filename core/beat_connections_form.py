# -*- coding: utf-8 -*-
"""Pestaña Conexiones del panel de Beats: semáforos, Notion y sincronización de secretos.

Es un mixin de ``BeatPanelForm``: usa ``self.config`` y ``self.tabs`` del panel. La lógica de
estado vive en ``core/automation_status.py``; aquí solo hay widgets y handlers.
"""
import re
import sys

from PyQt5.QtCore import QProcess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QPlainTextEdit,
)

from core import automation_status as status
from core.automation_status import ROOT, AutomationError
from core.upload_worker import ConnectChannelWorker

SYNC_SCRIPT = 'scripts/beat_secrets_sync.py'
_LIGHTS = {status.OK: ('●', '#2e9e4f', 'Listo'), status.MISSING: ('●', '#c0392b', 'Falta'),
           status.INVALID: ('●', '#d98e04', 'Inválido'), status.UNKNOWN: ('●', '#888888', 'Desconocido')}
_MAX_LOG = 4000


def sanitize_log(text):
    """Deja solo texto imprimible, sin secuencias largas parecidas a tokens, y con tope de tamaño."""
    text = ''.join(c for c in text if c == '\n' or 32 <= ord(c) < 127 or ord(c) > 159)
    text = re.sub(r'[A-Za-z0-9_\-./+=]{40,}', '[oculto]', text)
    return text[:_MAX_LOG]


class BeatConnectionsForm:
    def _build_connections(self, layout):
        """Construye la pestaña Conexiones dentro de ``layout``."""
        self.conn_process = None
        self.conn_worker = None
        form = QFormLayout()
        self.conn_channel = QComboBox()
        self.conn_channel.currentIndexChanged.connect(self.refresh_connections)
        form.addRow('Canal de Beats:', self.conn_channel)
        self.light_labels = {}
        for key, title in (('youtube', 'YouTube'), ('dropbox', 'Dropbox worker'),
                           ('notion', 'Notion Beats'), ('gh', 'GitHub CLI')):
            self.light_labels[key] = QLabel()
            form.addRow(title + ':', self.light_labels[key])
        layout.addLayout(form)

        self.connect_youtube_button = QPushButton('Conectar YouTube')
        self.connect_youtube_button.clicked.connect(self.connect_youtube)
        layout.addWidget(self.connect_youtube_button)

        notion = QFormLayout()
        self.notion_token = QLineEdit()
        self.notion_token.setEchoMode(QLineEdit.Password)
        self.notion_token.setPlaceholderText('Token de la integración de Notion')
        self.notion_page = QLineEdit()
        self.notion_page.setPlaceholderText('ID de página de Notion (32 hex o UUID)')
        notion.addRow('Token de Notion:', self.notion_token)
        notion.addRow('ID de página de Notion:', self.notion_page)
        layout.addLayout(notion)
        self.save_notion_button = QPushButton('Guardar Notion')
        self.save_notion_button.clicked.connect(self.save_notion)
        layout.addWidget(self.save_notion_button)

        self.sync_button = QPushButton('Sincronizar secretos del canal')
        self.sync_button.clicked.connect(self.sync_secrets)
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

    def _conn_channels(self):
        """Canales de Beats del panel: ``[(id, actions_slug o '')]``."""
        return [(ch['id'], ch.get('actions_slug', '')) for ch in self.config.get('channels', [])]

    def reload_connection_channels(self):
        """Repuebla el combo desde la configuración (conserva la selección si sigue existiendo)."""
        current = self.conn_channel.currentText()
        self.conn_channel.blockSignals(True)
        self.conn_channel.clear()
        self.conn_channel.addItems([cid for cid, _ in self._conn_channels()])
        if current:
            self.conn_channel.setCurrentText(current)
        self.conn_channel.blockSignals(False)
        self.refresh_connections()

    def _conn_selection(self):
        """``(canal, slug)`` del nombre visible. ``('', '')`` si ese id ya no está en la config.

        Se busca por texto y no por índice: un combo desactualizado no debe
        apuntar al canal que quedó en esa posición.
        """
        name = self.conn_channel.currentText()
        for cid, slug in self._conn_channels():
            if cid == name:
                return cid, slug
        return '', ''

    def _set_light(self, key, code):
        symbol, color, text = _LIGHTS[code]
        self.light_labels[key].setText(f'<span style="color:{color}">{symbol}</span> {text}')

    def refresh_connections(self, *_):
        """Recalcula semáforos y checklist (sin leer el contenido de ningún secreto)."""
        channel, slug = self._conn_selection()
        self._set_light('youtube', status.youtube_token_status(channel))
        self._set_light('dropbox', status.dropbox_worker_status())
        self._set_light('notion', status.beat_notion_status())
        self._set_light('gh', status.gh_available())
        items = status.readiness_beats(channel, slug)
        self.checklist.setText('<br>'.join(
            ('✔ ' if i['ok'] else '✘ ') + i['label'] for i in items))
        if hasattr(self, 'refresh_publish_readiness'):
            self.refresh_publish_readiness()
        self.connect_youtube_button.setEnabled(bool(channel) and self.conn_worker is None)

    def connect_youtube(self):
        """Abre el OAuth de YouTube del canal elegido en un hilo (reusa ConnectChannelWorker)."""
        channel, _ = self._conn_selection()
        if not channel or self.conn_worker is not None:
            return
        self.connect_youtube_button.setEnabled(False)
        self.conn_worker = ConnectChannelWorker(channel, self)
        self.conn_worker.finished_ok.connect(lambda *_: self._youtube_done('YouTube conectado.'))
        self.conn_worker.failed.connect(lambda *_: self._youtube_done('No se pudo conectar YouTube.'))
        self.conn_worker.finished.connect(self._youtube_finished)
        self.conn_worker.start()
        self.status.setText('Esperando la autorización en el navegador…')

    def _youtube_done(self, message):
        self.status.setText(message)  # el error del SDK no se muestra: puede incluir datos sensibles

    def _youtube_finished(self):
        worker, self.conn_worker = self.conn_worker, None
        worker.deleteLater()
        self.refresh_connections()

    def save_notion(self):
        """Guarda Notion Beats y limpia los campos para no dejar el secreto en pantalla."""
        try:
            status.save_beat_notion(self.notion_token.text(), self.notion_page.text())
            message = 'Notion guardado. Sincronizá los secretos para enviarlo a Actions.'
        except AutomationError as exc:
            message = str(exc)
        self.notion_token.clear()
        self.notion_page.clear()
        self.status.setText(message)
        self.refresh_connections()

    def sync_secrets(self):
        """Lanza beat_secrets_sync.py con QProcess (lista de args, sin shell)."""
        if self.conn_process is not None:
            return
        channel, slug = self._conn_selection()
        if not status.valid_slug(slug):
            self.status.setText('El canal necesita un actions_slug válido para sincronizar.')
            return
        if status.youtube_token_status(channel) != status.OK:
            self.status.setText('Conectá YouTube en este canal antes de sincronizar.')
            return
        if status.gh_available() != status.OK:
            # TODO: instalar GitHub CLI y ejecutar `gh auth login` (acción manual).
            self.status.setText('No se encontró GitHub CLI (gh).')
            return
        proc = QProcess(self)
        proc.setWorkingDirectory(str(ROOT))
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.readyReadStandardOutput.connect(self._sync_output)
        proc.finished.connect(self._sync_finished)
        proc.errorOccurred.connect(self._sync_error)
        self.conn_process = proc
        self._sync_key = channel  # clave de flags del asistente de alta
        self.sync_button.setEnabled(False)
        self.conn_log.clear()
        proc.start(sys.executable, [SYNC_SCRIPT, '--channel', channel, '--slug', slug])
        proc.closeWriteChannel()  # sin stdin: el script no debe quedarse esperando un prompt
        self.status.setText('Sincronizando secretos…')

    def _sync_output(self):
        if self.conn_process is None:
            return
        data = bytes(self.conn_process.readAllStandardOutput()).decode('utf-8', 'replace')
        self.conn_log.appendPlainText(sanitize_log(data).rstrip())

    def _sync_error(self, error):
        # Si no arrancó, no habrá señal finished: se libera el estado a mano.
        if error == QProcess.FailedToStart and self.conn_process is not None:
            self.conn_log.appendPlainText('No se pudo iniciar el proceso de sincronización.')
            self._sync_finished(-1)

    def _sync_finished(self, code, *_):
        proc, self.conn_process = self.conn_process, None
        if proc is None:
            return
        proc.deleteLater()
        self.sync_button.setEnabled(True)
        if code == 0 and getattr(self, '_sync_key', None):
            self.pilot_flag_set(self._sync_key, 'secrets')
        self.status.setText('Secretos sincronizados.' if code == 0 else 'Falló la sincronización; revisá el log.')
        self.refresh_connections()
