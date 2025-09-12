#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thumbnail Preview Dialog - Diálogo de Vista Previa de Miniaturas (Versión Simplificada)
---------------------------------------------------------------------------------------
Interfaz para configurar miniaturas con vista previa en tiempo real.
"""

from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                            QComboBox, QPushButton, QCheckBox, QSpinBox,
                            QLineEdit, QGroupBox, QGridLayout, QColorDialog,
                            QFileDialog, QScrollArea, QWidget, QFrame,
                            QSlider, QDoubleSpinBox, QTextEdit, QTabWidget,
                            QSplitter, QMessageBox)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QPixmap, QFont, QPainter
import os
import json
from PIL import Image, ImageDraw, ImageFont
from thumbnail_generator import ThumbnailGenerator
import tempfile

class ThumbnailPreview(QLabel):
    """Widget para mostrar la vista previa de la miniatura."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(400, 225)  # 16:9 aspect ratio
        self.setMaximumSize(640, 360)  # Tamaño máximo
        self.setStyleSheet("""
            QLabel {
                border: 2px solid #444;
                background-color: #2b2b2b;
                border-radius: 8px;
            }
        """)
        self.setAlignment(Qt.AlignCenter)
        self.setText("Vista previa aparecerá aquí")
        self.setScaledContents(True)
    
    def update_preview(self, image_path):
        """Actualiza la vista previa con una nueva imagen."""
        if os.path.exists(image_path):
            pixmap = QPixmap(image_path)
            self.setPixmap(pixmap)
        else:
            self.setText("Error cargando vista previa")

class ThumbnailPreviewDialog(QDialog):
    """Diálogo principal para configurar miniaturas con vista previa."""
    
    def __init__(self, channel_name="", parent=None):
        super().__init__(parent)
        self.channel_name = channel_name
        self.generator = ThumbnailGenerator()
        self.current_config = self._get_default_config()
        self.preview_timer = QTimer()
        self.preview_timer.setSingleShot(True)
        self.preview_timer.timeout.connect(self._update_preview)
        
        self.setWindowTitle(f"Configuración de Miniaturas - {channel_name}")
        self.setModal(True)
        self.resize(900, 700)
        
        self._setup_ui()
        self._load_current_config()
        self._update_preview()
    
    def _setup_ui(self):
        """Configura la interfaz principal."""
        layout = QHBoxLayout(self)
        
        # Panel izquierdo - Configuración
        config_widget = self._create_config_panel()
        
        # Panel derecho - Vista previa
        preview_widget = self._create_preview_panel()
        
        # Splitter para dividir el espacio
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(config_widget)
        splitter.addWidget(preview_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        
        layout.addWidget(splitter)
        
        # Botones inferiores
        buttons_layout = QVBoxLayout()
        button_widget = self._create_buttons()
        buttons_layout.addWidget(button_widget)
        
        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter, 1)
        main_layout.addLayout(buttons_layout)
        
        self.setLayout(main_layout)
    
    def _create_config_panel(self):
        """Crea el panel de configuración."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Scroll area para contenido
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarNever)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        
        # Template selection
        template_group = self._create_template_group()
        content_layout.addWidget(template_group)
        
        # Image settings
        image_group = self._create_image_group()
        content_layout.addWidget(image_group)
        
        # Text settings
        text_group = self._create_text_group()
        content_layout.addWidget(text_group)
        
        content_layout.addStretch()
        scroll.setWidget(content_widget)
        layout.addWidget(scroll)
        
        return widget
    
    def _create_template_group(self):
        """Crea el grupo de selección de template."""
        group = QGroupBox("Template")
        layout = QVBoxLayout(group)
        
        self.template_combo = QComboBox()
        available_templates = self.generator.get_available_templates()
        for template_id, description in available_templates.items():
            self.template_combo.addItem(f"{template_id} - {description}", template_id)
        
        self.template_combo.currentTextChanged.connect(self._on_config_changed)
        layout.addWidget(self.template_combo)
        
        return group
    
    def _create_image_group(self):
        """Crea el grupo de configuración de imagen."""
        group = QGroupBox("Configuración de Imagen")
        layout = QGridLayout(group)
        
        # Background image selector
        layout.addWidget(QLabel("Imagen de fondo:"), 0, 0)
        self.bg_image_edit = QLineEdit()
        self.bg_image_edit.setPlaceholderText("Seleccionar imagen de fondo...")
        self.bg_image_edit.textChanged.connect(self._on_config_changed)
        layout.addWidget(self.bg_image_edit, 0, 1)
        
        bg_browse_btn = QPushButton("📁")
        bg_browse_btn.clicked.connect(self._browse_background_image)
        layout.addWidget(bg_browse_btn, 0, 2)
        
        # Blur background
        self.blur_check = QCheckBox("Desenfocar fondo")
        self.blur_check.toggled.connect(self._on_config_changed)
        layout.addWidget(self.blur_check, 1, 0, 1, 3)
        
        return group
    
    def _create_text_group(self):
        """Crea el grupo de configuración de texto."""
        group = QGroupBox("Configuración de Texto")
        layout = QGridLayout(group)
        
        # Text input
        layout.addWidget(QLabel("Texto:"), 0, 0)
        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Texto para la miniatura...")
        self.text_edit.textChanged.connect(self._on_config_changed)
        layout.addWidget(self.text_edit, 0, 1, 1, 2)
        
        # Text size
        layout.addWidget(QLabel("Tamaño:"), 1, 0)
        self.text_size_spin = QSpinBox()
        self.text_size_spin.setRange(20, 200)
        self.text_size_spin.setValue(60)
        self.text_size_spin.setSuffix(" px")
        self.text_size_spin.valueChanged.connect(self._on_config_changed)
        layout.addWidget(self.text_size_spin, 1, 1)
        
        # Text color
        self.text_color_btn = QPushButton("Color")
        self.text_color_btn.clicked.connect(self._choose_text_color)
        self.text_color = QColor(255, 255, 255)
        self._update_color_button(self.text_color_btn, self.text_color)
        layout.addWidget(self.text_color_btn, 1, 2)
        
        # Text position
        layout.addWidget(QLabel("Posición:"), 2, 0)
        self.text_position_combo = QComboBox()
        self.text_position_combo.addItems([
            "bottom_center", "top_center", "center", 
            "bottom_left", "bottom_right", "top_left", "top_right"
        ])
        self.text_position_combo.currentTextChanged.connect(self._on_config_changed)
        layout.addWidget(self.text_position_combo, 2, 1, 1, 2)
        
        return group
    
    def _create_preview_panel(self):
        """Crea el panel de vista previa."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        
        # Título
        title = QLabel("Vista Previa")
        title.setFont(QFont("Arial", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Preview widget
        self.preview_widget = ThumbnailPreview()
        layout.addWidget(self.preview_widget, 1)
        
        # Preview controls
        controls_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Actualizar")
        refresh_btn.clicked.connect(self._update_preview)
        controls_layout.addWidget(refresh_btn)
        
        save_preview_btn = QPushButton("💾 Guardar Vista Previa")
        save_preview_btn.clicked.connect(self._save_preview)
        controls_layout.addWidget(save_preview_btn)
        
        layout.addLayout(controls_layout)
        
        return widget
    
    def _create_buttons(self):
        """Crea los botones principales del diálogo."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        
        # Botón guardar configuración
        save_config_btn = QPushButton("💾 Guardar Configuración")
        save_config_btn.clicked.connect(self._save_config)
        layout.addWidget(save_config_btn)
        
        layout.addStretch()
        
        # Botones estándar
        cancel_btn = QPushButton("Cancelar")
        cancel_btn.clicked.connect(self.reject)
        layout.addWidget(cancel_btn)
        
        ok_btn = QPushButton("Aceptar")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        layout.addWidget(ok_btn)
        
        return widget
    
    def _get_default_config(self):
        """Retorna la configuración por defecto."""
        return {
            'template': 'centered_image',
            'config': {
                'bg_image_path': '',
                'text': '',
                'text_size': 60,
                'text_color': (255, 255, 255, 255),
                'text_position': 'bottom_center',
                'blur_background': False
            }
        }
    
    def _load_current_config(self):
        """Carga la configuración actual del canal."""
        if self.channel_name:
            config = self.generator.get_channel_config(self.channel_name)
            self.current_config = config
            
            # Actualizar controles con la configuración cargada
            template_index = self.template_combo.findData(config['template'])
            if template_index >= 0:
                self.template_combo.setCurrentIndex(template_index)
            
            cfg = config['config']
            self.bg_image_edit.setText(cfg.get('bg_image_path', ''))
            self.text_edit.setText(cfg.get('text', ''))
            self.text_size_spin.setValue(cfg.get('text_size', 60))
            self.blur_check.setChecked(cfg.get('blur_background', False))
            
            # Text position
            position = cfg.get('text_position', 'bottom_center')
            pos_index = self.text_position_combo.findText(position)
            if pos_index >= 0:
                self.text_position_combo.setCurrentIndex(pos_index)
            
            # Text color
            color_tuple = cfg.get('text_color', (255, 255, 255, 255))
            self.text_color = QColor(color_tuple[0], color_tuple[1], color_tuple[2], color_tuple[3])
            self._update_color_button(self.text_color_btn, self.text_color)
    
    def _on_config_changed(self):
        """Callback cuando cambia la configuración."""
        # Actualizar configuración actual
        self.current_config['template'] = self.template_combo.currentData() or 'centered_image'
        self.current_config['config'].update({
            'bg_image_path': self.bg_image_edit.text(),
            'text': self.text_edit.text(),
            'text_size': self.text_size_spin.value(),
            'text_position': self.text_position_combo.currentText(),
            'blur_background': self.blur_check.isChecked(),
            'text_color': (self.text_color.red(), self.text_color.green(), 
                          self.text_color.blue(), self.text_color.alpha())
        })
        
        # Programar actualización de vista previa
        self.preview_timer.start(500)  # 500ms delay
    
    def _update_preview(self):
        """Actualiza la vista previa de la miniatura."""
        try:
            bg_image_path = self.bg_image_edit.text()
            if not bg_image_path or not os.path.exists(bg_image_path):
                self.preview_widget.setText("Seleccionar imagen de fondo")
                return
            
            # Crear archivo temporal para la vista previa
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as temp_file:
                temp_path = temp_file.name
            
            # Generar miniatura de vista previa
            template_type = self.current_config['template']
            config = self.current_config['config'].copy()
            
            success = self.generator.generate_thumbnail(
                template_type=template_type,
                bg_image_path=bg_image_path,
                output_path=temp_path,
                **config
            )
            
            if success:
                self.preview_widget.update_preview(temp_path)
            else:
                self.preview_widget.setText("Error generando vista previa")
                
        except Exception as e:
            print(f"Error updating preview: {e}")
            self.preview_widget.setText("Error en vista previa")
    
    def _browse_background_image(self):
        """Abre diálogo para seleccionar imagen de fondo."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar imagen de fondo",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            self.bg_image_edit.setText(file_path)
    
    def _choose_text_color(self):
        """Abre diálogo para seleccionar color de texto."""
        color = QColorDialog.getColor(self.text_color, self)
        if color.isValid():
            self.text_color = color
            self._update_color_button(self.text_color_btn, color)
            self._on_config_changed()
    
    def _update_color_button(self, button, color):
        """Actualiza el color del botón."""
        button.setStyleSheet(f"""
            QPushButton {{
                background-color: {color.name()};
                color: {'white' if color.lightness() < 128 else 'black'};
                border: 2px solid #555;
                border-radius: 4px;
                padding: 5px;
            }}
        """)
    
    def _save_preview(self):
        """Guarda la vista previa actual."""
        if hasattr(self.preview_widget, 'pixmap') and self.preview_widget.pixmap():
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Guardar vista previa",
                f"{self.channel_name}_preview.jpg",
                "Imágenes JPEG (*.jpg)"
            )
            
            if file_path:
                self.preview_widget.pixmap().save(file_path)
                QMessageBox.information(self, "Éxito", f"Vista previa guardada en:\n{file_path}")
    
    def _save_config(self):
        """Guarda la configuración actual."""
        if self.channel_name:
            self.generator.set_channel_config(self.channel_name, self.current_config)
            self.generator.save_channel_configs()
            QMessageBox.information(self, "Éxito", "Configuración guardada exitosamente")
    
    def get_config(self):
        """Retorna la configuración actual."""
        return self.current_config

def main():
    """Función principal para testing."""
    import sys
    from PyQt5.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    
    dialog = ThumbnailPreviewDialog("Canal de Prueba")
    if dialog.exec_() == QDialog.Accepted:
        print("Configuración aceptada:", dialog.get_config())
    
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()