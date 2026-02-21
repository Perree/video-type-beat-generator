#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diálogo para editar el nombre personalizado de un beat.
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                            QPushButton, QFormLayout, QFrame)
from PyQt5.QtCore import Qt
import os

try:
    import qtawesome as qta
except ImportError:
    qta = None

class EditBeatNameDialog(QDialog):
    """Diálogo para editar el nombre personalizado de un beat."""
    
    def __init__(self, beat_info=None, parent=None):
        super().__init__(parent)
        # Soportar llamada con (parent) cuando se edita desde la lista sin asignar
        if parent is None and beat_info is not None and not isinstance(beat_info, dict):
            parent, beat_info = beat_info, None
        if beat_info is None:
            beat_info = {'audio': '', 'channel': 'Sin asignar', 'group': '', 'custom_name': ''}
        self.beat_info = beat_info
        self.custom_name = self.beat_info.get('custom_name', '')
        self._setup_ui()
    
    def set_beat_info(self, beat_file, custom_name=''):
        """Asigna archivo y nombre (cuando se abre sin beat_info, ej. desde lista de beats)."""
        self.beat_info['audio'] = self.beat_info.get('beat_file') or beat_file
        self.beat_info['beat_file'] = beat_file
        self.beat_info['custom_name'] = custom_name
        self.custom_name = custom_name
        if hasattr(self, '_file_value'):
            self._file_value.setText(beat_file)
        if hasattr(self, 'name_input'):
            self.name_input.setText(custom_name)
            base_name, _ = os.path.splitext(beat_file)
            channel = self.beat_info.get('channel', '')
            group = self.beat_info.get('group', 'Principal')
            self.name_input.setPlaceholderText(f"{base_name}_{channel}_{group}")
    
    def get_custom_name(self):
        """Devuelve el nombre personalizado introducido."""
        return getattr(self, 'custom_name', '') or (self.name_input.text().strip() if hasattr(self, 'name_input') else '')
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo con estilo moderno."""
        self.setWindowTitle("Personalizar nombre del video")
        self.setFixedSize(600, 300)
        
        # Aplicar estilos
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E2E;
            }
            QLabel {
                color: #CDD6F4;
                font-size: 15px;
                margin: 2px;
                padding: 2px;
            }
            QLineEdit {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 8px;
                font-size: 15px;
                min-height: 30px;
                margin: 4px;
            }
            QPushButton {
                background-color: #89B4FA;
                color: #1E1E2E;
                font-weight: bold;
                padding: 10px 18px;
                border: none;
                border-radius: 6px;
                min-width: 120px;
                min-height: 36px;
                font-size: 14px;
                margin: 4px;
            }
            QPushButton:hover {
                background-color: #B4BEFE;
            }
            QPushButton:pressed {
                background-color: #74C7EC;
            }
            QFrame {
                background-color: #313244;
                border-radius: 8px;
                padding: 15px;
                margin: 5px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Título
        title = QLabel("Personalizar nombre del video")
        title.setStyleSheet("font-size: 18px; color: #89B4FA; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Tarjeta de información
        info_card = QFrame()
        info_card_layout = QFormLayout(info_card)
        
        # Información del beat (soporta 'audio' o 'beat_file')
        original_name = self.beat_info.get('audio') or self.beat_info.get('beat_file', '')
        base_name, _ = os.path.splitext(original_name)
        
        # Nombre del archivo (guardamos referencia por si se llama set_beat_info después)
        file_label = QLabel("Archivo de audio:")
        file_value = QLabel(original_name)
        file_value.setStyleSheet("font-weight: bold;")
        self._file_value = file_value
        info_card_layout.addRow(file_label, file_value)
        
        # Canal
        channel_label = QLabel("Canal:")
        channel_value = QLabel(self.beat_info.get('channel', 'Sin canal asignado'))
        channel_value.setStyleSheet("font-weight: bold;")
        info_card_layout.addRow(channel_label, channel_value)
        
        # Grupo
        group_label = QLabel("Grupo:")
        group_value = QLabel(self.beat_info.get('group', 'Principal'))
        group_value.setStyleSheet("font-weight: bold;")
        info_card_layout.addRow(group_label, group_value)
        
        layout.addWidget(info_card)
        
        # Explicación
        instruct = QLabel("Ingrese un nombre personalizado para el video final:")
        layout.addWidget(instruct)
        
        # Campo de texto para el nombre personalizado
        self.name_input = QLineEdit()
        if self.custom_name:
            self.name_input.setText(self.custom_name)
        else:
            channel = self.beat_info.get('channel', '')
            group = self.beat_info.get('group', 'Principal')
            self.name_input.setPlaceholderText(f"{base_name}_{channel}_{group}")
        
        layout.addWidget(self.name_input)
        
        # Nota
        note = QLabel("(Si lo deja vacío, se usará el formato predeterminado: nombre_beat_canal_grupo)")
        note.setStyleSheet("font-size: 12px; color: #6C7086; font-style: italic;")
        layout.addWidget(note)
        
        # Botones
        btn_layout = QHBoxLayout()
        
        self.btn_cancel = QPushButton("Cancelar")
        if qta:
            self.btn_cancel.setIcon(qta.icon("fa5s.times", color="#1E1E2E"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_save = QPushButton("Guardar")
        if qta:
            self.btn_save.setIcon(qta.icon("fa5s.save", color="#1E1E2E"))
        self.btn_save.clicked.connect(self._save_name)
        self.btn_save.setDefault(True)
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def _save_name(self):
        """Guarda el nombre personalizado."""
        self.custom_name = self.name_input.text().strip()
        self.accept()
