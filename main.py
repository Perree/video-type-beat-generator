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
                            QDialog, QLineEdit, QGridLayout, QMenu)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QPixmap, QIcon

# Importar el diálogo para editar nombres de beat
from edit_beat_dialog import EditBeatNameDialog

# Constantes
CONFIG_FILE = os.path.join('config', 'app_config.json')
DEFAULT_CONFIG = {
    'last_output_folder': 'exported_videos',
    'genres': []  # Lista de géneros conocidos
}

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
        self.running = True
    
    def run(self):
        """Ejecuta el proceso de generación de videos."""
        try:
            used_images = {}
            total_beats = len(self.beats_info)
            
            for i, info in enumerate(self.beats_info):
                if not self.running:
                    self.finished.emit(False, "Proceso cancelado por el usuario.")
                    return
                
                genre = info["genre"]
                audio_file = info["audio"]
                
                self.progress_updated.emit(
                    int((i / total_beats) * 100),
                    f"Procesando: {audio_file} ({i+1}/{total_beats})"
                )
                
                # Obtener imágenes para el género
                images = self._get_images_for_genre(genre)
                if not images:
                    self.finished.emit(False, f"No hay imágenes para el género '{genre}'.")
                    return
                
                # Gestionar las imágenes usadas
                if genre not in used_images:
                    used_images[genre] = set()
                
                # Filtrar imágenes ya utilizadas
                available_images = [img for img in images if img not in used_images[genre]]
                if not available_images:
                    # Si todas las imágenes fueron usadas, reiniciar para este género
                    used_images[genre] = set()
                    available_images = images
                
                # Seleccionar imagen aleatoria
                image = random.choice(available_images)
                used_images[genre].add(image)
                
                # Crear carpeta de género en la salida
                audio_path = os.path.join(self.beats_folder, audio_file)
                
                # Usar nombre personalizado si existe, o el formato predeterminado si no
                if info.get('custom_name'):
                    base_output_name = f"{info['custom_name']}"
                else:
                    base_output_name = f"{os.path.splitext(audio_file)[0]}_{genre}"
                
                output_name = f"{base_output_name}.mp4"
                    
                genre_folder = os.path.join(self.output_folder, genre)
                os.makedirs(genre_folder, exist_ok=True)
                output_path = os.path.join(genre_folder, output_name)
                
                # Generar video
                self.progress_updated.emit(
                    int((i / total_beats) * 100),
                    f"Generando video para: {audio_file}"
                )
                self._generate_video(audio_path, image, output_path)
                
                # Copiar la imagen utilizada junto al video
                image_extension = os.path.splitext(image)[1]
                image_output_name = f"{base_output_name}_imagen{image_extension}"
                image_output_path = os.path.join(genre_folder, image_output_name)
                
                try:
                    shutil.copy2(image, image_output_path)
                except Exception as e:
                    print(f"No se pudo copiar la imagen: {str(e)}")
                
            self.progress_updated.emit(100, "Proceso completado!")
            self.finished.emit(True, f"Se generaron {total_beats} videos exitosamente. Para cada video, se guardó también la imagen utilizada.")
            
        except Exception as e:
            self.finished.emit(False, f"Error: {str(e)}")
    
    def _get_images_for_genre(self, genre):
        """Obtiene la lista de imágenes para un género específico."""
        images_folder = os.path.join(self.images_folder, genre)
        if not os.path.exists(images_folder):
            return []
        
        return [os.path.join(images_folder, img) for img in os.listdir(images_folder) 
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
        self.running = False


class GenreImagesDialog(QDialog):
    """Diálogo para gestionar imágenes de un género."""
    
    def __init__(self, genre, images_folder, parent=None):
        super().__init__(parent)
        self.genre = genre
        self.images_folder = images_folder
        self.genre_folder = os.path.join(images_folder, genre)
        
        # Crear la carpeta si no existe
        os.makedirs(self.genre_folder, exist_ok=True)
        
        self._setup_ui()
        self._load_images()
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        self.setWindowTitle(f"Gestionar imágenes para '{self.genre}'")
        self.setMinimumWidth(600)
        self.setMinimumHeight(400)
        
        layout = QVBoxLayout()
        
        # Sección de información
        info_label = QLabel(f"Imágenes para el género: <b>{self.genre}</b>")
        layout.addWidget(info_label)
        
        # Lista de imágenes
        self.images_list = QListWidget()
        layout.addWidget(self.images_list)
        
        # Botones para gestionar imágenes
        btn_layout = QHBoxLayout()
        
        self.btn_add = QPushButton("Agregar imágenes")
        self.btn_add.clicked.connect(self._add_images)
        btn_layout.addWidget(self.btn_add)
        
        self.btn_remove = QPushButton("Eliminar seleccionadas")
        self.btn_remove.clicked.connect(self._remove_images)
        btn_layout.addWidget(self.btn_remove)
        
        layout.addLayout(btn_layout)
        
        # Botón de cerrar
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        layout.addWidget(self.btn_close)
        
        self.setLayout(layout)
    
    def _load_images(self):
        """Carga la lista de imágenes del género."""
        self.images_list.clear()
        
        if os.path.exists(self.genre_folder):
            images = [img for img in os.listdir(self.genre_folder) 
                     if img.lower().endswith(('.jpg', '.jpeg', '.png'))]
            
            self.images_list.addItems(images)
    
    def _add_images(self):
        """Permite al usuario agregar imágenes al género."""
        file_dialog = QFileDialog()
        file_paths, _ = file_dialog.getOpenFileNames(
            self,
            "Seleccionar imágenes",
            "",
            "Imágenes (*.png *.jpg *.jpeg)"
        )
        
        if file_paths:
            for path in file_paths:
                filename = os.path.basename(path)
                dest_path = os.path.join(self.genre_folder, filename)
                
                # Copiar el archivo a la carpeta del género
                shutil.copy2(path, dest_path)
            
            # Recargar la lista de imágenes
            self._load_images()
    
    def _remove_images(self):
        """Elimina las imágenes seleccionadas."""
        selected_items = self.images_list.selectedItems()
        
        if not selected_items:
            return
        
        confirm = QMessageBox.question(
            self,
            "Confirmar eliminación",
            f"¿Está seguro de eliminar {len(selected_items)} imagen(es)?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            for item in selected_items:
                image_path = os.path.join(self.genre_folder, item.text())
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


class AddGenreDialog(QDialog):
    """Diálogo para agregar un nuevo género."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.genre_name = ""
        
        self._setup_ui()
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo."""
        self.setWindowTitle("Agregar nuevo género")
        self.setFixedSize(400, 120)
        
        layout = QVBoxLayout()
        
        # Campo para el nombre del género
        form_layout = QGridLayout()
        form_layout.addWidget(QLabel("Nombre del género:"), 0, 0)
        
        self.genre_input = QLineEdit()
        form_layout.addWidget(self.genre_input, 0, 1)
        
        layout.addLayout(form_layout)
        
        # Botones
        btn_layout = QHBoxLayout()
        
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_add = QPushButton("Agregar")
        self.btn_add.clicked.connect(self._add_genre)
        btn_layout.addWidget(self.btn_add)
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def _add_genre(self):
        """Valida y guarda el nombre del género."""
        genre = self.genre_input.text().strip()
        
        if not genre:
            QMessageBox.warning(
                self,
                "Error",
                "El nombre del género no puede estar vacío."
            )
            return
        
        self.genre_name = genre
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
        
        # Configurar la interfaz
        self._setup_ui()
        
        # Actualizar la lista de beats
        self._update_beats_list()
    
    def _setup_ui(self):
        """Configura la interfaz de usuario."""
        self.setWindowTitle("Type Beat Video Generator")
        self.setMinimumSize(800, 600)
        
        # Widget central y layout principal
        central_widget = QWidget()
        main_layout = QVBoxLayout()
        
        # Sección de carga de beats
        beats_section = QVBoxLayout()
        beats_section.addWidget(QLabel("<h3>Archivos de Audio</h3>"))
        
        beats_btns_layout = QHBoxLayout()
        
        self.btn_load_beats = QPushButton("Cargar Beats")
        self.btn_load_beats.clicked.connect(self._load_beats)
        beats_btns_layout.addWidget(self.btn_load_beats)
        
        self.btn_delete_beats = QPushButton("Eliminar Archivos")
        self.btn_delete_beats.clicked.connect(self._delete_beat_files)
        beats_btns_layout.addWidget(self.btn_delete_beats)
        
        self.btn_clear_beats = QPushButton("Limpiar Lista")
        self.btn_clear_beats.clicked.connect(self._clear_beats)
        beats_btns_layout.addWidget(self.btn_clear_beats)
        
        beats_section.addLayout(beats_btns_layout)
        
        # Lista de beats
        self.beats_list = QListWidget()
        self.beats_list.setSelectionMode(QListWidget.ExtendedSelection)  # Permitir selección múltiple
        beats_section.addWidget(self.beats_list)
        
        main_layout.addLayout(beats_section)
        
        # Sección de asignación de géneros
        genres_section = QVBoxLayout()
        genres_section.addWidget(QLabel("<h3>Asignación de Géneros</h3>"))
        
        genres_layout = QHBoxLayout()
        
        genres_layout.addWidget(QLabel("Género:"))
        
        self.genre_combo = QComboBox()
        self._update_genres_combo()
        genres_layout.addWidget(self.genre_combo)
        
        self.btn_manage_genres = QPushButton("Gestionar Géneros")
        self.btn_manage_genres.clicked.connect(self._manage_genres)
        genres_layout.addWidget(self.btn_manage_genres)
        
        self.btn_assign_genre = QPushButton("Asignar a Seleccionados")
        self.btn_assign_genre.clicked.connect(self._assign_genre)
        genres_layout.addWidget(self.btn_assign_genre)
        
        genres_section.addLayout(genres_layout)
        
        main_layout.addLayout(genres_section)
        
        # Sección de tabla de asignaciones
        main_layout.addWidget(QLabel("<h3>Beats a Procesar</h3>"))
        self.process_list = QListWidget()
        self.process_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.process_list.customContextMenuRequested.connect(self._show_process_list_menu)
        self.process_list.doubleClicked.connect(self._edit_beat_name)
        self.process_list.setSelectionMode(QListWidget.ExtendedSelection)  # Permitir selección múltiple
        main_layout.addWidget(self.process_list)
        
        # Botones para editar nombre y eliminar beats
        edit_name_btn_layout = QHBoxLayout()
        
        self.btn_edit_name = QPushButton("Editar Nombre de Video")
        self.btn_edit_name.clicked.connect(self._edit_selected_beat_name)
        edit_name_btn_layout.addWidget(self.btn_edit_name)
        
        self.btn_remove_beat = QPushButton("Eliminar Seleccionados")
        self.btn_remove_beat.clicked.connect(self._remove_selected_beat)
        edit_name_btn_layout.addWidget(self.btn_remove_beat)
        
        main_layout.addLayout(edit_name_btn_layout)
        
        # Sección de exportación
        export_section = QVBoxLayout()
        export_section.addWidget(QLabel("<h3>Exportación</h3>"))
        
        export_layout = QHBoxLayout()
        
        export_layout.addWidget(QLabel("Carpeta de salida:"))
        
        self.output_path = QLineEdit()
        self.output_path.setText(self.output_folder)
        self.output_path.setReadOnly(True)
        export_layout.addWidget(self.output_path)
        
        self.btn_browse_output = QPushButton("Examinar")
        self.btn_browse_output.clicked.connect(self._browse_output)
        export_layout.addWidget(self.btn_browse_output)
        
        export_section.addLayout(export_layout)
        
        # Barra de progreso
        export_section.addWidget(QLabel("Progreso:"))
        self.progress_bar = QProgressBar()
        export_section.addWidget(self.progress_bar)
        
        self.status_label = QLabel("Listo para procesar")
        export_section.addWidget(self.status_label)
        
        # Botones de acción
        btns_layout = QHBoxLayout()
        
        self.btn_generate = QPushButton("Generar Videos")
        self.btn_generate.clicked.connect(self._generate_videos)
        self.btn_generate.setMinimumHeight(40)
        btns_layout.addWidget(self.btn_generate)
        
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.clicked.connect(self._cancel_process)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setMinimumHeight(40)
        btns_layout.addWidget(self.btn_cancel)
        
        export_section.addLayout(btns_layout)
        
        main_layout.addLayout(export_section)
        
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
    
    def _update_genres_combo(self):
        """Actualiza la lista de géneros en el combobox."""
        self.genre_combo.clear()
        
        # Obtener géneros existentes (carpetas en la carpeta de imágenes)
        genres = []
        if os.path.exists(self.images_folder):
            genres = [d for d in os.listdir(self.images_folder) 
                     if os.path.isdir(os.path.join(self.images_folder, d))]
        
        # Actualizar la lista en la configuración
        self.config['genres'] = genres
        self._save_config()
        
        # Actualizar el combobox
        self.genre_combo.addItems(genres)
        
        # Añadir opción para agregar nuevo género
        if genres:
            self.genre_combo.insertSeparator(len(genres))
        self.genre_combo.addItem("➕ Agregar nuevo género...")
    
    def _update_beats_list(self):
        """Actualiza la lista de beats disponibles."""
        self.beats_list.clear()
        
        if os.path.exists(self.beats_folder):
            beats = [f for f in os.listdir(self.beats_folder) 
                    if f.lower().endswith(('.mp3', '.wav'))]
            self.loaded_beats = beats
            self.beats_list.addItems(beats)
        
        # Habilitar el menú contextual en la lista de beats
        self.beats_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.beats_list.customContextMenuRequested.connect(self._show_beats_list_menu)
    
    def _update_process_list(self):
        """Actualiza la lista de beats a procesar."""
        self.process_list.clear()
        
        for info in self.beats_info:
            display_text = f"{info['audio']} - Género: {info['genre']}"
            if info.get('custom_name'):
                display_text += f" - Nombre de video: {info['custom_name']}"
            self.process_list.addItem(display_text)
    
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
    
    def _manage_genres(self):
        """Abre el diálogo para gestionar géneros."""
        selected_genre = self.genre_combo.currentText()
        
        # Verificar si se seleccionó "Agregar nuevo género"
        if selected_genre == "➕ Agregar nuevo género...":
            self._add_new_genre()
            return
        
        # Si no hay género seleccionado, mostrar lista de géneros
        if not selected_genre or selected_genre not in self.config['genres']:
            genres_dialog = QDialog(self)
            genres_dialog.setWindowTitle("Gestionar Géneros")
            genres_dialog.setMinimumWidth(400)
            
            layout = QVBoxLayout()
            
            layout.addWidget(QLabel("<h3>Géneros Disponibles</h3>"))
            
            genres_list = QListWidget()
            genres_list.addItems(self.config['genres'])
            layout.addWidget(genres_list)
            
            btns_layout = QHBoxLayout()
            
            btn_add = QPushButton("Agregar Género")
            btn_add.clicked.connect(lambda: self._add_new_genre(genres_dialog))
            btns_layout.addWidget(btn_add)
            
            btn_edit = QPushButton("Editar Imágenes")
            btn_edit.clicked.connect(lambda: self._edit_genre_images(genres_list.currentItem().text()))
            btns_layout.addWidget(btn_edit)
            
            layout.addLayout(btns_layout)
            
            btn_close = QPushButton("Cerrar")
            btn_close.clicked.connect(genres_dialog.accept)
            layout.addWidget(btn_close)
            
            genres_dialog.setLayout(layout)
            genres_dialog.exec_()
        else:
            # Abrir directamente el gestor de imágenes para el género seleccionado
            self._edit_genre_images(selected_genre)
    
    def _add_new_genre(self, parent_dialog=None):
        """Abre un diálogo para agregar un nuevo género."""
        dialog = AddGenreDialog(parent_dialog or self)
        
        if dialog.exec_() == QDialog.Accepted and dialog.genre_name:
            genre_name = dialog.genre_name
            
            # Crear carpeta para el nuevo género
            genre_folder = os.path.join(self.images_folder, genre_name)
            os.makedirs(genre_folder, exist_ok=True)
            
            # Actualizar la lista de géneros
            if genre_name not in self.config['genres']:
                self.config['genres'].append(genre_name)
                self._save_config()
            
            # Actualizar el combobox
            self._update_genres_combo()
            
            # Seleccionar el nuevo género
            index = self.genre_combo.findText(genre_name)
            if index >= 0:
                self.genre_combo.setCurrentIndex(index)
            
            # Abrir el gestor de imágenes para el nuevo género
            self._edit_genre_images(genre_name)
    
    def _edit_genre_images(self, genre):
        """Abre el gestor de imágenes para un género específico."""
        if not genre or genre == "➕ Agregar nuevo género...":
            return
        
        dialog = GenreImagesDialog(genre, self.images_folder, self)
        dialog.exec_()
    
    def _assign_genre(self):
        """Asigna un género a los beats seleccionados."""
        selected_items = self.beats_list.selectedItems()
        
        if not selected_items:
            QMessageBox.warning(
                self,
                "Selección vacía",
                "Por favor, seleccione al menos un beat de la lista."
            )
            return
        
        current_genre = self.genre_combo.currentText()
        
        if current_genre == "➕ Agregar nuevo género...":
            QMessageBox.warning(
                self,
                "Selección inválida",
                "Por favor, seleccione un género existente o cree uno nuevo."
            )
            return
        
        # Verificar si existen imágenes para el género
        genre_folder = os.path.join(self.images_folder, current_genre)
        if not os.path.exists(genre_folder) or not os.listdir(genre_folder):
            response = QMessageBox.question(
                self,
                "Sin imágenes",
                f"El género '{current_genre}' no tiene imágenes. ¿Desea agregar ahora?",
                QMessageBox.Yes | QMessageBox.No
            )
            
            if response == QMessageBox.Yes:
                self._edit_genre_images(current_genre)
                return
        
        # Asignar género a los beats seleccionados
        for item in selected_items:
            beat_name = item.text()
            
            # Verificar si el beat ya está en la lista
            existing_index = -1
            for i, info in enumerate(self.beats_info):
                if info['audio'] == beat_name:
                    existing_index = i
                    break
            
            if existing_index >= 0:
                # Actualizar género
                self.beats_info[existing_index]['genre'] = current_genre
            else:
                # Agregar a la lista
                self.beats_info.append({
                    'audio': beat_name,
                    'genre': current_genre
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
            self.output_path.setText(folder_path)
            
            # Guardar en la configuración
            self.config['last_output_folder'] = folder_path
            self._save_config()
    
    def _generate_videos(self):
        """Inicia el proceso de generación de videos."""
        if not self.beats_info:
            QMessageBox.warning(
                self,
                "Lista vacía",
                "No hay beats para procesar. Asigne géneros a los beats primero."
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
        
        # Verificar que todos los géneros tengan imágenes
        missing_images = []
        for info in self.beats_info:
            genre = info['genre']
            genre_folder = os.path.join(self.images_folder, genre)
            
            if not os.path.exists(genre_folder) or not os.listdir(genre_folder):
                missing_images.append(genre)
        
        if missing_images:
            QMessageBox.critical(
                self,
                "Error",
                f"Los siguientes géneros no tienen imágenes: {', '.join(set(missing_images))}"
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
            self.worker.stop()
    
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
        self.btn_assign_genre.setEnabled(not is_processing)
        self.btn_manage_genres.setEnabled(not is_processing)
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
