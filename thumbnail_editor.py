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
# import qdarkstyle  # Comentado temporalmente para debugging

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
        """Carga el overlay desde archivo con manejo robusto."""
        try:
            if not os.path.exists(self.overlay_path):
                print(f"Archivo de overlay no encontrado: {self.overlay_path}")
                return
                
            # Intentar cargar con QPixmap directamente primero
            pixmap = QPixmap(self.overlay_path)
            
            if not pixmap.isNull():
                self.setPixmap(pixmap)
                return
            
            # Si QPixmap falla, intentar con PIL
            try:
                from PIL import Image
                pil_image = Image.open(self.overlay_path)
                
                # Convertir a RGBA para mantener transparencia
                if pil_image.mode != 'RGBA':
                    pil_image = pil_image.convert('RGBA')
                
                # Convertir a Qt
                qt_image = ImageQt.ImageQt(pil_image)
                pixmap = QPixmap.fromImage(qt_image)
                
                if not pixmap.isNull():
                    self.setPixmap(pixmap)
                else:
                    print(f"No se pudo crear pixmap para overlay: {self.overlay_path}")
                    
            except Exception as pil_error:
                print(f"Error procesando overlay con PIL {self.overlay_path}: {pil_error}")
                
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
        """Carga una imagen base con manejo robusto de errores."""
        try:
            print(f"🖼️ Iniciando carga de imagen: {image_path}")
            
            if self.background_item:
                print("🗑️ Removiendo imagen anterior...")
                self.scene.removeItem(self.background_item)
                
            # Verificar que el archivo existe
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"El archivo no existe: {image_path}")
            
            print("📂 Abriendo imagen con PIL...")
            # Abrir imagen con PIL con manejo robusto
            try:
                pil_image = Image.open(image_path)
                print(f"✓ Imagen abierta: {pil_image.size}, modo: {pil_image.mode}")
                
                # Verificar formato y convertir si es necesario
                if hasattr(pil_image, '_getexif'):
                    # Manejar rotación EXIF si existe
                    try:
                        from PIL.ExifTags import ORIENTATION
                        exif = pil_image._getexif()
                        if exif is not None:
                            orientation = exif.get(ORIENTATION)
                            if orientation == 3:
                                pil_image = pil_image.rotate(180, expand=True)
                                print("🔄 Rotada 180°")
                            elif orientation == 6:
                                pil_image = pil_image.rotate(270, expand=True)
                                print("🔄 Rotada 270°")
                            elif orientation == 8:
                                pil_image = pil_image.rotate(90, expand=True)
                                print("🔄 Rotada 90°")
                    except:
                        pass  # Ignorar errores de EXIF
                
                print("🎨 Convirtiendo formato...")
                # Convertir a RGB para asegurar compatibilidad
                if pil_image.mode in ('RGBA', 'LA', 'P'):
                    # Para imágenes con transparencia, crear fondo blanco
                    background = Image.new('RGB', pil_image.size, (255, 255, 255))
                    if pil_image.mode == 'P':
                        pil_image = pil_image.convert('RGBA')
                    background.paste(pil_image, mask=pil_image.split()[-1] if pil_image.mode in ('RGBA', 'LA') else None)
                    pil_image = background
                    print("✓ Convertido con fondo blanco")
                elif pil_image.mode != 'RGB':
                    pil_image = pil_image.convert('RGB')
                    print("✓ Convertido a RGB")
                
                print("📏 Redimensionando...")
                # Redimensionar con alta calidad
                pil_image = pil_image.resize(
                    (YOUTUBE_THUMBNAIL_WIDTH, YOUTUBE_THUMBNAIL_HEIGHT), 
                    Image.Resampling.LANCZOS
                )
                print(f"✓ Redimensionado a {YOUTUBE_THUMBNAIL_WIDTH}x{YOUTUBE_THUMBNAIL_HEIGHT}")
                
            except Exception as pil_error:
                raise Exception(f"Error procesando imagen con PIL: {pil_error}")
            
            print("⚡ Convirtiendo a Qt...")
            # Convertir a Qt
            try:
                qt_image = ImageQt.ImageQt(pil_image)
                print("✓ Convertido a ImageQt")
                
                pixmap = QPixmap.fromImage(qt_image)
                print("✓ Pixmap creado")
                
                if pixmap.isNull():
                    raise Exception("No se pudo crear el pixmap de Qt")
                    
            except Exception as qt_error:
                raise Exception(f"Error convirtiendo a Qt: {qt_error}")
            
            print("🎭 Agregando al canvas...")
            # Agregar al canvas
            self.background_item = QGraphicsPixmapItem(pixmap)
            print("✓ QGraphicsPixmapItem creado")
            
            self.background_item.setZValue(-1)
            print("✓ Z-value configurado")
            
            self.scene.addItem(self.background_item)
            print("✓ Agregado a la escena")
            
            self.background_image_path = image_path
            print("✓ Path guardado")
            
            print(f"🎉 Imagen cargada exitosamente: {os.path.basename(image_path)}")
            print("🔍 Verificando estado post-carga...")
            print(f"  - Scene items count: {len(self.scene.items())}")
            print(f"  - Background item exists: {self.background_item is not None}")
            print(f"  - Background item in scene: {self.background_item in self.scene.items() if self.background_item else False}")
            print("✅ load_base_image completado exitosamente")
            
        except Exception as e:
            error_msg = f"Error cargando imagen base: {e}"
            print(f"❌ {error_msg}")
            import traceback
            traceback.print_exc()
            
            # Mostrar mensaje de error al usuario
            try:
                from PyQt6.QtWidgets import QMessageBox
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle("Error cargando imagen")
                msg.setText("No se pudo cargar la imagen")
                msg.setDetailedText(f"Archivo: {image_path}\nError: {str(e)}")
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg.exec()
            except Exception as msg_error:
                print(f"Error mostrando mensaje: {msg_error}")
            
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
    
    def get_config(self):
        """Obtiene la configuración actual del canvas."""
        config = {
            'background_image': self.background_image_path,
            'overlays': []
        }
        
        # Guardar información de overlays
        for item in self.scene.items():
            if isinstance(item, OverlayItem):
                overlay_config = {
                    'path': item.overlay_path,
                    'x': item.x(),
                    'y': item.y(),
                    'scale': item.scale(),
                    'rotation': item.rotation(),
                    'z_value': item.zValue()
                }
                config['overlays'].append(overlay_config)
        
        return config
    
    def load_config(self, config):
        """Carga configuración en el canvas."""
        try:
            # Limpiar canvas actual
            self.scene.clear()
            self.background_item = None
            self.background_image_path = None
            
            # Cargar imagen de fondo si existe
            if config.get('background_image') and os.path.exists(config['background_image']):
                self.load_base_image(config['background_image'])
            
            # Cargar overlays
            for overlay_config in config.get('overlays', []):
                if os.path.exists(overlay_config['path']):
                    overlay_item = OverlayItem(overlay_config['path'])
                    overlay_item.setPos(overlay_config.get('x', 0), overlay_config.get('y', 0))
                    overlay_item.setScale(overlay_config.get('scale', 1.0))
                    overlay_item.setRotation(overlay_config.get('rotation', 0))
                    overlay_item.setZValue(overlay_config.get('z_value', 0))
                    
                    self.scene.addItem(overlay_item)
                    self.overlay_added.emit(overlay_item)
            
            return True
            
        except Exception as e:
            print(f"Error cargando configuración: {e}")
            return False

class OverlayLibrary(QWidget):
    """Panel de librería de overlays."""
    
    overlay_dropped = pyqtSignal(str)
    image_selected = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.current_channel_images = []  # 🔥 Lista de imágenes del canal actual
        self.current_image_index = -1     # 🔥 Índice de la imagen actual
        self.setup_ui()
        self.load_overlays()
        
    def setup_ui(self):
        """Configura la interfaz."""
        layout = QVBoxLayout(self)
        
        title = QLabel("📁 Biblioteca de Recursos")
        title.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
        layout.addWidget(title)
        
        # Crear pestañas
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)
        
        # Pestaña de Overlays
        overlay_tab = QWidget()
        overlay_layout = QVBoxLayout(overlay_tab)
        
        self.overlay_list = QListWidget()
        self.overlay_list.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self.overlay_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.overlay_list.setIconSize(QSize(64, 64))
        self.overlay_list.setGridSize(QSize(80, 80))
        self.overlay_list.itemDoubleClicked.connect(self.on_overlay_double_click)
        overlay_layout.addWidget(self.overlay_list)
        
        refresh_btn = QPushButton("🔄 Actualizar Overlays")
        refresh_btn.clicked.connect(self.load_overlays)
        overlay_layout.addWidget(refresh_btn)
        
        load_overlay_btn = QPushButton("📁 Cargar Overlay")
        load_overlay_btn.clicked.connect(self.load_custom_overlay)
        overlay_layout.addWidget(load_overlay_btn)
        
        self.tab_widget.addTab(overlay_tab, "🎨 Overlays")
        
        # Pestaña de Imágenes del Canal
        images_tab = QWidget()
        images_layout = QVBoxLayout(images_tab)
        
        self.channel_label = QLabel("Selecciona un canal")
        self.channel_label.setStyleSheet("font-style: italic; padding: 5px;")
        images_layout.addWidget(self.channel_label)
        
        # 🔥 Agregar controles de navegación
        nav_layout = QHBoxLayout()
        
        self.prev_btn = QPushButton("⬅️ Anterior")
        self.prev_btn.clicked.connect(self.show_previous_image)
        self.prev_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_btn)
        
        self.image_counter_label = QLabel("0 / 0")
        self.image_counter_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_counter_label.setStyleSheet("font-weight: bold; padding: 5px;")
        nav_layout.addWidget(self.image_counter_label)
        
        self.next_btn = QPushButton("Siguiente ➡️")
        self.next_btn.clicked.connect(self.show_next_image)
        self.next_btn.setEnabled(False)
        nav_layout.addWidget(self.next_btn)
        
        images_layout.addLayout(nav_layout)
        
        self.images_list = QListWidget()
        self.images_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.images_list.setIconSize(QSize(128, 128))  # 🔥 Thumbnails más grandes
        self.images_list.setGridSize(QSize(150, 150))  # 🔥 Grid más espacioso
        self.images_list.setSpacing(8)  # 🔥 Más espacio entre elementos
        self.images_list.setResizeMode(QListWidget.ResizeMode.Adjust)  # 🔥 Ajustar automáticamente
        self.images_list.itemClicked.connect(self.on_image_click)  # 🔥 Clic simple en lugar de doble
        self.images_list.itemDoubleClicked.connect(self.on_image_double_click)
        images_layout.addWidget(self.images_list)
        
        refresh_images_btn = QPushButton("🔄 Actualizar Imágenes")
        refresh_images_btn.clicked.connect(self.refresh_channel_images)
        images_layout.addWidget(refresh_images_btn)
        
        self.tab_widget.addTab(images_tab, "🖼️ Imágenes del Canal")
        
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
            
    def load_custom_overlay(self):
        """Permite al usuario cargar un overlay personalizado."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import shutil
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Seleccionar overlay personalizado",
            "",
            "Imágenes (*.png *.jpg *.jpeg *.bmp *.gif)"
        )
        
        if file_path:
            try:
                # Copiar el archivo a la carpeta overlays
                filename = os.path.basename(file_path)
                name, ext = os.path.splitext(filename)
                
                # Si es JPG, convertir a PNG para transparencia
                if ext.lower() in ['.jpg', '.jpeg']:
                    from PIL import Image
                    img = Image.open(file_path)
                    if img.mode != 'RGBA':
                        img = img.convert('RGBA')
                    
                    # Crear nombre único
                    counter = 1
                    new_filename = f"{name}.png"
                    target_path = os.path.join("overlays", new_filename)
                    
                    while os.path.exists(target_path):
                        new_filename = f"{name}_{counter}.png"
                        target_path = os.path.join("overlays", new_filename)
                        counter += 1
                    
                    img.save(target_path, "PNG")
                    
                else:
                    # Copiar archivo PNG directamente
                    counter = 1
                    new_filename = filename
                    target_path = os.path.join("overlays", new_filename)
                    
                    while os.path.exists(target_path):
                        name_part, ext_part = os.path.splitext(filename)
                        new_filename = f"{name_part}_{counter}{ext_part}"
                        target_path = os.path.join("overlays", new_filename)
                        counter += 1
                    
                    shutil.copy2(file_path, target_path)
                
                # Actualizar la lista
                self.load_overlays()
                QMessageBox.information(self, "Éxito", f"Overlay '{new_filename}' agregado correctamente")
                
            except Exception as e:
                QMessageBox.warning(self, "Error", f"No se pudo cargar el overlay: {e}")
    
    def load_channel_images(self, image_files):
        """Carga las imágenes del canal en la pestaña correspondiente."""
        self.images_list.clear()
        self.current_channel_images = image_files  # 🔥 Guardar lista de imágenes
        self.current_image_index = 0 if image_files else -1  # 🔥 Empezar con la primera
        
        if not image_files:
            self.channel_label.setText("No hay imágenes en este canal")
            self.image_counter_label.setText("0 / 0")
            self.prev_btn.setEnabled(False)
            self.next_btn.setEnabled(False)
            return
        
        loaded_count = 0
        failed_count = 0
        
        for rel_path, full_path in image_files:
            try:
                # Verificar que el archivo existe
                if not os.path.exists(full_path):
                    failed_count += 1
                    continue
                
                # Crear thumbnail con manejo robusto
                pixmap = None
                
                # Intentar con QPixmap primero
                try:
                    pixmap = QPixmap(full_path)
                except Exception as qpixmap_error:
                    print(f"QPixmap falló para {full_path}: {qpixmap_error}")
                
                # Si QPixmap falla, intentar con PIL
                if pixmap is None or pixmap.isNull():
                    try:
                        from PIL import Image
                        pil_image = Image.open(full_path)
                        
                        # Convertir a RGB para evitar problemas
                        if pil_image.mode != 'RGB':
                            if pil_image.mode in ('RGBA', 'LA'):
                                # Crear fondo blanco para transparencia
                                background = Image.new('RGB', pil_image.size, (255, 255, 255))
                                background.paste(pil_image, mask=pil_image.split()[-1] if pil_image.mode in ('RGBA', 'LA') else None)
                                pil_image = background
                            else:
                                pil_image = pil_image.convert('RGB')
                        
                        # Redimensionar para thumbnail
                        pil_image.thumbnail((128, 128), Image.Resampling.LANCZOS)
                        
                        # Convertir a Qt
                        qt_image = ImageQt.ImageQt(pil_image)
                        pixmap = QPixmap.fromImage(qt_image)
                        
                    except Exception as pil_error:
                        print(f"PIL falló para {full_path}: {pil_error}")
                        failed_count += 1
                        continue
                
                if pixmap and not pixmap.isNull():
                    # Redimensionar para preview - 🔥 Thumbnails más grandes y bonitos
                    icon_pixmap = pixmap.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio, 
                                              Qt.TransformationMode.SmoothTransformation)
                    icon = QIcon(icon_pixmap)
                    
                    # Crear item con texto descriptivo
                    display_name = rel_path.replace('\\', '/').replace('/', ' / ')
                    item = QListWidgetItem(icon, display_name)
                    item.setData(Qt.ItemDataRole.UserRole, full_path)  # Guardar path completo
                    item.setToolTip(f"📁 Archivo: {os.path.basename(full_path)}\\n📂 Grupo: {os.path.dirname(rel_path) or 'Principal'}\\n🖼️ Clic para cambiar imagen")
                    
                    self.images_list.addItem(item)
                    loaded_count += 1
                else:
                    failed_count += 1
                    
            except Exception as e:
                print(f"Error cargando imagen {full_path}: {e}")
                failed_count += 1
        
        # Actualizar etiqueta con información de carga
        status_text = f"Canal: {loaded_count} imágenes cargadas"
        if failed_count > 0:
            status_text += f" ({failed_count} fallaron)"
        self.channel_label.setText(status_text)
        
        # 🔥 Configurar navegación
        total = len(self.current_channel_images)
        if total > 0:
            try:
                if hasattr(self, 'image_counter_label') and self.image_counter_label:
                    self.image_counter_label.setText(f"1 / {total}")
                if hasattr(self, 'prev_btn') and self.prev_btn:
                    self.prev_btn.setEnabled(False)  # Primera imagen, no hay anterior
                if hasattr(self, 'next_btn') and self.next_btn:
                    self.next_btn.setEnabled(total > 1)  # Habilitar siguiente si hay más de 1
                # Seleccionar primera imagen
                if hasattr(self, 'images_list') and self.images_list and self.images_list.count() > 0:
                    self.images_list.setCurrentRow(0)
                print(f"✅ Navegación configurada: {total} imágenes")
            except Exception as nav_error:
                print(f"⚠️ Error configurando navegación: {nav_error}")
        else:
            try:
                if hasattr(self, 'image_counter_label') and self.image_counter_label:
                    self.image_counter_label.setText("0 / 0")
                if hasattr(self, 'prev_btn') and self.prev_btn:
                    self.prev_btn.setEnabled(False)
                if hasattr(self, 'next_btn') and self.next_btn:
                    self.next_btn.setEnabled(False)
            except Exception as nav_error:
                print(f"⚠️ Error limpiando navegación: {nav_error}")
    
    def on_image_double_click(self, item):
        """Maneja doble clic en imagen del canal."""
        try:
            image_path = item.data(Qt.ItemDataRole.UserRole)
            if image_path:
                print(f"🖼️ Seleccionada imagen del canal: {os.path.basename(image_path)}")
                # Señal para usar como imagen base en el canvas
                self.image_selected.emit(image_path)
            else:
                print("⚠️ No se pudo obtener la ruta de la imagen")
        except Exception as e:
            print(f"❌ Error en on_image_double_click: {e}")
            import traceback
            traceback.print_exc()
    
    def on_image_click(self, item):
        """Maneja clic simple en imagen del canal - Cambio rápido de imagen."""
        try:
            image_path = item.data(Qt.ItemDataRole.UserRole)
            if image_path:
                # � Actualizar índice basado en la selección
                row = self.images_list.row(item)
                if row >= 0 and row < len(self.current_channel_images):
                    self.current_image_index = row
                    self.update_current_image()
                else:
                    # Fallback: emitir señal directamente
                    print(f"👆 Clic en imagen: {os.path.basename(image_path)}")
                    self.image_selected.emit(image_path)
            else:
                print("⚠️ No se pudo obtener la ruta de la imagen")
        except Exception as e:
            print(f"❌ Error en on_image_click: {e}")
            import traceback
            traceback.print_exc()
    
    def refresh_channel_images(self):
        """Actualiza las imágenes del canal actual."""
        # Esta función será conectada por el editor principal
        if hasattr(self.parent(), 'load_channel_images'):
            self.parent().load_channel_images()
    
    def show_previous_image(self):
        """Muestra la imagen anterior del canal."""
        try:
            if self.current_channel_images and self.current_image_index > 0:
                self.current_image_index -= 1
                self.update_current_image()
        except Exception as e:
            print(f"Error en show_previous_image: {e}")
    
    def show_next_image(self):
        """Muestra la siguiente imagen del canal."""
        try:
            if self.current_channel_images and self.current_image_index < len(self.current_channel_images) - 1:
                self.current_image_index += 1
                self.update_current_image()
        except Exception as e:
            print(f"Error en show_next_image: {e}")
    
    def update_current_image(self):
        """Actualiza la imagen mostrada y los controles."""
        try:
            if not self.current_channel_images or self.current_image_index < 0:
                print("⚠️ update_current_image: No hay imágenes o índice inválido")
                return
            
            if self.current_image_index >= len(self.current_channel_images):
                print(f"⚠️ update_current_image: Índice fuera de rango {self.current_image_index}/{len(self.current_channel_images)}")
                return
            
            # Obtener imagen actual
            rel_path, full_path = self.current_channel_images[self.current_image_index]
            
            # Emitir señal para cargar en canvas
            print(f"🔄 update_current_image: Emitiendo señal para {os.path.basename(full_path)}")
            self.image_selected.emit(full_path)
            
            # Actualizar contador - con verificación de existencia
            total = len(self.current_channel_images)
            current = self.current_image_index + 1
            
            if hasattr(self, 'image_counter_label') and self.image_counter_label:
                self.image_counter_label.setText(f"{current} / {total}")
            
            # Actualizar botones - con verificación de existencia
            if hasattr(self, 'prev_btn') and self.prev_btn:
                self.prev_btn.setEnabled(self.current_image_index > 0)
            if hasattr(self, 'next_btn') and self.next_btn:
                self.next_btn.setEnabled(self.current_image_index < total - 1)
            
            # Seleccionar item en la lista
            if hasattr(self, 'images_list') and self.images_list and self.current_image_index < self.images_list.count():
                self.images_list.setCurrentRow(self.current_image_index)
            
            print(f"🏹 Navegación: imagen {current}/{total} - {os.path.basename(full_path)}")
            print("✅ update_current_image completado exitosamente")
            
        except Exception as e:
            print(f"❌ Error crítico en update_current_image: {e}")
            import traceback
            traceback.print_exc()

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
        print("🔧 Inicializando ThumbnailEditor...")
        
        self.current_channel = None
        self.images_folder = os.path.abspath("images")
        self.config_folder = os.path.abspath("config")
        
        # Crear carpetas si no existen
        try:
            os.makedirs(self.images_folder, exist_ok=True)
            os.makedirs(self.config_folder, exist_ok=True)
            print(f"✓ Carpetas configuradas: {self.images_folder}, {self.config_folder}")
        except Exception as e:
            print(f"❌ Error creando carpetas: {e}")
        
        try:
            print("🎨 Configurando interfaz...")
            self.setup_ui()
            print("✓ Interfaz configurada")
        except Exception as e:
            print(f"❌ Error en setup_ui: {e}")
            raise
        
        try:
            print("📋 Configurando menú...")
            self.setup_menu()
            print("✓ Menú configurado")
        except Exception as e:
            print(f"❌ Error en setup_menu: {e}")
            raise
        
        try:
            print("📁 Cargando canales disponibles...")
            self.load_available_channels()
            print("✓ Canales cargados")
        except Exception as e:
            print(f"❌ Error cargando canales: {e}")
            # No hacer raise aquí, es un error no crítico
        
        print("🎉 ThumbnailEditor inicializado correctamente")
        
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
        self.channel_combo.currentTextChanged.connect(self.on_channel_changed)
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
        self.overlay_library.image_selected.connect(self.canvas.load_base_image)
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
        """Guarda la configuración actual para el canal."""
        channel_name = self.channel_combo.currentText().strip()
        if not channel_name:
            QMessageBox.warning(self, "Error", "Selecciona o ingresa un nombre de canal")
            return
        
        try:
            # Obtener configuración del canvas
            config = {}
            if hasattr(self.canvas, 'get_config'):
                config = self.canvas.get_config()
            
            # Agregar información del canal
            config['channel'] = channel_name
            config['saved_at'] = datetime.now().isoformat()
            
            # Guardar archivo de configuración
            config_file = os.path.join(self.config_folder, f"{channel_name}_thumbnail_config.json")
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            self.statusBar().showMessage(f"✓ Configuración guardada para {channel_name}")
            QMessageBox.information(self, "Éxito", f"Configuración guardada para el canal '{channel_name}'")
            
        except Exception as e:
            print(f"Error guardando configuración: {e}")
            QMessageBox.warning(self, "Error", f"No se pudo guardar la configuración: {str(e)}")
        
    def load_config(self):
        """Carga la configuración para el canal actual."""
        channel_name = self.channel_combo.currentText().strip()
        if not channel_name:
            QMessageBox.warning(self, "Error", "Selecciona un canal")
            return
        
        try:
            config_file = os.path.join(self.config_folder, f"{channel_name}_thumbnail_config.json")
            if not os.path.exists(config_file):
                QMessageBox.information(self, "Info", f"No hay configuración guardada para '{channel_name}'")
                return
            
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Aplicar configuración al canvas
            if hasattr(self.canvas, 'load_config'):
                self.canvas.load_config(config)
            
            self.statusBar().showMessage(f"✓ Configuración cargada: {channel_name}")
            QMessageBox.information(self, "Éxito", f"Configuración cargada para '{channel_name}'")
            
        except Exception as e:
            print(f"Error cargando configuración: {e}")
            QMessageBox.warning(self, "Error", f"No se pudo cargar la configuración: {str(e)}")
    
    def load_available_channels(self):
        """Carga los canales disponibles desde la estructura de carpetas."""
        try:
            if os.path.exists(self.images_folder):
                channels = []
                for item in os.listdir(self.images_folder):
                    channel_path = os.path.join(self.images_folder, item)
                    if os.path.isdir(channel_path):
                        channels.append(item)
                
                self.channel_combo.clear()
                self.channel_combo.addItems(sorted(channels))
                
                if channels:
                    self.statusBar().showMessage(f"Cargados {len(channels)} canales")
                else:
                    self.statusBar().showMessage("No se encontraron canales - crea carpetas en /images")
            else:
                self.statusBar().showMessage("Carpeta de imágenes no encontrada")
                
        except Exception as e:
            print(f"Error cargando canales: {e}")
            self.statusBar().showMessage("Error cargando canales")
    
    def on_channel_changed(self, channel_name):
        """Se ejecuta cuando cambia el canal seleccionado."""
        try:
            print(f"🔄 Cambiando canal a: '{channel_name}'")
            
            if not channel_name.strip():
                print("⚠️ Canal vacío, ignorando")
                return
                
            self.current_channel = channel_name.strip()
            print(f"📂 Canal actual: {self.current_channel}")
            
            print("🖼️ Cargando imágenes del canal...")
            self.load_channel_images()
            print("✓ Imágenes cargadas")
            
            print("⚙️ Cargando configuración del canal...")
            self.load_channel_config()
            print("✓ Configuración cargada")
            
            self.statusBar().showMessage(f"Canal activo: {self.current_channel}")
            print(f"✅ Canal '{self.current_channel}' activado correctamente")
            
        except Exception as e:
            print(f"❌ Error en on_channel_changed: {e}")
            import traceback
            traceback.print_exc()
            
            # Intentar mostrar error al usuario
            try:
                self.statusBar().showMessage(f"Error cargando canal: {str(e)}")
            except:
                pass
    
    def load_channel_images(self):
        """Carga las imágenes disponibles para el canal actual."""
        if not self.current_channel:
            return
            
        try:
            channel_path = os.path.join(self.images_folder, self.current_channel)
            if not os.path.exists(channel_path):
                self.statusBar().showMessage(f"Carpeta del canal no encontrada: {channel_path}")
                return
            
            # Buscar imágenes en todas las subcarpetas (grupos)
            image_files = []
            for root, dirs, files in os.walk(channel_path):
                for file in files:
                    if file.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp')):
                        full_path = os.path.join(root, file)
                        # Obtener path relativo para mostrar grupo/imagen
                        rel_path = os.path.relpath(full_path, channel_path)
                        image_files.append((rel_path, full_path))
            
            # Actualizar la biblioteca de overlays con las imágenes del canal
            if hasattr(self, 'overlay_library'):
                self.overlay_library.load_channel_images(image_files)
            
            # 🔥 AUTOMÁTICAMENTE CARGAR LA PRIMERA IMAGEN COMO PREVIEW
            if image_files:
                try:
                    first_image_path = image_files[0][1]  # Obtener path completo de la primera imagen
                    print(f"🎯 Intentando cargar primera imagen del canal: {os.path.basename(first_image_path)}")
                    self.canvas.load_base_image(first_image_path)
                    self.statusBar().showMessage(f"Canal: {self.current_channel} - {len(image_files)} imágenes - Mostrando: {os.path.basename(first_image_path)}")
                    print(f"✅ Primera imagen cargada exitosamente")
                except Exception as load_error:
                    print(f"❌ Error cargando primera imagen automáticamente: {load_error}")
                    import traceback
                    traceback.print_exc()
                    self.statusBar().showMessage(f"Canal: {self.current_channel} - {len(image_files)} imágenes (error cargando preview)")
            else:
                self.statusBar().showMessage(f"Cargadas {len(image_files)} imágenes para {self.current_channel}")
            
        except Exception as e:
            print(f"Error cargando imágenes del canal: {e}")
            self.statusBar().showMessage("Error cargando imágenes del canal")
    
    def load_channel_config(self):
        """Carga la configuración guardada para el canal actual."""
        if not self.current_channel:
            return
            
        try:
            config_file = os.path.join(self.config_folder, f"{self.current_channel}_thumbnail_config.json")
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # Aplicar configuración al canvas
                if hasattr(self.canvas, 'load_config'):
                    self.canvas.load_config(config)
                    
                self.statusBar().showMessage(f"Configuración cargada: {self.current_channel}")
            else:
                self.statusBar().showMessage(f"No hay configuración guardada para {self.current_channel}")
                
        except Exception as e:
            print(f"Error cargando configuración: {e}")
            self.statusBar().showMessage("Error cargando configuración del canal")

def main():
    """Función principal con manejo robusto de errores."""
    try:
        app = QApplication(sys.argv)
        
        # Configurar manejo de excepciones no capturadas
        def handle_exception(exc_type, exc_value, exc_traceback):
            if issubclass(exc_type, KeyboardInterrupt):
                sys.__excepthook__(exc_type, exc_value, exc_traceback)
                return
            
            import traceback
            error_msg = f"Error no manejado: {exc_type.__name__}: {exc_value}"
            traceback_str = ''.join(traceback.format_exception(exc_type, exc_value, exc_traceback))
            
            print("=" * 60)
            print("ERROR CAPTURADO:")
            print(error_msg)
            print("Traceback completo:")
            print(traceback_str)
            print("=" * 60)
            
            # Mostrar diálogo de error si es posible
            try:
                from PyQt6.QtWidgets import QMessageBox
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setWindowTitle("Error del Editor")
                msg.setText("Se produjo un error, pero el programa continuará")
                msg.setDetailedText(f"{exc_type.__name__}: {str(exc_value)}\n\nTraceback:\n{traceback_str}")
                msg.setStandardButtons(QMessageBox.StandardButton.Ok)
                msg.exec()
            except:
                pass
            
            # NO cerrar la aplicación, solo imprimir el error
        
        sys.excepthook = handle_exception
        
        # Aplicar tema oscuro
        try:
            # app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt6())
            print("💡 Tema oscuro deshabilitado temporalmente")
        except Exception as e:
            print(f"Tema oscuro no disponible: {e}")
        
        # Crear y mostrar ventana
        try:
            window = ThumbnailEditor()
            window.show()
            
            print("✓ Editor de thumbnails iniciado correctamente")
            print("💡 Consejos para imágenes de Pinterest:")
            print("   - Guarda las imágenes como JPG o PNG")
            print("   - Evita imágenes demasiado grandes (>10MB)")
            print("   - Si una imagen falla, prueba guardarla de nuevo")
            
            print("🔄 Iniciando bucle de eventos de Qt...")
            result = app.exec()
            print(f"✓ Aplicación cerrada con código: {result}")
            return result
            
        except Exception as e:
            print(f"Error creando la ventana principal: {e}")
            return 1
            
    except Exception as e:
        print(f"Error fatal iniciando la aplicación: {e}")
        return 1

if __name__ == "__main__":
    exit_code = main()
    print(f"🏁 Programa terminado con código: {exit_code}")
    # No usar sys.exit() para permitir cierre limpio