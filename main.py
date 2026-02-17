#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Type Beat Video Generator - Versión Completa
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
from PyQt5.QtWidgets import (QApplication, QMainWindow, QLabel, QPushButton, 
                            QVBoxLayout, QHBoxLayout, QWidget, QFileDialog, 
                            QListWidget, QComboBox, QProgressBar, QMessageBox,
                            QDialog, QLineEdit, QGridLayout, QMenu, QFrame,
                            QSplitter, QStyleFactory, QToolButton, QListWidgetItem,
                            QSizePolicy, QTabWidget, QInputDialog, QGraphicsDropShadowEffect,
                            QMenuBar, QGroupBox, QCheckBox, QRadioButton, QAction)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QRect, QSettings, QPoint, QTimer
from PyQt5.QtGui import QPixmap, QIcon, QColor, QPalette, QFont, QCursor, QLinearGradient, QPainter, QPainterPath

# Importar estilos y bibliotecas para la interfaz moderna
import qdarkstyle
import qtawesome as qta

# Importar diálogos
from edit_beat_dialog import EditBeatNameDialog
from content_selection_dialog import ContentSelectionDialog

# Constantes
CONFIG_FILE = os.path.join('config', 'app_config.json')
DEFAULT_CONFIG = {
    'last_output_folder': 'exported_videos',
    'channels': []  # Lista de canales de YouTube conocidos
}

# Estilos profesionales
STYLESHEET = """
QMainWindow {
    background-color: #2b2b2b;
    color: white;
}

QLabel {
    color: white;
    font-size: 12px;
    padding: 2px;
}

QPushButton {
    background-color: #404040;
    color: white;
    border: 1px solid #555;
    padding: 8px;
    border-radius: 4px;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #505050;
}

QPushButton:pressed {
    background-color: #606060;
}

QFrame {
    background-color: #353535;
    border: 1px solid #555;
    border-radius: 8px;
    margin: 2px;
}

QListWidget {
    background-color: #404040;
    color: white;
    border: 1px solid #555;
    selection-background-color: #0078D4;
    padding: 4px;
}

QComboBox {
    background-color: #404040;
    color: white;
    border: 1px solid #555;
    padding: 4px;
    border-radius: 4px;
}

QProgressBar {
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    background-color: #404040;
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
    
    def __init__(self, beats_folder, images_folder, output_folder, beats_info, content_type="images", main_window=None):
        super().__init__()
        self.beats_folder = beats_folder
        self.images_folder = images_folder
        self.output_folder = output_folder
        self.beats_info = beats_info
        self.content_type = content_type
        self.main_window = main_window  # Referencia para usar funciones de selección
        self.stop_processing = False
    
    def run(self):
        """Ejecuta el proceso de generación de videos."""
        try:
            total_beats = len(self.beats_info)
            successful_videos = 0
            
            for i, beat_info in enumerate(self.beats_info):
                if self.stop_processing:
                    break
                    
                beat_file = beat_info['beat_file']
                channel = beat_info['channel']
                group = beat_info['group']
                custom_name = beat_info.get('custom_name', '')
                
                # Actualizar progreso
                progress = int((i / total_beats) * 100)
                self.progress_updated.emit(progress, f"Procesando: {beat_file} ({i+1}/{total_beats})")
                
                # Buscar contenido para este beat usando el sistema anti-duplicados
                if self.main_window:
                    content_file = self.main_window._select_unique_content(channel, group, self.content_type)
                else:
                    # Fallback al método anterior
                    if self.content_type == "videos":
                        content_file = self._find_video_for_beat(channel, group)
                    else:
                        content_file = self._find_image_for_beat(channel, group)
                
                if not content_file:
                    content_name = "video" if self.content_type == "videos" else "imagen"
                    print(f"⚠️ No se encontró {content_name} para {beat_file} en {channel}/{group}")
                    continue
                
                # Crear carpeta de salida específica
                group_output_folder = os.path.join(self.output_folder, channel, group)
                os.makedirs(group_output_folder, exist_ok=True)
                
                # Generar video
                audio_file = os.path.join(self.beats_folder, beat_file)
                
                # Usar nombre personalizado o generar automático
                if custom_name:
                    base_output_name = custom_name
                else:
                    base_output_name = f"{os.path.splitext(beat_file)[0]}_{channel}_{group}"
                
                success = self._generate_video(content_file, audio_file, channel, group_output_folder, base_output_name, self.content_type)
                
                if success:
                    successful_videos += 1
                    # Copiar contenido utilizado para referencia
                    if self.content_type == "images":
                        content_copy_path = os.path.join(group_output_folder, f"{base_output_name}_imagen.jpg")
                        try:
                            shutil.copy2(content_file, content_copy_path)
                        except:
                            pass
                    # Para videos no copiamos ya que son archivos más grandes
                else:
                    print(f"❌ Error generando video para {beat_file}")
                
            # Mensaje final
            if successful_videos == total_beats:
                self.progress_updated.emit(100, "¡Proceso completado!")
                self.finished.emit(True, f"✅ ¡Proceso completado! Se generaron {successful_videos} videos de {total_beats} beats.")
            else:
                self.finished.emit(True, f"⚠️ Proceso completado con advertencias. Se generaron {successful_videos} videos de {total_beats} beats.")
            
        except Exception as e:
            self.finished.emit(False, f"Error en el procesamiento: {str(e)}")
    
    def _find_image_for_beat(self, channel, group):
        """Busca una imagen apropiada para el beat."""
        # Buscar en carpeta específica del canal y grupo
        channel_group_path = os.path.join(self.images_folder, channel, group)
        
        if os.path.exists(channel_group_path):
            images = [f for f in os.listdir(channel_group_path) 
                     if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
            if images:
                return os.path.join(channel_group_path, random.choice(images))
        
        # Buscar en carpeta del canal (cualquier grupo)
        channel_path = os.path.join(self.images_folder, channel)
        if os.path.exists(channel_path):
            for subdir in os.listdir(channel_path):
                subdir_path = os.path.join(channel_path, subdir)
                if os.path.isdir(subdir_path):
                    images = [f for f in os.listdir(subdir_path) 
                             if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
                    if images:
                        return os.path.join(subdir_path, random.choice(images))
        
        # Buscar en carpeta general
        if os.path.exists(self.images_folder):
            images = [f for f in os.listdir(self.images_folder) 
                     if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))]
            if images:
                return os.path.join(self.images_folder, random.choice(images))
        
        return None
    
    def _find_video_for_beat(self, channel, group):
        """Busca un video apropiado para el beat (método fallback)."""
        # Buscar en carpeta específica del canal y grupo
        channel_group_path = os.path.join("videos", channel, group)
        
        if os.path.exists(channel_group_path):
            videos = [f for f in os.listdir(channel_group_path) 
                     if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.wmv'))]
            if videos:
                return os.path.join(channel_group_path, random.choice(videos))
        
        # Buscar en carpeta del canal (cualquier grupo)
        channel_path = os.path.join("videos", channel)
        if os.path.exists(channel_path):
            for subdir in os.listdir(channel_path):
                subdir_path = os.path.join(channel_path, subdir)
                if os.path.isdir(subdir_path):
                    videos = [f for f in os.listdir(subdir_path) 
                             if f.lower().endswith(('.mp4', '.mov', '.avi', '.mkv', '.wmv'))]
                    if videos:
                        return os.path.join(subdir_path, random.choice(videos))
        
        return None
    
    def _generate_video(self, content_path, audio_path, channel, output_folder, base_name, content_type="images"):
        """Genera un video combinando imagen/video con audio."""
        try:
            output_file = os.path.join(output_folder, f"{base_name}.mp4")
            
            # Comando FFmpeg para generar video
            ffmpeg_path = os.path.join("bin", "ffmpeg.exe") if os.name == 'nt' else "ffmpeg"
            # Obtener la duración del audio con ffprobe para forzar la duración final
            audio_duration = self._get_media_duration(audio_path)
            duration_args = []
            if audio_duration is not None:
                duration_args = ["-t", f"{audio_duration:.3f}"]

            if content_type == "videos":
                # Para videos: loop del video y limitar duración al audio (más robusto)
                cmd = [
                    ffmpeg_path,
                    "-stream_loop", "-1",  # Loop infinito del video (será recortado por -t)
                    "-i", content_path,
                    "-i", audio_path,
                    # Mapear explícitamente para evitar ambigüedades
                    "-map", "0:v",
                    "-map", "1:a",
                    "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                ] + duration_args + [
                    "-y",
                    output_file
                ]
            else:
                # Para imágenes: loop estático, limitar duración al audio
                cmd = [
                    ffmpeg_path,
                    "-loop", "1",
                    "-i", content_path,
                    "-i", audio_path,
                    "-vf", "scale=-1:1080,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black",
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-tune", "stillimage",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                ] + duration_args + [
                    "-y",
                    output_file
                ]
            
            # Ejecutar comando
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                content_name = "video looped" if content_type == "videos" else "imagen"
                print(f"✓ Video generado con {content_name}: {os.path.basename(output_file)}")
                return True
            else:
                print(f"✗ Error FFmpeg: {result.stderr}")
                return False
                
        except Exception as e:
            print(f"Error generando video: {e}")
            return False

    def _get_media_duration(self, media_path):
        """Devuelve la duración en segundos (float) de un archivo multimedia usando ffprobe, o None si falla."""
        try:
            ffprobe_path = os.path.join("bin", "ffprobe.exe") if os.name == 'nt' else "ffprobe"
            cmd = [
                ffprobe_path,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                media_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                out = result.stdout.strip()
                if out:
                    try:
                        return float(out)
                    except:
                        return None
            return None
        except Exception:
            return None
    
    def stop(self):
        """Detiene el proceso."""
        self.stop_processing = True


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
            "Agrega imágenes (JPG, PNG) a esta carpeta.\n"
            "Se recomiendan 10-30 imágenes por grupo para mayor variedad."
        )
    
    def accept(self):
        """Guarda la configuración al aceptar."""
        self.save_config()
        super().accept()


class MainWindow(QMainWindow):
    """Ventana principal de la aplicación."""
    
    def __init__(self):
        super().__init__()
        
        # Inicializar variables
        self.beats_folder = os.path.abspath("beats")
        self.images_folder = os.path.abspath("images")
        self.output_folder = os.path.abspath("exported_videos")
        self.beats_info = []  # Lista de beats asignados para procesamiento
        self.worker = None
        
        # Sistema anti-duplicados
        self.used_content_files = []  # Archivos ya utilizados en la sesión actual
        self.current_content_type = "images"  # Tipo de contenido seleccionado
        
        # Configurar ventana
        self.setWindowTitle("🎵 Type Beat Video Generator v2.0")
        self.setMinimumSize(1200, 700)
        self.resize(1400, 800)
        
        # Aplicar estilos
        self.setStyleSheet(STYLESHEET)
        
        # Configurar interfaz
        self.setup_ui()
        self.load_config()
        
        # Cargar datos iniciales
        self._load_beats()
        self._load_channels()
        
        # Configurar atajos de teclado
        self._setup_shortcuts()
        
        print("✅ Type Beat Video Generator v2.0 iniciado")
    
    def _setup_shortcuts(self):
        """Configura atajos de teclado para operaciones comunes."""
        from PyQt5.QtWidgets import QShortcut
        from PyQt5.QtGui import QKeySequence
        
        # Ctrl+A para seleccionar todos los beats
        select_all_shortcut = QShortcut(QKeySequence("Ctrl+A"), self)
        select_all_shortcut.activated.connect(lambda: self.select_all_checkbox.setChecked(True))
        
        # Ctrl+D para deseleccionar todos
        deselect_all_shortcut = QShortcut(QKeySequence("Ctrl+D"), self)
        deselect_all_shortcut.activated.connect(lambda: self.select_all_checkbox.setChecked(False))
        
        # Delete para eliminar beats seleccionados
        delete_shortcut = QShortcut(QKeySequence("Delete"), self)
        delete_shortcut.activated.connect(self._delete_selected_beats)
        
        # Enter para asignar canal a beats seleccionados
        assign_shortcut = QShortcut(QKeySequence("Return"), self)
        assign_shortcut.activated.connect(self._assign_channel_to_beats)
    
    def setup_ui(self):
        """Configura la interfaz de usuario (3 columnas)."""
        # Widget central
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Layout principal (3 columnas)
        main_layout = QHBoxLayout(central_widget)
        
        # === COLUMNA 1: GESTIÓN DE BEATS ===
        left_panel = QFrame()
        left_panel.setMaximumWidth(350)
        left_layout = QVBoxLayout(left_panel)
        
        # Título de la columna
        beats_title = QLabel("🎵 Gestión de Beats")
        beats_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px; text-align: center;")
        beats_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(beats_title)
        
        # Botones de gestión de beats
        beats_buttons = QHBoxLayout()
        self.btn_load_beats = QPushButton("📂 Cargar Beats")
        self.btn_load_beats.clicked.connect(self._load_beats_from_files)
        self.btn_delete_beats = QPushButton("🗑️ Eliminar")
        self.btn_delete_beats.clicked.connect(self._delete_selected_beats)
        
        beats_buttons.addWidget(self.btn_load_beats)
        beats_buttons.addWidget(self.btn_delete_beats)
        left_layout.addLayout(beats_buttons)
        
        # Lista de beats disponibles
        beats_label = QLabel("📁 Beats Disponibles:")
        beats_label.setStyleSheet("font-weight: bold; padding: 5px;")
        left_layout.addWidget(beats_label)
        
        # Control de selección múltiple
        selection_layout = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Seleccionar todos")
        self.select_all_checkbox.stateChanged.connect(self._toggle_select_all_beats)
        selection_layout.addWidget(self.select_all_checkbox)
        
        # Contador de beats seleccionados
        self.selected_count_label = QLabel("0 seleccionados")
        self.selected_count_label.setStyleSheet("color: #3498DB; font-size: 10px;")
        selection_layout.addWidget(self.selected_count_label)
        selection_layout.addStretch()
        
        left_layout.addLayout(selection_layout)

        self.beats_list = QListWidget()
        self.beats_list.setMaximumHeight(200)
        self.beats_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.beats_list.itemSelectionChanged.connect(self._update_selection_count)
        left_layout.addWidget(self.beats_list)
        
        # Botones de acción para beats
        beats_actions_layout = QHBoxLayout()
        
        self.btn_edit_name = QPushButton("✏️ Editar Nombre")
        self.btn_edit_name.clicked.connect(self._edit_beat_name)
        beats_actions_layout.addWidget(self.btn_edit_name)
        
        self.btn_delete_selected = QPushButton("🗑️ Eliminar Seleccionados")
        self.btn_delete_selected.clicked.connect(self._delete_selected_beats)
        self.btn_delete_selected.setStyleSheet("background-color: #E74C3C; color: white; font-weight: bold;")
        beats_actions_layout.addWidget(self.btn_delete_selected)
        
        left_layout.addLayout(beats_actions_layout)
        
        left_layout.addStretch()
        
        # === COLUMNA 2: CONFIGURACIÓN DE CANALES ===
        center_panel = QFrame()
        center_panel.setMaximumWidth(400)
        center_layout = QVBoxLayout(center_panel)
        
        # Título de la columna
        config_title = QLabel("📺 Configuración de Canales")
        config_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px; text-align: center;")
        config_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.addWidget(config_title)
        
        # Gestión de canales
        self.btn_manage_channels = QPushButton("⚙️ Gestionar Canales")
        self.btn_manage_channels.clicked.connect(self._open_channel_manager)
        center_layout.addWidget(self.btn_manage_channels)
        
        # Selector de canal
        channel_label = QLabel("Canal:")
        channel_label.setStyleSheet("font-weight: bold; padding: 5px;")
        center_layout.addWidget(channel_label)
        
        self.channel_combo = QComboBox()
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        center_layout.addWidget(self.channel_combo)
        
        # Selector de grupo
        group_label = QLabel("Grupo:")
        group_label.setStyleSheet("font-weight: bold; padding: 5px;")
        center_layout.addWidget(group_label)
        
        self.group_combo = QComboBox()
        center_layout.addWidget(self.group_combo)
        
        # Botón de asignación
        self.btn_assign_channel = QPushButton("➡️ Asignar Canal a Seleccionados")
        self.btn_assign_channel.setStyleSheet("background-color: #27AE60; font-size: 14px; padding: 10px; font-weight: bold;")
        self.btn_assign_channel.clicked.connect(self._assign_channel_to_beats)
        center_layout.addWidget(self.btn_assign_channel)
        
        # Información de imágenes
        self.images_info_label = QLabel("Selecciona un canal y grupo para ver información de imágenes")
        self.images_info_label.setStyleSheet("padding: 10px; font-size: 12px; color: #888;")
        self.images_info_label.setWordWrap(True)
        center_layout.addWidget(self.images_info_label)
        
        # Botón para subir contenido (imágenes y videos)
        self.btn_upload_images = QPushButton("� Subir Contenido")
        self.btn_upload_images.clicked.connect(self._upload_content_to_channel)
        center_layout.addWidget(self.btn_upload_images)
        
        center_layout.addStretch()
        
        # === COLUMNA 3: LISTA DE PROCESAMIENTO ===
        right_panel = QFrame()
        right_layout = QVBoxLayout(right_panel)
        
        # Título de la columna
        process_title = QLabel("🎬 Lista de Procesamiento")
        process_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px; text-align: center;")
        process_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(process_title)
        
        # Lista de beats asignados
        assigned_label = QLabel("📋 Beats Listos para Procesar:")
        assigned_label.setStyleSheet("font-weight: bold; padding: 5px;")
        right_layout.addWidget(assigned_label)
        
        self.process_list = QListWidget()
        self.process_list.setMaximumHeight(250)
        self.process_list.itemDoubleClicked.connect(self._edit_assigned_beat)
        right_layout.addWidget(self.process_list)
        
        # Botones de control de procesamiento
        process_buttons = QHBoxLayout()
        self.btn_remove_from_process = QPushButton("❌ Quitar")
        self.btn_remove_from_process.clicked.connect(self._remove_from_process_list)
        self.btn_clear_process = QPushButton("🗑️ Limpiar Todo")
        self.btn_clear_process.clicked.connect(self._clear_process_list)
        
        process_buttons.addWidget(self.btn_remove_from_process)
        process_buttons.addWidget(self.btn_clear_process)
        right_layout.addLayout(process_buttons)
        
        # Configuración de salida
        output_label = QLabel("📁 Carpeta de Salida:")
        output_label.setStyleSheet("font-weight: bold; padding: 5px; margin-top: 10px;")
        right_layout.addWidget(output_label)
        
        self.btn_browse_output = QPushButton("📂 Seleccionar Carpeta")
        self.btn_browse_output.clicked.connect(self._browse_output_folder)
        right_layout.addWidget(self.btn_browse_output)
        
        self.output_label = QLabel(f"📍 {self.output_folder}")
        self.output_label.setStyleSheet("padding: 5px; font-size: 11px; color: #888;")
        self.output_label.setWordWrap(True)
        right_layout.addWidget(self.output_label)
        
        # Botones principales
        main_buttons = QVBoxLayout()
        
        self.btn_generate = QPushButton("▶️ GENERAR VIDEOS")
        self.btn_generate.setStyleSheet("background-color: #27AE60; font-size: 16px; padding: 15px; font-weight: bold;")
        self.btn_generate.clicked.connect(self._start_generation)
        main_buttons.addWidget(self.btn_generate)
        
        self.btn_cancel = QPushButton("⏹️ CANCELAR")
        self.btn_cancel.setStyleSheet("background-color: #E74C3C; font-size: 14px; padding: 10px; font-weight: bold;")
        self.btn_cancel.clicked.connect(self._cancel_generation)
        self.btn_cancel.setEnabled(False)
        main_buttons.addWidget(self.btn_cancel)
        
        # Espaciado
        main_buttons.addSpacing(20)
        
        # Botón para cerrar programa
        self.btn_exit = QPushButton("🚪 CERRAR PROGRAMA")
        self.btn_exit.setStyleSheet("background-color: #95A5A6; font-size: 12px; padding: 8px; font-weight: bold;")
        self.btn_exit.clicked.connect(self.close)
        main_buttons.addWidget(self.btn_exit)
        
        right_layout.addLayout(main_buttons)
        
        # Progreso
        progress_label = QLabel("📊 Progreso:")
        progress_label.setStyleSheet("font-weight: bold; padding: 5px; margin-top: 10px;")
        right_layout.addWidget(progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        right_layout.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Listo para generar videos")
        self.status_label.setStyleSheet("padding: 10px; font-size: 12px; color: #888;")
        right_layout.addWidget(self.status_label)
        
        # Agregar columnas al layout principal
        main_layout.addWidget(left_panel)
        main_layout.addWidget(center_panel)
        main_layout.addWidget(right_panel, stretch=1)
    
    def load_config(self):
        """Carga la configuración desde archivo."""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.output_folder = config.get('last_output_folder', self.output_folder)
                    self.output_label.setText(f"📍 {self.output_folder}")
        except Exception as e:
            print(f"Error cargando config: {e}")
    
    def save_config(self):
        """Guarda la configuración a archivo."""
        try:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            
            # Cargar configuración existente
            config = DEFAULT_CONFIG.copy()
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config.update(json.load(f))
            
            # Actualizar configuración
            config['last_output_folder'] = self.output_folder
            
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error guardando config: {e}")
    
    def _load_beats(self):
        """Carga los archivos de beat desde la carpeta beats."""
        self.beats_list.clear()
        
        if not os.path.exists(self.beats_folder):
            os.makedirs(self.beats_folder, exist_ok=True)
            self.status_label.setText("Carpeta 'beats' creada. Añade archivos de audio.")
            return
        
        # Buscar archivos de audio
        audio_extensions = ['.mp3', '.wav', '.m4a', '.aac', '.flac']
        beat_files = []
        
        for file in os.listdir(self.beats_folder):
            if any(file.lower().endswith(ext) for ext in audio_extensions):
                beat_files.append(file)
        
        # Añadir a la lista
        for beat_file in sorted(beat_files):
            self.beats_list.addItem(beat_file)
        
        self.status_label.setText(f"Cargados {len(beat_files)} archivos de beat")
        self._update_selection_count()  # Actualizar contador de selección
    
    def _load_beats_from_files(self):
        """Permite cargar beats desde archivos."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar archivos de beat",
            "",
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac)"
        )
        
        if files:
            copied_files = 0
            for file in files:
                try:
                    filename = os.path.basename(file)
                    dest_path = os.path.join(self.beats_folder, filename)
                    if not os.path.exists(dest_path):
                        shutil.copy2(file, dest_path)
                        copied_files += 1
                except Exception as e:
                    print(f"Error copiando {file}: {e}")
            
            self._load_beats()
            self.status_label.setText(f"Se copiaron {copied_files} archivos nuevos")
    
    def _load_channels(self):
        """Carga los canales desde la configuración."""
        self.channel_combo.clear()
        self.channel_combo.addItem("Seleccionar canal...")
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    channels = config.get('channels', {})
                    
                    for channel_name in sorted(channels.keys()):
                        self.channel_combo.addItem(channel_name)
        except Exception as e:
            print(f"Error cargando canales: {e}")
    
    def _on_channel_changed(self, channel_name):
        """Se ejecuta cuando cambia el canal seleccionado."""
        self.group_combo.clear()
        self.group_combo.addItem("Seleccionar grupo...")
        
        if not channel_name or channel_name == "Seleccionar canal...":
            self.images_info_label.setText("Selecciona un canal y grupo para ver información de imágenes")
            return
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    channels = config.get('channels', {})
                    
                    if channel_name in channels:
                        groups = channels[channel_name].get('groups', [])
                        for group in groups:
                            self.group_combo.addItem(group)
                        
                        self._update_images_info()
        except Exception as e:
            print(f"Error cargando grupos: {e}")
    
    def _update_images_info(self):
        """Actualiza la información de imágenes del canal/grupo seleccionado."""
        channel = self.channel_combo.currentText()
        group = self.group_combo.currentText()
        
        if not channel or channel == "Seleccionar canal..." or not group or group == "Seleccionar grupo...":
            self.images_info_label.setText("Selecciona un canal y grupo para ver información de imágenes")
            return
        
        images_path = os.path.join(self.images_folder, channel, group)
        
        if not os.path.exists(images_path):
            self.images_info_label.setText(f"📁 Carpeta: {channel}/{group}\n❌ No existe la carpeta de imágenes")
            return
        
        # Contar imágenes
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
        image_count = 0
        
        for file in os.listdir(images_path):
            if any(file.lower().endswith(ext) for ext in image_extensions):
                image_count += 1
        
        if image_count == 0:
            self.images_info_label.setText(f"📁 Carpeta: {channel}/{group}\n⚠️ No hay imágenes en esta carpeta")
        else:
            self.images_info_label.setText(f"📁 Carpeta: {channel}/{group}\n✅ {image_count} imágenes disponibles")
    
    def _open_channel_manager(self):
        """Abre el gestor de canales."""
        manager = ChannelManager(self, CONFIG_FILE)
        if manager.exec() == QDialog.DialogCode.Accepted:
            # Recargar canales
            self._load_channels()
            self.status_label.setText("Configuración de canales actualizada")
    
    def _assign_channel_to_beats(self):
        """Asigna canal y grupo a los beats seleccionados."""
        selected_beats = self.beats_list.selectedItems()
        
        if not selected_beats:
            QMessageBox.warning(self, "Selección vacía", "Selecciona al menos un beat para asignar.")
            return
        
        channel = self.channel_combo.currentText()
        group = self.group_combo.currentText()
        
        if not channel or channel == "Seleccionar canal..." or not group or group == "Seleccionar grupo...":
            QMessageBox.warning(self, "Configuración incompleta", "Selecciona un canal y grupo válido.")
            return
        
        # Verificar que existan imágenes
        images_path = os.path.join(self.images_folder, channel, group)
        if not os.path.exists(images_path):
            QMessageBox.warning(self, "Sin imágenes", f"No existe la carpeta de imágenes para {channel}/{group}")
            return
        
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp']
        image_count = sum(1 for f in os.listdir(images_path) if any(f.lower().endswith(ext) for ext in image_extensions))
        
        if image_count == 0:
            QMessageBox.warning(self, "Sin imágenes", f"No hay imágenes en la carpeta {channel}/{group}")
            return
        
        # Confirmar operación masiva
        selected_count = len(selected_beats)
        if selected_count > 1:
            reply = QMessageBox.question(
                self, "Confirmar Asignación Masiva",
                f"¿Asignar {selected_count} beats al canal '{channel}' grupo '{group}'?\n\n"
                f"Imágenes disponibles: {image_count}",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        
        # Asignar beats
        assigned_count = 0
        already_assigned_count = 0
        for beat_item in selected_beats:
            beat_file = beat_item.text()
            
            # Verificar si ya está asignado
            already_assigned = False
            for beat_info in self.beats_info:
                if beat_info['beat_file'] == beat_file:
                    already_assigned = True
                    already_assigned_count += 1
                    break
            
            if not already_assigned:
                self.beats_info.append({
                    'beat_file': beat_file,
                    'channel': channel,
                    'group': group,
                    'custom_name': ''
                })
                assigned_count += 1
        
        self._update_process_list()
        
        # Mensaje de estado detallado
        status_message = f"✅ Asignados {assigned_count} beats a {channel}/{group}"
        if already_assigned_count > 0:
            status_message += f" ({already_assigned_count} ya estaban asignados)"
        
        self.status_label.setText(status_message)
        
        # Limpiar selección después de la asignación
        self.beats_list.clearSelection()
    
    def _update_process_list(self):
        """Actualiza la lista de procesamiento."""
        self.process_list.clear()
        
        for beat_info in self.beats_info:
            display_name = beat_info.get('custom_name', '') or beat_info['beat_file']
            item_text = f"{display_name} → {beat_info['channel']}/{beat_info['group']}"
            self.process_list.addItem(item_text)
    
    def _edit_assigned_beat(self, item):
        """Edita el nombre personalizado de un beat asignado."""
        index = self.process_list.row(item)
        if 0 <= index < len(self.beats_info):
            beat_info = self.beats_info[index]
            
            dialog = EditBeatNameDialog(beat_info, self)
            dialog.set_beat_info(beat_info['beat_file'], beat_info.get('custom_name', ''))
            
            if dialog.exec() == QDialog.DialogCode.Accepted:
                new_name = dialog.get_custom_name()
                self.beats_info[index]['custom_name'] = new_name
                self._update_process_list()
    
    def _edit_beat_name(self):
        """Edita el nombre de un beat seleccionado (antes de asignar)."""
        current_item = self.beats_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "Sin selección", "Selecciona un beat para editar su nombre.")
            return
        
        beat_file = current_item.text()
        dialog = EditBeatNameDialog(self)
        dialog.set_beat_info(beat_file, "")
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_name = dialog.get_custom_name()
            if new_name:
                # Renombrar archivo físico
                old_path = os.path.join(self.beats_folder, beat_file)
                new_filename = f"{new_name}.{beat_file.split('.')[-1]}"
                new_path = os.path.join(self.beats_folder, new_filename)
                
                try:
                    os.rename(old_path, new_path)
                    self._load_beats()
                    self.status_label.setText(f"Beat renombrado a: {new_filename}")
                except Exception as e:
                    QMessageBox.critical(self, "Error", f"No se pudo renombrar el archivo: {e}")
    
    def _remove_from_process_list(self):
        """Quita beats de la lista de procesamiento."""
        selected_items = self.process_list.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(self, "Sin selección", "Selecciona beats para quitar de la lista.")
            return
        
        # Obtener índices en orden inverso para evitar problemas al eliminar
        indices = [self.process_list.row(item) for item in selected_items]
        indices.sort(reverse=True)
        
        for index in indices:
            if 0 <= index < len(self.beats_info):
                del self.beats_info[index]
        
        self._update_process_list()
        self.status_label.setText(f"Quitados {len(indices)} beats de la lista")
    
    def _clear_process_list(self):
        """Limpia toda la lista de procesamiento."""
        if self.beats_info:
            reply = QMessageBox.question(
                self, "Confirmar", 
                "¿Limpiar toda la lista de procesamiento?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self.beats_info.clear()
                self._update_process_list()
                self.status_label.setText("Lista de procesamiento limpiada")
    
    def _delete_selected_beats(self):
        """Elimina los beats seleccionados."""
        selected_items = self.beats_list.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(self, "Selección vacía", "Selecciona al menos un beat para eliminar.")
            return
        
        reply = QMessageBox.question(
            self, "Confirmar eliminación",
            f"¿Estás seguro de que quieres eliminar {len(selected_items)} beat(s)?\n\n"
            f"Esta acción eliminará permanentemente los archivos del disco.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            deleted_count = 0
            error_count = 0
            
            for item in selected_items:
                beat_file = item.text()
                file_path = os.path.join(self.beats_folder, beat_file)
                try:
                    os.remove(file_path)
                    # También quitar de lista de procesamiento si está
                    self.beats_info = [b for b in self.beats_info if b['beat_file'] != beat_file]
                    deleted_count += 1
                except Exception as e:
                    QMessageBox.warning(self, "Error", f"No se pudo eliminar {beat_file}: {e}")
                    error_count += 1
            
            self._load_beats()
            self._update_process_list()
            
            # Mensaje de estado detallado
            if error_count == 0:
                self.status_label.setText(f"✅ {deleted_count} beats eliminados correctamente")
            else:
                self.status_label.setText(f"⚠️ {deleted_count} eliminados, {error_count} errores")
    
    def _toggle_select_all_beats(self, state):
        """Selecciona o deselecciona todos los beats."""
        if state == Qt.CheckState.Checked.value:
            self.beats_list.selectAll()
        else:
            self.beats_list.clearSelection()
        self._update_selection_count()
    
    def _update_selection_count(self):
        """Actualiza el contador de beats seleccionados."""
        selected_count = len(self.beats_list.selectedItems())
        total_count = self.beats_list.count()
        
        self.selected_count_label.setText(f"{selected_count} de {total_count} seleccionados")
        
        # Actualizar estado del checkbox sin disparar la señal
        if selected_count == 0:
            self.select_all_checkbox.blockSignals(True)
            self.select_all_checkbox.setCheckState(Qt.CheckState.Unchecked)
            self.select_all_checkbox.blockSignals(False)
        elif selected_count == total_count and total_count > 0:
            self.select_all_checkbox.blockSignals(True)
            self.select_all_checkbox.setCheckState(Qt.CheckState.Checked)
            self.select_all_checkbox.blockSignals(False)
        else:
            self.select_all_checkbox.blockSignals(True)
            self.select_all_checkbox.setCheckState(Qt.CheckState.PartiallyChecked)
            self.select_all_checkbox.blockSignals(False)
        
        # Actualizar texto de los botones según la selección
        if selected_count == 0:
            self.btn_assign_channel.setText("➡️ Asignar Canal a Seleccionados")
            self.btn_delete_selected.setText("🗑️ Eliminar Seleccionados")
        elif selected_count == 1:
            self.btn_assign_channel.setText("➡️ Asignar Canal a 1 Beat")
            self.btn_delete_selected.setText("🗑️ Eliminar 1 Beat")
        else:
            self.btn_assign_channel.setText(f"➡️ Asignar Canal a {selected_count} Beats")
            self.btn_delete_selected.setText(f"🗑️ Eliminar {selected_count} Beats")
    
    def _upload_content_to_channel(self):
        """Permite subir imágenes y videos al canal/grupo seleccionado."""
        channel = self.channel_combo.currentText()
        group = self.group_combo.currentText()
        
        if not channel or channel == "Seleccionar canal..." or not group or group == "Seleccionar grupo...":
            QMessageBox.warning(self, "Selección incompleta", "Selecciona un canal y grupo primero.")
            return
        
        # Crear diálogo para seleccionar tipo de contenido a subir
        content_type_dialog = QMessageBox()
        content_type_dialog.setWindowTitle("Tipo de Contenido")
        content_type_dialog.setText("¿Qué tipo de contenido quieres subir?")
        content_type_dialog.setIcon(QMessageBox.Icon.Question)
        
        btn_images = content_type_dialog.addButton("🖼️ Imágenes", QMessageBox.ButtonRole.AcceptRole)
        btn_videos = content_type_dialog.addButton("🎬 Videos", QMessageBox.ButtonRole.AcceptRole)
        btn_cancel = content_type_dialog.addButton("❌ Cancelar", QMessageBox.ButtonRole.RejectRole)
        
        content_type_dialog.exec()
        clicked_button = content_type_dialog.clickedButton()
        
        if clicked_button == btn_cancel:
            return
        
        # Configurar filtros según el tipo seleccionado
        if clicked_button == btn_images:
            file_filter = "Image Files (*.jpg *.jpeg *.png *.bmp *.gif)"
            dialog_title = "Seleccionar imágenes"
            target_base = self.images_folder
            content_type = "imágenes"
        else:  # Videos
            file_filter = "Video Files (*.mp4 *.mov *.avi *.mkv *.wmv)"
            dialog_title = "Seleccionar videos"
            target_base = "videos"
            content_type = "videos"
        
        # Abrir diálogo de selección de archivos
        files, _ = QFileDialog.getOpenFileNames(
            self,
            dialog_title,
            "",
            file_filter
        )
        
        if files:
            target_path = os.path.join(target_base, channel, group)
            os.makedirs(target_path, exist_ok=True)
            
            copied_files = 0
            for file in files:
                try:
                    filename = os.path.basename(file)
                    dest_path = os.path.join(target_path, filename)
                    if not os.path.exists(dest_path):
                        shutil.copy2(file, dest_path)
                        copied_files += 1
                    else:
                        print(f"El archivo {filename} ya existe, omitiendo...")
                except Exception as e:
                    print(f"Error copiando {file}: {e}")
            
            # Actualizar información de imágenes/videos
            self._update_images_info()
            
            if copied_files > 0:
                self.status_label.setText(f"✅ {copied_files} {content_type} copiadas a {channel}/{group}")
            else:
                self.status_label.setText(f"⚠️ No se copiaron archivos (ya existían o hubo errores)")
    
    def _browse_output_folder(self):
        """Permite seleccionar la carpeta de salida."""
        folder = QFileDialog.getExistingDirectory(self, "Seleccionar carpeta de salida", self.output_folder)
        if folder:
            self.output_folder = folder
            self.output_label.setText(f"📍 {self.output_folder}")
            self.save_config()
            self.status_label.setText(f"Carpeta de salida: {self.output_folder}")
    
    def _start_generation(self):
        """Inicia el proceso de generación de videos con selección de contenido."""
        if not self.beats_info:
            QMessageBox.warning(self, "Lista vacía", "No hay beats para procesar. Asigna canales y grupos a los beats primero.")
            return
        
        # Obtener canal y grupo predominante o del primer beat
        first_beat = self.beats_info[0]
        channel = first_beat['channel']
        group = first_beat['group']
        
        # Verificar que todos los beats usen el mismo canal/grupo
        mixed_channels = any(beat['channel'] != channel or beat['group'] != group for beat in self.beats_info)
        if mixed_channels:
            QMessageBox.warning(self, "Canales mixtos", 
                              "Todos los beats deben usar el mismo canal y grupo para poder seleccionar el tipo de contenido.\n"
                              "Organiza tus beats por canal/grupo antes de generar.")
            return
        
        # Contar contenido disponible
        image_count, video_count = self._get_content_counts(channel, group)
        beats_count = len(self.beats_info)
        
        # Mostrar diálogo de selección
        dialog = ContentSelectionDialog(channel, group, image_count, video_count, beats_count, self)
        
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return  # Usuario canceló
        
        # Obtener tipo de contenido seleccionado
        self.current_content_type = dialog.get_selected_content_type()
        
        # Reiniciar tracking de contenido usado
        self._reset_content_tracking()
        
        if not os.path.exists(self.output_folder):
            try:
                os.makedirs(self.output_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo crear la carpeta de salida: {e}")
                return
        
        # Configurar UI para procesamiento
        self._set_ui_processing(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        
        # Crear y iniciar worker con el tipo de contenido seleccionado
        self.worker = VideoGeneratorWorker(
            self.beats_folder,
            self.images_folder,
            self.output_folder,
            self.beats_info,
            self.current_content_type,
            self  # Pasar referencia para usar sistema anti-duplicados
        )
        
        self.worker.progress_updated.connect(self._update_progress)
        self.worker.finished.connect(self._process_finished)
        self.worker.start()
    
    def _cancel_generation(self):
        """Cancela el proceso de generación."""
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
            self._set_ui_processing(False)
            self.progress_bar.setVisible(False)
            self.status_label.setText("Proceso cancelado")
    
    def _update_progress(self, progress, message):
        """Actualiza la barra de progreso y el mensaje."""
        self.progress_bar.setValue(progress)
        self.status_label.setText(message)
    
    def _process_finished(self, success, message):
        """Se ejecuta cuando termina el procesamiento."""
        self._set_ui_processing(False)
        self.progress_bar.setVisible(False)
        
        if success:
            QMessageBox.information(self, "Completado", message)
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
        self.beats_list.setEnabled(not is_processing)
        self.process_list.setEnabled(not is_processing)
        self.btn_edit_name.setEnabled(not is_processing)
        self.btn_remove_from_process.setEnabled(not is_processing)
        self.btn_clear_process.setEnabled(not is_processing)
    
    # ========== FUNCIONES DE DETECCIÓN DE CONTENIDO ==========
    
    def _get_content_counts(self, channel, group):
        """Cuenta las imágenes y videos disponibles para un canal/grupo."""
        # Extensiones soportadas
        image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.wmv']
        
        # Contar imágenes
        images_path = os.path.join(self.images_folder, channel, group)
        image_count = 0
        if os.path.exists(images_path):
            image_count = sum(1 for f in os.listdir(images_path) 
                            if any(f.lower().endswith(ext) for ext in image_extensions))
        
        # Contar videos
        videos_path = os.path.join("videos", channel, group)
        video_count = 0
        if os.path.exists(videos_path):
            video_count = sum(1 for f in os.listdir(videos_path) 
                            if any(f.lower().endswith(ext) for ext in video_extensions))
        
        return image_count, video_count
    
    def _get_available_content(self, channel, group, content_type):
        """Obtiene la lista de archivos disponibles según el tipo de contenido."""
        if content_type == "images":
            extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.gif']
            base_path = os.path.join(self.images_folder, channel, group)
        else:  # videos
            extensions = ['.mp4', '.mov', '.avi', '.mkv', '.wmv']
            base_path = os.path.join("videos", channel, group)
        
        if not os.path.exists(base_path):
            return []
        
        files = []
        for file in os.listdir(base_path):
            if any(file.lower().endswith(ext) for ext in extensions):
                files.append(os.path.join(base_path, file))
        
        return files
    
    def _select_unique_content(self, channel, group, content_type):
        """Selecciona un archivo de contenido sin repetir hasta agotar todos."""
        available_files = self._get_available_content(channel, group, content_type)
        
        if not available_files:
            return None
        
        # Filtrar archivos no utilizados
        unused_files = [f for f in available_files if f not in self.used_content_files]
        
        # Si se agotaron los archivos, reiniciar la lista
        if not unused_files:
            self.used_content_files.clear()
            unused_files = available_files
        
        # Seleccionar uno al azar
        import random
        selected_file = random.choice(unused_files)
        
        # Marcarlo como utilizado
        self.used_content_files.append(selected_file)
        
        return selected_file
    
    def _reset_content_tracking(self):
        """Reinicia el tracking de contenido utilizado."""
        self.used_content_files.clear()


def main():
    """Función principal."""
    app = QApplication(sys.argv)
    
    # Configurar estilo
    app.setStyle(QStyleFactory.create('Fusion'))
    
    # Crear ventana principal
    window = MainWindow()
    window.show()
    
    # Ejecutar aplicación
    sys.exit(app.exec())


if __name__ == "__main__":
    main()