# -*- coding: utf-8 -*-
"""Pestaña Conexiones del panel de Beats: semáforos, Notion y secretos del canal.

Es un mixin de ``BeatPanelForm``: usa ``self.config`` y ``self.tabs`` del panel. La lógica de
estado vive en ``core/automation_status.py``; aquí solo hay widgets y handlers.
Dropbox y GitHub se conectan por PC (``CloudLoginBox``). El token de YouTube y Notion van
directo a GitHub Secrets por stdin: no se escriben archivos y nunca se muestran valores,
solo «cargado ✓ (fecha)».
"""
from PyQt5.QtWidgets import (
    QFormLayout, QLabel, QLineEdit, QPushButton, QPlainTextEdit,
    QComboBox,
)

from core import automation_status as status
from core.cloud_login_box import CloudLoginBox
from core.connections_mixin import ConnectionsMixin, sanitize_log  # noqa: F401
import ui_theme as theme


def push_beat_channel(channel, slug, token_json=None, log=None, *, config_channels,
                      registry):
    """Sube los secretos del canal con ``gh`` por stdin y agrega el slug a ``BEAT_CHANNELS``.

    Antes comprueba que ``slug`` sea de ``channel`` (config y registro): nunca pisa los
    ``BEAT_*_<SLUG>`` de otro canal. Sin archivos y sin copiar el Dropbox de esta PC.
    """
    from core import gh_status
    from scripts import beat_secrets_sync
    error = status.beat_slug_error(channel, slug, config_channels, registry)
    if error:
        raise status.AutomationError(error)
    gh = gh_status.default()
    lines = []
    try:
        return beat_secrets_sync.push_channel(
            channel, slug, token_json, repo=gh.repo, runner=gh.runner, out=lines.append,
            reader=gh.read)
    finally:
        if log is not None:
            log(lines)


class BeatConnectionsForm(ConnectionsMixin):
    def _build_connections(self, layout):
        """Construye la pestaña Conexiones dentro de ``layout``."""
        self._init_connections()
        self.login_box = CloudLoginBox()
        self.login_box.changed.connect(self.refresh_connections)
        self.login_box.message.connect(lambda text, _err: self.status.setText(text))
        layout.addWidget(self.login_box)

        box, form = theme.section('Canal en la nube', form=True)
        self.conn_channel = QComboBox()
        self.conn_channel.currentIndexChanged.connect(self.refresh_connections)
        form.addRow('Canal de Beats', self.conn_channel)
        self.light_labels = {}
        for key, title in (('youtube', 'YouTube'), ('dropbox', 'Dropbox del robot'),
                           ('notion', 'Notion'), ('gh', 'GitHub')):
            self.light_labels[key] = QLabel()
            form.addRow(title, self.light_labels[key])
        self.connect_youtube_button = QPushButton('Conectar YouTube y subir a GitHub')
        self.connect_youtube_button.clicked.connect(self.connect_youtube)
        self.sync_button = theme.flat(QPushButton('Sincronizar secretos del canal'))
        self.sync_button.clicked.connect(self.sync_secrets)
        form.addRow('', theme.button_row(self.connect_youtube_button, self.sync_button))
        layout.addWidget(box)

        notion_box = theme.Collapsible('Notion (opcional: informes de tendencias)')
        notion = theme.form_layout()
        self.notion_token = QLineEdit()
        self.notion_token.setEchoMode(QLineEdit.Password)
        self.notion_token.setPlaceholderText('Token de la integración de Notion')
        self.notion_page = QLineEdit()
        self.notion_page.setPlaceholderText('ID de página de Notion (32 hex o UUID)')
        notion.addRow('Token', self.notion_token)
        notion.addRow('ID de la página', self.notion_page)
        notion_box.body.addLayout(notion)
        self.save_notion_button = QPushButton('Guardar Notion en GitHub')
        self.save_notion_button.clicked.connect(self.save_notion)
        notion_box.body.addLayout(theme.button_row(self.save_notion_button))
        layout.addWidget(notion_box)

        box, lay = theme.section('Qué falta para publicar')
        self.checklist = QLabel()
        self.checklist.setWordWrap(True)
        lay.addWidget(self.checklist)
        self.conn_log = QPlainTextEdit()
        self.conn_log.setReadOnly(True)
        self.conn_log.setMaximumHeight(110)
        self.conn_log.setPlaceholderText('Acá aparece el detalle de cada conexión.')
        lay.addWidget(self.conn_log)
        layout.addWidget(box)
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

    def refresh_connections(self, *_):
        """Recalcula semáforos y checklist (solo nombres y fechas de secretos, nunca valores)."""
        channel, slug = self._conn_selection()
        names = status.beat_secret_names(slug)
        if names:
            self._set_light('youtube', *status.secrets_badge(names[1:]))
        else:
            self._set_light('youtube', status.UNKNOWN, 'Falta el actions_slug del canal')
        self._set_light('dropbox', *status.secrets_badge(status.KIT_DROPBOX_KEYS))
        self._set_light('notion', *status.secrets_badge(status.NOTION_KEYS))
        gh = status.gh_auth_status()
        self._set_gh_light(gh)
        items = status.readiness_beats(channel, slug)
        self.checklist.setText('<br>'.join(
            ('✔ ' if i['ok'] else '✘ ') + i['label'] for i in items))
        if hasattr(self, 'refresh_publish_readiness'):
            self.refresh_publish_readiness()
        idle = self.conn_worker is None
        ready = bool(channel) and status.valid_slug(slug) and gh == status.OK
        self.connect_youtube_button.setEnabled(ready and idle)
        self.sync_button.setEnabled(ready and idle)
        self.save_notion_button.setEnabled(gh == status.OK and idle)

    def _conn_say(self, text, error=False):
        self.status.setText(text)

    def _slug_guard(self):
        """``(config_channels, registry)`` con los que se valida a qué canal va cada secreto."""
        return list(self.config.get('channels', [])), getattr(self, 'registry', None)

    def connect_youtube(self):
        """OAuth en memoria → confirmar la cuenta → subir el token al secreto del slug."""
        channel, slug = self._conn_selection()
        if not channel or self.conn_worker is not None:
            return
        rows, registry = self._slug_guard()
        error = status.beat_slug_error(channel, slug, rows, registry)
        if error:
            self.status.setText(error)
            return
        expected = next((ch.get('youtube_channel_id') for ch in rows if ch.get('id') == channel),
                        None)
        log = []
        self.conn_log.clear()

        def push(token_json):
            return push_beat_channel(channel, slug, token_json, log=log.extend,
                                     config_channels=rows, registry=registry)

        def pushed(title):
            self._conn_log_lines(log)
            self.pilot_flag_set(channel, 'secrets')
            self.status.setText(f'YouTube conectado ({title}) y cargado en GitHub.' if title
                                else 'YouTube conectado y cargado en GitHub.')
        self._youtube_two_steps(channel, expected, push, pushed)

    def save_notion(self):
        """Sube Notion Beats a GitHub Secrets y limpia los campos."""
        token, page = self.notion_token.text(), self.notion_page.text()
        self.notion_token.clear()
        self.notion_page.clear()
        self._conn_start(lambda: status.save_beat_notion(token, page),
                         'No se pudo guardar Notion en GitHub.', 'Notion cargado en GitHub.',
                         'Guardando Notion en GitHub…')

    def sync_secrets(self):
        """Nombre del canal + ``BEAT_CHANNELS``. El token no se toca."""
        if self.conn_worker is not None:
            return
        channel, slug = self._conn_selection()
        rows, registry = self._slug_guard()
        error = status.beat_slug_error(channel, slug, rows, registry)
        if error:
            self.status.setText(error)
            return
        if status.beat_youtube_status(slug) != status.OK:
            self.status.setText('Conectá YouTube en este canal antes de sincronizar.')
            return
        if status.gh_auth_status() != status.OK:
            self.status.setText('GitHub no está conectado: corré «gh auth login».')
            return
        log = []
        self.conn_log.clear()

        def ok(_slugs):
            self._conn_log_lines(log)
            self.pilot_flag_set(channel, 'secrets')
        self._conn_start(lambda: push_beat_channel(channel, slug, log=log.extend,
                                                   config_channels=rows, registry=registry),
                         'Falló la sincronización.', 'Secretos sincronizados.',
                         'Sincronizando secretos…', ok)
