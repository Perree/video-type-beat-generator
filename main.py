#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Type Beat Video Generator - Versión Simplificada
------------------------------------------------
Aplicación para generar automáticamente videos para Type Beats.
Combina beats de audio con imágenes según género y exporta videos en formato MP4.
"""

# Suprimir warnings de deprecación de PyQt5
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module=".*PyQt5.*")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="sip")

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
                            QSizePolicy, QTabWidget, QInputDialog, QGraphicsDropShadowEffect)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QRect, QSettings, QPoint, QTimer
from PyQt5.QtGui import QPixmap, QIcon, QColor, QPalette, QFont, QCursor, QLinearGradient, QPainter, QPainterPath

# Importar estilos y bibliotecas para la interfaz moderna
import qdarkstyle
import qtawesome as qta

# Importar el diálogo para editar nombres de beat
from edit_beat_dialog import EditBeatNameDialog

# Importar sistema de miniaturas
from thumbnail_generator import ThumbnailGenerator
from thumbnail_config_dialog import ThumbnailConfigDialog
from thumbnail_preview_dialog import ThumbnailPreviewDialog

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
    
    def __init__(self, beats_folder, images_folder, output_folder, beats_info, thumbnail_settings=None):
        super().__init__()
        self.beats_folder = beats_folder
        self.images_folder = images_folder
        self.output_folder = output_folder
        self.beats_info = beats_info
        self.stop_processing = False
        self.thumbnail_settings = thumbnail_settings or {}
        self.thumbnail_generator = ThumbnailGenerator() if self.thumbnail_settings.get('generate_thumbnails', False) else None
    
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
                
                # Generar miniatura si está habilitado
                if self.thumbnail_generator:
                    self.progress_updated.emit(
                        int((i / total_beats) * 100),
                        f"Generando miniatura para: {audio_file}"
                    )
                    self._generate_thumbnail(image, base_output_name, group_output_folder, channel)
                
                # Copiar la imagen utilizada junto al video
                image_extension = os.path.splitext(image)[1]
                image_output_name = f"{base_output_name}_imagen{image_extension}"
                image_output_path = os.path.join(group_output_folder, image_output_name)
                
                try:
                    shutil.copy2(image, image_output_path)
                except Exception as e:
                    print(f"No se pudo copiar la imagen: {str(e)}")
                
            # Mensaje final actualizado
            thumbnail_msg = " y miniaturas" if self.thumbnail_generator else ""
            self.progress_updated.emit(100, "Proceso completado!")
            self.finished.emit(True, f"Se generaron {total_beats} videos{thumbnail_msg} exitosamente. Para cada video, se guardó también la imagen utilizada.")
            
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
    
    def _generate_thumbnail(self, image_path, base_name, output_folder, channel):
        """Genera miniatura usando el sistema de templates."""
        try:
            # Definir rutas de salida
            thumbnail_name = f"{base_name}_thumbnail.jpg"
            thumbnail_path = os.path.join(output_folder, thumbnail_name)
            
            # Crear también carpeta de miniaturas global
            global_thumbnails_folder = os.path.join(os.path.dirname(self.output_folder), "thumbnails")
            os.makedirs(global_thumbnails_folder, exist_ok=True)
            global_thumbnail_path = os.path.join(global_thumbnails_folder, thumbnail_name)
            
            # Generar miniatura usando configuración del canal
            success = self.thumbnail_generator.generate_thumbnail(
                bg_image_path=image_path,
                output_path=thumbnail_path,
                channel=channel
            )
            
            if success:
                # Copiar también a la carpeta global de miniaturas
                try:
                    shutil.copy2(thumbnail_path, global_thumbnail_path)
                except Exception as e:
                    print(f"No se pudo copiar miniatura a carpeta global: {e}")
            
            return success
            
        except Exception as e:
            print(f"Error generando miniatura: {e}")
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
        self.thumbnails_folder = os.path.abspath("thumbnails")
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
            self.thumbnails_folder,
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
        
        # Botón configurar miniaturas
        self.btn_thumbnail_config = QPushButton("🖼️ CONFIGURAR MINIATURAS")
        self.btn_thumbnail_config.clicked.connect(self._configure_thumbnails)
        self.btn_thumbnail_config.setStyleSheet("background-color: #9B59B6; font-size: 12px; padding: 6px; font-weight: bold;")
        buttons_layout.addWidget(self.btn_thumbnail_config)
        
        self.btn_generate = QPushButton("▶ GENERAR VIDEOS")
        self.btn_generate.clicked.connect(self._generate_videos)
        self.btn_generate.setStyleSheet("background-color: #27AE60; font-size: 14px; padding: 8px; font-weight: bold;")
        buttons_layout.addWidget(self.btn_generate)
        
        self.btn_cancel = QPushButton("⏹ CANCELAR")
        self.btn_cancel.clicked.connect(self._cancel_process)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("background-color: #E74C3C; font-size: 14px; padding: 8px; font-weight: bold;")
        buttons_layout.addWidget(self.btn_cancel)
        
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
        
        if not os.path.exists(self.output_folder):
            try:
                os.makedirs(self.output_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"No se pudo crear la carpeta de salida: {str(e)}")
                return
        
        # Mostrar diálogo de configuración de miniaturas
        beats_dict = {beat['audio']: beat for beat in self.beats_info}
        thumbnail_dialog = ThumbnailConfigDialog(beats_dict, self)
        
        if thumbnail_dialog.exec_() != QDialog.Accepted:
            return
        
        # Obtener configuración de miniaturas
        thumbnail_settings = thumbnail_dialog.get_generation_settings()
        
        self._set_ui_processing(True)
        
        self.worker = VideoGeneratorWorker(
            self.beats_folder,
            self.images_folder,
            self.output_folder,
            self.beats_info,
            thumbnail_settings
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
            QMessageBox.information(self, "Proceso completado", message)
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
        self.btn_thumbnail_config.setEnabled(not is_processing)
        self.btn_generate.setEnabled(not is_processing)
        self.btn_cancel.setEnabled(is_processing)
        self.beats_list.setEnabled(not is_processing)
        self.process_list.setEnabled(not is_processing)
        self.btn_edit_name.setEnabled(not is_processing)
        self.btn_remove_beat.setEnabled(not is_processing)
    
    def _configure_thumbnails(self):
        """Abre el diálogo de configuración de miniaturas con vista previa."""
        if not self.beats_info:
            QMessageBox.information(
                self, 
                "Sin beats asignados", 
                "Primero debe asignar beats a canales para configurar las miniaturas."
            )
            return
        
        # Crear diccionario de canales desde beats_info
        channels_dict = {}
        for beat in self.beats_info:
            channel = beat.get('channel', '')
            if channel and channel not in channels_dict:
                channels_dict[channel] = []
            if channel:
                channels_dict[channel].append(beat)
        
        # Abrir el nuevo diálogo con vista previa
        preview_dialog = ThumbnailPreviewDialog(channels_dict, self)
        
        if preview_dialog.exec_() == QDialog.Accepted:
            QMessageBox.information(
                self,
                "Configuración guardada",
                "La configuración de miniaturas se ha guardado correctamente.\n"
                "Se aplicará en la próxima generación de videos con vista previa en tiempo real."
            )
    
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
