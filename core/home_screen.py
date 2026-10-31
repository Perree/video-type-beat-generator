# -*- coding: utf-8 -*-
"""Pantalla de Inicio: una sola decisión — hacer videos ahora o automatizar en la nube."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.guide_panel import GuideStep
import ui_theme as theme

COLUMN_WIDTH = 640  # columna central: deja aire a los costados en ventanas anchas


def choice(text, primary=False):
    """Opción grande de dos líneas (qué hace + para qué)."""
    button = QPushButton(text)
    button.setCursor(Qt.PointingHandCursor)
    return theme.set_role(button, 'choice_primary' if primary else 'choice')


def centered_column(parent_layout):
    """Columna central de ancho máximo fijo; devuelve su layout."""
    row = QHBoxLayout()
    row.addStretch(1)
    column = QWidget()
    column.setMaximumWidth(COLUMN_WIDTH)
    layout = QVBoxLayout(column)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(theme.SPACE['m'])
    row.addWidget(column, 100)
    row.addStretch(1)
    parent_layout.addLayout(row)
    return layout


class HomeScreen(QWidget):
    local_requested = pyqtSignal()
    cloud_requested = pyqtSignal()
    assistant_requested = pyqtSignal()
    connections_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        layout = centered_column(outer)
        title = theme.set_role(QLabel('¿Qué querés hacer?'), 'display')
        layout.addWidget(title)
        layout.addWidget(theme.muted(QLabel('Elegí una opción. Podés usar las dos formas de trabajar: no se pisan.')))
        layout.addSpacing(theme.SPACE['s'])
        # A vertical list also fits with the guide open at the minimum window size.
        self.btn_local = choice('🎬   Crear videos ahora\nSoltá beats, elegí el canal y generá los videos.', primary=True)
        self.btn_local.clicked.connect(self.local_requested)
        self.btn_cloud = choice('📡   Mis canales automatizados\nPausá canales, cambiá horarios y revisá qué falta.')
        self.btn_cloud.clicked.connect(self.cloud_requested)
        self.btn_connections = choice('🔌   Conexiones\nConfigurá Dropbox, GitHub y YouTube, paso a paso.')
        self.btn_connections.clicked.connect(self.connections_requested)
        for button in (self.btn_local, self.btn_cloud, self.btn_connections):
            layout.addWidget(button)
        self.btn_assistant = theme.flat(QPushButton('🧭  ¿No sabés por dónde empezar? Guiame paso a paso'))
        self.btn_assistant.clicked.connect(self.assistant_requested)
        layout.addWidget(self.btn_assistant, 0, Qt.AlignLeft)
        outer.addStretch(2)

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
