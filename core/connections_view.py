# -*- coding: utf-8 -*-
"""Pantalla «🔌 Conexiones»: una tarjeta por servicio con su luz y un asistente para configurarlo.

Separa lo necesario para automatizar en la nube de lo opcional. Para crear videos en esta PC no
hace falta ninguna conexión. Los pasos de cada servicio están en ``core/connection_steps.py``.
"""
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QStackedWidget,
                             QVBoxLayout, QWidget)

from core import connection_steps as cs
from core.cloud_worker import CallWorker
from core.guide_panel import GuideStep
from core.wizard import Wizard

_COLORS = {cs.OK: '#2ecc71', cs.MISSING: '#c0392b', cs.UNKNOWN: '#888888'}
_CARD = ('QFrame#card {{ border: 1px solid {border}; border-radius: 10px; background: #333; }}'
         ' QFrame#card QLabel {{ border: none; background: transparent; }}')


class ConnectionCard(QFrame):
    def __init__(self, connection, on_open, parent=None):
        super().__init__(parent)
        self.connection = connection
        self.setObjectName('card')
        layout = QVBoxLayout(self)
        head = QLabel(f'<span style="font-size:20px">{connection.icon}</span>  <b style="font-size:15px">'
                      f'{connection.title}</b>')
        layout.addWidget(head)
        text = QLabel(connection.description)
        text.setWordWrap(True)
        text.setStyleSheet('color: #bbb;')
        layout.addWidget(text, 1)
        row = QHBoxLayout()
        self.light = QLabel()
        row.addWidget(self.light, 1)
        self.button = QPushButton('Configurar')
        self.button.clicked.connect(lambda: on_open(connection))
        row.addWidget(self.button)
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        code = self.connection.status()
        code = code if code in _COLORS else cs.MISSING
        self.light.setText(f'<span style="color:{_COLORS[code]}; font-size:16px">●</span> '
                           f'{self.connection.status_text()}')
        self.button.setText('Cambiar' if code == cs.OK else 'Configurar')
        border = '#2ecc71' if code == cs.OK else '#555'
        self.setStyleSheet(_CARD.format(border=border))


class ConnectionsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.connections = cs.all_connections()
        self.wizard = None
        self.cards = []
        self._checker = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.cards_page = self._build_cards()
        self.stack.addWidget(self.cards_page)
        self.timer = QTimer(self)
        self.timer.setInterval(1500)
        self.timer.timeout.connect(self.refresh)

    def _build_cards(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet('QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }')
        body = QWidget()
        layout = QVBoxLayout(body)
        title = QLabel('Conexiones')
        title.setStyleSheet('font-size: 22px; font-weight: bold;')
        layout.addWidget(title)
        note = QLabel('Para <b>crear videos en esta PC</b> no hace falta ninguna. Para <b>automatizar en la nube</b> '
                      'completá las de arriba en orden; cada una tiene su paso a paso.')
        note.setWordWrap(True)
        layout.addWidget(note)
        self.summary = QLabel()
        self.summary.setStyleSheet('font-size: 14px;')
        layout.addWidget(self.summary)
        for heading, required in (('Necesarias para la nube', True), ('Opcionales', False)):
            label = QLabel(heading)
            label.setStyleSheet('font-size: 15px; font-weight: bold; color: #ddd; margin-top: 8px;')
            layout.addWidget(label)
            grid = QGridLayout()
            group = [c for c in self.connections if c.required == required]
            for index, connection in enumerate(group):
                card = ConnectionCard(connection, self.open)
                card.setMinimumHeight(130)
                self.cards.append(card)
                grid.addWidget(card, index // 3, index % 3)
            layout.addLayout(grid)
        layout.addStretch(1)
        scroll.setWidget(body)
        return scroll

    # --- Estado ---

    def refresh(self):
        for card in self.cards:
            card.refresh()
        required = [c for c in self.connections if c.required]
        done = sum(c.status() == cs.OK for c in required)
        text = f'{done} de {len(required)} conexiones necesarias listas'
        self.summary.setText(text + (' — ¡todo listo para automatizar! ✓' if done == len(required) else ''))

    def check_cloud(self):
        """«Preparar la nube» lee Dropbox: se revisa en segundo plano."""
        if self._checker is not None:
            return
        self._checker = CallWorker(cs.CloudPrep.check, '', self)
        self._checker.finished.connect(self._checked)
        self._checker.start()

    def _checked(self):
        worker, self._checker = self._checker, None
        if worker is not None:
            worker.deleteLater()
        self.refresh()

    def showEvent(self, event):
        self.timer.start()
        self.check_cloud()
        self.refresh()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    # --- Asistente de cada conexión ---

    def connection(self, key):
        return next(c for c in self.connections if c.key == key)

    def open(self, connection):
        if isinstance(connection, str):
            connection = self.connection(connection)
        self.close_wizard()
        self.wizard = Wizard(f'{connection.icon}  {connection.title}', connection.pages(self))
        self.wizard.btn_cancel.setText('← Volver a Conexiones')
        self.wizard.finished.connect(self.close_wizard)
        self.wizard.cancelled.connect(self.close_wizard)
        self.stack.addWidget(self.wizard)
        self.stack.setCurrentWidget(self.wizard)
        return self.wizard

    def wizard_advance(self):
        if self.wizard is not None:
            self.wizard.advance()

    def close_wizard(self):
        if self.wizard is not None:
            self.stack.removeWidget(self.wizard)
            self.wizard.hide()
            self.wizard.deleteLater()
            self.wizard = None
        self.stack.setCurrentWidget(self.cards_page)
        cs.CloudPrep._cache['at'] = 0.0
        self.check_cloud()
        self.refresh()

    def guide(self):
        steps = []
        for connection in self.connections:
            if not connection.required:
                continue
            steps.append(GuideStep(connection.title, connection.description,
                                   done=lambda c=connection: c.status() == cs.OK,
                                   action=lambda c=connection: self.open(c), action_text='Configurar'))
        steps.append(GuideStep('Opcionales', 'Telegram (obligatorio si automatizás Loop kits), Notion e IA.'))
        return ('Conexiones', 'Hacelas en orden, de arriba a abajo. Cada una abre su paso a paso y se tilda sola.',
                steps)
