#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Type Beat Video Generator
-------------------------
Inicio con dos caminos: «Crear videos ahora» (local, ``core/local_view.py``) y «Automatizar en la
nube» (pestañas Beats y Loop kits). La armadura (barra, guía) está en ``core/app_shell.py``.
Canales y plantillas de la nube viven en Dropbox (/automatizacion/canales.json).
"""

import os
import sys

from PyQt5.QtWidgets import QApplication, QMainWindow, QStyleFactory, QTabWidget

from core.app_shell import AppShell
from core.assistant import AssistantView
from core.beat_panel import BeatPanel
from core.cloud_page import CloudPage
from core.connections_view import ConnectionsView
from core.home_screen import HomeScreen
from core.local_view import LocalView
from core.sections import SECTION_BEATS, SECTION_LOOP_KITS
from loop_kit_panel import LoopKitPanel
from ui_theme import APPLICATION_STYLESHEET


class MainWindow(QMainWindow):
    """Ventana principal: Inicio → crear videos (local) o automatizar (nube)."""

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

        self.connections = ConnectionsView()
        self.assistant = AssistantView(self.local_view)
        self.assistant.cloud = self.cloud_page
        self.home = HomeScreen()
        self.shell = AppShell(self.home, {'local': (self.local_view, 'Crear videos ahora'),
                                          'cloud': (self.cloud_page, 'Automatizar en la nube'),
                                          'assistant': (self.assistant, 'Asistente paso a paso'),
                                          'connections': (self.connections, 'Conexiones')}, **settings)
        self.home.local_requested.connect(lambda: self.shell.show_page('local'))
        self.home.cloud_requested.connect(lambda: self.shell.show_page('cloud'))
        self.home.assistant_requested.connect(self.open_assistant)
        self.home.connections_requested.connect(lambda: self.shell.show_page('connections'))
        self.local_view.assistant_requested.connect(self.open_assistant)
        self.assistant.cloud_requested.connect(lambda: self.shell.show_page('cloud'))
        self.cloud_page.assistant_requested.connect(self.resume_assistant)
        self.setCentralWidget(self.shell)

    def open_assistant(self):
        self.assistant.show_goals()
        self.shell.show_page('assistant')

    def resume_assistant(self):
        self.assistant.resume()
        self.shell.show_page('assistant')

    def _current_section(self):
        return SECTION_LOOP_KITS if self.tabs.currentWidget() is self.loop_kit_panel else SECTION_BEATS

    def _on_tab_changed(self, _index):
        # Loop kits lee Dropbox: se carga la primera vez que se abre la pestaña.
        if self.tabs.currentWidget() is self.loop_kit_panel and not self._loop_kit_loaded:
            self._loop_kit_loaded = True
            self.loop_kit_panel.reload()

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


def main():
    """Función principal."""
    # tokens/, config/ e images/ se resuelven relativos al cwd en varios módulos.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
