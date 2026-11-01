# -*- coding: utf-8 -*-
"""Pestaña Conexiones del panel de Loop kits: semáforos, secretos SHARED y Environment.

Mixin de ``LoopKitPanel``. El estado vive en ``core/automation_status.py``; acá solo hay
widgets y handlers. Dropbox y GitHub se conectan por PC (``CloudLoginBox``). El token de
YouTube, Telegram, Notion y las claves van directo a GitHub Secrets por stdin (los
compartidos, una sola vez a ``kit-weekly`` y a cada ``kit-weekly-<slug>``). La UI nunca
muestra valores, solo «cargado ✓ (fecha)»; los campos password se limpian al guardar.
"""
from PyQt5.QtWidgets import (
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton,
)

import ui_theme as theme
from core import automation_status as status
from core.cloud_login_box import CloudLoginBox
from core.connections_mixin import ConnectionsMixin, sanitize_log  # noqa: F401


def push_kit_channel(env_name, channel, token_json=None, log=None, *, default_channel):
    """Crea/usa el Environment y sube ``KIT_YT_*``. Sin archivos.

    ``kit-weekly`` solo acepta al canal por defecto (``default_channel``): el worker no controla
    el dueño de ese Environment. El Dropbox de esta PC nunca se copia al worker.
    """
    from core import gh_status
    from scripts import kit_secrets_sync
    gh = gh_status.default()
    lines = []
    try:
        return kit_secrets_sync.push_channel(
            env_name, channel, token_json, repo=gh.repo, runner=gh.runner, out=lines.append,
            default_channel=default_channel)
    finally:
        if log is not None:
            log(lines)


class KitConnectionsForm(ConnectionsMixin):
    def _build_connections(self, layout):
        """Construye la pestaña Conexiones dentro de ``layout``."""
        self._init_connections()
        self.login_box = CloudLoginBox()
        self.login_box.changed.connect(self.refresh_connections)
        self.login_box.message.connect(lambda text, err: self._say(text, error=err))
        layout.addWidget(self.login_box)
        self.dbx_start_button = self.login_box.dbx_start_button
        self.dbx_finish_button = self.login_box.dbx_finish_button

        box, form = theme.section('Canal en la nube', form=True)
        self.light_labels = {}
        for key, title in (('youtube', 'YouTube'), ('dropbox', 'Dropbox del robot'),
                           ('telegram', 'Telegram'), ('notion', 'Notion'),
                           ('llm', 'Nombres con IA'), ('image', 'Portadas con IA'),
                           ('gh', 'GitHub')):
            self.light_labels[key] = QLabel()
            form.addRow(title, self.light_labels[key])
        self.telegram = theme.muted(QLabel(''))
        form.addRow('', self.telegram)
        self.connect_youtube_button = QPushButton('Conectar YouTube y subir a GitHub')
        self.connect_youtube_button.clicked.connect(self.connect_youtube)
        self.sync_button = theme.flat(QPushButton('Preparar Environment del canal'))
        self.sync_button.clicked.connect(self.sync_kit_secrets)
        form.addRow('', theme.button_row(self.connect_youtube_button, self.sync_button))
        layout.addWidget(box)

        box, tg = theme.section('Avisos por Telegram (uno solo para todos los canales)', form=True)
        self.tg_token = QLineEdit()
        self.tg_token.setEchoMode(QLineEdit.Password)
        self.tg_token.setPlaceholderText('Token del bot')
        self.tg_chat = QLineEdit()
        self.tg_chat.setPlaceholderText('Chat id')
        tg.addRow('Token del bot', self.tg_token)
        tg.addRow('Chat id', self.tg_chat)
        self.save_telegram_button = QPushButton('Guardar Telegram en GitHub')
        self.save_telegram_button.clicked.connect(self.save_telegram)
        self.test_telegram_button = theme.flat(QPushButton('Probar mensaje'))
        self.test_telegram_button.setToolTip('Usa el token y el chat escritos arriba '
                                             '(GitHub no devuelve los guardados).')
        self.test_telegram_button.clicked.connect(self.test_telegram)
        tg.addRow('', theme.button_row(self.save_telegram_button, self.test_telegram_button))
        layout.addWidget(box)

        extra = theme.Collapsible('Opcionales: Notion y claves de IA')
        notion = theme.form_layout()
        self.kit_notion_token = QLineEdit()
        self.kit_notion_token.setEchoMode(QLineEdit.Password)
        self.kit_notion_token.setPlaceholderText('Token de la integración de Notion')
        self.kit_notion_page = QLineEdit()
        self.kit_notion_page.setPlaceholderText('ID o URL de la página de Notion')
        notion.addRow('Token de Notion', self.kit_notion_token)
        notion.addRow('Página de Notion', self.kit_notion_page)
        extra.body.addLayout(notion)
        self.save_kit_notion_button = QPushButton('Guardar Notion en GitHub')
        self.save_kit_notion_button.clicked.connect(self.save_kit_notion)
        extra.body.addLayout(theme.button_row(self.save_kit_notion_button))
        keys = theme.form_layout()
        self.llm_key = QLineEdit()
        self.llm_key.setEchoMode(QLineEdit.Password)
        self.llm_key.setPlaceholderText('Se sube a GitHub: no se muestra el valor')
        self.image_key = QLineEdit()
        self.image_key.setEchoMode(QLineEdit.Password)
        self.image_key.setPlaceholderText('Se sube a GitHub: no se muestra el valor')
        keys.addRow('Clave de texto (IA)', self.llm_key)
        keys.addRow('Clave de imágenes (IA)', self.image_key)
        extra.body.addLayout(keys)
        self.save_keys_button = QPushButton('Guardar claves en GitHub')
        self.save_keys_button.clicked.connect(self.save_llm_image)
        extra.body.addLayout(theme.button_row(self.save_keys_button))
        layout.addWidget(extra)

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

    def _conn_channel_name(self):
        """Nombre del canal de YouTube elegido en la pestaña Canal."""
        return (self.channel.currentText() or '').strip() if hasattr(self, 'channel') else ''

    def _conn_slug(self):
        """Slug de automatización del selector superior (vacío = canal por defecto)."""
        return self.automation.currentData() if hasattr(self, 'automation') else ''

    def _conn_env(self):
        return status.kit_env_name(self._conn_slug() or '')

    def refresh_connections(self, *_):
        """Recalcula semáforos y checklist (solo nombres y fechas de secretos, nunca valores)."""
        if not getattr(self, 'light_labels', None):
            return
        channel = self._conn_channel_name()
        slug = self._conn_slug()
        env = self._conn_env() or status.ENV
        self._set_light('youtube', *status.secrets_badge(status.KIT_YT_KEYS, env))
        self._set_light('dropbox', *status.shared_badge(status.KIT_DROPBOX_KEYS, env))
        self._set_light('telegram', *status.shared_badge(status.KIT_TELEGRAM_KEYS, env))
        self._set_light('notion', *status.shared_badge(status.KIT_NOTION_KEYS, env))
        self._set_light('llm', *status.shared_badge((status.KIT_LLM_KEY,), env))
        self._set_light('image', *status.shared_badge((status.KIT_IMAGE_KEY,), env))
        gh = status.gh_auth_status()
        self._set_gh_light(gh)
        items = status.readiness_kits(channel, slug)
        self.checklist.setText('<br>'.join(
            ('✔ ' if i['ok'] else '✘ ') + i['label'] for i in items))
        if hasattr(self, 'refresh_publish_readiness'):
            self.refresh_publish_readiness()
        self.refresh_telegram()
        idle = self.conn_worker is None and getattr(self, '_task', None) is None
        ready = gh == status.OK and idle
        self.connect_youtube_button.setEnabled(bool(channel) and bool(self._conn_env()) and ready)
        self.sync_button.setEnabled(bool(channel) and bool(self._conn_env()) and ready)
        for button in (self.save_telegram_button, self.save_kit_notion_button,
                       self.save_keys_button):
            button.setEnabled(ready)
        self.test_telegram_button.setEnabled(idle)

    def refresh_telegram(self):
        """Texto de estado de Telegram: configurado o no, nunca el token."""
        code, text = status.shared_badge(status.KIT_TELEGRAM_KEYS, self._conn_env() or status.ENV)
        self.telegram.setText(f'Configurado en GitHub para todos los canales: {text}.' if code == status.OK
                              else 'No configurado en GitHub (el robot no podrá avisar).')

    def _conn_say(self, text, error=False):
        self._say(text, error=error)

    def _default_channel(self):
        """Dueño de ``kit-weekly`` según lo guardado en Dropbox (no lo editado en el formulario)."""
        return status.kit_default_channel(getattr(self, '_registry', None),
                                          getattr(self, '_base_config', None))

    def _env_error(self, env_name, channel):
        """Mensaje si los secretos de ``channel`` irían a un Environment ajeno; si no, None."""
        from scripts import kit_secrets_sync
        default = self._default_channel()
        if env_name == status.ENV and default is None:
            return ('No se sabe cuál es el canal por defecto de kit-weekly: recargá desde '
                    'Dropbox y reintentá.')
        try:
            kit_secrets_sync.check_channel_env(env_name, channel, default)
        except Exception as exc:  # noqa: BLE001 - SyncError o KitChannelError, sin valores
            return str(exc)
        return None

    def connect_youtube(self):
        """OAuth en memoria → confirmar la cuenta → subir a ``KIT_YT_TOKEN_JSON`` del Environment."""
        channel, env_name, key = self._conn_channel_name(), self._conn_env(), self._conn_slug() or ''
        if not channel or not env_name or self.conn_worker is not None:
            return
        error = self._env_error(env_name, channel)
        if error:
            self._say(error, error=True)
            return
        default = self._default_channel()
        log = []
        self.conn_log.clear()

        def push(token_json):
            return push_kit_channel(env_name, channel, token_json, log=log.extend,
                                    default_channel=default)

        def pushed(title):
            self._conn_log_lines(log)
            self.pilot_flag_set(key, 'secrets')
            self._say(f'YouTube conectado ({title}) y cargado en GitHub.' if title
                      else 'YouTube conectado y cargado en GitHub.')
        self._youtube_two_steps(channel, None, push, pushed)

    def _save_shared(self, updates, fields, wait_text):
        """Sube claves SHARED una vez para todos los canales (repo + Environments) y limpia los campos."""
        for field in fields:
            field.clear()
        self._conn_start(lambda: status.save_kit_keys(updates),
                         'No se pudieron guardar las credenciales en GitHub.',
                         'Guardado en GitHub.', wait_text,
                         lambda _envs: self._say('Guardado en GitHub para todos los canales '
                                                 '(también los que crees después).'))

    def save_telegram(self):
        """Sube token y chat de Telegram a GitHub Secrets."""
        self._save_shared({'KIT_TELEGRAM_TOKEN': self.tg_token.text(),
                           'KIT_TELEGRAM_CHAT_ID': self.tg_chat.text()},
                          (self.tg_token, self.tg_chat), 'Guardando Telegram en GitHub…')

    def test_telegram(self):
        """Manda un mensaje fijo con lo escrito en los campos (no se guarda ni se muestra)."""
        from core import kit_notify
        values = {'KIT_TELEGRAM_TOKEN': self.tg_token.text().strip(),
                  'KIT_TELEGRAM_CHAT_ID': self.tg_chat.text().strip()}
        if status.kit_telegram_status(env=values) != status.OK:
            self._say('Escribí el token y el chat id para probar (GitHub no devuelve los '
                      'guardados).', error=True)
            return

        def work():
            kit_notify.send('Prueba desde el panel de Loop kits.', env=values)
            return True

        self._run(work, lambda _: self._say('Mensaje de prueba enviado.'),
                  'Enviando prueba de Telegram…')

    def save_kit_notion(self):
        """Sube Notion Kits (token + página) a GitHub Secrets."""
        token, page = self.kit_notion_token.text(), self.kit_notion_page.text()
        self.kit_notion_token.clear()
        self.kit_notion_page.clear()
        self._conn_start(lambda: status.save_kit_notion(token, page),
                         'No se pudo guardar Notion en GitHub.', 'Notion cargado en GitHub.',
                         'Guardando Notion en GitHub…')

    def save_llm_image(self):
        """Sube solo las claves LLM/imagen que el usuario acaba de escribir."""
        self._save_shared({'KIT_LLM_API_KEY': self.llm_key.text(),
                           'KIT_IMAGE_API_KEY': self.image_key.text()},
                          (self.llm_key, self.image_key), 'Guardando claves en GitHub…')

    def sync_kit_secrets(self):
        """Crea el Environment si falta y sube ``KIT_YT_CHANNEL``; informa qué falta en GitHub."""
        if self.conn_worker is not None:
            return
        channel, env_name, key = self._conn_channel_name(), self._conn_env(), self._conn_slug() or ''
        blockers = status.kit_sync_blockers(channel, key)
        if blockers:
            self._say('Antes de sincronizar: ' + '; '.join(blockers), error=True)
            return
        log = []

        def ok(_names):
            self._conn_log_lines(log)
            missing = [i['label'] for i in status.readiness_kits(channel, key)
                       if i['id'] in ('youtube', 'telegram', 'dropbox') and not i['ok']]
            if missing:
                self._say('Environment listo. Falta en GitHub: ' + '; '.join(missing)
                          + '. Cargalo en esta pestaña.', error=True)
            else:
                self.pilot_flag_set(key, 'secrets')
        self.conn_log.clear()
        error = self._env_error(env_name, channel)
        if error:
            self._say(error, error=True)
            return
        default = self._default_channel()
        self._conn_start(lambda: push_kit_channel(env_name, channel, log=log.extend,
                                                  default_channel=default),
                         'Falló la sincronización.', 'Secretos sincronizados.',
                         'Sincronizando secretos…', ok)
