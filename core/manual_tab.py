# -*- coding: utf-8 -*-
"""Pestaña «Manual» de la ventana: subpestañas «Arrastrar» y «Tandas por canal»."""
from PyQt5.QtWidgets import QTabWidget

from core.bulk_panel import BulkPanel
from core.manual_panel import ManualPanel


class ManualTab(QTabWidget):
    def __init__(self, parent=None, **panel_kwargs):
        super().__init__(parent)
        self.drag_panel = ManualPanel(self, **panel_kwargs)
        self.bulk_panel = BulkPanel(self.drag_panel, self)
        self.addTab(self.drag_panel, 'Arrastrar')
        self.addTab(self.bulk_panel, 'Tandas por canal')
        self.currentChanged.connect(self._on_changed)

    def _on_changed(self, _index):
        # Al entrar a «Tandas por canal» se revisan las carpetas de entrada.
        if self.currentWidget() is self.bulk_panel and self.bulk_panel.worker is None:
            self.bulk_panel.scan()

    def shutdown(self):
        self.drag_panel.shutdown()
        self.bulk_panel.shutdown()
