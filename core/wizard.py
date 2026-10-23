# -*- coding: utf-8 -*-
"""Asistente genérico: una pantalla por paso, «Atrás» / «Siguiente» y nada más a la vista.

Cada ``WizardPage`` dice si está lista (``ready``) y, si no, qué falta (``blocker``): el botón
«Siguiente» se habilita solo y el aviso explica qué hacer. Lo usan los caminos del asistente
local (``core/assistant.py``) y, más adelante, el de la nube.
"""
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget, QVBoxLayout,
                             QWidget)

from ui_theme import ACCENT_GENERATE, ACCENT_GENERATE_HOVER

_NEXT = (f'QPushButton {{ background: {ACCENT_GENERATE}; color: white; font-size: 15px; font-weight: bold;'
         f' padding: 10px 28px; }} QPushButton:hover {{ background: {ACCENT_GENERATE_HOVER}; }}'
         ' QPushButton:disabled { background: #555; color: #aaa; }')


class WizardPage:
    """Un paso del asistente.

    ``ready()``: True si se puede seguir. ``blocker()``: texto de qué falta (si no está listo).
    ``on_enter()``: al mostrarse. ``on_next()``: al apretar el botón principal; si devuelve False
    el asistente no avanza (p. ej. arrancó una tarea que avanzará sola con ``Wizard.advance``).
    ``busy()``: True mientras corre una tarea (se bloquean los botones).
    ``refresh()``: se llama en cada chequeo periódico (p. ej. para actualizar luces de estado).
    """

    def __init__(self, title, text, widget=None, ready=None, blocker=None, next_text='Siguiente →',
                 on_enter=None, on_next=None, busy=None, can_back=True, refresh=None):
        self.title, self.text, self.next_text = title, text, next_text
        self.widget = widget or QWidget()
        self.ready = ready or (lambda: True)
        self.blocker = blocker or (lambda: '')
        self.on_enter, self.on_next = on_enter, on_next
        self.busy = busy or (lambda: False)
        self.can_back = can_back
        self.refresh = refresh


class Wizard(QWidget):
    finished = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, title, pages, parent=None):
        super().__init__(parent)
        self.pages = list(pages)
        self.index = 0
        layout = QVBoxLayout(self)
        self.flow_title = QLabel(title)
        self.flow_title.setStyleSheet('color: #bbb;')
        layout.addWidget(self.flow_title)
        self.dots = QLabel()
        self.dots.setTextFormat(Qt.RichText)
        layout.addWidget(self.dots)
        self.title = QLabel()
        self.title.setStyleSheet('font-size: 20px; font-weight: bold;')
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.text = QLabel()
        self.text.setWordWrap(True)
        self.text.setStyleSheet('font-size: 14px;')
        layout.addWidget(self.text)
        self.stack = QStackedWidget()
        for page in self.pages:
            self.stack.addWidget(page.widget)
        layout.addWidget(self.stack, 1)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet('color: #f1c40f; font-size: 13px;')
        layout.addWidget(self.hint)
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)
        buttons = QHBoxLayout()
        self.btn_cancel = QPushButton('Salir del asistente')
        self.btn_cancel.clicked.connect(self.cancelled)
        buttons.addWidget(self.btn_cancel)
        buttons.addStretch()
        self.btn_back = QPushButton('← Atrás')
        self.btn_back.clicked.connect(self.back)
        buttons.addWidget(self.btn_back)
        self.btn_next = QPushButton()
        self.btn_next.setStyleSheet(_NEXT)
        self.btn_next.clicked.connect(self.next)
        buttons.addWidget(self.btn_next)
        layout.addLayout(buttons)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.update_state)
        self.go(0)

    def page(self):
        return self.pages[self.index]

    def go(self, index):
        self.index = max(0, min(index, len(self.pages) - 1))
        page = self.page()
        if page.on_enter:
            page.on_enter()
        self.stack.setCurrentWidget(page.widget)
        self.title.setText(page.title)
        self.text.setText(page.text)
        self.text.setVisible(bool(page.text))
        self.update_state()

    def next(self):
        page = self.page()
        if not page.ready() or page.busy():
            return
        if page.on_next and page.on_next() is False:
            self.update_state()
            return
        self.advance()

    def advance(self):
        """Pasa al paso siguiente (o termina si era el último)."""
        if self.index >= len(self.pages) - 1:
            self.finished.emit()
            return
        self.go(self.index + 1)

    def back(self):
        if self.index > 0 and not self.page().busy():
            self.go(self.index - 1)

    def update_state(self):
        page = self.page()
        if page.refresh:
            page.refresh()
        busy, ready = page.busy(), page.ready()
        self.btn_next.setText(page.next_text)
        self.btn_next.setEnabled(ready and not busy)
        self.btn_back.setVisible(self.index > 0 and page.can_back)
        self.btn_back.setEnabled(not busy)
        self.btn_cancel.setEnabled(not busy)
        hint = '' if ready or busy else page.blocker()
        self.hint.setText(f'Para seguir: {hint}' if hint else '')
        self.hint.setVisible(bool(hint))
        total = len(self.pages)
        dots = ' '.join('<span style="color:%s">●</span>' % ('#2ecc71' if i < self.index else
                                                               '#f1c40f' if i == self.index else '#555')
                        for i in range(total))
        self.dots.setText(f'{dots}&nbsp;&nbsp;Paso {self.index + 1} de {total}')

    def showEvent(self, event):
        self.timer.start()
        self.update_state()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)
