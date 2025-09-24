#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diálogo para seleccionar el tipo de contenido (imágenes o videos) antes de la generación.
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QPushButton, QRadioButton, QButtonGroup, QFrame,
                            QGroupBox, QMessageBox)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

try:
    import qtawesome as qta
except ImportError:
    qta = None


class ContentSelectionDialog(QDialog):
    """Diálogo para seleccionar el tipo de contenido antes de generar videos."""
    
    def __init__(self, channel, group, image_count, video_count, beats_count, parent=None):
        super().__init__(parent)
        self.channel = channel
        self.group = group
        self.image_count = image_count
        self.video_count = video_count
        self.beats_count = beats_count
        self.selected_content_type = "images"  # Por defecto
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        self.setWindowTitle("Configurar Generación de Videos")
        self.setFixedSize(500, 400)
        self.setModal(True)
        
        # Aplicar estilos
        self.setStyleSheet("""
            QDialog {
                background-color: #2C3E50;
                color: #ECF0F1;
            }
            QLabel {
                color: #ECF0F1;
                font-size: 14px;
            }
            QRadioButton {
                color: #ECF0F1;
                font-size: 14px;
                padding: 8px;
            }
            QRadioButton::indicator {
                width: 18px;
                height: 18px;
            }
            QRadioButton::indicator:unchecked {
                border: 2px solid #7F8C8D;
                border-radius: 9px;
                background-color: #34495E;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #3498DB;
                border-radius: 9px;
                background-color: #3498DB;
            }
            QGroupBox {
                color: #ECF0F1;
                font-size: 16px;
                font-weight: bold;
                border: 2px solid #34495E;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 15px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
            }
            QPushButton {
                background-color: #34495E;
                color: #ECF0F1;
                border: none;
                padding: 12px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4A6278;
            }
            QPushButton:pressed {
                background-color: #2C3E50;
            }
        """)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(20)
        
        # Título
        title_label = QLabel("🎬 Configurar Generación de Videos")
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Información del canal/grupo
        info_frame = QFrame()
        info_frame.setStyleSheet("QFrame { border: 1px solid #34495E; border-radius: 8px; padding: 10px; }")
        info_layout = QVBoxLayout(info_frame)
        
        info_label = QLabel(f"📁 Canal: {self.channel} / Grupo: {self.group}")
        info_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #3498DB;")
        info_layout.addWidget(info_label)
        
        beats_label = QLabel(f"🎵 Beats a procesar: {self.beats_count}")
        info_layout.addWidget(beats_label)
        
        layout.addWidget(info_frame)
        
        # Información de contenido disponible
        content_group = QGroupBox("📊 Contenido Disponible")
        content_layout = QVBoxLayout(content_group)
        
        # Información de imágenes
        img_info = QLabel(f"🖼️ Imágenes disponibles: {self.image_count} archivos")
        if self.image_count >= self.beats_count:
            img_info.setStyleSheet("color: #27AE60; font-weight: bold;")
        else:
            img_info.setStyleSheet("color: #E74C3C; font-weight: bold;")
        content_layout.addWidget(img_info)
        
        # Información de videos
        vid_info = QLabel(f"🎬 Videos disponibles: {self.video_count} archivos")
        if self.video_count >= self.beats_count:
            vid_info.setStyleSheet("color: #27AE60; font-weight: bold;")
        else:
            vid_info.setStyleSheet("color: #E74C3C; font-weight: bold;")
        content_layout.addWidget(vid_info)
        
        layout.addWidget(content_group)
        
        # Selección de tipo de contenido
        selection_group = QGroupBox("🎯 Tipo de Contenido para Beats")
        selection_layout = QVBoxLayout(selection_group)
        
        self.button_group = QButtonGroup()
        
        self.radio_images = QRadioButton("🖼️ Usar Imágenes Estáticas")
        self.radio_images.setChecked(True)  # Por defecto
        self.radio_images.toggled.connect(self._on_radio_changed)
        if self.image_count == 0:
            self.radio_images.setEnabled(False)
            self.radio_images.setStyleSheet("color: #7F8C8D;")
        
        self.radio_videos = QRadioButton("🎬 Usar Videos Looped")
        self.radio_videos.toggled.connect(self._on_radio_changed)
        if self.video_count == 0:
            self.radio_videos.setEnabled(False)
            self.radio_videos.setStyleSheet("color: #7F8C8D;")
            if self.image_count > 0:
                self.radio_images.setChecked(True)
        elif self.image_count == 0 and self.video_count > 0:
            self.radio_videos.setChecked(True)
            self.radio_images.setChecked(False)
        
        self.button_group.addButton(self.radio_images)
        self.button_group.addButton(self.radio_videos)
        
        selection_layout.addWidget(self.radio_images)
        selection_layout.addWidget(self.radio_videos)
        
        layout.addWidget(selection_group)
        
        # Advertencia si no hay suficiente contenido
        self.warning_label = QLabel()
        self.warning_label.setStyleSheet("color: #E74C3C; font-weight: bold; padding: 10px;")
        self.warning_label.setWordWrap(True)
        self._update_warning()
        layout.addWidget(self.warning_label)
        
        # Botones
        buttons_layout = QHBoxLayout()
        
        btn_cancel = QPushButton("❌ Cancelar")
        btn_cancel.setStyleSheet("background-color: #E74C3C;")
        btn_cancel.clicked.connect(self.reject)
        
        self.btn_continue = QPushButton("✅ Continuar")
        self.btn_continue.setStyleSheet("background-color: #27AE60;")
        self.btn_continue.clicked.connect(self._on_continue)
        
        buttons_layout.addWidget(btn_cancel)
        buttons_layout.addWidget(self.btn_continue)
        
        layout.addLayout(buttons_layout)
        
        # Validar si se puede continuar
        self._validate_selection()
    
    def _on_radio_changed(self):
        """Se ejecuta cuando cambia la selección de radio buttons."""
        if self.radio_images.isChecked():
            self.selected_content_type = "images"
        else:
            self.selected_content_type = "videos"
        
        self._update_warning()
        self._validate_selection()
    
    def _update_warning(self):
        """Actualiza el mensaje de advertencia según la selección."""
        if self.selected_content_type == "images":
            available = self.image_count
            content_name = "imágenes"
        else:
            available = self.video_count
            content_name = "videos"
        
        if available == 0:
            self.warning_label.setText(f"⚠️ No hay {content_name} disponibles en {self.channel}/{self.group}")
        elif available < self.beats_count:
            self.warning_label.setText(f"⚠️ Solo hay {available} {content_name} para {self.beats_count} beats. Se reutilizarán archivos.")
        else:
            self.warning_label.setText(f"✅ Suficientes {content_name} disponibles para generar sin duplicados.")
    
    def _validate_selection(self):
        """Valida si la selección actual permite continuar."""
        if self.selected_content_type == "images":
            can_continue = self.image_count > 0
        else:
            can_continue = self.video_count > 0
        
        self.btn_continue.setEnabled(can_continue)
    
    def _on_continue(self):
        """Se ejecuta al hacer clic en continuar."""
        if self.selected_content_type == "images" and self.image_count == 0:
            QMessageBox.warning(self, "Sin contenido", "No hay imágenes disponibles.")
            return
        
        if self.selected_content_type == "videos" and self.video_count == 0:
            QMessageBox.warning(self, "Sin contenido", "No hay videos disponibles.")
            return
        
        self.accept()
    
    def get_selected_content_type(self):
        """Retorna el tipo de contenido seleccionado."""
        return self.selected_content_type