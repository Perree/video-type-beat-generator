#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Type Beat Video Generator
-------------------------
Shell mínimo: automatizaciones de Beats y Loop kits (nube) y la pestaña Manual (local).
Canales y plantillas viven en Dropbox (/automatizacion/canales.json); las plantillas de Beats
se editan en la pestaña SEO del panel de Beats.
"""

import os
import sys

from PyQt5.QtWidgets import QApplication, QMainWindow, QStyleFactory, QTabWidget

from core.beat_panel import BeatPanel
from core.manual_panel import ManualPanel
from core.sections import SECTION_BEATS, SECTION_LOOP_KITS
from loop_kit_panel import LoopKitPanel
from ui_theme import APPLICATION_STYLESHEET


class MainWindow(QMainWindow):
    """Ventana principal: pestañas Beats, Loop kits y Manual."""

    def __init__(self):
        super().__init__()
        self.close_pending = False  # lo consulta BeatPanel al terminar una tarea cancelada
        self.setWindowTitle("Type Beat Video Generator")
        self.setMinimumSize(900, 620)
        self.resize(1000, 850)
        self.setStyleSheet(APPLICATION_STYLESHEET)

        self.beat_panel = BeatPanel(self)
        self.loop_kit_panel = LoopKitPanel(self)
        self.manual_panel = ManualPanel(self)
        self._loop_kit_loaded = False

        self.tabs = QTabWidget()
        self.tabs.addTab(self.beat_panel, "Beats")
        self.tabs.addTab(self.loop_kit_panel, "Loop kits")
        self.tabs.addTab(self.manual_panel, "Manual")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

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
        self.manual_panel.shutdown()
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
