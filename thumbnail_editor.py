#!/usr/bin/env python3
"""
Thumbnail Editor - Versión Unificada
Editor completo de thumbnails para YouTube con todas las características
"""

import sys
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from PIL import Image, ImageQt
import qdarkstyle

# Constantes
YOUTUBE_THUMBNAIL_WIDTH = 1280
YOUTUBE_THUMBNAIL_HEIGHT = 720
SAFE_MARGIN_PERCENT = 0.1

class OverlayItem(QGraphicsPixmapItem):
    """Item de overlay manipulable en el canvas."""
    
    def __init__(self, overlay_path):
        super().__init__()
        self.overlay_path = overlay_path
        self.load_overlay()
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges
        )
        
    def load_overlay(self):
        """Carga el overlay desde archivo."""
        try:
            pixmap = QPixmap(self.overlay_path)
            if not pixmap.isNull():
                self.setPixmap(pixmap)
            else:
                print(f"Error cargando overlay: {self.overlay_path}")
        except Exception as e:
            print(f"Error cargando overlay {self.overlay_path}: {e}")

class ThumbnailCanvas(QGraphicsView):
    """Canvas principal para editar thumbnails."""
    
    overlay_selected = pyqtSignal(object)
    overlay_added = pyqtSignal(object)
    
    def __init__(self):
        super().__init__()
        self.background_image_path = None
        self.background_item = None
        self.setup_canvas()
        
    def setup_canvas(self):
        """Configura el canvas básico."""
        self.scene = QGraphicsScene()
        self.scene.setSceneRect(0, 0, YOUTUBE_THUMBNAIL_WIDTH, YOUTUBE_THUMBNAIL_HEIGHT)
        self.setScene(self.scene)
        
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setStyleSheet("QGraphicsView { background-color: #2b2b2b; }")
        
        self.scene.selectionChanged.connect(self.on_selection_changed)
        self.draw_safe_zone()
        
    def draw_safe_zone(self):
        """Dibuja las guías de zona segura."""
        pen = QPen(QColor(255, 255, 0, 100), 2, Qt.PenStyle.DashLine)
        margin_x = YOUTUBE_THUMBNAIL_WIDTH * SAFE_MARGIN_PERCENT
        margin_y = YOUTUBE_THUMBNAIL_HEIGHT * SAFE_MARGIN_PERCENT
        
        safe_rect = QRectF(margin_x, margin_y, 
                          YOUTUBE_THUMBNAIL_WIDTH - 2*margin_x,
                          YOUTUBE_THUMBNAIL_HEIGHT - 2*margin_y)
        
        self.scene.addRect(safe_rect, pen)
        
    def add_overlay(self, overlay_path):
        """Añade un overlay al canvas."""
        try:
            overlay_item = OverlayItem(overlay_path)
            overlay_item.setPos(
                YOUTUBE_THUMBNAIL_WIDTH/2 - overlay_item.boundingRect().width()/2,
                YOUTUBE_THUMBNAIL_HEIGHT/2 - overlay_item.boundingRect().height()/2
            )
            self.scene.addItem(overlay_item)
            
            self.scene.clearSelection()
            overlay_item.setSelected(True)
            
            self.overlay_added.emit(overlay_item)
            self.overlay_selected.emit(overlay_item)
            
        except Exception as e:
            print(f"Error añadiendo overlay: {e}")
            
    def on_selection_changed(self):
        """Maneja cambios en la selección."""
        selected_items = self.scene.selectedItems()
        overlay_items = [item for item in selected_items if isinstance(item, OverlayItem)]
        
        if overlay_items:
            self.overlay_selected.emit(overlay_items[0])
        else:
            self.overlay_selected.emit(None)
            
    def load_base_image(self, image_path):
        """Carga una imagen base."""
        try:
            if self.background_item:
                self.scene.removeItem(self.background_item)
                
            pil_image = Image.open(image_path)
            pil_image = pil_image.convert('RGB')
            pil_image = pil_image.resize((YOUTUBE_THUMBNAIL_WIDTH, YOUTUBE_THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
            
            qt_image = ImageQt.ImageQt(pil_image)
            pixmap = QPixmap.fromImage(qt_image)
            
            self.background_item = QGraphicsPixmapItem(pixmap)
            self.background_item.setZValue(-1)
            self.scene.addItem(self.background_item)
            self.background_image_path = image_path
            
        except Exception as e:
            print(f"Error cargando imagen base: {e}")
            
    def clear_overlays(self):
        """Limpia todos los overlays."""
        for item in self.scene.items():
            if isinstance(item, OverlayItem):
                self.scene.removeItem(item)
                
    def export_thumbnail(self, file_path):
        """Exporta el thumbnail final."""
        try:
            image = QImage(YOUTUBE_THUMBNAIL_WIDTH, YOUTUBE_THUMBNAIL_HEIGHT, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.black)
            
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Renderizar solo background y overlays
            for item in self.scene.items():
                if isinstance(item, (QGraphicsPixmapItem, OverlayItem)) and not isinstance(item, QGraphicsRectItem):
                    painter.save()
                    painter.setTransform(item.sceneTransform(), True)
                    item.paint(painter, QStyleOptionGraphicsItem(), None)
                    painter.restore()
                    
            painter.end()
            image.save(file_path)
            return True
            
        except Exception as e:
            print(f"Error exportando thumbnail: {e}")
            return False

class OverlayLibrary(QWidget):
    """Panel de librería de overlays."""
    
    overlay_dropped = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.load_overlays()
        
    def setup_ui(self):
        """Configura la interfaz."""
        layout = QVBoxLayout(self)
        
        title = QLabel("📁 Librería de Overlays")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        layout.addWidget(title)
        
        self.overlay_list = QListWidget()
        self.overlay_list.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self.overlay_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.overlay_list.setIconSize(QSize(64, 64))
        self.overlay_list.setGridSize(QSize(80, 80))
        self.overlay_list.itemDoubleClicked.connect(self.on_overlay_double_click)
        
        layout.addWidget(self.overlay_list)
        
        refresh_btn = QPushButton("🔄 Actualizar")
        refresh_btn.clicked.connect(self.load_overlays)
        layout.addWidget(refresh_btn)
        
    def load_overlays(self):
        """Carga overlays desde la carpeta."""
        self.overlay_list.clear()
        overlays_folder = "overlays"
        
        if not os.path.exists(overlays_folder):
            os.makedirs(overlays_folder, exist_ok=True)
            return
            
        for filename in os.listdir(overlays_folder):
            if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                overlay_path = os.path.join(overlays_folder, filename)
                self.add_overlay_to_list(overlay_path)
                
    def add_overlay_to_list(self, overlay_path):
        """Agrega un overlay a la lista."""
        try:
            pixmap = QPixmap(overlay_path)
            if not pixmap.isNull():
                thumbnail = pixmap.scaled(64, 64, Qt.AspectRatioMode.KeepAspectRatio, 
                                        Qt.TransformationMode.SmoothTransformation)
                
                item = QListWidgetItem()
                item.setIcon(QIcon(thumbnail))
                item.setText(os.path.basename(overlay_path))
                item.setData(Qt.ItemDataRole.UserRole, overlay_path)
                item.setToolTip(f"Overlay: {os.path.basename(overlay_path)}")
                
                self.overlay_list.addItem(item)
                
        except Exception as e:
            print(f"Error cargando overlay {overlay_path}: {e}")
            
    def on_overlay_double_click(self, item):
        """Maneja doble clic en overlay."""
        overlay_path = item.data(Qt.ItemDataRole.UserRole)
        if overlay_path:
            self.overlay_dropped.emit(overlay_path)

class OverlayProperties(QWidget):
    """Panel de propiedades de overlays."""
    
    property_changed = pyqtSignal()
    
    def __init__(self):
        super().__init__()
        self.current_overlay = None
        self.setup_ui()
        
    def setup_ui(self):
        """Configura la interfaz."""
        layout = QVBoxLayout(self)
        
        title = QLabel("⚙️ Propiedades")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        layout.addWidget(title)
        
        # Posición
        pos_group = QGroupBox("Posición")
        pos_layout = QGridLayout(pos_group)
        
        pos_layout.addWidget(QLabel("X:"), 0, 0)
        self.x_spin = QDoubleSpinBox()
        self.x_spin.setRange(-500, 2000)
        self.x_spin.valueChanged.connect(self.update_position)
        pos_layout.addWidget(self.x_spin, 0, 1)
        
        pos_layout.addWidget(QLabel("Y:"), 1, 0)
        self.y_spin = QDoubleSpinBox()
        self.y_spin.setRange(-500, 2000)
        self.y_spin.valueChanged.connect(self.update_position)
        pos_layout.addWidget(self.y_spin, 1, 1)
        
        layout.addWidget(pos_group)
        
        # Escala
        scale_group = QGroupBox("Escala")
        scale_layout = QVBoxLayout(scale_group)
        
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(10, 300)
        self.scale_slider.setValue(100)
        self.scale_slider.valueChanged.connect(self.update_scale)
        scale_layout.addWidget(self.scale_slider)
        
        self.scale_label = QLabel("100%")
        self.scale_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scale_layout.addWidget(self.scale_label)
        
        layout.addWidget(scale_group)
        
        # Rotación
        rotation_group = QGroupBox("Rotación")
        rotation_layout = QVBoxLayout(rotation_group)
        
        self.rotation_slider = QSlider(Qt.Orientation.Horizontal)
        self.rotation_slider.setRange(-180, 180)
        self.rotation_slider.setValue(0)
        self.rotation_slider.valueChanged.connect(self.update_rotation)
        rotation_layout.addWidget(self.rotation_slider)
        
        self.rotation_label = QLabel("0°")
        self.rotation_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rotation_layout.addWidget(self.rotation_label)
        
        layout.addWidget(rotation_group)
        
        # Opacidad
        opacity_group = QGroupBox("Opacidad")
        opacity_layout = QVBoxLayout(opacity_group)
        
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self.update_opacity)
        opacity_layout.addWidget(self.opacity_slider)
        
        self.opacity_label = QLabel("100%")
        self.opacity_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        opacity_layout.addWidget(self.opacity_label)
        
        layout.addWidget(opacity_group)
        
        # Botones de acción
        btn_layout = QVBoxLayout()
        
        front_btn = QPushButton("↑ Al frente")
        front_btn.clicked.connect(self.move_to_front)
        btn_layout.addWidget(front_btn)
        
        back_btn = QPushButton("↓ Atrás")
        back_btn.clicked.connect(self.move_to_back)
        btn_layout.addWidget(back_btn)
        
        delete_btn = QPushButton("🗑️ Eliminar")
        delete_btn.clicked.connect(self.delete_overlay)
        btn_layout.addWidget(delete_btn)
        
        layout.addLayout(btn_layout)
        layout.addStretch()
        
        # Inicialmente deshabilitar
        self.setEnabled(False)
        
    def set_overlay(self, overlay):
        """Establece el overlay actual."""
        self.current_overlay = overlay
        
        if overlay:
            self.setEnabled(True)
            self.x_spin.setValue(overlay.x())
            self.y_spin.setValue(overlay.y())
            self.scale_slider.setValue(int(overlay.scale() * 100))
            self.rotation_slider.setValue(int(overlay.rotation()))
            self.opacity_slider.setValue(int(overlay.opacity() * 100))
            self.update_labels()
        else:
            self.setEnabled(False)
            
    def update_position(self):
        """Actualiza la posición del overlay."""
        if self.current_overlay:
            self.current_overlay.setPos(self.x_spin.value(), self.y_spin.value())
            self.property_changed.emit()
            
    def update_scale(self):
        """Actualiza la escala del overlay."""
        if self.current_overlay:
            scale = self.scale_slider.value() / 100.0
            self.current_overlay.setScale(scale)
            self.scale_label.setText(f"{self.scale_slider.value()}%")
            self.property_changed.emit()
            
    def update_rotation(self):
        """Actualiza la rotación del overlay."""
        if self.current_overlay:
            self.current_overlay.setRotation(self.rotation_slider.value())
            self.rotation_label.setText(f"{self.rotation_slider.value()}°")
            self.property_changed.emit()
            
    def update_opacity(self):
        """Actualiza la opacidad del overlay."""
        if self.current_overlay:
            opacity = self.opacity_slider.value() / 100.0
            self.current_overlay.setOpacity(opacity)
            self.opacity_label.setText(f"{self.opacity_slider.value()}%")
            self.property_changed.emit()
            
    def update_labels(self):
        """Actualiza las etiquetas de valores."""
        if self.current_overlay:
            self.scale_label.setText(f"{int(self.current_overlay.scale() * 100)}%")
            self.rotation_label.setText(f"{int(self.current_overlay.rotation())}°")
            self.opacity_label.setText(f"{int(self.current_overlay.opacity() * 100)}%")
            
    def move_to_front(self):
        """Mueve el overlay al frente."""
        if self.current_overlay:
            self.current_overlay.setZValue(999)
            self.property_changed.emit()
            
    def move_to_back(self):
        """Mueve el overlay atrás."""
        if self.current_overlay:
            self.current_overlay.setZValue(-0.5)
            self.property_changed.emit()
            
    def delete_overlay(self):
        """Elimina el overlay actual."""
        if self.current_overlay:
            scene = self.current_overlay.scene()
            if scene:
                scene.removeItem(self.current_overlay)
            self.set_overlay(None)
            self.property_changed.emit()

class ThumbnailEditor(QMainWindow):
    """Ventana principal del editor."""
    
    def __init__(self):
        super().__init__()
        self.current_channel = None
        self.setup_ui()
        self.setup_menu()
        
    def setup_ui(self):
        """Configura la interfaz principal."""
        self.setWindowTitle("Thumbnail Editor")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal
        main_layout = QVBoxLayout(central_widget)
        
        # Barra de canal
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Canal:"))
        
        self.channel_combo = QComboBox()
        self.channel_combo.setEditable(True)
        self.channel_combo.setMinimumWidth(200)
        channel_layout.addWidget(self.channel_combo)
        
        save_btn = QPushButton("💾 Guardar")
        save_btn.clicked.connect(self.save_config)
        channel_layout.addWidget(save_btn)
        
        load_btn = QPushButton("📂 Cargar")
        load_btn.clicked.connect(self.load_config)
        channel_layout.addWidget(load_btn)
        
        channel_layout.addStretch()
        main_layout.addLayout(channel_layout)
        
        # Splitter principal
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # Paneles
        self.overlay_library = OverlayLibrary()
        self.canvas = ThumbnailCanvas()
        self.properties = OverlayProperties()
        
        splitter.addWidget(self.overlay_library)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.properties)
        splitter.setSizes([300, 700, 300])
        
        # Conectar señales
        self.overlay_library.overlay_dropped.connect(self.canvas.add_overlay)
        self.canvas.overlay_selected.connect(self.properties.set_overlay)
        
        # Status bar
        self.statusBar().showMessage("Listo para crear thumbnails")
        
    def setup_menu(self):
        """Configura el menú."""
        menubar = self.menuBar()
        
        # Menú Archivo
        file_menu = menubar.addMenu("Archivo")
        
        open_action = QAction("Abrir imagen base...", self)
        open_action.triggered.connect(self.open_base_image)
        file_menu.addAction(open_action)
        
        file_menu.addSeparator()
        
        export_action = QAction("Exportar thumbnail...", self)
        export_action.triggered.connect(self.export_thumbnail)
        file_menu.addAction(export_action)
        
        file_menu.addSeparator()
        
        exit_action = QAction("Salir", self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
    def open_base_image(self):
        """Abre una imagen base."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Seleccionar imagen base",
            "", "Imágenes (*.png *.jpg *.jpeg *.bmp)"
        )
        
        if file_path:
            self.canvas.load_base_image(file_path)
            self.statusBar().showMessage(f"Imagen cargada: {os.path.basename(file_path)}")
            
    def export_thumbnail(self):
        """Exporta el thumbnail."""
        channel_name = self.channel_combo.currentText().strip() or "thumbnail"
        default_name = f"{channel_name}_thumbnail.png"
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Exportar thumbnail",
            default_name, "PNG (*.png);;JPEG (*.jpg)"
        )
        
        if file_path:
            if self.canvas.export_thumbnail(file_path):
                self.statusBar().showMessage(f"Thumbnail exportado: {os.path.basename(file_path)}")
                QMessageBox.information(self, "Éxito", "Thumbnail exportado correctamente")
            else:
                QMessageBox.warning(self, "Error", "No se pudo exportar el thumbnail")
                
    def save_config(self):
        """Guarda la configuración actual."""
        channel_name = self.channel_combo.currentText().strip()
        if not channel_name:
            QMessageBox.warning(self, "Error", "Ingresa un nombre de canal")
            return
            
        self.statusBar().showMessage(f"Configuración guardada para {channel_name}")
        
    def load_config(self):
        """Carga una configuración."""
        channel_name = self.channel_combo.currentText().strip()
        if not channel_name:
            QMessageBox.warning(self, "Error", "Ingresa un nombre de canal")
            return
            
        self.statusBar().showMessage(f"Configuración cargada: {channel_name}")

def main():
    """Función principal."""
    app = QApplication(sys.argv)
    
    # Aplicar tema oscuro
    try:
        app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt6())
    except:
        print("Tema oscuro no disponible, usando tema por defecto")
    
    # Crear y mostrar ventana
    window = ThumbnailEditor()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()