#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thumbnail Configuration Dialog - Diálogo de Configuración de Miniaturas
----------------------------------------------------------------------
Interfaz para configurar templates y opciones de miniaturas por canal.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QComboBox, QPushButton, QCheckBox, QSpinBox,
                            QLineEdit, QGroupBox, QGridLayout, QColorDialog,
                            QFileDialog, QScrollArea, QWidget, QFrame,
                            QSlider, QDoubleSpinBox, QTextEdit, QTabWidget)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap, QFont
import os
from thumbnail_generator import ThumbnailGenerator

class ThumbnailConfigDialog(QDialog):
    """Diálogo para configurar opciones de miniatura antes de la exportación."""
    
    def __init__(self, channels_data, parent=None):
        super().__init__(parent)
        self.channels_data = channels_data
        self.thumbnail_generator = ThumbnailGenerator()
        self.preview_configs = {}  # Configuraciones temporales para preview
        
        self.setWindowTitle("Configuración de Miniaturas")
        self.setModal(True)
        self.resize(800, 600)
        
        self._setup_ui()
        self._load_current_configs()
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        layout = QVBoxLayout(self)
        
        # Título
        title = QLabel("⚙️ Configuración de Miniaturas por Canal")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setStyleSheet("color: #3498DB; margin: 10px 0px;")
        layout.addWidget(title)
        
        # Área de scroll para múltiples canales
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        self.scroll_layout = QVBoxLayout(scroll_widget)
        
        # Configuración global
        self._create_global_config()
        
        # Configuraciones por canal
        self._create_channel_configs()
        
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
        # Botones
        button_layout = QHBoxLayout()
        
        self.preview_btn = QPushButton("🔍 Vista Previa")
        self.preview_btn.clicked.connect(self._show_preview)
        
        self.save_btn = QPushButton("💾 Guardar Configuración")
        self.save_btn.clicked.connect(self._save_configs)
        
        self.apply_btn = QPushButton("✅ Aplicar y Cerrar")
        self.apply_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("❌ Cancelar")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.preview_btn)
        button_layout.addStretch()
        button_layout.addWidget(self.save_btn)
        button_layout.addWidget(self.apply_btn)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def _create_global_config(self):
        """Crea la sección de configuración global."""
        global_group = QGroupBox("🌍 Configuración Global")
        global_layout = QGridLayout(global_group)
        
        # Opción para generar miniaturas
        self.generate_thumbnails_cb = QCheckBox("Generar miniaturas automáticamente")
        self.generate_thumbnails_cb.setChecked(True)
        global_layout.addWidget(self.generate_thumbnails_cb, 0, 0, 1, 2)
        
        # Calidad de miniatura
        global_layout.addWidget(QLabel("Calidad JPEG:"), 1, 0)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(60, 100)
        self.quality_spin.setValue(95)
        self.quality_spin.setSuffix("%")
        global_layout.addWidget(self.quality_spin, 1, 1)
        
        # Carpeta de overlays globales
        global_layout.addWidget(QLabel("Carpeta de Overlays:"), 2, 0)
        overlay_layout = QHBoxLayout()
        self.overlay_folder_edit = QLineEdit("overlays/")
        overlay_browse_btn = QPushButton("📁")
        overlay_browse_btn.clicked.connect(self._browse_overlay_folder)
        overlay_layout.addWidget(self.overlay_folder_edit)
        overlay_layout.addWidget(overlay_browse_btn)
        global_layout.addLayout(overlay_layout, 2, 1)
        
        self.scroll_layout.addWidget(global_group)
    
    def _create_channel_configs(self):
        """Crea las configuraciones específicas por canal."""
        # Obtener canales únicos de los datos
        channels = set()
        for beat_info in self.channels_data.values():
            if beat_info.get('channel'):
                channels.add(beat_info['channel'])
        
        for channel in sorted(channels):
            self._create_channel_config_section(channel)
    
    def _create_channel_config_section(self, channel):
        """Crea una sección de configuración para un canal específico."""
        channel_group = QGroupBox(f"📺 Canal: {channel}")
        channel_layout = QVBoxLayout(channel_group)
        
        # Tabs para diferentes aspectos de configuración
        tabs = QTabWidget()
        
        # Tab 1: Template básico
        basic_tab = QWidget()
        basic_layout = QGridLayout(basic_tab)
        
        # Selector de template
        basic_layout.addWidget(QLabel("Template:"), 0, 0)
        template_combo = QComboBox()
        templates = self.thumbnail_generator.get_available_templates()
        for template_name, description in templates.items():
            template_combo.addItem(f"{template_name}: {description}", template_name)
        basic_layout.addWidget(template_combo, 0, 1)
        
        # Configuración para template centrado
        centered_group = QGroupBox("Configuración - Imagen Centrada")
        centered_layout = QGridLayout(centered_group)
        
        centered_layout.addWidget(QLabel("Proporción de bordes:"), 0, 0)
        border_slider = QSlider(Qt.Horizontal)
        border_slider.setRange(5, 25)
        border_slider.setValue(10)
        border_label = QLabel("10%")
        border_slider.valueChanged.connect(lambda v: border_label.setText(f"{v}%"))
        
        centered_layout.addWidget(border_slider, 0, 1)
        centered_layout.addWidget(border_label, 0, 2)
        
        basic_layout.addWidget(centered_group, 1, 0, 1, 2)
        tabs.addTab(basic_tab, "🎨 Template")
        
        # Tab 2: Overlay y texto
        overlay_tab = QWidget()
        overlay_layout = QGridLayout(overlay_tab)
        
        # Overlay específico del canal
        overlay_layout.addWidget(QLabel("Overlay PNG:"), 0, 0)
        overlay_path_layout = QHBoxLayout()
        overlay_path_edit = QLineEdit()
        overlay_browse_btn = QPushButton("📁")
        overlay_browse_btn.clicked.connect(
            lambda: self._browse_overlay_file(overlay_path_edit)
        )
        overlay_path_layout.addWidget(overlay_path_edit)
        overlay_path_layout.addWidget(overlay_browse_btn)
        overlay_layout.addLayout(overlay_path_layout, 0, 1)
        
        # Texto personalizado
        overlay_layout.addWidget(QLabel("Texto:"), 1, 0)
        text_edit = QLineEdit()
        text_edit.setPlaceholderText("Ej: BEATS BY {CHANNEL}")
        overlay_layout.addWidget(text_edit, 1, 1)
        
        # Color del texto
        overlay_layout.addWidget(QLabel("Color del texto:"), 2, 0)
        color_btn = QPushButton("🎨 Seleccionar Color")
        color_btn.setStyleSheet("background-color: white; color: black;")
        color_btn.clicked.connect(lambda: self._select_text_color(color_btn))
        overlay_layout.addWidget(color_btn, 2, 1)
        
        # Tamaño del texto
        overlay_layout.addWidget(QLabel("Tamaño del texto:"), 3, 0)
        text_size_spin = QSpinBox()
        text_size_spin.setRange(20, 120)
        text_size_spin.setValue(60)
        text_size_spin.setSuffix(" px")
        overlay_layout.addWidget(text_size_spin, 3, 1)
        
        # Posición del texto
        overlay_layout.addWidget(QLabel("Posición del texto:"), 4, 0)
        text_pos_combo = QComboBox()
        text_pos_combo.addItems([
            "bottom_center", "top_center", "center", 
            "bottom_left", "bottom_right", "top_left", "top_right"
        ])
        overlay_layout.addWidget(text_pos_combo, 4, 1)
        
        tabs.addTab(overlay_tab, "🖼️ Overlay & Texto")
        
        # Tab 3: Configuración avanzada
        advanced_tab = QWidget()
        advanced_layout = QGridLayout(advanced_tab)
        
        # Opción de desenfoque para full cover
        blur_cb = QCheckBox("Aplicar desenfoque (template full_cover)")
        advanced_layout.addWidget(blur_cb, 0, 0, 1, 2)
        
        # Configuración personalizada
        advanced_layout.addWidget(QLabel("Configuración JSON:"), 1, 0)
        config_text = QTextEdit()
        config_text.setMaximumHeight(100)
        config_text.setPlaceholderText('{"border_ratio": 0.1, "custom_param": "value"}')
        advanced_layout.addWidget(config_text, 2, 0, 1, 2)
        
        tabs.addTab(advanced_tab, "⚙️ Avanzado")
        
        channel_layout.addWidget(tabs)
        
        # Guardar referencias para acceso posterior
        setattr(self, f"{channel}_template_combo", template_combo)
        setattr(self, f"{channel}_border_slider", border_slider)
        setattr(self, f"{channel}_overlay_edit", overlay_path_edit)
        setattr(self, f"{channel}_text_edit", text_edit)
        setattr(self, f"{channel}_color_btn", color_btn)
        setattr(self, f"{channel}_text_size", text_size_spin)
        setattr(self, f"{channel}_text_pos", text_pos_combo)
        setattr(self, f"{channel}_blur_cb", blur_cb)
        setattr(self, f"{channel}_config_text", config_text)
        
        self.scroll_layout.addWidget(channel_group)
    
    def _browse_overlay_folder(self):
        """Abre diálogo para seleccionar carpeta de overlays."""
        folder = QFileDialog.getExistingDirectory(
            self, "Seleccionar Carpeta de Overlays"
        )
        if folder:
            self.overlay_folder_edit.setText(folder)
    
    def _browse_overlay_file(self, line_edit):
        """Abre diálogo para seleccionar archivo overlay PNG."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar Overlay PNG", "",
            "Archivos PNG (*.png);;Todos los archivos (*)"
        )
        if file_path:
            line_edit.setText(file_path)
    
    def _select_text_color(self, button):
        """Abre diálogo para seleccionar color del texto."""
        color = QColorDialog.getColor(QColor(255, 255, 255), self)
        if color.isValid():
            button.setStyleSheet(
                f"background-color: {color.name()}; "
                f"color: {'white' if color.lightness() < 128 else 'black'};"
            )
            button.color = color
    
    def _load_current_configs(self):
        """Carga las configuraciones actuales desde el generador."""
        # Cargar configuraciones existentes por canal
        channels = set()
        for beat_info in self.channels_data.values():
            if beat_info.get('channel'):
                channels.add(beat_info['channel'])
        
        for channel in channels:
            config = self.thumbnail_generator.get_channel_config(channel)
            
            # Aplicar configuración al UI
            template_combo = getattr(self, f"{channel}_template_combo", None)
            if template_combo:
                # Buscar y seleccionar el template actual
                for i in range(template_combo.count()):
                    if template_combo.itemData(i) == config['template']:
                        template_combo.setCurrentIndex(i)
                        break
            
            # Aplicar otras configuraciones
            channel_config = config.get('config', {})
            
            # Border ratio
            border_slider = getattr(self, f"{channel}_border_slider", None)
            if border_slider and 'border_ratio' in channel_config:
                border_slider.setValue(int(channel_config['border_ratio'] * 100))
            
            # Overlay path
            overlay_edit = getattr(self, f"{channel}_overlay_edit", None)
            if overlay_edit and 'overlay_path' in channel_config:
                overlay_edit.setText(channel_config['overlay_path'])
            
            # Text
            text_edit = getattr(self, f"{channel}_text_edit", None)
            if text_edit and 'text' in channel_config:
                text_edit.setText(channel_config['text'])
    
    def _show_preview(self):
        """Muestra vista previa de las miniaturas configuradas."""
        # Implementar vista previa
        pass
    
    def _save_configs(self):
        """Guarda las configuraciones actuales."""
        channels = set()
        for beat_info in self.channels_data.values():
            if beat_info.get('channel'):
                channels.add(beat_info['channel'])
        
        for channel in channels:
            # Recopilar configuración del UI
            template_combo = getattr(self, f"{channel}_template_combo", None)
            border_slider = getattr(self, f"{channel}_border_slider", None)
            overlay_edit = getattr(self, f"{channel}_overlay_edit", None)
            text_edit = getattr(self, f"{channel}_text_edit", None)
            color_btn = getattr(self, f"{channel}_color_btn", None)
            text_size = getattr(self, f"{channel}_text_size", None)
            text_pos = getattr(self, f"{channel}_text_pos", None)
            blur_cb = getattr(self, f"{channel}_blur_cb", None)
            
            if not template_combo:
                continue
            
            # Crear configuración
            config = {}
            
            # Border ratio
            if border_slider:
                config['border_ratio'] = border_slider.value() / 100.0
            
            # Overlay
            if overlay_edit and overlay_edit.text().strip():
                config['overlay_path'] = overlay_edit.text().strip()
            
            # Texto
            if text_edit and text_edit.text().strip():
                config['text'] = text_edit.text().strip()
            
            # Color del texto
            if hasattr(color_btn, 'color'):
                color = color_btn.color
                config['text_color'] = (color.red(), color.green(), color.blue(), 255)
            
            # Tamaño del texto
            if text_size:
                config['text_size'] = text_size.value()
            
            # Posición del texto
            if text_pos:
                config['text_position'] = text_pos.currentText()
            
            # Desenfoque
            if blur_cb:
                config['blur_background'] = blur_cb.isChecked()
            
            # Guardar configuración del canal
            template_name = template_combo.currentData()
            self.thumbnail_generator.set_channel_config(channel, template_name, **config)
    
    def get_generation_settings(self):
        """Retorna la configuración para la generación de miniaturas."""
        return {
            'generate_thumbnails': self.generate_thumbnails_cb.isChecked(),
            'quality': self.quality_spin.value(),
            'overlay_folder': self.overlay_folder_edit.text()
        }

class ThumbnailPreviewDialog(QDialog):
    """Diálogo para mostrar vista previa de miniaturas."""
    
    def __init__(self, preview_images, parent=None):
        super().__init__(parent)
        self.preview_images = preview_images
        
        self.setWindowTitle("Vista Previa de Miniaturas")
        self.setModal(True)
        self.resize(1000, 700)
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura la interfaz de vista previa."""
        layout = QVBoxLayout(self)
        
        # Título
        title = QLabel("👀 Vista Previa de Miniaturas")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 14, QFont.Bold))
        layout.addWidget(title)
        
        # Área de scroll para las previsualizaciones
        scroll_area = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        
        # Mostrar previsualizaciones por canal
        for channel, preview_path in self.preview_images.items():
            if os.path.exists(preview_path):
                channel_group = QGroupBox(f"Canal: {channel}")
                channel_layout = QVBoxLayout(channel_group)
                
                # Cargar y mostrar imagen
                pixmap = QPixmap(preview_path)
                if not pixmap.isNull():
                    # Escalar imagen para vista previa
                    scaled_pixmap = pixmap.scaled(640, 360, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    image_label = QLabel()
                    image_label.setPixmap(scaled_pixmap)
                    image_label.setAlignment(Qt.AlignCenter)
                    channel_layout.addWidget(image_label)
                
                scroll_layout.addWidget(channel_group)
        
        scroll_area.setWidget(scroll_widget)
        scroll_area.setWidgetResizable(True)
        layout.addWidget(scroll_area)
        
        # Botón cerrar
        close_btn = QPushButton("Cerrar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
