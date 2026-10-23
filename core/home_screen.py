# -*- coding: utf-8 -*-
"""Pantalla de Inicio: una sola decisión — hacer videos ahora o automatizar en la nube."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.guide_panel import GuideStep
from ui_theme import ACCENT_GENERATE, ACCENT_GENERATE_HOVER

_BIG = ('QPushButton {{ background: {bg}; color: white; font-size: 18px; font-weight: bold; '
        'padding: 28px; border-radius: 10px; text-align: left; }} '
        'QPushButton:hover {{ background: {hover}; }}')


class HomeScreen(QWidget):
    local_requested = pyqtSignal()
    cloud_requested = pyqtSignal()
    assistant_requested = pyqtSignal()
    connections_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        title = QLabel('¿Qué querés hacer?')
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet('font-size: 24px; font-weight: bold;')
        layout.addWidget(title)
        row = QHBoxLayout()
        row.addStretch(1)
        self.btn_local = QPushButton('🎬  Crear videos ahora\n\nSoltás tus beats, elegís\nel canal y tenés los '
                                     'videos\nlistos para subir.')
        self.btn_local.setStyleSheet(_BIG.format(bg=ACCENT_GENERATE, hover=ACCENT_GENERATE_HOVER))
        self.btn_local.clicked.connect(self.local_requested)
        self.btn_cloud = QPushButton('📡  Mis canales\n      automatizados\n\nPausá, cambiá horarios y\n'
                                     'mirá qué falta en cada canal.')
        self.btn_cloud.setStyleSheet(_BIG.format(bg='#2c5d8f', hover='#3a75b0'))
        self.btn_cloud.clicked.connect(self.cloud_requested)
        self.btn_connections = QPushButton('🔌  Conexiones\n\nDropbox, GitHub, YouTube\ny más, paso a paso.\n'
                                           'Hacen falta para la nube.')
        self.btn_connections.setStyleSheet(_BIG.format(bg='#6b4f8f', hover='#8463ad'))
        self.btn_connections.clicked.connect(self.connections_requested)
        for button in (self.btn_local, self.btn_cloud, self.btn_connections):
            button.setMinimumWidth(270)
            row.addWidget(button)
        row.addStretch(1)
        layout.addLayout(row)
        self.btn_assistant = QPushButton('🧭  ¿No sabés por dónde empezar? Guiame paso a paso')
        self.btn_assistant.setStyleSheet('QPushButton { font-size: 15px; padding: 14px; }')
        self.btn_assistant.clicked.connect(self.assistant_requested)
        assistant_row = QHBoxLayout()
        assistant_row.addStretch(1)
        assistant_row.addWidget(self.btn_assistant)
        assistant_row.addStretch(1)
        layout.addLayout(assistant_row)
        tip = QLabel('También tenés «? Guía» arriba a la derecha con los pasos de cada pantalla.')
        tip.setAlignment(Qt.AlignCenter)
        tip.setStyleSheet('color: #bbb;')
        layout.addWidget(tip)
        layout.addStretch(2)

    def guide(self):
        return ('Cómo usar la app',
                'Hay dos formas de trabajar. Podés usar las dos: no se pisan.',
                [GuideStep('Crear videos ahora (en esta PC)',
                           'Para tandas de beats nuevos. Vos subís los videos a YouTube a mano.',
                           action=self.local_requested.emit, action_text='Ir a crear videos'),
                 GuideStep('Mis canales automatizados',
                           'Los canales que un robot publica solo todos los días: pausar, horarios y qué falta.',
                           action=self.cloud_requested.emit, action_text='Ir a Mis canales'),
                 GuideStep('Conexiones', 'Dropbox, GitHub, YouTube y más, cada una con su paso a paso. Hacen '
                           'falta para la nube (no para crear videos en esta PC).',
                           action=self.connections_requested.emit, action_text='Ir a Conexiones'),
                 GuideStep('¿Dudas? Usá el asistente',
                           'Te pregunta qué querés lograr y te lleva pantalla por pantalla.',
                           action=self.assistant_requested.emit, action_text='Abrir asistente')])
