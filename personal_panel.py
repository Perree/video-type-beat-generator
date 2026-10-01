# -*- coding: utf-8 -*-
"""Panel de la sección Marca personal: acceso al diálogo de clips 9:16."""
import json
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from clip_dialog import ClipDialog

_INTRO = ("Armá clips verticales 9:16 de tu marca personal: Estudio, Loop o Hook.\n"
          "Cada exportación genera el mp4 y un .txt con título y descripción del canal.")


class PersonalPanel(QWidget):
    """Pantalla de Marca personal. Los datos de la app llegan por funciones, sin tocar la UI de beats."""

    def __init__(self, ffmpeg_provider, output_dir_provider, config_path, parent=None):
        super().__init__(parent)
        self._ffmpeg_provider = ffmpeg_provider
        self._output_dir_provider = output_dir_provider
        self._config_path = config_path
        layout = QVBoxLayout(self)
        layout.addStretch(1)
        intro = QLabel(_INTRO)
        intro.setAlignment(Qt.AlignCenter)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        btn = QPushButton("Nuevo clip")
        btn.setMinimumHeight(40)
        btn.setMaximumWidth(260)
        btn.clicked.connect(self.open_clip_dialog)
        layout.addWidget(btn, 0, Qt.AlignHCenter)
        layout.addStretch(1)

    def _channels(self):
        try:
            with open(self._config_path, 'r', encoding='utf-8') as f:
                return json.load(f).get('channels', {})
        except (OSError, ValueError):
            return {}

    def open_clip_dialog(self):
        dialog = ClipDialog(self._ffmpeg_provider(), self._output_dir_provider(),
                            self._channels(), self.window())
        dialog.exec_()
