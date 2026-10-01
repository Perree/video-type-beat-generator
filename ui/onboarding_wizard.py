# -*- coding: utf-8 -*-
"""
Wizard de primer uso (cuando no hay canales configurados).
"""
import os
import sys
import json
import subprocess

from PyQt5.QtWidgets import (QDialog, QWidget, QVBoxLayout, QLabel, QPushButton,
                             QLineEdit, QMessageBox, QTabWidget)

from core.config import CONFIG_FILE, DEFAULT_CONFIG


class OnboardingWizard(QDialog):
    """Wizard de 3 pasos para nuevos usuarios (sin canales configurados)."""
    
    def __init__(self, parent=None, config_file=None):
        super().__init__(parent)
        self.config_file = config_file or CONFIG_FILE
        self.channel_name = ""
        self.setWindowTitle("Bienvenido - Configura tu primer canal")
        self.setMinimumSize(500, 380)
        self.setModal(True)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.stacked = QTabWidget()
        # Paso 1: Nombre del canal
        step1 = QWidget()
        step1_layout = QVBoxLayout(step1)
        step1_layout.addWidget(QLabel("Paso 1: Crea tu primer canal"))
        step1_layout.addWidget(QLabel("Nombre del canal (ej: tu nombre o marca):"))
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("Ej: MiCanalBeats")
        step1_layout.addWidget(self.channel_edit)
        self.btn_step1 = QPushButton("Crear canal y continuar")
        self.btn_step1.clicked.connect(self._on_step1_next)
        step1_layout.addWidget(self.btn_step1)
        step1_layout.addStretch()
        self.stacked.addTab(step1, "1. Canal")
        
        # Paso 2: Subir contenido
        step2 = QWidget()
        step2_layout = QVBoxLayout(step2)
        step2_layout.addWidget(QLabel("Paso 2: Contenido visual"))
        step2_layout.addWidget(QLabel("Sube al menos 10 imágenes o 5 videos para este canal.\nAbre la carpeta y agrega los archivos, luego continúa."))
        self.btn_open_content = QPushButton("Abrir carpeta de contenido")
        self.btn_open_content.clicked.connect(self._open_content_folder)
        step2_layout.addWidget(self.btn_open_content)
        self.btn_step2 = QPushButton("Continuar")
        self.btn_step2.clicked.connect(self._on_step2_next)
        step2_layout.addWidget(self.btn_step2)
        step2_layout.addStretch()
        self.stacked.addTab(step2, "2. Contenido")
        
        # Paso 3: Listo
        step3 = QWidget()
        step3_layout = QVBoxLayout(step3)
        step3_layout.addWidget(QLabel("Paso 3: Generar videos"))
        step3_layout.addWidget(QLabel("Ya puedes cargar beats (recomendado: 10), asignarlos a tu canal y pulsar GENERAR VIDEOS.\n\n¡Listo para publicar en minutos!"))
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        step3_layout.addWidget(self.btn_close)
        step3_layout.addStretch()
        self.stacked.addTab(step3, "3. Listo")
        
        layout.addWidget(self.stacked)
    
    def _on_step1_next(self):
        name = self.channel_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nombre vacío", "Escribe el nombre de tu canal.")
            return
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            config = DEFAULT_CONFIG.copy()
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config.update(json.load(f))
            channels = config.get('channels', {})
            if not isinstance(channels, dict):
                channels = {}
            if name in channels:
                QMessageBox.information(self, "Canal existente", "Ese canal ya existe. Pasando al paso 2.")
            else:
                channels[name] = {'groups': ['Principal']}
                config['channels'] = channels
                config['last_channel'] = name
                config['last_group'] = 'Principal'
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                os.makedirs(os.path.join("images", name, "Principal"), exist_ok=True)
                os.makedirs(os.path.join("videos", name, "Principal"), exist_ok=True)
            self.channel_name = name
            self.stacked.setCurrentIndex(1)
            self._update_step2_folder()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear el canal: {e}")
    
    def _update_step2_folder(self):
        self._content_folder = os.path.join("images", self.channel_name, "Principal") if self.channel_name else ""
    
    def _open_content_folder(self):
        if not self.channel_name:
            self._on_step1_next()
            if not self.channel_name:
                return
        folder = os.path.join("images", self.channel_name, "Principal")
        os.makedirs(folder, exist_ok=True)
        if os.name == 'nt':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.run(['open', folder])
        else:
            subprocess.run(['xdg-open', folder])
        QMessageBox.information(self, "Carpeta abierta",
            "Agrega aquí al menos 10 imágenes (JPG/PNG) o sube videos en la app después.\nLuego haz clic en Continuar.")
    
    def _on_step2_next(self):
        self.stacked.setCurrentIndex(2)
    
    def run_wizard(self):
        self.stacked.setCurrentIndex(0)
        self.exec()
