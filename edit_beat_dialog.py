#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diálogo para editar el nombre personalizado de un beat.
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                            QPushButton, QFormLayout)
import os

class EditBeatNameDialog(QDialog):
    """Diálogo para editar el nombre personalizado de un beat."""
    
    def __init__(self, beat_info, parent=None):
        super().__init__(parent)
        self.beat_info = beat_info
        self.custom_name = beat_info.get('custom_name', '')
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        self.setWindowTitle("Personalizar nombre del video")
        self.setFixedSize(500, 200)
        
        layout = QVBoxLayout()
        
        # Información del beat
        info_layout = QFormLayout()
        
        # Nombre original del archivo
        original_name = self.beat_info['audio']
        base_name, _ = os.path.splitext(original_name)
        
        info_layout.addRow("Archivo de audio:", QLabel(original_name))
        info_layout.addRow("Género:", QLabel(self.beat_info['genre']))
        
        layout.addLayout(info_layout)
        
        # Explicación
        layout.addWidget(QLabel("Ingrese un nombre personalizado para el video final:"))
        layout.addWidget(QLabel("(Si lo deja vacío, se usará el formato predeterminado: nombre_beat_género)"))
        
        # Campo de texto para el nombre personalizado
        self.name_input = QLineEdit()
        if self.custom_name:
            self.name_input.setText(self.custom_name)
        else:
            self.name_input.setPlaceholderText(f"{base_name}_{self.beat_info['genre']}")
        
        layout.addWidget(self.name_input)
        
        # Botones
        btn_layout = QHBoxLayout()
        
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_save = QPushButton("Guardar")
        self.btn_save.clicked.connect(self._save_name)
        self.btn_save.setDefault(True)
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def _save_name(self):
        """Guarda el nombre personalizado."""
        self.custom_name = self.name_input.text().strip()
        self.accept()
