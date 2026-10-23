# -*- coding: utf-8 -*-
"""Armadura de la ventana: barra superior (← Inicio, ? Guía), páginas y guía lateral.

Cada página expone ``guide() -> (título, intro, pasos)``. La guía se abre sola la primera vez
que se usa la app; después, con el botón «? Guía».
"""
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout, QWidget

from core import manual_render as mr
from core.guide_panel import GuidePanel


class AppShell(QWidget):
    def __init__(self, home, pages, settings_path=mr.SETTINGS_FILE, parent=None):
        """``pages``: ``{nombre: (widget, título de la barra)}``; ``home`` es la página inicial."""
        super().__init__(parent)
        self.home, self.pages, self.settings_path = home, pages, settings_path
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        bar = QHBoxLayout()
        self.btn_back = QPushButton('← Inicio')
        self.btn_back.clicked.connect(self.show_home)
        bar.addWidget(self.btn_back)
        self.title = QLabel()
        self.title.setStyleSheet('font-size: 14px; font-weight: bold;')
        bar.addWidget(self.title, 1)
        self.btn_guide = QPushButton('? Guía')
        self.btn_guide.setCheckable(True)
        self.btn_guide.setToolTip('Pasos para usar esta pantalla; se tildan solos.')
        self.btn_guide.toggled.connect(self.set_guide_visible)
        bar.addWidget(self.btn_guide)
        layout.addLayout(bar)

        body = QHBoxLayout()
        self.stack = QStackedWidget()
        self.stack.addWidget(home)
        for widget, _title in pages.values():
            self.stack.addWidget(widget)
        body.addWidget(self.stack, 1)
        self.guide = GuidePanel()
        self.guide.closed.connect(lambda: self.btn_guide.setChecked(False))
        self.guide.setVisible(False)
        body.addWidget(self.guide)
        layout.addLayout(body, 1)

        self.show_home()
        settings = mr.load_settings(settings_path)
        if not settings.get('guide_seen'):
            self.btn_guide.setChecked(True)  # primera vez: guía abierta
            settings['guide_seen'] = True
            try:
                mr.save_settings(settings, settings_path)
            except OSError:
                pass

    def current(self):
        return self.stack.currentWidget()

    def show_home(self):
        self._show(self.home, 'Inicio')

    def show_page(self, name):
        widget, title = self.pages[name]
        self._show(widget, title)

    def _show(self, widget, title):
        self.stack.setCurrentWidget(widget)
        self.title.setText(title)
        self.btn_back.setVisible(widget is not self.home)
        self.guide.set_guide(*widget.guide())

    def set_guide_visible(self, visible):
        self.guide.setVisible(visible)
        if self.btn_guide.isChecked() != visible:
            self.btn_guide.setChecked(visible)
