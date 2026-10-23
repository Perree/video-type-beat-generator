# -*- coding: utf-8 -*-
"""«Automatizar en la nube»: las pestañas Beats y Loop kits, con su guía y su estado real.

- «Mostrar opciones avanzadas»: sin tildar, se ocultan «SEO y tendencias» y «Avanzado».
- ``readiness()``: el mismo checklist del panel (Dropbox, GitHub, YouTube…) para la guía y el
  asistente. No cambia nada de cómo trabaja el robot.
"""
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from core import automation_status as status
from core import cloud_login
from core.automation_save_bar import BEATS_PILOT_REQUIRED, KITS_PILOT_REQUIRED
from core import manual_render as mr
from core.guide_panel import GuideStep

BEATS, KITS = 'beats', 'kits'
TAB_CONNECTIONS, TAB_CHANNEL, TAB_SEO, TAB_ADVANCED = range(4)
# Requisitos que bloquean «Publicar al robot» (los mismos del panel; Notion, LLM e imagen son opcionales).
REQUIRED = {BEATS: BEATS_PILOT_REQUIRED, KITS: KITS_PILOT_REQUIRED}


class CloudPage(QWidget):
    assistant_requested = pyqtSignal()  # «Volver al asistente»

    def __init__(self, tabs, beat_panel, loop_kit_panel, parent=None, settings_path=mr.SETTINGS_FILE):
        super().__init__(parent)
        self.tabs, self.beat_panel, self.loop_kit_panel = tabs, beat_panel, loop_kit_panel
        self.settings_path = settings_path
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.banner = QFrame()
        self.banner.setStyleSheet('QFrame { background: #3d3410; border: 1px solid #f1c40f; border-radius: 6px; }'
                                  ' QLabel { border: none; background: transparent; }')
        banner = QHBoxLayout(self.banner)
        self.banner_text = QLabel('🧭 Estás siguiendo el asistente. Hacé lo que te pidió acá y después volvé.')
        self.banner_text.setWordWrap(True)
        banner.addWidget(self.banner_text, 1)
        back = QPushButton('← Volver al asistente')
        back.clicked.connect(self._back_to_assistant)
        banner.addWidget(back)
        self.banner.setVisible(False)
        layout.addWidget(self.banner)

        top = QHBoxLayout()
        top.addStretch()
        self.advanced = QCheckBox('Mostrar opciones avanzadas (SEO y tendencias, Avanzado)')
        self.advanced.setChecked(bool(mr.load_settings(settings_path).get('cloud_advanced')))
        self.advanced.toggled.connect(self.set_advanced)
        top.addWidget(self.advanced)
        layout.addLayout(top)
        layout.addWidget(tabs, 1)
        self.set_advanced(self.advanced.isChecked(), save=False)

    # --- Opciones avanzadas ---

    def _inner(self, panel):
        return getattr(panel, 'tabs', None) if isinstance(getattr(panel, 'tabs', None), QTabWidget) else None

    def set_advanced(self, on, save=True):
        for panel in (self.beat_panel, self.loop_kit_panel):
            inner = self._inner(panel)
            if inner is None:
                continue
            for index in (TAB_SEO, TAB_ADVANCED):
                if index < inner.count():
                    inner.setTabVisible(index, on)
            if not on and inner.currentIndex() in (TAB_SEO, TAB_ADVANCED):
                inner.setCurrentIndex(TAB_CONNECTIONS)
        if save:
            settings = mr.load_settings(self.settings_path)
            settings['cloud_advanced'] = bool(on)
            try:
                mr.save_settings(settings, self.settings_path)
            except OSError:
                pass

    # --- Navegación ---

    def kind(self):
        return KITS if self.tabs.currentWidget() is self.loop_kit_panel else BEATS

    def panel(self):
        return self.loop_kit_panel if self.kind() == KITS else self.beat_panel

    def set_kind(self, kind):
        self.tabs.setCurrentWidget(self.loop_kit_panel if kind == KITS else self.beat_panel)

    def open_tab(self, index):
        """Abre la subpestaña ``index`` del panel actual (las avanzadas se muestran si hace falta)."""
        inner = self._inner(self.panel())
        if inner is None or index >= inner.count():
            return
        if index in (TAB_SEO, TAB_ADVANCED) and not self.advanced.isChecked():
            self.advanced.setChecked(True)
        inner.setCurrentIndex(index)

    def show_banner(self, text=None):
        if text:
            self.banner_text.setText(f'🧭 {text}')
        self.banner.setVisible(True)

    def _back_to_assistant(self):
        self.banner.setVisible(False)
        self.assistant_requested.emit()

    # --- Estado real (mismo checklist que el panel) ---

    def channel_and_slug(self):
        if self.kind() == KITS:
            panel = self.loop_kit_panel
            channel = (panel.channel.currentText() or '').strip() if hasattr(panel, 'channel') else ''
            slug = panel.automation.currentData() or '' if hasattr(panel, 'automation') else ''
            return channel, slug
        panel = self.beat_panel
        channel = panel.channel.currentText() if hasattr(panel, 'channel') else ''
        selected = getattr(panel, 'selected', -1)
        channels = getattr(panel, 'config', {}).get('channels', [])
        slug = channels[selected].get('actions_slug', '') if 0 <= selected < len(channels) else ''
        return channel, slug

    def readiness(self):
        """``{id: ok}`` del checklist del canal actual, más ``pc_dropbox`` (llavero de esta PC)."""
        channel, slug = self.channel_and_slug()
        try:
            items = (status.readiness_kits(channel, slug) if self.kind() == KITS
                     else status.readiness_beats(channel, slug))
        except Exception:  # noqa: BLE001 - sin gh o sin red: todo «falta», nunca rompe la UI
            items = []
        result = {item['id']: item['ok'] for item in items}
        result['pc_dropbox'] = cloud_login.dropbox_status() == cloud_login.OK
        return result

    def missing(self, ids=None):
        state = self.readiness()
        return [i for i in (ids or REQUIRED[self.kind()]) if not state.get(i)]

    # --- Guía ---

    def guide(self):
        ok = lambda key: lambda: bool(self.readiness().get(key))
        channel_key = lambda: 'env' if self.kind() == KITS else 'slug'
        return ('Automatizar en la nube',
                'Un robot en GitHub arma y publica los videos solo. Se configura una vez por canal. '
                'Si preferís ir pantalla por pantalla, usá «🧭 Guiame paso a paso» → «Automatizar un canal».',
                [GuideStep('Conectar Dropbox en esta PC', 'Conexiones → recuadro «Esta PC».', done=ok('pc_dropbox'),
                           action=lambda: self.open_tab(TAB_CONNECTIONS), action_text='Abrir Conexiones'),
                 GuideStep('Conectar GitHub', 'Instalá GitHub CLI y corré «gh auth login» en una terminal; después '
                           '«Revisar».', done=ok('gh'), action=lambda: self.open_tab(TAB_CONNECTIONS),
                           action_text='Abrir Conexiones'),
                 GuideStep('Elegir el canal', 'En «Canal»: qué canal, qué fondos y a qué hora publicar.',
                           done=lambda: bool(self.readiness().get(channel_key())),
                           action=lambda: self.open_tab(TAB_CHANNEL), action_text='Abrir Canal'),
                 GuideStep('Conectar YouTube del canal', 'Conexiones → «Conectar YouTube y subir a GitHub».',
                           done=ok('youtube'), action=lambda: self.open_tab(TAB_CONNECTIONS),
                           action_text='Abrir Conexiones'),
                 GuideStep('Dropbox del robot', 'Conexiones → «Esta PC» → «Subir al worker (GitHub)» con un código '
                           'nuevo de Dropbox.', done=ok('dropbox'), action=lambda: self.open_tab(TAB_CONNECTIONS),
                           action_text='Abrir Conexiones'),
                 GuideStep('Publicar al robot', 'Cuando el checklist de abajo esté completo, apretá «Publicar al '
                           'robot». Desde ahí trabaja solo.')])
