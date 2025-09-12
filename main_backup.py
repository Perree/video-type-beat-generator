#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Type Beat Video Generator - Versión Simplificada
------------------------------------------------
Aplicación para generar automáticamente videos para Type Beats.
Combina beats de audio con imágenes según género y exporta videos en formato MP4.
"""

import os
import sys
import random
import subprocess
import json
import shutil
from PyQt6.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                            QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, 
                            QListWidget, QComboBox, QProgressBar, QMessageBox,
                            QDialog, QLineEdit, QGridLayout, QMenu, QFrame,
                            QSplitter, QStyleFactory, QToolButton, QListWidgetItem,
                            QSizePolicy, QTabWidget, QInputDialog, QGraphicsDropShadowEffect,
                            QGroupBox, QCheckBox, QRadioButton)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QRect, QSettings, QPoint, QTimer
from PyQt6.QtGui import QPixmap, QIcon, QColor, QPalette, QFont, QCursor, QLinearGradient, QPainter, QPainterPath

# Importar estilos y bibliotecas para la interfaz moderna
import qdarkstyle
import qtawesome as qta

# Importar el diálogo para editar nombres de beat
from edit_beat_dialog import EditBeatNameDialog

class ThumbnailConfigDialog(QDialog):
    """Diálogo para configurar opciones de thumbnails antes de generar videos."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de Thumbnails")
        self.setModal(True)
        self.resize(500, 400)
        self.setup_ui()
        
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Título
        title = QLabel("🎨 Configuración de Thumbnails")
        title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Descripción
        desc = QLabel("Configura cómo se generarán los thumbnails para tus videos:")
        desc.setWordWrap(True)
        desc.setStyleSheet("padding: 5px; color: #666;")
        layout.addWidget(desc)
        
        # Opciones de estilo
        style_group = QGroupBox("Estilo de Thumbnail")
        style_layout = QVBoxLayout(style_group)
        
        self.letterbox_radio = QRadioButton("📺 Letterbox (barras negras) - Recomendado para Type Beats")
        self.letterbox_radio.setChecked(True)
        self.letterbox_radio.setToolTip("Imagen centrada con barras negras a los lados, ideal para type beats")
        style_layout.addWidget(self.letterbox_radio)
        
        self.fullscreen_radio = QRadioButton("🖼️ Pantalla completa (sin barras)")
        self.fullscreen_radio.setToolTip("Imagen escalada para llenar todo el espacio")
        style_layout.addWidget(self.fullscreen_radio)
        
        layout.addWidget(style_group)
        
        # Opciones de texto
        text_group = QGroupBox("Texto en Thumbnails")
        text_layout = QVBoxLayout(text_group)
        
        self.show_title_check = QCheckBox("✅ Mostrar nombre del beat")
        self.show_title_check.setChecked(True)
        text_layout.addWidget(self.show_title_check)
        
        self.show_type_beat_check = QCheckBox("✅ Mostrar 'TYPE BEAT'")
        self.show_type_beat_check.setChecked(True)
        text_layout.addWidget(self.show_type_beat_check)
        
        self.show_channel_check = QCheckBox("✅ Mostrar nombre del canal")
        self.show_channel_check.setChecked(True)
        text_layout.addWidget(self.show_channel_check)
        
        layout.addWidget(text_group)
        
        # Opciones de overlays personalizados
        overlay_group = QGroupBox("Overlays Personalizados")
        overlay_layout = QVBoxLayout(overlay_group)
        
        self.use_custom_overlays_check = QCheckBox("🎨 Usar configuración personalizada de overlays (si existe)")
        self.use_custom_overlays_check.setChecked(True)
        self.use_custom_overlays_check.setToolTip("Si has guardado configuraciones en el editor, las usará automáticamente")
        overlay_layout.addWidget(self.use_custom_overlays_check)
        
        # Botón para abrir editor
        self.open_editor_btn = QPushButton("🛠️ Abrir Editor de Thumbnails")
        self.open_editor_btn.clicked.connect(self.open_thumbnail_editor)
        overlay_layout.addWidget(self.open_editor_btn)
        
        layout.addWidget(overlay_group)
        
        # Botones
        button_layout = QHBoxLayout()
        
        self.ok_btn = QPushButton("✅ Continuar con la Generación")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setStyleSheet("background-color: #27AE60; padding: 8px; font-weight: bold;")
        
        self.cancel_btn = QPushButton("❌ Cancelar")
        self.cancel_btn.clicked.connect(self.reject)
        self.cancel_btn.setStyleSheet("background-color: #E74C3C; padding: 8px;")
        
        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.ok_btn)
        
        layout.addLayout(button_layout)
        
    def open_thumbnail_editor(self):
        """Abre el editor de thumbnails."""
        try:
            from thumbnail_editor import ThumbnailEditor
            self.thumbnail_editor_window = ThumbnailEditor()
            self.thumbnail_editor_window.show()
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir el editor: {e}")
            
    def get_config(self):
        """Retorna la configuración seleccionada."""
        return {
            'letterbox_style': self.letterbox_radio.isChecked(),
            'show_title': self.show_title_check.isChecked(),
            'show_type_beat': self.show_type_beat_check.isChecked(),
            'show_channel': self.show_channel_check.isChecked(),
            'use_custom_overlays': self.use_custom_overlays_check.isChecked()
        }

# Constantes
CONFIG_FILE = os.path.join('config', 'app_config.json')
DEFAULT_CONFIG = {
    'last_output_folder': 'exported_videos',
    'channels': []  # Lista de canales de YouTube conocidos
}

# Estilos simples y limpios
STYLESHEET = """
QMainWindow {
    background-color: #303030;
    color: white;
}

QLabel {
    color: white;
    font-size: 12px;
    padding: 2px;
}

QLabel[heading=true] {
    color: #5DADE2;
    font-size: 14px;
    font-weight: bold;
    padding: 5px;
    margin: 3px 0px;
}

QPushButton {
    background-color: #3498DB;
    color: white;
    border: none;
    border-radius: 3px;
    padding: 6px 12px;
    min-height: 25px;
    font-size: 11px;
}

QPushButton:hover {
    background-color: #5DADE2;
}

QPushButton:disabled {
    background-color: #7F8C8D;
}

QFrame {
    background-color: #404040;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 8px;
    margin: 3px;
}

QListWidget {
    background-color: #404040;
    border: 1px solid #555555;
    color: white;
    padding: 3px;
}

QListWidget::item {
    padding: 3px;
    border-bottom: 1px solid #555555;
}

QListWidget::item:selected {
    background-color: #3498DB;
}

QComboBox {
    background-color: #404040;
    border: 1px solid #555555;
    color: white;
    padding: 3px;
    min-height: 20px;
}

QLineEdit {
    background-color: #404040;
    border: 1px solid #555555;
    color: white;
    padding: 3px;
}

QProgressBar {
    border: 1px solid #555555;
    background-color: #404040;
    text-align: center;
    color: white;
}

QProgressBar::chunk {
    background-color: #3498DB;
}
"""

class VideoGeneratorWorker(QThread):
    """Clase para procesar la generación de videos en un hilo separado."""
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, beats_folder, images_folder, output_folder, beats_info, thumbnail_config=None):
        super().__init__()
        self.beats_folder = beats_folder
        self.images_folder = images_folder
        self.output_folder = output_folder
        self.beats_info = beats_info
        self.thumbnail_config = thumbnail_config or {}
        self.stop_processing = False
    
    def run(self):
        """Ejecuta el proceso de generación de videos."""
        try:
            used_images = {}  # {canal_grupo: set(imagenes_usadas)}
            total_beats = len(self.beats_info)
            
            for i, info in enumerate(self.beats_info):
                if self.stop_processing:
                    self.finished.emit(False, "Proceso cancelado por el usuario.")
                    return
                
                channel = info["channel"]
                group = info.get("group", "Principal")  # Por defecto usamos el grupo Principal
                audio_file = info["audio"]
                
                self.progress_updated.emit(
                    int((i / total_beats) * 100),
                    f"Procesando: {audio_file} ({i+1}/{total_beats})"
                )
                
                # Obtener imágenes para el canal/grupo
                images = self._get_images_for_channel_group(channel, group)
                if not images:
                    self.finished.emit(False, f"No hay imágenes para el canal '{channel}', grupo '{group}'.")
                    return
                
                # Gestionar las imágenes usadas con clave compuesta canal_grupo
                image_key = f"{channel}_{group}"
                if image_key not in used_images:
                    used_images[image_key] = set()
                
                # Filtrar imágenes ya utilizadas
                available_images = [img for img in images if img not in used_images[image_key]]
                if not available_images:
                    # Si todas las imágenes fueron usadas, reiniciar para este canal/grupo
                    used_images[image_key] = set()
                    available_images = images
                
                # Seleccionar imagen aleatoria
                image = random.choice(available_images)
                used_images[image_key].add(image)
                
                # Crear carpeta de canal en la salida
                audio_path = os.path.join(self.beats_folder, audio_file)
                
                # Usar nombre personalizado si existe, o el formato predeterminado si no
                if info.get('custom_name'):
                    base_output_name = f"{info['custom_name']}"
                else:
                    base_output_name = f"{os.path.splitext(audio_file)[0]}_{channel}_{group}"
                
                output_name = f"{base_output_name}.mp4"
                    
                channel_folder = os.path.join(self.output_folder, channel)
                os.makedirs(channel_folder, exist_ok=True)
                
                # Crear carpeta de grupo dentro del canal
                group_output_folder = os.path.join(channel_folder, group)
                os.makedirs(group_output_folder, exist_ok=True)
                
                output_path = os.path.join(group_output_folder, output_name)
                
                # Generar video
                self.progress_updated.emit(
                    int((i / total_beats) * 100),
                    f"Generando video para: {audio_file}"
                )
                self._generate_video(audio_path, image, output_path)
                
                # Copiar la imagen utilizada junto al video
                image_extension = os.path.splitext(image)[1]
                image_output_name = f"{base_output_name}_imagen{image_extension}"
                image_output_path = os.path.join(group_output_folder, image_output_name)
                
                try:
                    shutil.copy2(image, image_output_path)
                except Exception as e:
                    print(f"No se pudo copiar la imagen: {str(e)}")
                
                # Generar thumbnail automáticamente
                self.progress_updated.emit(
                    int((i / total_beats) * 100),
                    f"Generando thumbnail para: {audio_file}"
                )
                
                # Intentar usar configuración personalizada del canal primero
                thumbnail_generated = False
                if self.thumbnail_config.get('use_custom_overlays', True):
                    thumbnail_generated = self._try_generate_custom_thumbnail(channel, group_output_folder, base_output_name)
                
                if not thumbnail_generated:
                    # Si no hay configuración personalizada, generar thumbnail automático
                    self._generate_thumbnail(image, audio_file, channel, group_output_folder, base_output_name)
                
            # Mensaje final actualizado
            self.progress_updated.emit(100, "Proceso completado!")
            self.finished.emit(True, f"Se generaron {total_beats} videos exitosamente.\\n\\nPara cada video se creó:\\n• Video MP4\\n• Imagen utilizada\\n• Thumbnail para YouTube (1280x720)")
            
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
    
    def _get_images_for_channel_group(self, channel, group="Principal"):
        """Obtiene la lista de imágenes para un canal y grupo específico."""
        group_folder = os.path.join(self.images_folder, channel, group)
        if not os.path.exists(group_folder):
            return []
        
        return [os.path.join(group_folder, img) for img in os.listdir(group_folder) 
                if img.lower().endswith(('.jpg', '.jpeg', '.png'))]
    
    def _generate_video(self, audio_path, image_path, output_path):
        """Genera un video combinando un archivo de audio con una imagen."""
        # Usar FFmpeg desde la carpeta bin si está disponible
        ffmpeg_path = "ffmpeg"
        local_ffmpeg = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "ffmpeg.exe")
        if os.path.exists(local_ffmpeg):
            ffmpeg_path = local_ffmpeg
            
        cmd = [
            ffmpeg_path,
            "-loop", "1",
            "-i", image_path,
            "-i", audio_path,
            "-vf", "scale=-1:1080,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264",
            "-preset", "fast",
            "-tune", "stillimage",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-y",  # Sobrescribir archivos existentes
            output_path
        ]
        
        # Ejecutar FFmpeg silenciosamente (sin mostrar la salida en consola)
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        process.communicate()
        
        if process.returncode != 0:
            raise Exception(f"Error al generar el video para {os.path.basename(audio_path)}")
    
    def _generate_thumbnail(self, image_path, audio_file, channel, output_folder, base_name):
        """Genera un thumbnail automático para YouTube usando la imagen del video."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            
            # Abrir la imagen base
            background = Image.open(image_path)
            background = background.convert('RGB')
            
            # Redimensionar y centrar la imagen para YouTube (1280x720)
            target_width, target_height = 1280, 720
            
            # Verificar si usar estilo letterbox (por defecto) o pantalla completa
            use_letterbox = self.thumbnail_config.get('letterbox_style', True)
            
            if use_letterbox:
                # Estilo letterbox con barras negras para type beats
                content_width = int(target_width * 0.75)  # 75% del ancho
                content_height = int(target_height * 0.8)  # 80% de la altura
                
                # Calcular el escalado manteniendo proporción
                scale_x = content_width / background.width
                scale_y = content_height / background.height
                scale = min(scale_x, scale_y)  # Usar el menor para que quepa completa
                
                new_width = int(background.width * scale)
                new_height = int(background.height * scale)
            else:
                # Estilo pantalla completa
                img_ratio = background.width / background.height
                target_ratio = target_width / target_height
                
                if img_ratio > target_ratio:
                    new_height = target_height
                    new_width = int(new_height * img_ratio)
                else:
                    new_width = target_width
                    new_height = int(new_width / img_ratio)
            
            # Redimensionar imagen
            background = background.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Crear canvas YouTube con fondo negro
            thumbnail = Image.new('RGB', (target_width, target_height), (0, 0, 0))
            
            # Centrar imagen en el canvas
            paste_x = (target_width - new_width) // 2
            paste_y = (target_height - new_height) // 2
            thumbnail.paste(background, (paste_x, paste_y))
            
            # Verificar si usar overlay personalizado
            use_custom_overlay = self.thumbnail_config.get('use_custom_overlay', False)
            custom_overlay_path = self.thumbnail_config.get('custom_overlay_path', None)
            
            if use_custom_overlay and custom_overlay_path and os.path.exists(custom_overlay_path):
                try:
                    # Cargar overlay personalizado
                    overlay_img = Image.open(custom_overlay_path).convert('RGBA')
                    # Redimensionar overlay al tamaño del thumbnail
                    overlay_img = overlay_img.resize((target_width, target_height), Image.Resampling.LANCZOS)
                    
                    # Aplicar overlay usando canal alpha
                    thumbnail_rgba = thumbnail.convert('RGBA')
                    thumbnail = Image.alpha_composite(thumbnail_rgba, overlay_img).convert('RGB')
                except Exception as e:
                    print(f"Warning: No se pudo aplicar overlay personalizado: {e}")
                    # Aplicar overlay semitransparente por defecto
                    thumbnail = self._apply_default_overlay(thumbnail, paste_x, paste_y, new_width, new_height)
            else:
                # Aplicar overlay semitransparente por defecto
                thumbnail = self._apply_default_overlay(thumbnail, paste_x, paste_y, new_width, new_height)
            
            draw = ImageDraw.Draw(thumbnail)
    
    def _apply_default_overlay(self, thumbnail, paste_x, paste_y, img_width, img_height):
        """Aplica el overlay semitransparente por defecto solo en la imagen."""
        from PIL import Image
        
        target_width, target_height = thumbnail.size
        
        # Aplicar overlay semitransparente solo en la imagen, no en las barras negras
        thumbnail_rgba = thumbnail.convert('RGBA')
        
        # Crear máscara para aplicar overlay solo en la imagen
        mask = Image.new('L', (target_width, target_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rectangle([paste_x, paste_y, paste_x + img_width, paste_y + img_height], fill=255)
        
        # Aplicar overlay usando la máscara
        overlay_full = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 40))
        thumbnail_rgba = Image.composite(overlay_full, thumbnail_rgba, mask)
        
        # Actualizar la imagen original
        thumbnail.paste(thumbnail_rgba.convert('RGB'))
            
            # Preparar texto del beat
            beat_name = os.path.splitext(audio_file)[0]
            
            # Intentar cargar fuente
            try:
                title_font = ImageFont.truetype("arial.ttf", 72)
                subtitle_font = ImageFont.truetype("arial.ttf", 48)
                small_font = ImageFont.truetype("arial.ttf", 36)
            except:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
                small_font = ImageFont.load_default()
            
            # Texto principal: "[Beat Name] TYPE BEAT"
            main_text = f"{beat_name.upper()}"
            type_beat_text = "TYPE BEAT"
            channel_text = f"by {channel}"
            
            # Función para dibujar texto con borde
            def draw_text_with_border(draw, pos, text, font, fill_color, border_color, border_width=3):
                x, y = pos
                # Dibujar borde
                for adj_x in range(-border_width, border_width + 1):
                    for adj_y in range(-border_width, border_width + 1):
                        if adj_x != 0 or adj_y != 0:
                            draw.text((x + adj_x, y + adj_y), text, font=font, fill=border_color)
                # Dibujar texto principal
                draw.text((x, y), text, font=font, fill=fill_color)
            
            # Calcular posiciones del texto
            # Título principal centrado
            title_bbox = draw.textbbox((0, 0), main_text, font=title_font)
            title_width = title_bbox[2] - title_bbox[0]
            title_x = (target_width - title_width) // 2
            title_y = target_height // 2 - 80
            
            # "TYPE BEAT" debajo del título
            type_bbox = draw.textbbox((0, 0), type_beat_text, font=subtitle_font)
            type_width = type_bbox[2] - type_bbox[0]
            type_x = (target_width - type_width) // 2
            type_y = title_y + 90
            
            # Canal en la parte inferior
            channel_bbox = draw.textbbox((0, 0), channel_text, font=small_font)
            channel_width = channel_bbox[2] - channel_bbox[0]
            channel_x = (target_width - channel_width) // 2
            channel_y = target_height - 80
            
            # Dibujar textos con bordes
            draw_text_with_border(draw, (title_x, title_y), main_text, title_font, 
                                (255, 255, 255), (0, 0, 0), 4)
            draw_text_with_border(draw, (type_x, type_y), type_beat_text, subtitle_font, 
                                (255, 215, 0), (0, 0, 0), 3)  # Dorado
            draw_text_with_border(draw, (channel_x, channel_y), channel_text, small_font, 
                                (200, 200, 200), (0, 0, 0), 2)
            
            # Agregar elementos gráficos opcionales
            # Líneas decorativas
            line_color = (255, 215, 0, 180)  # Dorado semitransparente
            line_width = 5
            
            # Líneas horizontales arriba y abajo del texto principal
            line_y1 = title_y - 20
            line_y2 = type_y + 60
            line_margin = 200
            
            draw.rectangle([line_margin, line_y1, target_width - line_margin, line_y1 + line_width], 
                         fill=(255, 215, 0))
            draw.rectangle([line_margin, line_y2, target_width - line_margin, line_y2 + line_width], 
                         fill=(255, 215, 0))
            
            # Guardar thumbnail
            thumbnail_name = f"{base_name}_thumbnail.png"
            thumbnail_path = os.path.join(output_folder, thumbnail_name)
            thumbnail.save(thumbnail_path, "PNG", quality=95)
            
            print(f"✓ Thumbnail generado: {thumbnail_name}")
            
        except Exception as e:
            print(f"Error generando thumbnail para {audio_file}: {e}")
    
    def _apply_default_overlay(self, thumbnail, paste_x, paste_y, img_width, img_height):
        """Aplica el overlay semitransparente por defecto solo en la imagen."""
        from PIL import Image, ImageDraw
        
        target_width, target_height = thumbnail.size
        
        # Aplicar overlay semitransparente solo en la imagen, no en las barras negras
        thumbnail_rgba = thumbnail.convert('RGBA')
        
        # Crear máscara para aplicar overlay solo en la imagen
        mask = Image.new('L', (target_width, target_height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rectangle([paste_x, paste_y, paste_x + img_width, paste_y + img_height], fill=255)
        
        # Aplicar overlay usando la máscara
        overlay_full = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 40))
        result = Image.composite(overlay_full, thumbnail_rgba, mask)
        
        # Retornar la imagen resultante
        return result.convert('RGB')
        
    def _try_generate_custom_thumbnail(self, channel, output_folder, base_name):
        """Intenta generar un thumbnail usando la configuración personalizada del canal."""
        try:
            from thumbnail_config import ThumbnailConfig, OverlayConfigSerializer
            
            # Verificar si hay configuración guardada para el canal
            config_manager = ThumbnailConfig()
            channel_config = config_manager.load_config(channel)
            
            if not channel_config:
                return False  # No hay configuración personalizada
                
            # Importar componentes necesarios dentro del método para evitar problemas de importación circular
            from thumbnail_editor import ThumbnailCanvas, OverlayLibrary
            from PyQt6.QtGui import QImage, QPainter
            
            # Crear canvas temporal para renderizar
            temp_canvas = ThumbnailCanvas()
            temp_library = OverlayLibrary()
            
            # Restaurar configuración en el canvas
            OverlayConfigSerializer.deserialize_to_scene(
                channel_config, 
                temp_canvas.scene, 
                temp_library
            )
            
            # Renderizar la escena a imagen
            scene_rect = temp_canvas.scene.sceneRect()
            image = QImage(
                int(scene_rect.width()), 
                int(scene_rect.height()), 
                QImage.Format.Format_ARGB32
            )
            image.fill(0)  # Fondo transparente
            
            painter = QPainter(image)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            temp_canvas.scene.render(painter)
            painter.end()
            
            # Guardar thumbnail personalizado
            thumbnail_name = f"{base_name}_custom_thumbnail.png"
            thumbnail_path = os.path.join(output_folder, thumbnail_name)
            
            if image.save(thumbnail_path):
                print(f"✓ Thumbnail personalizado generado: {thumbnail_name}")
                return True
            else:
                print(f"Error guardando thumbnail personalizado")
                return False
                
        except Exception as e:
            print(f"Error generando thumbnail personalizado: {e}")
            return False
    
    def stop(self):
        """Detiene el proceso."""
        self.stop_processing = True


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación."""
    
    def __init__(self):
        super().__init__()
        
        # Inicializar variables
        self.beats_folder = os.path.abspath("beats")
        self.images_folder = os.path.abspath("images")
        self.output_folder = os.path.abspath("exported_videos")
        self.videos_folder = os.path.abspath("videos")
        self.config_folder = os.path.abspath("config")
        self.loaded_beats = []
        self.beats_info = []  # Lista de diccionarios {audio, genre, custom_name}
        self.config = self._load_config()
        
        # Crear carpetas si no existen
        folders_to_create = [
            self.beats_folder, 
            self.images_folder, 
            self.output_folder,
            self.videos_folder,
            self.config_folder
        ]
        for folder in folders_to_create:
            os.makedirs(folder, exist_ok=True)
        
        # Configurar la interfaz
        self._setup_ui()
        
        # Actualizar la lista de beats
        self._update_beats_list()
        
        # Restaurar tamaño y posición de la ventana
        self._restore_window_state()
    
    def _setup_ui(self):
        """Configura la interfaz de usuario de forma simple y clara."""
        self.setWindowTitle("Type Beat Video Generator")
        self.setMinimumSize(900, 600)
        
        # Aplicar estilo
        self.setStyleSheet(STYLESHEET)
        
        # Configurar menú
        self._setup_menu()
        
        # Widget central y layout principal
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Título simple
        title = QLabel("🎵 Type Beat Video Generator")
        title.setProperty("heading", True)
        title.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title)
        
        # Layout de 3 columnas
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(15)
        
        # === COLUMNA 1: BEATS ===
        beats_frame = QFrame()
        beats_layout = QVBoxLayout(beats_frame)
        beats_layout.setSpacing(8)
        
        beats_title = QLabel("📂 Beats")
        beats_title.setProperty("heading", True)
        beats_layout.addWidget(beats_title)
        
        # Botones de beats
        self.btn_load_beats = QPushButton("Cargar Beats")
        self.btn_load_beats.clicked.connect(self._load_beats)
        beats_layout.addWidget(self.btn_load_beats)
        
        self.btn_delete_beats = QPushButton("Eliminar")
        self.btn_delete_beats.clicked.connect(self._delete_beat_files)
        beats_layout.addWidget(self.btn_delete_beats)
        
        # Lista de beats
        self.beats_list = QListWidget()
        self.beats_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.beats_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.beats_list.customContextMenuRequested.connect(self._show_beats_list_menu)
        self.beats_list.setMinimumHeight(200)
        beats_layout.addWidget(self.beats_list)
        
        columns_layout.addWidget(beats_frame)
        
        # === COLUMNA 2: CONFIGURACIÓN ===
        config_frame = QFrame()
        config_layout = QVBoxLayout(config_frame)
        config_layout.setSpacing(8)
        
        config_title = QLabel("⚙️ Configuración")
        config_title.setProperty("heading", True)
        config_layout.addWidget(config_title)
        
        # Canal
        config_layout.addWidget(QLabel("Canal:"))
        self.channel_combo = QComboBox()
        self.channel_combo.currentIndexChanged.connect(lambda: self._update_groups_for_channel(self.channel_combo.currentText()))
        self._update_channels_combo()
        config_layout.addWidget(self.channel_combo)
        
        # Grupo
        config_layout.addWidget(QLabel("Grupo:"))
        self.group_combo = QComboBox()
        config_layout.addWidget(self.group_combo)
        
        # Botón asignar
        self.btn_assign_channel = QPushButton("Asignar Canal")
        self.btn_assign_channel.clicked.connect(self._assign_channel_and_group)
        config_layout.addWidget(self.btn_assign_channel)
        
        # Gestionar canales
        self.btn_manage_channels = QPushButton("Gestionar Canales")
        self.btn_manage_channels.clicked.connect(self._manage_channels)
        config_layout.addWidget(self.btn_manage_channels)
        
        # Subir imágenes al canal
        self.btn_upload_images = QPushButton("📁 Subir Imágenes")
        self.btn_upload_images.clicked.connect(self._upload_images_to_channel)
        config_layout.addWidget(self.btn_upload_images)
        
        # Espaciado
        config_layout.addStretch()
        
        columns_layout.addWidget(config_frame)
        
        # === COLUMNA 3: PROCESAMIENTO ===
        process_frame = QFrame()
        process_layout = QVBoxLayout(process_frame)
        process_layout.setSpacing(8)
        
        process_title = QLabel("🎬 Procesamiento")
        process_title.setProperty("heading", True)
        process_layout.addWidget(process_title)
        
        # Lista de procesos
        self.process_list = QListWidget()
        self.process_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.process_list.customContextMenuRequested.connect(self._show_process_list_menu)
        self.process_list.doubleClicked.connect(self._edit_beat_name)
        self.process_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.process_list.setMinimumHeight(150)
        process_layout.addWidget(self.process_list)
        
        # Botones de edición
        self.btn_edit_name = QPushButton("Editar Nombre")
        self.btn_edit_name.clicked.connect(self._edit_selected_beat_name)
        process_layout.addWidget(self.btn_edit_name)
        
        self.btn_remove_beat = QPushButton("Eliminar Beat")
        self.btn_remove_beat.clicked.connect(self._remove_selected_beat)
        process_layout.addWidget(self.btn_remove_beat)
        
        columns_layout.addWidget(process_frame)
        
        main_layout.addLayout(columns_layout)
        
        # === SECCIÓN INFERIOR: EXPORTACIÓN ===
        export_frame = QFrame()
        export_layout = QVBoxLayout(export_frame)
        export_layout.setSpacing(8)
        
        export_title = QLabel("📤 Exportación")
        export_title.setProperty("heading", True)
        export_layout.addWidget(export_title)
        
        # Carpeta de salida
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Carpeta:"))
        
        self.output_path = QLineEdit()
        self.output_path.setText(self.output_folder)
        self.output_path.setReadOnly(True)
        folder_layout.addWidget(self.output_path)
        
        self.btn_browse_output = QPushButton("...")
        self.btn_browse_output.clicked.connect(self._browse_output)
        self.btn_browse_output.setMaximumWidth(40)
        folder_layout.addWidget(self.btn_browse_output)
        
        export_layout.addLayout(folder_layout)
        
        # Progreso
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        export_layout.addWidget(self.progress_bar)
        
        # Estado
        self.status_label = QLabel("Listo para procesar")
        self.status_label.setAlignment(Qt.AlignCenter)
        export_layout.addWidget(self.status_label)
        
        # Botones principales
        buttons_layout = QHBoxLayout()
        
        self.btn_generate = QPushButton("▶ GENERAR VIDEOS")
        self.btn_generate.clicked.connect(self._generate_videos)
        self.btn_generate.setStyleSheet("background-color: #27AE60; font-size: 14px; padding: 8px; font-weight: bold;")
        buttons_layout.addWidget(self.btn_generate)
        
        self.btn_cancel = QPushButton("⏹ CANCELAR")
        self.btn_cancel.clicked.connect(self._cancel_process)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("background-color: #E74C3C; font-size: 14px; padding: 8px; font-weight: bold;")
        buttons_layout.addWidget(self.btn_cancel)
        
        # Botón del editor de thumbnails
        self.btn_thumbnail_editor = QPushButton("🎨 EDITOR THUMBNAILS")
        self.btn_thumbnail_editor.clicked.connect(self._open_thumbnail_editor)
        self.btn_thumbnail_editor.setStyleSheet("background-color: #3498DB; font-size: 14px; padding: 8px; font-weight: bold;")
        buttons_layout.addWidget(self.btn_thumbnail_editor)
        
        # Botón de cerrar aplicación
        self.btn_close_app = QPushButton("❌ CERRAR TODO")
        self.btn_close_app.clicked.connect(self._close_application)
        self.btn_close_app.setStyleSheet("background-color: #95A5A6; font-size: 12px; padding: 6px; font-weight: bold;")
        buttons_layout.addWidget(self.btn_close_app)
        
        export_layout.addLayout(buttons_layout)
        
        main_layout.addWidget(export_frame)
        
        # Footer simple
        footer = QLabel("Type Beat Video Generator v1.0")
        footer.setAlignment(Qt.AlignRight)
        footer.setStyleSheet("color: #888888; font-size: 10px; padding: 5px;")
        main_layout.addWidget(footer)
        self.worker = None
    
    # === MÉTODOS DE CONFIGURACIÓN ===
    def _load_config(self):
        """Carga la configuración desde el archivo JSON."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return DEFAULT_CONFIG.copy()
        else:
            # Crear carpeta de configuración si no existe
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            
            # Guardar configuración predeterminada
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            
            return DEFAULT_CONFIG.copy()
    
    def _save_config(self):
        """Guarda la configuración en el archivo JSON."""
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, indent=2)
    
    def _save_window_state(self):
        """Guarda el estado de la ventana (posición, tamaño)."""
        settings = QSettings("TypeBeatVideoGen", "VideoGenerator")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("windowState", self.saveState())
        
    def _restore_window_state(self):
        """Restaura el estado de la ventana (posición, tamaño)."""
        settings = QSettings("TypeBeatVideoGen", "VideoGenerator")
        geometry = settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        window_state = settings.value("windowState")
        if window_state is not None:
            self.restoreState(window_state)
    
    def closeEvent(self, event):
        """Captura el evento de cierre de la ventana para guardar configuraciones."""
        self._save_window_state()
        super().closeEvent(event)
    
    def _setup_menu(self):
        """Configura el menú principal de la aplicación."""
        menubar = self.menuBar()
        
        # Menú Herramientas
        tools_menu = menubar.addMenu("Herramientas")
        
        # Acción para abrir editor de thumbnails
        thumbnail_editor_action = tools_menu.addAction("🎨 Editor de Thumbnails")
        thumbnail_editor_action.triggered.connect(self._open_thumbnail_editor)
        thumbnail_editor_action.setShortcut("Ctrl+T")
        thumbnail_editor_action.setStatusTip("Abrir el editor de thumbnails para crear miniaturas personalizadas")
        
        tools_menu.addSeparator()
        
        # Acción para abrir carpeta de salida
        open_output_action = tools_menu.addAction("📁 Abrir Carpeta de Videos")
        open_output_action.triggered.connect(self._open_output_folder)
        open_output_action.setStatusTip("Abrir la carpeta donde se guardan los videos generados")
        
        # Acción para abrir carpeta de overlays
        open_overlays_action = tools_menu.addAction("🖼️ Abrir Carpeta de Overlays")
        open_overlays_action.triggered.connect(self._open_overlays_folder)
        open_overlays_action.setStatusTip("Abrir la carpeta de overlays para thumbnails")
        
        # Menú Ayuda
        help_menu = menubar.addMenu("Ayuda")
        
        about_action = help_menu.addAction("Acerca de...")
        about_action.triggered.connect(self._show_about)
        
    def _open_output_folder(self):
        """Abre la carpeta de videos generados en el explorador."""
        try:
            if sys.platform == "win32":
                os.startfile(self.output_folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", self.output_folder])
            else:
                subprocess.Popen(["xdg-open", self.output_folder])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir la carpeta: {e}")
            
    def _open_overlays_folder(self):
        """Abre la carpeta de overlays para thumbnails."""
        overlays_folder = os.path.abspath("overlays")
        try:
            if not os.path.exists(overlays_folder):
                os.makedirs(overlays_folder, exist_ok=True)
                
            if sys.platform == "win32":
                os.startfile(overlays_folder)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", overlays_folder])
            else:
                subprocess.Popen(["xdg-open", overlays_folder])
        except Exception as e:
            QMessageBox.warning(self, "Error", f"No se pudo abrir la carpeta de overlays: {e}")
            
    def _show_about(self):
        """Muestra información sobre la aplicación."""
        QMessageBox.about(
            self,
            "Acerca de Type Beat Video Generator",
            """
            <h3>Type Beat Video Generator v2.0</h3>
            <p>Generador automático de videos para Type Beats con editor de thumbnails integrado.</p>
            <p><b>Características:</b></p>
            <ul>
            <li>Generación automática de videos</li>
            <li>Editor de thumbnails integrado</li>
            <li>Gestión de canales</li>
            <li>Soporte para múltiples formatos</li>
            </ul>
            <p>Desarrollado con PyQt6 y FFmpeg</p>
            """
        )

    # === MÉTODOS DE GESTIÓN DE BEATS ===
    def _update_beats_list(self):
        """Actualiza la lista de beats disponibles."""
        self.beats_list.clear()
        
        if os.path.exists(self.beats_folder):
            beats = [f for f in os.listdir(self.beats_folder) 
                    if f.lower().endswith(('.mp3', '.wav'))]
            self.loaded_beats = beats
            
            for beat in beats:
                item = QListWidgetItem()
                is_mp3 = beat.lower().endswith('.mp3')
                if is_mp3:
                    item.setIcon(qta.icon('fa5s.music', color='#4A9EFF'))
                else:
                    item.setIcon(qta.icon('fa5s.file-audio', color='#4CAF50'))
                
                item.setText(beat)
                item.setToolTip(f"Archivo: {beat}\nTipo: {'MP3' if is_mp3 else 'WAV'}")
                self.beats_list.addItem(item)
    
    def _load_beats(self):
        """Carga archivos de audio a la carpeta de beats."""
        file_dialog = QFileDialog()
        file_paths, _ = file_dialog.getOpenFileNames(
            self,
            "Seleccionar archivos de audio",
            "",
            "Archivos de audio (*.mp3 *.wav)"
        )
        
        if file_paths:
            for path in file_paths:
                filename = os.path.basename(path)
                dest_path = os.path.join(self.beats_folder, filename)
                
                if os.path.exists(dest_path):
                    response = QMessageBox.question(
                        self,
                        "Archivo duplicado",
                        f"El archivo '{filename}' ya existe. ¿Desea reemplazarlo?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    
                    if response == QMessageBox.No:
                        continue
                
                shutil.copy2(path, dest_path)
            
            self._update_beats_list()
    
    def _clear_beats(self):
        """Limpia la lista de beats seleccionados."""
        self.beats_list.clearSelection()
        self.beats_info = []
        self._update_process_list()
    
    def _delete_beat_files(self):
        """Elimina los archivos de beats seleccionados del disco."""
        selected_items = self.beats_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selección vacía", "Por favor, seleccione al menos un beat para eliminar.")
            return
        
        confirm = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"¿Está seguro de eliminar {len(selected_items)} archivo(s) del disco?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            for item in selected_items:
                file_name = item.text()
                file_path = os.path.join(self.beats_folder, file_name)
                try:
                    os.remove(file_path)
                    # Eliminar también de la lista de procesamiento
                    self.beats_info = [info for info in self.beats_info if info['audio'] != file_name]
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"No se pudo eliminar {file_name}: {str(e)}")
            
            self._update_beats_list()
            self._update_process_list()
    
    def _show_beats_list_menu(self, position):
        """Muestra un menú contextual para la lista de beats disponibles."""
        selected_items = self.beats_list.selectedItems()
        if not selected_items:
            return
            
        menu = QMenu()
        delete_action = menu.addAction("Eliminar archivo(s) del disco")
        select_all_action = menu.addAction("Seleccionar Todos")
        select_none_action = menu.addAction("Deseleccionar Todos")
        
        action = menu.exec_(self.beats_list.mapToGlobal(position))
        
        if action == delete_action:
            self._delete_beat_files()
        elif action == select_all_action:
            self.beats_list.selectAll()
        elif action == select_none_action:
            self.beats_list.clearSelection()
    
    # === MÉTODOS DE GESTIÓN DE CANALES ===
    def _update_channels_combo(self):
        """Actualiza la lista de canales en el combobox."""
        self.channel_combo.clear()
        
        channels = []
        if os.path.exists(self.images_folder):
            channels = [d for d in os.listdir(self.images_folder) 
                       if os.path.isdir(os.path.join(self.images_folder, d))]
        
        self.config['channels'] = channels
        self._save_config()
        
        self.channel_combo.addItems(channels)
        
        if channels:
            self.channel_combo.insertSeparator(len(channels))
        self.channel_combo.addItem("➕ Agregar nuevo canal...")
    
    def _update_groups_for_channel(self, channel):
        """Actualiza la lista de grupos disponibles para un canal."""
        if not hasattr(self, 'group_combo') or not channel:
            return
        
        # Verificar si se seleccionó "Agregar nuevo canal..."
        if channel == "➕ Agregar nuevo canal...":
            self._create_new_channel()
            return
        
        self.group_combo.clear()
        
        channel_folder = os.path.join(self.images_folder, channel)
        if os.path.exists(channel_folder):
            groups = [d for d in os.listdir(channel_folder) 
                     if os.path.isdir(os.path.join(channel_folder, d))]
            self.group_combo.addItems(groups)
    
    def _manage_channels(self):
        """Abre el diálogo para gestionar canales de YouTube."""
        
        # Crear diálogo personalizado para gestión de canales
        dialog = QDialog(self)
        dialog.setWindowTitle("Gestión de Canales")
        dialog.setModal(True)
        dialog.resize(500, 400)
        
        layout = QVBoxLayout(dialog)
        
        # Título
        title_label = QLabel("Gestión de Canales de YouTube")
        title_label.setProperty("heading", True)
        layout.addWidget(title_label)
        
        # Lista de canales existentes
        channels_label = QLabel("Canales existentes:")
        layout.addWidget(channels_label)
        
        channels_list = QListWidget()
        
        # Cargar canales existentes
        if os.path.exists(self.images_folder):
            existing_channels = [d for d in os.listdir(self.images_folder) 
                               if os.path.isdir(os.path.join(self.images_folder, d))]
            for channel in existing_channels:
                channels_list.addItem(channel)
        
        layout.addWidget(channels_list)
        
        # Botones de acción
        buttons_layout = QHBoxLayout()
        
        btn_create = QPushButton("➕ Crear Nuevo Canal")
        btn_create.clicked.connect(lambda: self._create_new_channel_from_dialog(dialog))
        buttons_layout.addWidget(btn_create)
        
        btn_open_folder = QPushButton("📁 Abrir Carpeta")
        btn_open_folder.clicked.connect(lambda: self._open_channel_folder(channels_list))
        buttons_layout.addWidget(btn_open_folder)
        
        btn_delete = QPushButton("🗑️ Eliminar Canal")
        btn_delete.clicked.connect(lambda: self._delete_channel(channels_list))
        buttons_layout.addWidget(btn_delete)
        
        layout.addWidget(QWidget())  # Spacer
        layout.addLayout(buttons_layout)
        
        # Botón cerrar
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(dialog.accept)
        layout.addWidget(btn_close)
        
        dialog.exec_()
        
        # Actualizar lista después de cerrar el diálogo
        self._update_channels_combo()
    
    def _create_new_channel(self):
        """Crear un nuevo canal de YouTube."""
        channel_name, ok = QInputDialog.getText(
            self, 
            "Nuevo Canal", 
            "Ingrese el nombre del nuevo canal de YouTube:",
            QLineEdit.Normal,
            ""
        )
        
        if not ok or not channel_name.strip():
            # Usuario canceló o no ingresó nombre, volver al canal anterior
            self._update_channels_combo()
            return
        
        channel_name = channel_name.strip()
        
        # Validar nombre del canal
        if not self._validate_channel_name(channel_name):
            QMessageBox.warning(
                self, 
                "Nombre inválido", 
                "El nombre del canal contiene caracteres no válidos.\n"
                "Use solo letras, números, guiones y espacios."
            )
            self._update_channels_combo()
            return
        
        # Verificar si el canal ya existe
        channel_folder = os.path.join(self.images_folder, channel_name)
        if os.path.exists(channel_folder):
            QMessageBox.warning(
                self, 
                "Canal existente", 
                f"El canal '{channel_name}' ya existe."
            )
            self._update_channels_combo()
            return
        
        try:
            # Crear carpeta del canal
            os.makedirs(channel_folder, exist_ok=True)
            
            # Crear grupo por defecto "Principal"
            default_group_folder = os.path.join(channel_folder, "Principal")
            os.makedirs(default_group_folder, exist_ok=True)
            
            # Crear archivo README con instrucciones
            readme_path = os.path.join(channel_folder, "README.txt")
            with open(readme_path, 'w', encoding='utf-8') as f:
                f.write(f"Canal: {channel_name}\n")
                f.write("=" * (len(channel_name) + 7) + "\n\n")
                f.write("Instrucciones:\n")
                f.write("1. Agregue las imágenes para este canal en las subcarpetas correspondientes\n")
                f.write("2. Cada subcarpeta representa un 'grupo' de imágenes (ej: Principal, Covers, etc.)\n")
                f.write("3. Use imágenes en formato JPG, PNG o BMP\n\n")
                f.write("Estructura recomendada:\n")
                f.write("├── Principal/       (imágenes generales del canal)\n")
                f.write("├── Covers/          (portadas de álbumes)\n")
                f.write("├── Artistas/        (imágenes de artistas)\n")
                f.write("└── Especiales/      (imágenes para eventos especiales)\n")
            
            QMessageBox.information(
                self, 
                "Canal creado", 
                f"Canal '{channel_name}' creado exitosamente.\n\n"
                f"Se creó la carpeta: {channel_folder}\n"
                f"Grupo por defecto: Principal\n\n"
                f"Agregue imágenes en las subcarpetas para usar con este canal."
            )
            
            # Actualizar lista de canales y seleccionar el nuevo
            self._update_channels_combo()
            
            # Seleccionar el nuevo canal creado
            index = self.channel_combo.findText(channel_name)
            if index >= 0:
                self.channel_combo.setCurrentIndex(index)
            
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"Error al crear el canal '{channel_name}':\n{str(e)}"
            )
            self._update_channels_combo()
    
    def _validate_channel_name(self, name):
        """Valida que el nombre del canal sea seguro para usar como nombre de carpeta."""
        import re
        # Permitir letras, números, espacios, guiones y algunos caracteres especiales seguros
        pattern = r'^[a-zA-Z0-9\s\-_\.()]+$'
        return bool(re.match(pattern, name)) and len(name) <= 50
    
    def _create_new_channel_from_dialog(self, parent_dialog):
        """Crear nuevo canal desde el diálogo de gestión."""
        self._create_new_channel()
        parent_dialog.accept()  # Cerrar diálogo de gestión
    
    def _open_channel_folder(self, channels_list):
        """Abrir la carpeta del canal seleccionado en el explorador."""
        current_item = channels_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selección vacía", "Seleccione un canal de la lista.")
            return
        
        channel_name = current_item.text()
        channel_folder = os.path.join(self.images_folder, channel_name)
        
        if os.path.exists(channel_folder):
            import platform
            if platform.system() == "Windows":
                os.startfile(channel_folder)
            elif platform.system() == "Darwin":  # macOS
                subprocess.Popen(["open", channel_folder])
            else:  # Linux
                subprocess.Popen(["xdg-open", channel_folder])
        else:
            QMessageBox.warning(self, "Carpeta no encontrada", f"La carpeta del canal '{channel_name}' no existe.")
    
    def _delete_channel(self, channels_list):
        """Eliminar canal seleccionado (solo si está vacío)."""
        current_item = channels_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Selección vacía", "Seleccione un canal de la lista.")
            return
        
        channel_name = current_item.text()
        channel_folder = os.path.join(self.images_folder, channel_name)
        
        # Confirmar eliminación
        reply = QMessageBox.question(
            self, 
            "Confirmar eliminación", 
            f"¿Está seguro de que desea eliminar el canal '{channel_name}'?\n\n"
            f"ADVERTENCIA: Esto eliminará permanentemente la carpeta:\n{channel_folder}\n\n"
            f"Solo se puede eliminar si la carpeta está vacía o contiene solo archivos README.",
            QMessageBox.Yes | QMessageBox.No, 
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            try:
                # Verificar si está vacío o solo tiene README
                if os.path.exists(channel_folder):
                    contents = os.listdir(channel_folder)
                    non_readme_files = [f for f in contents if not f.lower().startswith('readme')]
                    
                    if non_readme_files:
                        QMessageBox.warning(
                            self, 
                            "Canal no vacío", 
                            f"El canal '{channel_name}' contiene archivos o subcarpetas.\n"
                            f"Elimine todo el contenido primero antes de eliminar el canal."
                        )
                        return
                    
                    # Eliminar carpeta
                    shutil.rmtree(channel_folder)
                    QMessageBox.information(self, "Canal eliminado", f"Canal '{channel_name}' eliminado exitosamente.")
                    
                    # Actualizar lista
                    channels_list.takeItem(channels_list.currentRow())
                    
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Error al eliminar el canal:\n{str(e)}")
    
    def _assign_channel_and_group(self):
        """Asigna un canal y grupo a los beats seleccionados."""
        selected_items = self.beats_list.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(self, "Selección vacía", "Por favor, seleccione al menos un beat de la lista.")
            return
        
        current_channel = self.channel_combo.currentText()
        current_group = self.group_combo.currentText() or "Principal"
        
        if current_channel == "➕ Agregar nuevo canal...":
            QMessageBox.warning(self, "Selección inválida", "Por favor, seleccione un canal existente.")
            return
        
        for item in selected_items:
            beat_name = item.text()
            
            # Verificar si el beat ya está en la lista
            existing_index = -1
            for i, info in enumerate(self.beats_info):
                if info['audio'] == beat_name:
                    existing_index = i
                    break
            
            if existing_index >= 0:
                self.beats_info[existing_index]['channel'] = current_channel
                self.beats_info[existing_index]['group'] = current_group
            else:
                self.beats_info.append({
                    'audio': beat_name,
                    'channel': current_channel,
                    'group': current_group
                })
        
        self._update_process_list()
    
    # === MÉTODOS DE GESTIÓN DE PROCESOS ===
    def _update_process_list(self):
        """Actualiza la lista de beats a procesar."""
        self.process_list.clear()
        
        for info in self.beats_info:
            item = QListWidgetItem()
            item.setIcon(qta.icon('fa5s.video', color='#4A9EFF'))
            
            channel = info.get('channel', '')
            group = info.get('group', 'Principal')
            
            if info.get('custom_name'):
                display_text = f"{info['custom_name']} ({info['audio']}) | {channel} - {group}"
            else:
                display_text = f"{info['audio']} | {channel} - {group}"
            
            item.setText(display_text)
            item.setToolTip(f"Audio: {info['audio']}\nCanal: {channel}\nGrupo: {group}")
            self.process_list.addItem(item)
    
    def _edit_selected_beat_name(self):
        """Abre un diálogo para editar el nombre personalizado del beat seleccionado."""
        selected_items = self.process_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selección vacía", "Por favor, seleccione un beat de la lista para editar su nombre.")
            return
        
        selected_index = self.process_list.row(selected_items[0])
        if selected_index < 0 or selected_index >= len(self.beats_info):
            return
        
        beat_info = self.beats_info[selected_index]
        dialog = EditBeatNameDialog(beat_info, self)
        
        if dialog.exec_() == QDialog.Accepted:
            self.beats_info[selected_index]['custom_name'] = dialog.custom_name
            self._update_process_list()
    
    def _edit_beat_name(self, item):
        """Maneja el doble clic en un elemento de la lista de procesos."""
        self._edit_selected_beat_name()
    
    def _remove_selected_beat(self):
        """Quita los beats seleccionados de la lista de procesos."""
        selected_items = self.process_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Selección vacía", "Por favor, seleccione al menos un beat de la lista para eliminar.")
            return
        
        confirm = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"¿Está seguro de eliminar {len(selected_items)} beat(s) de la lista?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            indices = sorted([self.process_list.row(item) for item in selected_items], reverse=True)
            
            for index in indices:
                if index < len(self.beats_info):
                    del self.beats_info[index]
            
            self._update_process_list()
    
    def _show_process_list_menu(self, position):
        """Muestra un menú contextual para la lista de procesos."""
        menu = QMenu()
        edit_action = menu.addAction("Editar Nombre de Video")
        remove_action = menu.addAction("Quitar de la Lista")
        
        action = menu.exec_(self.process_list.mapToGlobal(position))
        
        if action == edit_action:
            self._edit_selected_beat_name()
        elif action == remove_action:
            self._remove_selected_beat()
    
    # === MÉTODOS DE EXPORTACIÓN ===
    def _browse_output(self):
        """Permite al usuario seleccionar la carpeta de salida."""
        folder_dialog = QFileDialog()
        folder_path = folder_dialog.getExistingDirectory(
            self,
            "Seleccionar carpeta de salida",
            self.output_folder
        )
        
        if folder_path:
            self.output_folder = folder_path
            self.output_path.setText(folder_path)
            self.config['last_output_folder'] = folder_path
            self._save_config()
    
    def _generate_videos(self):
        """Inicia el proceso de generación de videos."""
        if not self.beats_info:
            QMessageBox.warning(self, "Lista vacía", "No hay beats para procesar. Asigne canales y grupos a los beats primero.")
            return
        
        # Mostrar diálogo de configuración de thumbnails
        config_dialog = ThumbnailConfigDialog(self)
        if config_dialog.exec() != QDialog.DialogCode.Accepted:
            return  # Usuario canceló
            
        # Obtener configuración seleccionada
        thumbnail_config = config_dialog.get_config()
        
        if not os.path.exists(self.output_folder):
            try:
                os.makedirs(self.output_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo crear la carpeta de salida: {str(e)}")
                return
        
        self._set_ui_processing(True)
        
        self.worker = VideoGeneratorWorker(
            self.beats_folder,
            self.images_folder,
            self.output_folder,
            self.beats_info,
            thumbnail_config  # Pasar configuración al worker
        )
        
        self.worker.progress_updated.connect(self._update_progress)
        self.worker.finished.connect(self._process_finished)
        
        self.worker.start()
    
    def _cancel_process(self):
        """Cancela el proceso de generación de videos."""
        if self.worker and self.worker.isRunning():
            self.worker.stop_processing = True
    
    def _update_progress(self, value, message):
        """Actualiza la barra de progreso y el mensaje de estado."""
        self.progress_bar.setValue(value)
        self.status_label.setText(message)
    
    def _process_finished(self, success, message):
        """Maneja la finalización del proceso de generación."""
        self._set_ui_processing(False)
        
        if success:
            # Preguntar si quiere crear thumbnails automáticamente
            reply = QMessageBox.question(
                self, 
                "Proceso completado", 
                f"{message}\\n\\n¿Quieres abrir el editor de thumbnails para crear thumbnails para los videos generados?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self._open_thumbnail_editor()
            else:
                QMessageBox.information(self, "Completado", "Videos generados exitosamente")
        else:
            QMessageBox.warning(self, "Error", message)
    
    def _set_ui_processing(self, is_processing):
        """Habilita/deshabilita elementos de la interfaz durante el procesamiento."""
        self.btn_load_beats.setEnabled(not is_processing)
        self.btn_delete_beats.setEnabled(not is_processing)
        self.btn_assign_channel.setEnabled(not is_processing)
        self.btn_manage_channels.setEnabled(not is_processing)
        self.btn_upload_images.setEnabled(not is_processing)
        self.btn_browse_output.setEnabled(not is_processing)
        self.btn_generate.setEnabled(not is_processing)
        self.btn_cancel.setEnabled(is_processing)
        self.btn_thumbnail_editor.setEnabled(not is_processing)
        self.beats_list.setEnabled(not is_processing)
        self.process_list.setEnabled(not is_processing)
        self.btn_edit_name.setEnabled(not is_processing)
        self.btn_remove_beat.setEnabled(not is_processing)
    
    def _open_thumbnail_editor(self):
        """Abre el editor de thumbnails en una ventana separada."""
        try:
            # Importar el editor de thumbnails
            from thumbnail_editor import ThumbnailEditor
            
            # Crear y mostrar la ventana del editor
            self.thumbnail_editor_window = ThumbnailEditor()
            
            # Configurar el canal actual si hay uno seleccionado
            current_channel = self.channel_combo.currentText()
            if current_channel and current_channel != "➕ Agregar nuevo canal...":
                self.thumbnail_editor_window.channel_combo.setCurrentText(current_channel)
                
            # Mostrar la ventana
            self.thumbnail_editor_window.show()
            
            # Actualizar el status
            self.status_label.setText("Editor de thumbnails abierto")
            
        except ImportError as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"No se pudo cargar el editor de thumbnails: {e}\\n\\nAsegúrate de que thumbnail_editor.py existe."
            )
        except Exception as e:
            QMessageBox.critical(
                self, 
                "Error", 
                f"Error inesperado al abrir el editor de thumbnails: {e}"
            )
    
    def _generate_custom_thumbnails_for_channel(self, channel_name, output_folder):
        """Genera thumbnails personalizados usando las configuraciones guardadas del canal."""
        try:
            from thumbnail_config import ThumbnailConfig, OverlayConfigSerializer
            from thumbnail_editor import ThumbnailCanvas, OverlayLibrary
            from PyQt6.QtWidgets import QApplication
            
            # Cargar configuración del canal
            config_manager = ThumbnailConfig()
            channel_config = config_manager.load_config(channel_name)
            
            if not channel_config:
                print(f"No hay configuración guardada para el canal {channel_name}")
                return False
                
            # Crear canvas temporal para renderizar
            temp_canvas = ThumbnailCanvas()
            temp_library = OverlayLibrary()
            
            # Restaurar configuración
            OverlayConfigSerializer.deserialize_to_scene(
                channel_config, 
                temp_canvas.scene, 
                temp_library
            )
            
            # Renderizar y guardar
            thumbnail_image = temp_canvas.render_to_image()
            thumbnail_path = os.path.join(output_folder, f"{channel_name}_custom_thumbnail.png")
            
            if thumbnail_image.save(thumbnail_path):
                print(f"✓ Thumbnail personalizado generado: {channel_name}_custom_thumbnail.png")
                return True
            else:
                print(f"Error guardando thumbnail personalizado para {channel_name}")
                return False
                
        except Exception as e:
            print(f"Error generando thumbnail personalizado para {channel_name}: {e}")
            return False
    
    def _upload_images_to_channel(self):
        """Permite subir imágenes al canal seleccionado."""
        current_channel = self.channel_combo.currentText()
        
        # Validar que hay un canal seleccionado
        if not current_channel or current_channel == "➕ Agregar nuevo canal...":
            QMessageBox.warning(
                self, 
                "Sin canal seleccionado", 
                "Por favor, seleccione un canal válido antes de subir imágenes."
            )
            return
        
        # Verificar que el canal existe
        channel_folder = os.path.join(self.images_folder, current_channel)
        if not os.path.exists(channel_folder):
            reply = QMessageBox.question(
                self,
                "Canal no encontrado",
                f"La carpeta del canal '{current_channel}' no existe.\n"
                f"¿Desea crearla ahora?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                try:
                    os.makedirs(channel_folder, exist_ok=True)
                    os.makedirs(os.path.join(channel_folder, "Principal"), exist_ok=True)
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error al crear la carpeta del canal:\n{str(e)}")
                    return
            else:
                return
        
        # Obtener grupos disponibles
        groups = []
        if os.path.exists(channel_folder):
            groups = [d for d in os.listdir(channel_folder) 
                     if os.path.isdir(os.path.join(channel_folder, d))]
        
        if not groups:
            groups = ["Principal"]
            os.makedirs(os.path.join(channel_folder, "Principal"), exist_ok=True)
        
        # Seleccionar grupo
        group, ok = QInputDialog.getItem(
            self,
            "Seleccionar Grupo",
            f"Seleccione el grupo dentro del canal '{current_channel}':",
            groups,
            0,
            False
        )
        
        if not ok:
            return
        
        group_folder = os.path.join(channel_folder, group)
        
        # Seleccionar archivos de imagen
        file_dialog = QFileDialog()
        file_dialog.setFileMode(QFileDialog.ExistingFiles)
        file_dialog.setNameFilter("Imágenes (*.jpg *.jpeg *.png *.bmp *.gif *.tiff)")
        file_dialog.setViewMode(QFileDialog.Detail)
        
        if file_dialog.exec_():
            selected_files = file_dialog.selectedFiles()
            
            if not selected_files:
                return
            
            # Confirmar subida
            reply = QMessageBox.question(
                self,
                "Confirmar subida",
                f"¿Subir {len(selected_files)} imagen(es) a:\n"
                f"Canal: {current_channel}\n"
                f"Grupo: {group}\n\n"
                f"Carpeta destino: {group_folder}",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            )
            
            if reply == QMessageBox.Yes:
                try:
                    copied_files = 0
                    errors = []
                    
                    for source_file in selected_files:
                        filename = os.path.basename(source_file)
                        destination = os.path.join(group_folder, filename)
                        
                        # Verificar si el archivo ya existe
                        if os.path.exists(destination):
                            reply = QMessageBox.question(
                                self,
                                "Archivo existente",
                                f"El archivo '{filename}' ya existe.\n¿Desea reemplazarlo?",
                                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                                QMessageBox.No
                            )
                            
                            if reply == QMessageBox.Cancel:
                                break
                            elif reply == QMessageBox.No:
                                continue
                        
                        try:
                            shutil.copy2(source_file, destination)
                            copied_files += 1
                        except Exception as e:
                            errors.append(f"{filename}: {str(e)}")
                    
                    # Mostrar resultado
                    message = f"Subida completada:\n✅ {copied_files} archivo(s) copiado(s)"
                    if errors:
                        message += f"\n❌ {len(errors)} error(es):\n" + "\n".join(errors[:3])
                        if len(errors) > 3:
                            message += f"\n... y {len(errors) - 3} error(es) más"
                    
                    QMessageBox.information(self, "Subida de imágenes", message)
                    
                    # Actualizar la lista de grupos si es necesario
                    self._update_groups_for_channel(current_channel)
                    
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"Error durante la subida:\n{str(e)}")
    
    def _close_application(self):
        """Cierra la aplicación completamente."""
        reply = QMessageBox.question(
            self,
            "Cerrar aplicación",
            "¿Está seguro de que desea cerrar la aplicación?\n\n"
            "Se perderán los datos no guardados.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Cancelar cualquier proceso en curso
            if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
                self.worker.terminate()
                self.worker.wait(3000)  # Esperar máximo 3 segundos
            
            # Cerrar aplicación
            QApplication.quit()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
