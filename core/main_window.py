# -*- coding: utf-8 -*-
"""Ventana principal: Inicio → crear videos, mis canales automatizados, conexiones y asistente.

Arma las páginas y las conecta entre sí. La armadura (barra, guía) está en ``core/app_shell.py``.
Las pestañas técnicas de la nube (Beats / Loop kits) quedan en «Modo avanzado» (``core/cloud_page.py``).
"""
from PyQt5.QtWidgets import QMainWindow, QTabWidget

from core.app_shell import AppShell
from core.assistant import AssistantView
from core.beat_panel import BeatPanel
from core.cloud_page import KITS, TAB_CHANNEL, CloudPage
from core.connections_view import ConnectionsView
from core.home_screen import HomeScreen
from core.local_view import LocalView
from core.my_channels import MyChannelsView
from core.sections import SECTION_BEATS, SECTION_LOOP_KITS
from loop_kit_panel import LoopKitPanel
from ui_theme import APPLICATION_STYLESHEET


class MainWindow(QMainWindow):
    def __init__(self, settings_path=None):
        """``settings_path``: preferencias locales (por defecto ``config/manual_mode.json``)."""
        super().__init__()
        settings = {} if settings_path is None else {'settings_path': settings_path}
        self.close_pending = False  # lo consulta BeatPanel al terminar una tarea cancelada
        self.setWindowTitle("Type Beat Video Generator")
        self.setMinimumSize(900, 620)
        self.resize(1100, 850)
        self.setStyleSheet(APPLICATION_STYLESHEET)

        self.beat_panel = BeatPanel(self)
        self.loop_kit_panel = LoopKitPanel(self)
        self.local_view = LocalView(self, **settings)
        self._loop_kit_loaded = False

        self.tabs = QTabWidget()
        self.tabs.addTab(self.beat_panel, "Beats")
        self.tabs.addTab(self.loop_kit_panel, "Loop kits")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.cloud_page = CloudPage(self.tabs, self.beat_panel, self.loop_kit_panel, **settings)
        self.channels = MyChannelsView(self.beat_panel, self.loop_kit_panel, open_kit=self.open_kit,
                                       ensure_kits=self.ensure_kits, open_beat=self.open_beat)
        self.connections = ConnectionsView()
        self.assistant = AssistantView(self.local_view)
        self.assistant.cloud = self.cloud_page
        self.home = HomeScreen()
        self.shell = AppShell(self.home, {
            'local': (self.local_view, 'Crear videos ahora'),
            'channels': (self.channels, 'Mis canales automatizados'),
            'cloud': (self.cloud_page, 'Mis canales — modo avanzado'),
            'assistant': (self.assistant, 'Asistente paso a paso'),
            'connections': (self.connections, 'Conexiones')}, **settings)
        show = self.shell.show_page
        self.home.local_requested.connect(lambda: show('local'))
        self.home.cloud_requested.connect(lambda: show('channels'))
        self.home.assistant_requested.connect(self.open_assistant)
        self.home.connections_requested.connect(lambda: show('connections'))
        self.local_view.assistant_requested.connect(self.open_assistant)
        self.assistant.cloud_requested.connect(lambda: show('cloud'))
        self.cloud_page.assistant_requested.connect(self.resume_assistant)
        self.channels.connections_requested.connect(lambda: show('connections'))
        self.channels.advanced_requested.connect(lambda: show('cloud'))
        self.setCentralWidget(self.shell)

    def open_assistant(self):
        self.assistant.show_goals()
        self.shell.show_page('assistant')

    def resume_assistant(self):
        self.assistant.resume()
        self.shell.show_page('assistant')

    def ensure_kits(self, force=False):
        """Loop kits lee Dropbox: se carga la primera vez que hace falta (o al recargar)."""
        if force or not self._loop_kit_loaded:
            self._loop_kit_loaded = True
            self.loop_kit_panel.reload()

    def open_kit(self, slug):
        """Abre la pestaña de Loop kits en la automatización ``slug``, en «Canal»."""
        combo = self.loop_kit_panel.automation
        index = combo.findData(slug)
        if index >= 0:
            combo.setCurrentIndex(index)
        self.cloud_page.set_kind(KITS)
        self.cloud_page.open_tab(TAB_CHANNEL)
        self.shell.show_page('cloud')

    def open_beat(self, _index):
        """Abre la pestaña de Beats en «Canal» (el canal ya quedó elegido en la lista)."""
        self.cloud_page.set_kind('beats')
        self.cloud_page.open_tab(TAB_CHANNEL)
        self.shell.show_page('cloud')

    def _current_section(self):
        return SECTION_LOOP_KITS if self.tabs.currentWidget() is self.loop_kit_panel else SECTION_BEATS

    def _on_tab_changed(self, _index):
        if self.tabs.currentWidget() is self.loop_kit_panel:
            self.ensure_kits()

    def closeEvent(self, event):
        if self.beat_panel.task is not None:
            self.close_pending = True
            self.beat_panel.cancel()
            event.ignore()
            return
        self.loop_kit_panel.shutdown()
        self.local_view.shutdown()
        self.assistant.shutdown()
        super().closeEvent(event)
