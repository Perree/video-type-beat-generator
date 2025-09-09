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

# Constantes
CONFIG_FILE = os.path.join('config', 'app_config.json')
DEFAULT_CONFIG = {
    'last_output_folder': 'exported_videos',
    'channels': []  # Lista de canales de YouTube conocidos
}

# Estilos personalizados - Versión limpia y legible
STYLESHEET = """
QMainWindow {
    background-color: #2B2B2B;
    color: #FFFFFF;
}

QWidget {
    background-color: #2B2B2B;
    color: #FFFFFF;
}

QLabel {
    color: #FFFFFF;
    font-size: 13px;
    padding: 3px;
    margin: 2px;
}

QLabel[heading=true] {
    color: #4A9EFF;
    font-size: 16px;
    font-weight: bold;
    padding: 8px;
    margin: 5px 0px;
    border-bottom: 2px solid #4A9EFF;
}

QPushButton {
    background-color: #4A9EFF;
    color: white;
    font-weight: bold;
    padding: 8px 16px;
    border: none;
    border-radius: 5px;
    min-width: 80px;
    min-height: 30px;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #6BB6FF;
}

QPushButton:pressed {
    background-color: #2E7BD6;
}

QPushButton:disabled {
    background-color: #555555;
    color: #AAAAAA;
}

QProgressBar {
    border: 1px solid #555555;
    border-radius: 3px;
    text-align: center;
    color: white;
    background-color: #3C3C3C;
}

QProgressBar::chunk {
    background-color: #4A9EFF;
    border-radius: 2px;
}

QComboBox {
    background-color: #3C3C3C;
    color: #FFFFFF;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 5px;
    min-height: 25px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 25px;
    border-left: 1px solid #555555;
}

QComboBox QAbstractItemView {
    background-color: #3C3C3C;
    color: #FFFFFF;
    selection-background-color: #4A9EFF;
    border: 1px solid #555555;
}

QListWidget {
    background-color: #3C3C3C;
    color: #FFFFFF;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 3px;
}

QListWidget::item {
    padding: 4px;
    margin: 1px;
    border-radius: 2px;
}

QListWidget::item:selected {
    background-color: #4A9EFF;
    color: white;
}

QListWidget::item:hover {
    background-color: #555555;
}

QFrame[cardStyle=true] {
    background-color: #363636;
    border: 1px solid #555555;
    border-radius: 5px;
    padding: 10px;
    margin: 5px;
}

QLineEdit {
    background-color: #3C3C3C;
    color: #FFFFFF;
    border: 1px solid #555555;
    border-radius: 3px;
    padding: 5px;
}

QLineEdit:focus {
    border: 1px solid #4A9EFF;
}

QSplitter::handle {
    background-color: #555555;
    height: 3px;
}

QSplitter::handle:hover {
    background-color: #4A9EFF;
}
"""

class VideoGeneratorWorker(QThread):
    """Clase para procesar la generación de videos en un hilo separado."""
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, beats_folder, images_folder, output_folder, beats_info):
        super().__init__()
        self.beats_folder = beats_folder
        self.images_folder = images_folder
        self.output_folder = output_folder
        self.beats_info = beats_info
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
                
            self.progress_updated.emit(100, "Proceso completado!")
            self.finished.emit(True, f"Se generaron {total_beats} videos exitosamente. Para cada video, se guardó también la imagen utilizada.")
            
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
        self.loaded_beats = []
        self.beats_info = []  # Lista de diccionarios {audio, genre, custom_name}
        self.config = self._load_config()
        
        # Crear carpetas si no existen
        for folder in [self.beats_folder, self.images_folder, self.output_folder]:
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
        self.setMinimumSize(900, 700)
        
        # Aplicar estilo
        self.setStyleSheet(STYLESHEET)
        
        # Widget central y layout principal
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(15, 15, 15, 15)
        
        # Título de la aplicación
        title_layout = QHBoxLayout()
        app_icon = QLabel()
        app_icon.setPixmap(qta.icon("fa5s.music", color="#4A9EFF").pixmap(24, 24))
        title_layout.addWidget(app_icon)
        
        app_title = QLabel("Type Beat Video Generator")
        app_title.setProperty("heading", True)
        app_title.setStyleSheet("font-size: 20px; color: #4A9EFF; font-weight: bold;")
        title_layout.addWidget(app_title)
        title_layout.addStretch()
        main_layout.addLayout(title_layout)
        
        # === SECCIÓN 1: ARCHIVOS DE AUDIO ===
        audio_frame = QFrame()
        audio_frame.setProperty("cardStyle", True)
        audio_layout = QVBoxLayout(audio_frame)
        
        # Encabezado
        audio_header = QLabel("🎵 Archivos de Audio")
        audio_header.setProperty("heading", True)
        audio_layout.addWidget(audio_header)
        
        # Botones
        audio_buttons = QHBoxLayout()
        
        self.btn_load_beats = QPushButton("Cargar")
        self.btn_load_beats.clicked.connect(self._load_beats)
        audio_buttons.addWidget(self.btn_load_beats)
        
        self.btn_delete_beats = QPushButton("Eliminar")
        self.btn_delete_beats.clicked.connect(self._delete_beat_files)
        audio_buttons.addWidget(self.btn_delete_beats)
        
        self.btn_clear_beats = QPushButton("Limpiar Lista")
        self.btn_clear_beats.clicked.connect(self._clear_beats)
        audio_buttons.addWidget(self.btn_clear_beats)
        
        audio_buttons.addStretch()
        audio_layout.addLayout(audio_buttons)
        
        # Lista de beats
        self.beats_list = QListWidget()
        self.beats_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.beats_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.beats_list.customContextMenuRequested.connect(self._show_beats_list_menu)
        self.beats_list.setMinimumHeight(120)
        audio_layout.addWidget(self.beats_list)
        
        main_layout.addWidget(audio_frame)
        
        # === SECCIÓN 2: ASIGNACIÓN DE CANALES ===
        channel_frame = QFrame()
        channel_frame.setProperty("cardStyle", True)
        channel_layout = QVBoxLayout(channel_frame)
        
        # Encabezado
        channel_header = QLabel("📺 Asignación de Canal y Grupo")
        channel_header.setProperty("heading", True)
        channel_layout.addWidget(channel_header)
        
        # Selectores
        selectors_layout = QGridLayout()
        
        selectors_layout.addWidget(QLabel("Canal:"), 0, 0)
        self.channel_combo = QComboBox()
        self.channel_combo.currentIndexChanged.connect(lambda: self._update_groups_for_channel(self.channel_combo.currentText()))
        self._update_channels_combo()
        selectors_layout.addWidget(self.channel_combo, 0, 1)
        
        selectors_layout.addWidget(QLabel("Grupo:"), 1, 0)
        self.group_combo = QComboBox()
        selectors_layout.addWidget(self.group_combo, 1, 1)
        
        channel_layout.addLayout(selectors_layout)
        
        # Botones de gestión
        channel_buttons = QHBoxLayout()
        
        self.btn_manage_channels = QPushButton("Gestionar")
        self.btn_manage_channels.clicked.connect(self._manage_channels)
        channel_buttons.addWidget(self.btn_manage_channels)
        
        self.btn_assign_channel = QPushButton("Asignar")
        self.btn_assign_channel.clicked.connect(self._assign_channel_and_group)
        channel_buttons.addWidget(self.btn_assign_channel)
        
        channel_buttons.addStretch()
        channel_layout.addLayout(channel_buttons)
        
        main_layout.addWidget(channel_frame)
        
        # === SECCIÓN 3: BEATS A PROCESAR ===
        process_frame = QFrame()
        process_frame.setProperty("cardStyle", True)
        process_layout = QVBoxLayout(process_frame)
        
        # Encabezado
        process_header = QLabel("📋 Beats a Procesar")
        process_header.setProperty("heading", True)
        process_layout.addWidget(process_header)
        
        # Lista de procesos
        self.process_list = QListWidget()
        self.process_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.process_list.customContextMenuRequested.connect(self._show_process_list_menu)
        self.process_list.doubleClicked.connect(self._edit_beat_name)
        self.process_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.process_list.setMinimumHeight(100)
        process_layout.addWidget(self.process_list)
        
        # Botones de edición
        process_buttons = QHBoxLayout()
        
        self.btn_edit_name = QPushButton("Editar")
        self.btn_edit_name.clicked.connect(self._edit_selected_beat_name)
        process_buttons.addWidget(self.btn_edit_name)
        
        self.btn_remove_beat = QPushButton("Eliminar")
        self.btn_remove_beat.clicked.connect(self._remove_selected_beat)
        process_buttons.addWidget(self.btn_remove_beat)
        
        process_buttons.addStretch()
        process_layout.addLayout(process_buttons)
        
        main_layout.addWidget(process_frame)
        
        # === SECCIÓN 4: EXPORTACIÓN ===
        export_frame = QFrame()
        export_frame.setProperty("cardStyle", True)
        export_layout = QVBoxLayout(export_frame)
        
        # Encabezado
        export_header = QLabel("📤 Exportación")
        export_header.setProperty("heading", True)
        export_layout.addWidget(export_header)
        
        # Selector de carpeta
        folder_layout = QHBoxLayout()
        folder_layout.addWidget(QLabel("Carpeta de salida:"))
        
        self.output_path = QLineEdit()
        self.output_path.setText(self.output_folder)
        self.output_path.setReadOnly(True)
        folder_layout.addWidget(self.output_path)
        
        self.btn_browse_output = QPushButton("...")
        self.btn_browse_output.clicked.connect(self._browse_output)
        self.btn_browse_output.setMaximumWidth(30)
        folder_layout.addWidget(self.btn_browse_output)
        
        export_layout.addLayout(folder_layout)
        
        # Barra de progreso
        export_layout.addWidget(QLabel("Progreso:"))
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        export_layout.addWidget(self.progress_bar)
        
        # Estado
        self.status_label = QLabel("Listo para procesar")
        self.status_label.setAlignment(Qt.AlignCenter)
        export_layout.addWidget(self.status_label)
        
        # Botones principales
        main_buttons = QHBoxLayout()
        
        self.btn_generate = QPushButton("▶ Generar")
        self.btn_generate.clicked.connect(self._generate_videos)
        self.btn_generate.setStyleSheet("background-color: #4CAF50; font-size: 14px; padding: 10px;")
        main_buttons.addWidget(self.btn_generate)
        
        self.btn_cancel = QPushButton("⏹ Cancelar")
        self.btn_cancel.clicked.connect(self._cancel_process)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setStyleSheet("background-color: #F44336; font-size: 14px; padding: 10px;")
        main_buttons.addWidget(self.btn_cancel)
        
        export_layout.addLayout(main_buttons)
        
        main_layout.addWidget(export_frame)
        
        # Footer
        footer = QLabel("Type Beat Video Generator v1.0")
        footer.setAlignment(Qt.AlignRight)
        footer.setStyleSheet("color: #888888; font-size: 10px;")
        main_layout.addWidget(footer)
        
        # Establecer el layout principal
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # Inicializar variables adicionales
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
        
        self.group_combo.clear()
        
        channel_folder = os.path.join(self.images_folder, channel)
        if os.path.exists(channel_folder):
            groups = [d for d in os.listdir(channel_folder) 
                     if os.path.isdir(os.path.join(channel_folder, d))]
            self.group_combo.addItems(groups)
    
    def _manage_channels(self):
        """Abre el diálogo para gestionar canales de YouTube."""
        QMessageBox.information(self, "Gestión de Canales", "Funcionalidad de gestión de canales simplificada.")
    
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
        
        self._set_ui_processing(True)
        
        self.worker = VideoGeneratorWorker(
            self.beats_folder,
            self.images_folder,
            self.output_folder,
            self.beats_info
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
        self.btn_clear_beats.setEnabled(not is_processing)
        self.btn_delete_beats.setEnabled(not is_processing)
        self.btn_assign_channel.setEnabled(not is_processing)
        self.btn_manage_channels.setEnabled(not is_processing)
        self.btn_browse_output.setEnabled(not is_processing)
        self.btn_generate.setEnabled(not is_processing)
        self.btn_cancel.setEnabled(is_processing)
        self.beats_list.setEnabled(not is_processing)
        self.process_list.setEnabled(not is_processing)
        self.btn_edit_name.setEnabled(not is_processing)
        self.btn_remove_beat.setEnabled(not is_processing)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
