#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Type Beat Video Generator
------------------------
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
                            QSizePolicy, QTabWidget, QInputDialog)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize, QPropertyAnimation, QEasingCurve, QRect, QSettings
from PyQt5.QtGui import QPixmap, QIcon, QColor, QPalette, QFont, QCursor

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

# Estilos personalizados
STYLESHEET = """
QMainWindow {
    background-color: #1E1E2E;
}

QLabel {
    color: #CDD6F4;
    font-size: 14px;
    qproperty-wordWrap: true;
    min-height: 20px;
    margin: 2px;
    padding: 2px;
}

QLabel[heading=true] {
    color: #89B4FA;
    font-size: 18px;
    font-weight: bold;
    padding: 6px;
    border-bottom: 1px solid #45475A;
    min-height: 28px;
}

QPushButton {
    background-color: #89B4FA;
    color: #1E1E2E;
    font-weight: bold;
    padding: 8px 12px;
    border: none;
    border-radius: 6px;
    text-align: center;
    min-width: 100px;
    min-height: 30px;
    font-size: 13px;
    margin: 2px;
}

QPushButton:hover {
    background-color: #B4BEFE;
}

QPushButton:pressed {
    background-color: #74C7EC;
}

QPushButton:disabled {
    background-color: #45475A;
    color: #6C7086;
}

QProgressBar {
    border: 1px solid #45475A;
    border-radius: 3px;
    text-align: center;
    color: #CDD6F4;
}

QProgressBar::chunk {
    background-color: #89B4FA;
    width: 10px;
    margin: 0px;
}

QComboBox {
    background-color: #313244;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 4px;
    padding: 6px 8px;
    font-size: 14px;
    min-height: 30px;
    margin: 2px;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 30px;
    border-left-width: 1px;
    border-left-color: #45475A;
    border-left-style: solid;
}

QComboBox QAbstractItemView {
    background-color: #313244;
    color: #CDD6F4;
    selection-background-color: #89B4FA;
    selection-color: #1E1E2E;
    border: 1px solid #45475A;
    font-size: 14px;
    padding: 4px;
}

QListWidget {
    background-color: #313244;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 3px;
    padding: 3px;
    font-size: 13px;
}

QListWidget::item {
    padding: 5px 4px;
    min-height: 24px;
    border-radius: 4px;
    margin: 2px 0px;
    font-size: 14px;
}

QListWidget::item:selected {
    background-color: #89B4FA;
    color: #1E1E2E;
    font-weight: bold;
}

QListWidget::item:hover {
    background-color: #45475A;
}

QFrame[cardStyle=true] {
    background-color: #313244;
    border-radius: 8px;
    padding: 10px;
}

QToolButton {
    background-color: transparent;
    border: none;
    padding: 3px;
}

QToolButton:hover {
    background-color: #45475A;
    border-radius: 3px;
}

QLineEdit {
    background-color: #313244;
    color: #CDD6F4;
    border: 1px solid #45475A;
    border-radius: 3px;
    padding: 5px;
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


class ChannelImagesDialog(QDialog):
    """Diálogo para gestionar imágenes de un canal."""
    
    def __init__(self, channel, images_folder, parent=None, group=None):
        super().__init__(parent)
        self.channel = channel
        self.images_folder = images_folder
        self.channel_folder = os.path.join(images_folder, channel)
        self.selected_group = group
        
        # Crear la carpeta si no existe
        os.makedirs(self.channel_folder, exist_ok=True)
        
        self._setup_ui()
        self._load_images()
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        self.setWindowTitle(f"Gestionar imágenes para el canal '{self.channel}'")
        self.setMinimumWidth(700)
        self.setMinimumHeight(500)
        
        main_layout = QVBoxLayout()
        
        # Sección de información
        info_label = QLabel(f"Imágenes para el canal: <b>{self.channel}</b>")
        info_label.setStyleSheet("font-size: 16px; margin-bottom: 5px;")
        main_layout.addWidget(info_label)
        
        # Selector de grupo
        group_layout = QHBoxLayout()
        group_layout.addWidget(QLabel("Grupo de imágenes:"))
        
        self.group_combo = QComboBox()
        self._update_groups_combo()
        self.group_combo.currentIndexChanged.connect(self._on_group_changed)
        group_layout.addWidget(self.group_combo)
        
        self.btn_add_group = QPushButton("Nuevo grupo")
        self.btn_add_group.setIcon(qta.icon("fa5s.plus-circle", color="#1E1E2E"))
        self.btn_add_group.clicked.connect(self._add_new_group)
        group_layout.addWidget(self.btn_add_group)
        
        self.btn_rename_group = QPushButton("Renombrar")
        self.btn_rename_group.setIcon(qta.icon("fa5s.edit", color="#1E1E2E"))
        self.btn_rename_group.clicked.connect(self._rename_group)
        group_layout.addWidget(self.btn_rename_group)
        
        self.btn_delete_group = QPushButton("Eliminar grupo")
        self.btn_delete_group.setIcon(qta.icon("fa5s.trash", color="#1E1E2E"))
        self.btn_delete_group.clicked.connect(self._delete_group)
        group_layout.addWidget(self.btn_delete_group)
        
        main_layout.addLayout(group_layout)
        
        # Lista de imágenes con una etiqueta que muestra el grupo seleccionado
        self.group_info_label = QLabel("Imágenes en este grupo:")
        main_layout.addWidget(self.group_info_label)
        
        self.images_list = QListWidget()
        main_layout.addWidget(self.images_list)
        
        # Botones para gestionar imágenes
        btn_layout = QHBoxLayout()
        
        self.btn_add = QPushButton("Agregar imágenes")
        self.btn_add.setIcon(qta.icon("fa5s.file-image", color="#1E1E2E"))
        self.btn_add.clicked.connect(self._add_images)
        btn_layout.addWidget(self.btn_add)
        
        self.btn_remove = QPushButton("Eliminar seleccionadas")
        self.btn_remove.setIcon(qta.icon("fa5s.trash-alt", color="#1E1E2E"))
        self.btn_remove.clicked.connect(self._remove_images)
        btn_layout.addWidget(self.btn_remove)
        
        main_layout.addLayout(btn_layout)
        
        # Botón de cerrar
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        main_layout.addWidget(self.btn_close)
        
        self.setLayout(main_layout)
    
    def _update_groups_combo(self):
        """Actualiza el combo box con los grupos disponibles."""
        self.group_combo.clear()
        
        # Obtener grupos (subcarpetas) dentro del canal
        groups = []
        if os.path.exists(self.channel_folder):
            groups = [d for d in os.listdir(self.channel_folder) 
                     if os.path.isdir(os.path.join(self.channel_folder, d))]
        
        # Si no hay grupos, crear el grupo por defecto "Principal"
        if not groups:
            default_group_folder = os.path.join(self.channel_folder, "Principal")
            os.makedirs(default_group_folder, exist_ok=True)
            groups = ["Principal"]
        
        # Actualizar el combo
        self.group_combo.addItems(groups)
        
        # Seleccionar el grupo pasado como parámetro si existe
        if self.selected_group and self.selected_group in groups:
            index = self.group_combo.findText(self.selected_group)
            if index >= 0:
                self.group_combo.setCurrentIndex(index)
    
    def _on_group_changed(self):
        """Actualiza la lista de imágenes cuando se cambia el grupo seleccionado."""
        self._load_images()
        
    def _add_new_group(self):
        """Añade un nuevo grupo de imágenes."""
        name, ok = QInputDialog.getText(
            self, 
            "Nuevo grupo de imágenes", 
            "Nombre del grupo:"
        )
        
        if ok and name:
            # Crear la carpeta del nuevo grupo
            group_folder = os.path.join(self.channel_folder, name)
            
            # Verificar si ya existe
            if os.path.exists(group_folder):
                QMessageBox.warning(
                    self,
                    "Grupo duplicado",
                    f"Ya existe un grupo llamado '{name}'."
                )
                return
            
            # Crear el grupo (carpeta)
            os.makedirs(group_folder, exist_ok=True)
            
            # Actualizar el combo y seleccionar el nuevo grupo
            self._update_groups_combo()
            index = self.group_combo.findText(name)
            if index >= 0:
                self.group_combo.setCurrentIndex(index)
    
    def _rename_group(self):
        """Renombra el grupo actual."""
        current_group = self.group_combo.currentText()
        
        # No permitir renombrar el grupo "Principal"
        if current_group == "Principal":
            QMessageBox.information(
                self,
                "Información",
                "El grupo 'Principal' no puede ser renombrado."
            )
            return
        
        new_name, ok = QInputDialog.getText(
            self, 
            "Renombrar grupo", 
            "Nuevo nombre:",
            text=current_group
        )
        
        if ok and new_name and new_name != current_group:
            old_path = os.path.join(self.channel_folder, current_group)
            new_path = os.path.join(self.channel_folder, new_name)
            
            # Verificar si el nuevo nombre ya existe
            if os.path.exists(new_path):
                QMessageBox.warning(
                    self,
                    "Grupo duplicado",
                    f"Ya existe un grupo llamado '{new_name}'."
                )
                return
            
            try:
                # Renombrar la carpeta
                os.rename(old_path, new_path)
                
                # Actualizar el combo
                self._update_groups_combo()
                index = self.group_combo.findText(new_name)
                if index >= 0:
                    self.group_combo.setCurrentIndex(index)
                
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Error al renombrar el grupo: {str(e)}"
                )
    
    def _delete_group(self):
        """Elimina el grupo actual y sus imágenes."""
        current_group = self.group_combo.currentText()
        
        # No permitir eliminar el grupo "Principal"
        if current_group == "Principal" and self.group_combo.count() > 1:
            QMessageBox.information(
                self,
                "Información",
                "No se puede eliminar el grupo 'Principal'.\nSi deseas eliminarlo, primero debes eliminar los otros grupos."
            )
            return
        
        confirm = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"¿Está seguro de eliminar el grupo '{current_group}' y todas sus imágenes?\nEsta acción no se puede deshacer.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            group_path = os.path.join(self.channel_folder, current_group)
            
            try:
                # Eliminar la carpeta y su contenido
                shutil.rmtree(group_path)
                
                # Si era el último grupo, crear el grupo Principal
                if self.group_combo.count() <= 1:
                    default_group = os.path.join(self.channel_folder, "Principal")
                    os.makedirs(default_group, exist_ok=True)
                
                # Actualizar el combo
                self._update_groups_combo()
                
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"Error al eliminar el grupo: {str(e)}"
                )
    
    def _load_images(self):
        """Carga la lista de imágenes del grupo seleccionado."""
        self.images_list.clear()
        
        current_group = self.group_combo.currentText()
        if not current_group:
            return
        
        group_folder = os.path.join(self.channel_folder, current_group)
        self.group_info_label.setText(f"Imágenes en el grupo <b>{current_group}</b>:")
        
        if os.path.exists(group_folder):
            images = [img for img in os.listdir(group_folder) 
                     if img.lower().endswith(('.jpg', '.jpeg', '.png'))]
            
            self.images_list.addItems(images)
    
    def _add_images(self):
        """Permite al usuario agregar imágenes al grupo seleccionado."""
        current_group = self.group_combo.currentText()
        if not current_group:
            return
            
        group_folder = os.path.join(self.channel_folder, current_group)
        
        file_dialog = QFileDialog()
        file_paths, _ = file_dialog.getOpenFileNames(
            self,
            f"Seleccionar imágenes para el grupo {current_group}",
            "",
            "Imágenes (*.png *.jpg *.jpeg)"
        )
        
        if file_paths:
            for path in file_paths:
                filename = os.path.basename(path)
                dest_path = os.path.join(group_folder, filename)
                
                # Verificar si ya existe
                if os.path.exists(dest_path):
                    response = QMessageBox.question(
                        self,
                        "Imagen duplicada",
                        f"La imagen '{filename}' ya existe en este grupo. ¿Desea reemplazarla?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    
                    if response == QMessageBox.No:
                        continue
                
                # Copiar el archivo a la carpeta del grupo
                shutil.copy2(path, dest_path)
            
            # Recargar la lista de imágenes
            self._load_images()
    
    def _remove_images(self):
        """Elimina las imágenes seleccionadas del grupo actual."""
        selected_items = self.images_list.selectedItems()
        
        if not selected_items:
            return
        
        current_group = self.group_combo.currentText()
        group_folder = os.path.join(self.channel_folder, current_group)
        
        confirm = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"¿Está seguro de eliminar {len(selected_items)} imagen(es) del grupo '{current_group}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            for item in selected_items:
                image_path = os.path.join(group_folder, item.text())
                try:
                    os.remove(image_path)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Error",
                        f"No se pudo eliminar {item.text()}: {str(e)}"
                    )
            
            # Recargar la lista de imágenes
            self._load_images()


class AddChannelDialog(QDialog):
    """Diálogo para agregar un nuevo canal."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.channel_name = ""
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        self.setWindowTitle("Agregar nuevo canal de YouTube")
        self.setFixedSize(400, 120)
        
        layout = QVBoxLayout()
        
        # Campo para el nombre del canal
        form_layout = QGridLayout()
        form_layout.addWidget(QLabel("Nombre del canal:"), 0, 0)
        
        self.channel_input = QLineEdit()
        form_layout.addWidget(self.channel_input, 0, 1)
        
        layout.addLayout(form_layout)
        
        # Botones
        btn_layout = QHBoxLayout()
        
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_add = QPushButton("Agregar")
        self.btn_add.clicked.connect(self._add_channel)
        btn_layout.addWidget(self.btn_add)
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def _add_channel(self):
        """Valida y guarda el nombre del canal."""
        channel = self.channel_input.text().strip()
        
        if not channel:
            QMessageBox.warning(
                self,
                "Error",
                "El nombre del canal no puede estar vacío."
            )
            return
        
        self.channel_name = channel
        self.accept()


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
        
        # Aplicar estilo oscuro moderno
        self.setStyleSheet(STYLESHEET)
        
        # Configurar la interfaz
        self._setup_ui()
        
        # Actualizar la lista de beats
        self._update_beats_list()
        
        # Restaurar tamaño y posición de la ventana
        self._restore_window_state()
    
    def _setup_ui(self):
        """Configura la interfaz de usuario moderna."""
        self.setWindowTitle("Type Beat Video Generator")
        self.setMinimumSize(800, 800)  # Tamaño mínimo más grande para garantizar visibilidad
        
        # Widget central y layout principal
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setSpacing(10)  # Menor espaciado
        main_layout.setContentsMargins(15, 15, 15, 15)  # Márgenes reducidos
        
        # Título de la aplicación
        app_title = QLabel("Type Beat Video Generator")
        app_title.setProperty("heading", True)
        app_title.setStyleSheet("font-size: 24px; color: #89B4FA; margin-bottom: 15px;")
        main_layout.addWidget(app_title)
        
        # Divisor principal para las secciones
        main_splitter = QSplitter(Qt.Vertical)
        main_splitter.setChildrenCollapsible(False)  # Evitar que las secciones se colapsen
        
        # === SECCIÓN 1: ARCHIVOS DE AUDIO ===
        audio_card = QFrame()
        audio_card.setProperty("cardStyle", True)
        audio_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # Política de tamaño para mejor adaptabilidad
        audio_layout = QVBoxLayout(audio_card)
        audio_layout.setContentsMargins(10, 10, 10, 10)  # Márgenes reducidos
        
        # Encabezado con icono
        header_layout = QHBoxLayout()
        header_icon = QLabel()
        header_icon.setPixmap(qta.icon("fa5s.music", color="#89B4FA").pixmap(20, 20))  # Icono más pequeño
        header_layout.addWidget(header_icon)
        
        audio_header = QLabel("Archivos de Audio")
        audio_header.setProperty("heading", True)
        audio_header.setToolTip("Gestión de archivos de audio (beats)")
        header_layout.addWidget(audio_header)
        header_layout.addStretch()
        audio_layout.addLayout(header_layout)
        
        # Botones de acción - Grid para mejor distribución en pantallas pequeñas
        beats_btns_grid = QGridLayout()
        beats_btns_grid.setSpacing(6)
        beats_btns_grid.setColumnStretch(0, 1)
        beats_btns_grid.setColumnStretch(1, 1)
        
        self.btn_load_beats = QPushButton(qta.icon("fa5s.file-upload", color="#1E1E2E"), " Cargar")
        self.btn_load_beats.clicked.connect(self._load_beats)
        self.btn_load_beats.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_load_beats.setToolTip("Cargar nuevos beats de audio")
        beats_btns_grid.addWidget(self.btn_load_beats, 0, 0)
        
        self.btn_delete_beats = QPushButton(qta.icon("fa5s.trash-alt", color="#1E1E2E"), " Eliminar")
        self.btn_delete_beats.clicked.connect(self._delete_beat_files)
        self.btn_delete_beats.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_delete_beats.setToolTip("Eliminar archivos seleccionados del disco")
        beats_btns_grid.addWidget(self.btn_delete_beats, 0, 1)
        
        self.btn_clear_beats = QPushButton(qta.icon("fa5s.eraser", color="#1E1E2E"), " Limpiar Lista")
        self.btn_clear_beats.clicked.connect(self._clear_beats)
        self.btn_clear_beats.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_clear_beats.setToolTip("Deseleccionar todos los elementos")
        beats_btns_grid.addWidget(self.btn_clear_beats, 1, 0, 1, 2)  # Ocupa ambas columnas
        
        audio_layout.addLayout(beats_btns_grid)
        
        # Lista de beats
        self.beats_list = QListWidget()
        self.beats_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.beats_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.beats_list.customContextMenuRequested.connect(self._show_beats_list_menu)
        self.beats_list.setMinimumHeight(150)
        audio_layout.addWidget(self.beats_list)
        
        main_splitter.addWidget(audio_card)
        
        # === SECCIÓN 2: ASIGNACIÓN DE CANALES Y GRUPOS ===
        channel_card = QFrame()
        channel_card.setProperty("cardStyle", True)
        channel_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)  # Mínimo vertical, expandirse horizontalmente
        channel_layout = QVBoxLayout(channel_card)
        channel_layout.setContentsMargins(10, 10, 10, 10)  # Márgenes más pequeños
        channel_layout.setSpacing(8)  # Reducir espacio
        
        # Encabezado con icono
        channel_header_layout = QHBoxLayout()
        channel_header_layout.setSpacing(6)  # Reducir espacio
        channel_icon = QLabel()
        channel_icon.setPixmap(qta.icon("fa5s.video", color="#89B4FA").pixmap(20, 20))  # Icono más pequeño
        channel_header_layout.addWidget(channel_icon)
        
        channel_header = QLabel("Asignación de Canal y Grupo")
        channel_header.setProperty("heading", True)
        channel_header.setToolTip("Asigna canales de YouTube y grupos de imágenes a los beats")
        channel_header_layout.addWidget(channel_header)
        channel_header_layout.addStretch()
        channel_layout.addLayout(channel_header_layout)
        
        # Selector de canal y grupo - Layout más flexible
        channels_grid_layout = QGridLayout()
        channels_grid_layout.setSpacing(6)
        
        # Canal
        canal_label = QLabel("Canal:")
        canal_label.setToolTip("Selecciona el canal de YouTube para los beats")
        channels_grid_layout.addWidget(canal_label, 0, 0)
        
        self.channel_combo = QComboBox()
        self.channel_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.channel_combo.currentIndexChanged.connect(lambda: self._update_groups_for_channel(self.channel_combo.currentText()))
        self._update_channels_combo()
        channels_grid_layout.addWidget(self.channel_combo, 0, 1, 1, 3)  # Ocupa 3 columnas
        
        # Grupo
        grupo_label = QLabel("Grupo:")
        grupo_label.setToolTip("Selecciona el grupo de imágenes para los beats")
        channels_grid_layout.addWidget(grupo_label, 1, 0)
        
        self.group_combo = QComboBox()
        self.group_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        channels_grid_layout.addWidget(self.group_combo, 1, 1, 1, 3)  # Ocupa 3 columnas
        
        # Botones con tooltips y mejor distribución
        self.btn_manage_channels = QPushButton(qta.icon("fa5s.cog", color="#1E1E2E"), " Gestionar")
        self.btn_manage_channels.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_manage_channels.setToolTip("Gestionar canales y grupos")
        self.btn_manage_channels.clicked.connect(self._manage_channels)
        channels_grid_layout.addWidget(self.btn_manage_channels, 2, 1)
        
        self.btn_assign_channel = QPushButton(qta.icon("fa5s.check", color="#1E1E2E"), " Asignar")
        self.btn_assign_channel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_assign_channel.setToolTip("Asignar canal y grupo a los beats seleccionados")
        self.btn_assign_channel.clicked.connect(self._assign_channel_and_group)
        channels_grid_layout.addWidget(self.btn_assign_channel, 2, 2)
        
        channel_layout.addLayout(channels_grid_layout)
        
        main_splitter.addWidget(channel_card)
        
        # === SECCIÓN 3: BEATS A PROCESAR ===
        process_card = QFrame()
        process_card.setProperty("cardStyle", True)
        process_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)  # Mejor política de tamaño
        process_layout = QVBoxLayout(process_card)
        process_layout.setContentsMargins(10, 10, 10, 10)  # Márgenes más pequeños
        process_layout.setSpacing(8)  # Reducir espacio entre elementos
        
        # Encabezado con icono
        process_header_layout = QHBoxLayout()
        process_header_layout.setSpacing(6)  # Reducir espacio entre elementos
        process_icon = QLabel()
        process_icon.setPixmap(qta.icon("fa5s.list-ul", color="#89B4FA").pixmap(20, 20))  # Icono más pequeño
        process_header_layout.addWidget(process_icon)
        
        process_header = QLabel("Beats a Procesar")
        process_header.setProperty("heading", True)
        process_header.setToolTip("Lista de beats que serán procesados para generar videos")
        process_header_layout.addWidget(process_header)
        process_header_layout.addStretch()
        process_layout.addLayout(process_header_layout)
        
        # Lista de procesos
        self.process_list = QListWidget()
        self.process_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.process_list.customContextMenuRequested.connect(self._show_process_list_menu)
        self.process_list.doubleClicked.connect(self._edit_beat_name)
        self.process_list.setSelectionMode(QListWidget.ExtendedSelection)
        self.process_list.setMinimumHeight(120)  # Altura mínima un poco menor
        self.process_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)  # Expandir en ambas direcciones
        process_layout.addWidget(self.process_list)
        
        # Botones para editar nombre y eliminar beats (usando grid para mejor adaptabilidad)
        edit_btns_grid = QGridLayout()
        edit_btns_grid.setSpacing(6)  # Reducir espacio entre botones
        edit_btns_grid.setColumnStretch(0, 1)
        edit_btns_grid.setColumnStretch(1, 1)
        
        self.btn_edit_name = QPushButton(qta.icon("fa5s.edit", color="#1E1E2E"), " Editar")
        self.btn_edit_name.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Expandir horizontalmente
        self.btn_edit_name.setToolTip("Editar nombre del video")
        self.btn_edit_name.clicked.connect(self._edit_selected_beat_name)
        edit_btns_grid.addWidget(self.btn_edit_name, 0, 0)
        
        self.btn_remove_beat = QPushButton(qta.icon("fa5s.minus-circle", color="#1E1E2E"), " Eliminar")
        self.btn_remove_beat.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Expandir horizontalmente
        self.btn_remove_beat.setToolTip("Eliminar seleccionados")
        self.btn_remove_beat.clicked.connect(self._remove_selected_beat)
        edit_btns_grid.addWidget(self.btn_remove_beat, 0, 1)
        
        process_layout.addLayout(edit_btns_grid)
        
        main_splitter.addWidget(process_card)
        
        # === SECCIÓN 4: EXPORTACIÓN ===
        export_card = QFrame()
        export_card.setProperty("cardStyle", True)
        export_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        export_layout = QVBoxLayout(export_card)
        export_layout.setContentsMargins(10, 10, 10, 10)  # Márgenes más pequeños
        export_layout.setSpacing(8)  # Reducir espacio entre elementos
        
        # Encabezado con icono
        export_header_layout = QHBoxLayout()
        export_header_layout.setSpacing(6)  # Reducir espacio
        export_icon = QLabel()
        export_icon.setPixmap(qta.icon("fa5s.file-export", color="#89B4FA").pixmap(20, 20))  # Icono más pequeño
        export_header_layout.addWidget(export_icon)
        
        export_header = QLabel("Exportación")
        export_header.setProperty("heading", True)
        export_header.setToolTip("Opciones para exportar y generar videos")
        export_header_layout.addWidget(export_header)
        export_header_layout.addStretch()
        export_layout.addLayout(export_header_layout)
        
        # Selector de carpeta - Layout más flexible y adaptativo
        folder_grid = QGridLayout()
        folder_grid.setSpacing(6)
        folder_grid.setColumnStretch(1, 3)  # La columna del input tendrá más prioridad para expandirse
        
        folder_label = QLabel("Salida:")
        folder_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        folder_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)  # Alinear a la derecha
        folder_grid.addWidget(folder_label, 0, 0)
        
        self.output_path = QLineEdit()
        self.output_path.setText(self.output_folder)
        self.output_path.setReadOnly(True)
        self.output_path.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.output_path.setMinimumWidth(50)  # Ancho mínimo para que siempre sea visible
        self.output_path.setToolTip(self.output_folder)  # Mostrar ruta completa en tooltip
        folder_grid.addWidget(self.output_path, 0, 1)
        
        self.btn_browse_output = QPushButton(qta.icon("fa5s.folder-open", color="#1E1E2E"), "")
        self.btn_browse_output.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        self.btn_browse_output.setMaximumWidth(40)  # Ancho máximo para solo mostrar el icono
        self.btn_browse_output.setToolTip("Seleccionar carpeta de salida")
        self.btn_browse_output.clicked.connect(self._browse_output)
        folder_grid.addWidget(self.btn_browse_output, 0, 2)
        
        export_layout.addLayout(folder_grid)
        
        # Barra de progreso
        progress_label = QLabel("Progreso:")
        progress_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        export_layout.addWidget(progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v/%m")
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.progress_bar.setMinimumHeight(20)
        export_layout.addWidget(self.progress_bar)
        
        # Estado
        self.status_label = QLabel("Listo para procesar")
        self.status_label.setAlignment(Qt.AlignCenter)
        self.status_label.setStyleSheet("font-weight: bold;")
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        export_layout.addWidget(self.status_label)
        
        # Botones de acción en una grid para mejor distribución en pantallas pequeñas
        btns_grid = QGridLayout()
        btns_grid.setSpacing(10)
        btns_grid.setColumnStretch(0, 1)  # Ambas columnas tienen el mismo peso
        btns_grid.setColumnStretch(1, 1)
        
        self.btn_generate = QPushButton(qta.icon("fa5s.play", color="#1E1E2E"), " Generar")
        self.btn_generate.clicked.connect(self._generate_videos)
        self.btn_generate.setMinimumHeight(40)  # Un poco más pequeño para pantallas compactas
        self.btn_generate.setStyleSheet("font-size: 14px;")  # Fuente un poco más pequeña
        self.btn_generate.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_generate.setToolTip("Generar videos con las opciones seleccionadas")
        btns_grid.addWidget(self.btn_generate, 0, 0)
        
        self.btn_cancel = QPushButton(qta.icon("fa5s.stop", color="#1E1E2E"), " Cancelar")
        self.btn_cancel.clicked.connect(self._cancel_process)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumHeight(40)
        self.btn_cancel.setStyleSheet("font-size: 14px;")
        self.btn_cancel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_cancel.setToolTip("Cancelar el proceso de generación")
        btns_grid.addWidget(self.btn_cancel, 0, 1)
        
        export_layout.addLayout(btns_grid)
        
        main_splitter.addWidget(export_card)
        
        # Configurar proporciones del splitter
        main_splitter.setSizes([300, 160, 300, 200])  # Tamaños relativos iniciales de cada sección
        
        # Establecer tamaños mínimos para cada widget del splitter para evitar que desaparezcan
        audio_card.setMinimumHeight(200)
        channel_card.setMinimumHeight(160)
        process_card.setMinimumHeight(200)
        export_card.setMinimumHeight(180)
        
        # Añadir el splitter al layout principal y hacerlo expandir
        main_splitter.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(main_splitter)
        
        # Pie de página con información de versión
        footer = QLabel("Type Beat Video Generator v1.0")
        footer.setAlignment(Qt.AlignRight)
        footer.setStyleSheet("color: #6C7086; font-size: 12px;")
        main_layout.addWidget(footer)
        
        # Establecer el layout principal
        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)
        
        # Inicializar variables adicionales
        self.worker = None
    
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
    
    def _update_channels_combo(self):
        """Actualiza la lista de canales en el combobox."""
        self.channel_combo.clear()
        
        # Obtener canales existentes (carpetas en la carpeta de imágenes)
        channels = []
        if os.path.exists(self.images_folder):
            channels = [d for d in os.listdir(self.images_folder) 
                       if os.path.isdir(os.path.join(self.images_folder, d))]
        
        # Actualizar la lista en la configuración
        self.config['channels'] = channels
        self._save_config()
        
        # Actualizar el combobox
        self.channel_combo.addItems(channels)
        
        # Añadir opción para agregar nuevo canal
        if channels:
            self.channel_combo.insertSeparator(len(channels))
        self.channel_combo.addItem("➕ Agregar nuevo canal...")
    
    def _update_beats_list(self):
        """Actualiza la lista de beats disponibles con iconos e información."""
        self.beats_list.clear()
        
        if os.path.exists(self.beats_folder):
            beats = [f for f in os.listdir(self.beats_folder) 
                    if f.lower().endswith(('.mp3', '.wav'))]
            self.loaded_beats = beats
            
            # Añadir elementos con iconos
            for beat in beats:
                item = QListWidgetItem()
                
                # Añadir icono según tipo de archivo
                is_mp3 = beat.lower().endswith('.mp3')
                if is_mp3:
                    item.setIcon(qta.icon('fa5s.music', color='#FAB387'))
                else:
                    item.setIcon(qta.icon('fa5s.file-audio', color='#F9E2AF'))
                
                # Texto para mostrar (acortar si es muy largo)
                display_text = beat
                if len(beat) > 35:
                    display_text = beat[:32] + "..."
                
                item.setText(display_text)
                
                # Mejorar estilo y visibilidad
                if len(beat) > 35:
                    # Usar un color más contrastante para textos truncados
                    item.setForeground(QColor('#F9E2AF'))
                
                # Añadir tooltip con información completa
                tooltip = f"<b>Archivo:</b> {beat}<br>"
                tooltip += f"<b>Tipo:</b> {'MP3' if is_mp3 else 'WAV'}<br>"
                
                # Añadir ruta completa
                full_path = os.path.join(self.beats_folder, beat)
                tooltip += f"<b>Ruta:</b> {full_path}"
                
                item.setToolTip(tooltip)
                self.beats_list.addItem(item)
    
    def _update_process_list(self):
        """Actualiza la lista de beats a procesar con iconos e información."""
        self.process_list.clear()
        
        for info in self.beats_info:
            item = QListWidgetItem()
            item.setIcon(qta.icon('fa5s.video', color='#89B4FA'))
            
            # Crear texto con formato
            channel = info.get('channel', '')
            group = info.get('group', 'Principal')
            
            # Acortar nombre de audio si es muy largo
            audio_name = info['audio']
            if len(audio_name) > 18:
                audio_name = audio_name[:15] + "..."
                
            # Crear un texto de visualización más corto pero informativo
            display_text = f"{audio_name}"
            
            # Si hay un nombre personalizado, mostrarlo con prioridad
            if info.get('custom_name'):
                custom = info['custom_name']
                if len(custom) > 20:
                    custom = custom[:17] + "..."
                display_text = f"{custom} ({audio_name})"
            
            # Añadir canal y grupo de forma compacta
            channel_text = channel
            if len(channel) > 12:
                channel_text = channel[:9] + "..."
            
            display_text += f" | {channel_text}"
            
            if group and group != "Principal":
                group_text = group
                if len(group) > 10:
                    group_text = group[:7] + "..."
                display_text += f" - {group_text}"
            
            # Mostrar texto completo en tooltip con formato HTML para mayor claridad
            full_text = f"<b>Audio:</b> {info['audio']}<br>"
            full_text += f"<b>Canal:</b> {channel}<br>"
            full_text += f"<b>Grupo:</b> {group}"
            if info.get('custom_name'):
                full_text += f"<br><b>Nombre personalizado:</b> {info['custom_name']}"
                full_text += f"<br><b>Salida:</b> {info['custom_name']}.mp4"
            else:
                base_name = os.path.splitext(info['audio'])[0]
                full_text += f"<br><b>Salida:</b> {base_name}_{channel}_{group}.mp4"
            
            item.setToolTip(full_text)    
            item.setText(display_text)
            
            # Añadir color de fondo según el canal para mejor identificación
            # Aumentar saturación para mejor visibilidad
            channel_hash = hash(channel) % 360
            item.setBackground(QColor.fromHsv(channel_hash, 70, 220, 70))
            
            # Mejorar contraste del texto para legibilidad
            item.setForeground(QColor('#FFFFFF'))
            
            self.process_list.addItem(item)
    
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
            # Copiar los archivos seleccionados a la carpeta de beats
            for path in file_paths:
                filename = os.path.basename(path)
                dest_path = os.path.join(self.beats_folder, filename)
                
                # Verificar si el archivo ya existe
                if os.path.exists(dest_path):
                    response = QMessageBox.question(
                        self,
                        "Archivo duplicado",
                        f"El archivo '{filename}' ya existe. ¿Desea reemplazarlo?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    
                    if response == QMessageBox.No:
                        continue
                
                # Copiar el archivo
                shutil.copy2(path, dest_path)
            
            # Actualizar la lista de beats
            self._update_beats_list()
    
    def _clear_beats(self):
        """Limpia la lista de beats seleccionados."""
        self.beats_list.clearSelection()
        
        # También limpiar la lista de beats a procesar
        self.beats_info = []
        self._update_process_list()
    
    def _show_beats_list_menu(self, position):
        """Muestra un menú contextual para la lista de beats disponibles."""
        selected_items = self.beats_list.selectedItems()
        if not selected_items:
            return
            
        menu = QMenu()
        delete_action = menu.addAction("Eliminar archivo(s) del disco")
        
        menu.addSeparator()
        select_all_action = menu.addAction("Seleccionar Todos")
        select_none_action = menu.addAction("Deseleccionar Todos")
        
        action = menu.exec_(self.beats_list.mapToGlobal(position))
        
        if action == delete_action:
            self._delete_beat_files()
        elif action == select_all_action:
            self.beats_list.selectAll()
        elif action == select_none_action:
            self.beats_list.clearSelection()
    
    def _delete_beat_files(self):
        """Elimina los archivos de beats seleccionados del disco."""
        selected_items = self.beats_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self,
                "Selección vacía",
                "Por favor, seleccione al menos un beat para eliminar."
            )
            return
        
        # Mostrar mensaje de confirmación con advertencia
        confirmation_message = "¿Está seguro de eliminar permanentemente "
        if len(selected_items) == 1:
            confirmation_message += f"el archivo '{selected_items[0].text()}' del disco? Esta acción no se puede deshacer."
        else:
            confirmation_message += f"los {len(selected_items)} archivos seleccionados del disco? Esta acción no se puede deshacer."
        
        confirm = QMessageBox.question(
            self,
            "Confirmar eliminación permanente",
            confirmation_message,
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return
        
        # Eliminar los archivos físicamente
        deleted_files = []
        failed_files = []
        
        for item in selected_items:
            file_name = item.text()
            file_path = os.path.join(self.beats_folder, file_name)
            
            try:
                os.remove(file_path)
                deleted_files.append(file_name)
                
                # También eliminar el archivo de la lista de procesamiento si está ahí
                for i, info in reversed(list(enumerate(self.beats_info))):
                    if info['audio'] == file_name:
                        del self.beats_info[i]
                
            except Exception as e:
                failed_files.append((file_name, str(e)))
        
        # Actualizar la lista de beats
        self._update_beats_list()
        self._update_process_list()
        
        # Mostrar mensaje de resultados
        if deleted_files:
            message = ""
            if len(deleted_files) == 1:
                message = f"Se eliminó correctamente el archivo '{deleted_files[0]}'."
            else:
                message = f"Se eliminaron correctamente {len(deleted_files)} archivos."
                
            if failed_files:
                message += "\n\nLos siguientes archivos no pudieron eliminarse:\n"
                for file_name, error in failed_files:
                    message += f"• {file_name}: {error}\n"
                
            QMessageBox.information(
                self,
                "Eliminación de archivos",
                message
            )
    
    def _manage_channels(self):
        """Abre el diálogo para gestionar canales de YouTube."""
        selected_channel = self.channel_combo.currentText()
        
        # Verificar si se seleccionó "Agregar nuevo canal"
        if selected_channel == "➕ Agregar nuevo canal...":
            self._add_new_channel()
            return
        
        # Si no hay canal seleccionado, mostrar lista de canales
        if not selected_channel or selected_channel not in self.config['channels']:
            channels_dialog = QDialog(self)
            channels_dialog.setWindowTitle("Gestionar Canales de YouTube")
            channels_dialog.setMinimumWidth(500)
            
            layout = QVBoxLayout()
            
            layout.addWidget(QLabel("<h3>Canales Disponibles</h3>"))
            
            channels_list = QListWidget()
            channels_list.addItems(self.config['channels'])
            layout.addWidget(channels_list)
            
            btns_layout = QHBoxLayout()
            
            btn_add = QPushButton("Agregar Canal")
            btn_add.setIcon(qta.icon("fa5s.plus", color="#1E1E2E"))
            btn_add.clicked.connect(lambda: self._add_new_channel(channels_dialog))
            btns_layout.addWidget(btn_add)
            
            btn_edit = QPushButton("Gestionar Grupos de Imágenes")
            btn_edit.setIcon(qta.icon("fa5s.images", color="#1E1E2E"))
            btn_edit.clicked.connect(lambda: self._edit_channel_images(channels_list.currentItem().text() if channels_list.currentItem() else None))
            btns_layout.addWidget(btn_edit)
            
            layout.addLayout(btns_layout)
            
            btn_close = QPushButton("Cerrar")
            btn_close.clicked.connect(channels_dialog.accept)
            layout.addWidget(btn_close)
            
            channels_dialog.setLayout(layout)
            channels_dialog.exec_()
        else:
            # Abrir directamente el gestor de imágenes para el canal seleccionado
            self._edit_channel_images(selected_channel)
    
    def _add_new_channel(self, parent_dialog=None):
        """Abre un diálogo para agregar un nuevo canal."""
        dialog = AddChannelDialog(parent_dialog or self)
        
        if dialog.exec_() == QDialog.Accepted and dialog.channel_name:
            channel_name = dialog.channel_name
            
            # Crear carpeta para el nuevo canal
            channel_folder = os.path.join(self.images_folder, channel_name)
            os.makedirs(channel_folder, exist_ok=True)
            
            # Crear el grupo Principal por defecto
            principal_folder = os.path.join(channel_folder, "Principal")
            os.makedirs(principal_folder, exist_ok=True)
            
            # Actualizar la lista de canales
            if channel_name not in self.config['channels']:
                if 'channels' not in self.config:
                    self.config['channels'] = []
                self.config['channels'].append(channel_name)
                self._save_config()
            
            # Actualizar el combobox
            self._update_channels_combo()
            
            # Seleccionar el nuevo canal
            index = self.channel_combo.findText(channel_name)
            if index >= 0:
                self.channel_combo.setCurrentIndex(index)
            
            # Actualizar el combobox de grupos
            self._update_groups_for_channel(channel_name)
            
            # Abrir el gestor de imágenes para el nuevo canal
            self._edit_channel_images(channel_name)
    
    def _edit_channel_images(self, channel, group=None):
        """Abre el gestor de imágenes para un canal específico."""
        if not channel or channel == "➕ Agregar nuevo canal...":
            return
        
        dialog = ChannelImagesDialog(channel, self.images_folder, self, group)
        dialog.exec_()
        
        # Actualizar el combobox de grupos para reflejar cambios
        self._update_groups_for_channel(channel)
    
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
    
    def _assign_channel_and_group(self):
        """Asigna un canal y grupo a los beats seleccionados."""
        selected_items = self.beats_list.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(
                self,
                "Selección vacía",
                "Por favor, seleccione al menos un beat de la lista."
            )
            return
        
        current_channel = self.channel_combo.currentText()
        
        if current_channel == "➕ Agregar nuevo canal...":
            QMessageBox.warning(
                self,
                "Selección inválida",
                "Por favor, seleccione un canal existente o cree uno nuevo."
            )
            return
        
        # Seleccionar grupo
        current_group = self.group_combo.currentText() if hasattr(self, 'group_combo') else None
        
        # Si no hay grupos o el canal no tiene grupos, seleccionamos el grupo de forma dinámica
        channel_folder = os.path.join(self.images_folder, current_channel)
        
        # Comprobar si el canal tiene grupos
        has_groups = False
        if os.path.exists(channel_folder):
            groups = [d for d in os.listdir(channel_folder) 
                     if os.path.isdir(os.path.join(channel_folder, d))]
            has_groups = len(groups) > 0
        
        if not has_groups:
            # Crear el grupo Principal si no existe
            principal_folder = os.path.join(channel_folder, "Principal")
            os.makedirs(principal_folder, exist_ok=True)
            current_group = "Principal"
        elif not current_group:
            # Mostrar diálogo para seleccionar grupo
            groups_dialog = QDialog(self)
            groups_dialog.setWindowTitle(f"Seleccionar grupo para canal '{current_channel}'")
            
            layout = QVBoxLayout()
            layout.addWidget(QLabel(f"Selecciona un grupo de imágenes para el canal <b>{current_channel}</b>:"))
            
            group_list = QListWidget()
            groups = [d for d in os.listdir(channel_folder) 
                     if os.path.isdir(os.path.join(channel_folder, d))]
            group_list.addItems(groups)
            
            # Seleccionar el primer grupo por defecto
            if groups:
                group_list.setCurrentRow(0)
            
            layout.addWidget(group_list)
            
            btn_layout = QHBoxLayout()
            
            btn_cancel = QPushButton("Cancelar")
            btn_cancel.clicked.connect(groups_dialog.reject)
            btn_layout.addWidget(btn_cancel)
            
            btn_select = QPushButton("Seleccionar")
            btn_select.clicked.connect(groups_dialog.accept)
            btn_layout.addWidget(btn_select)
            
            layout.addLayout(btn_layout)
            groups_dialog.setLayout(layout)
            
            if groups_dialog.exec_() == QDialog.Accepted and group_list.currentItem():
                current_group = group_list.currentItem().text()
            else:
                return
        
        # Verificar si existen imágenes para el grupo
        group_folder = os.path.join(channel_folder, current_group)
        image_files = []
        if os.path.exists(group_folder):
            image_files = [f for f in os.listdir(group_folder) 
                          if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
        
        if not image_files:
            response = QMessageBox.question(
                self,
                "Sin imágenes",
                f"El grupo '{current_group}' del canal '{current_channel}' no tiene imágenes. ¿Desea agregar ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if response == QMessageBox.Yes:
                self._edit_channel_images(current_channel, current_group)
                return
        
        # Asignar canal y grupo a los beats seleccionados
        for item in selected_items:
            beat_name = item.text()
            
            # Verificar si el beat ya está en la lista
            existing_index = -1
            for i, info in enumerate(self.beats_info):
                if info['audio'] == beat_name:
                    existing_index = i
                    break
            
            if existing_index >= 0:
                # Actualizar canal y grupo
                self.beats_info[existing_index]['channel'] = current_channel
                self.beats_info[existing_index]['group'] = current_group
            else:
                # Agregar a la lista
                self.beats_info.append({
                    'audio': beat_name,
                    'channel': current_channel,
                    'group': current_group
                })
        
        # Actualizar la lista de proceso
        self._update_process_list()
    
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
            # Truncar la ruta si es muy larga para mostrarla
            display_path = folder_path
            if len(folder_path) > 40:
                display_path = "..." + folder_path[-37:]
            
            self.output_path.setText(display_path)
            self.output_path.setToolTip(folder_path)  # Mostrar ruta completa en tooltip
            
            # Guardar en la configuración
            self.config['last_output_folder'] = folder_path
            self._save_config()
            
    def _generate_videos(self):
        """Inicia el proceso de generación de videos."""
        if not self.beats_info:
            QMessageBox.warning(
                self,
                "Lista vacía",
                "No hay beats para procesar. Asigne canales y grupos a los beats primero."
            )
            return
        
        # Verificar que la carpeta de salida existe
        if not os.path.exists(self.output_folder):
            try:
                os.makedirs(self.output_folder, exist_ok=True)
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Error",
                    f"No se pudo crear la carpeta de salida: {str(e)}"
                )
                return
        
        # Verificar que todos los canales y grupos tengan imágenes
        missing_images = []
        for info in self.beats_info:
            channel = info.get('channel', '')
            group = info.get('group', 'Principal')
            
            if not channel:
                QMessageBox.critical(
                    self,
                    "Error",
                    "Algunos beats no tienen un canal asignado. Por favor, asigne un canal a todos los beats."
                )
                return
            
            group_folder = os.path.join(self.images_folder, channel, group)
            
            if not os.path.exists(group_folder) or not os.listdir(group_folder):
                missing_images.append(f"Canal: {channel}, Grupo: {group}")
        
        if missing_images:
            QMessageBox.critical(
                self,
                "Error",
                f"Los siguientes canales/grupos no tienen imágenes: {', '.join(set(missing_images))}"
            )
            return
        
        # Deshabilitar interfaz durante el procesamiento
        self._set_ui_processing(True)
        
        # Iniciar el worker
        self.worker = VideoGeneratorWorker(
            self.beats_folder,
            self.images_folder,
            self.output_folder,
            self.beats_info
        )
        
        # Conectar señales
        self.worker.progress_updated.connect(self._update_progress)
        self.worker.finished.connect(self._process_finished)
        
        # Iniciar el proceso
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
            QMessageBox.information(
                self,
                "Proceso completado",
                message + "\n\nPara cada video, se ha copiado la imagen utilizada con el nombre: 'nombre_del_video_imagen.jpg'"
            )
        else:
            QMessageBox.warning(
                self,
                "Error",
                message
            )
    
    def _show_process_list_menu(self, position):
        """Muestra un menú contextual para la lista de procesos."""
        menu = QMenu()
        edit_action = menu.addAction("Editar Nombre de Video")
        remove_action = menu.addAction("Quitar de la Lista")
        
        menu.addSeparator()
        select_all_action = menu.addAction("Seleccionar Todos")
        select_none_action = menu.addAction("Deseleccionar Todos")
        
        action = menu.exec_(self.process_list.mapToGlobal(position))
        
        if action == edit_action:
            self._edit_selected_beat_name()
        elif action == remove_action:
            self._remove_selected_beat()
        elif action == select_all_action:
            self.process_list.selectAll()
        elif action == select_none_action:
            self.process_list.clearSelection()
    
    def _edit_selected_beat_name(self):
        """Abre un diálogo para editar el nombre personalizado del beat seleccionado."""
        selected_items = self.process_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self,
                "Selección vacía",
                "Por favor, seleccione un beat de la lista para editar su nombre."
            )
            return
        
        # Solo permitimos editar un beat a la vez
        selected_index = self.process_list.row(selected_items[0])
        if selected_index < 0 or selected_index >= len(self.beats_info):
            return
        
        beat_info = self.beats_info[selected_index]
        dialog = EditBeatNameDialog(beat_info, self)
        
        if dialog.exec_() == QDialog.Accepted:
            # Actualizar el nombre personalizado
            self.beats_info[selected_index]['custom_name'] = dialog.custom_name
            # Actualizar la lista de procesos
            self._update_process_list()
    
    def _edit_beat_name(self, item):
        """Maneja el doble clic en un elemento de la lista de procesos."""
        self._edit_selected_beat_name()
    
    def _remove_selected_beat(self):
        """Quita los beats seleccionados de la lista de procesos."""
        selected_items = self.process_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(
                self,
                "Selección vacía",
                "Por favor, seleccione al menos un beat de la lista para eliminar."
            )
            return
        
        # Mostrar mensaje de confirmación
        confirmation_message = "¿Está seguro de eliminar "
        if len(selected_items) == 1:
            confirmation_message += "este beat de la lista?"
        else:
            confirmation_message += f"estos {len(selected_items)} beats de la lista?"
        
        confirm = QMessageBox.question(
            self,
            "Confirmar eliminación",
            confirmation_message,
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm != QMessageBox.Yes:
            return
        
        # Obtener índices de los elementos seleccionados (en orden descendente para eliminar correctamente)
        indices = sorted([self.process_list.row(item) for item in selected_items], reverse=True)
        
        # Guardar nombres de beats para mostrar en mensaje
        removed_beats = []
        
        # Eliminar los elementos de la lista de beats_info
        for index in indices:
            if index < len(self.beats_info):
                beat_info = self.beats_info[index]
                removed_beats.append(beat_info['audio'])
                del self.beats_info[index]
        
        # Actualizar la lista de procesos
        self._update_process_list()
        
        # Mostrar mensaje de éxito
        if removed_beats:
            if len(removed_beats) == 1:
                QMessageBox.information(
                    self,
                    "Beat eliminado",
                    f"Se eliminó '{removed_beats[0]}' de la lista de procesamiento."
                )
            else:
                QMessageBox.information(
                    self,
                    "Beats eliminados",
                    f"Se eliminaron {len(removed_beats)} beats de la lista de procesamiento."
                )
    
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
