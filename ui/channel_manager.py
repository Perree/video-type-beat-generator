# -*- coding: utf-8 -*-
"""
Diálogo para gestionar canales y grupos.
"""
import os
import sys
import json

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QListWidget, QMessageBox, QInputDialog)

from core.config import CONFIG_FILE, DEFAULT_CONFIG


class ChannelManager(QDialog):
    """Diálogo para gestionar canales y grupos."""
    
    def __init__(self, parent=None, config_file=None):
        super().__init__(parent)
        self.config_file = config_file or CONFIG_FILE
        self.setWindowTitle("Gestión de Canales y Grupos")
        self.setModal(True)
        self.setMinimumSize(600, 400)
        self.load_config()
        self.setup_ui()
    
    def load_config(self):
        """Carga la configuración de canales."""
        self.channels_config = {}
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.channels_config = config.get('channels', {})
        except Exception as e:
            print(f"Error cargando configuración: {e}")
    
    def save_config(self):
        """Guarda la configuración de canales."""
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            # Cargar configuración existente
            config = DEFAULT_CONFIG.copy()
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config.update(json.load(f))
            
            # Actualizar canales
            config['channels'] = self.channels_config
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando configuración: {e}")
    
    def setup_ui(self):
        """Configura la interfaz del gestor de canales."""
        layout = QVBoxLayout(self)
        
        # Título
        title = QLabel("📺 Gestión de Canales y Grupos")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        layout.addWidget(title)
        
        # Layout principal
        main_layout = QHBoxLayout()
        
        # Panel izquierdo - Lista de canales
        left_panel = QVBoxLayout()
        left_panel.addWidget(QLabel("Canales:"))
        
        self.channels_list = QListWidget()
        self.channels_list.currentTextChanged.connect(self.on_channel_selected)
        left_panel.addWidget(self.channels_list)
        
        # Botones de canales
        channel_buttons = QHBoxLayout()
        self.btn_add_channel = QPushButton("➕ Agregar Canal")
        self.btn_add_channel.clicked.connect(self.add_channel)
        self.btn_remove_channel = QPushButton("🗑️ Eliminar Canal")
        self.btn_remove_channel.clicked.connect(self.remove_channel)
        
        channel_buttons.addWidget(self.btn_add_channel)
        channel_buttons.addWidget(self.btn_remove_channel)
        left_panel.addLayout(channel_buttons)
        
        # Panel derecho - Grupos del canal seleccionado
        right_panel = QVBoxLayout()
        right_panel.addWidget(QLabel("Grupos:"))
        
        self.groups_list = QListWidget()
        right_panel.addWidget(self.groups_list)
        
        # Botones de grupos
        group_buttons = QHBoxLayout()
        self.btn_add_group = QPushButton("➕ Agregar Grupo")
        self.btn_add_group.clicked.connect(self.add_group)
        self.btn_remove_group = QPushButton("🗑️ Eliminar Grupo")
        self.btn_remove_group.clicked.connect(self.remove_group)
        self.btn_edit_images = QPushButton("🖼️ Editar Imágenes")
        self.btn_edit_images.clicked.connect(self.edit_images)
        
        group_buttons.addWidget(self.btn_add_group)
        group_buttons.addWidget(self.btn_remove_group)
        group_buttons.addWidget(self.btn_edit_images)
        right_panel.addLayout(group_buttons)
        
        # Agregar paneles al layout principal
        main_layout.addLayout(left_panel)
        main_layout.addLayout(right_panel)
        layout.addLayout(main_layout)
        
        # Botones de control
        control_buttons = QHBoxLayout()
        self.btn_ok = QPushButton("✅ Guardar")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("❌ Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        
        control_buttons.addWidget(self.btn_ok)
        control_buttons.addWidget(self.btn_cancel)
        layout.addLayout(control_buttons)
        
        # Cargar datos iniciales
        self.refresh_channels_list()
    
    def refresh_channels_list(self):
        """Actualiza la lista de canales."""
        self.channels_list.clear()
        for channel in sorted(self.channels_config.keys()):
            self.channels_list.addItem(channel)
    
    def on_channel_selected(self, channel_name):
        """Se ejecuta cuando se selecciona un canal."""
        self.groups_list.clear()
        if channel_name and channel_name in self.channels_config:
            groups = self.channels_config[channel_name].get('groups', [])
            for group in groups:
                self.groups_list.addItem(group)
    
    def add_channel(self):
        """Agrega un nuevo canal."""
        channel_name, ok = QInputDialog.getText(self, "Nuevo Canal", "Nombre del canal:")
        if ok and channel_name.strip():
            channel_name = channel_name.strip()
            if channel_name not in self.channels_config:
                self.channels_config[channel_name] = {
                    'groups': ['Principal']  # Grupo por defecto
                }
                self.refresh_channels_list()
                # Crear carpeta del canal
                channel_path = os.path.join("images", channel_name, "Principal")
                os.makedirs(channel_path, exist_ok=True)
            else:
                QMessageBox.warning(self, "Error", f"El canal '{channel_name}' ya existe.")
    
    def remove_channel(self):
        """Elimina el canal seleccionado."""
        current_channel = self.channels_list.currentItem()
        if current_channel:
            channel_name = current_channel.text()
            reply = QMessageBox.question(
                self, "Confirmar", 
                f"¿Eliminar el canal '{channel_name}' y todos sus grupos?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                del self.channels_config[channel_name]
                self.refresh_channels_list()
                self.groups_list.clear()
    
    def add_group(self):
        """Agrega un nuevo grupo al canal seleccionado."""
        current_channel = self.channels_list.currentItem()
        if not current_channel:
            QMessageBox.warning(self, "Error", "Selecciona un canal primero.")
            return
        
        channel_name = current_channel.text()
        group_name, ok = QInputDialog.getText(self, "Nuevo Grupo", "Nombre del grupo:")
        
        if ok and group_name.strip():
            group_name = group_name.strip()
            groups = self.channels_config[channel_name].get('groups', [])
            if group_name not in groups:
                groups.append(group_name)
                self.channels_config[channel_name]['groups'] = groups
                self.on_channel_selected(channel_name)
                # Crear carpeta del grupo
                group_path = os.path.join("images", channel_name, group_name)
                os.makedirs(group_path, exist_ok=True)
            else:
                QMessageBox.warning(self, "Error", f"El grupo '{group_name}' ya existe en este canal.")
    
    def remove_group(self):
        """Elimina el grupo seleccionado."""
        current_channel = self.channels_list.currentItem()
        current_group = self.groups_list.currentItem()
        
        if not current_channel or not current_group:
            QMessageBox.warning(self, "Error", "Selecciona un canal y grupo.")
            return
        
        channel_name = current_channel.text()
        group_name = current_group.text()
        
        reply = QMessageBox.question(
            self, "Confirmar", 
            f"¿Eliminar el grupo '{group_name}' del canal '{channel_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            groups = self.channels_config[channel_name].get('groups', [])
            if group_name in groups:
                groups.remove(group_name)
                self.channels_config[channel_name]['groups'] = groups
                self.on_channel_selected(channel_name)
    
    def edit_images(self):
        """Abre el explorador para editar imágenes del grupo."""
        current_channel = self.channels_list.currentItem()
        current_group = self.groups_list.currentItem()
        
        if not current_channel or not current_group:
            QMessageBox.warning(self, "Error", "Selecciona un canal y grupo.")
            return
        
        channel_name = current_channel.text()
        group_name = current_group.text()
        
        images_path = os.path.join("images", channel_name, group_name)
        os.makedirs(images_path, exist_ok=True)
        
        # Abrir explorador de archivos
        if os.name == 'nt':  # Windows
            os.startfile(images_path)
        elif os.name == 'posix':  # macOS y Linux
            os.system(f'open "{images_path}"' if sys.platform == 'darwin' else f'xdg-open "{images_path}"')
        
        QMessageBox.information(
            self, "Editar Imágenes", 
            f"Se abrió la carpeta: {images_path}\n\n"
            "Agrega imágenes (JPG, JPEG, JFIF, PNG, WebP, GIF, BMP, etc.) a esta carpeta.\n"
            "Se recomiendan 10-30 imágenes por grupo para mayor variedad."
        )
    
    def accept(self):
        """Guarda la configuración al aceptar."""
        self.save_config()
        super().accept()
