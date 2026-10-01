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
import csv
from datetime import datetime
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
from library_dialog import LibraryDialog
from core import library, description, youtube
from core.upload_worker import ConnectChannelWorker, YouTubeUploadWorker

# Constantes
CONFIG_FILE = os.path.join('config', 'app_config.json')
# Extensiones de imagen (Pinterest y descargas: jfif, webp, etc.; FFmpeg las soporta)
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.jfif', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic')
IMAGE_EXTENSIONS_LIST = list(IMAGE_EXTENSIONS)
DEFAULT_CONFIG = {
    'last_output_folder': 'exported_videos',
    'last_channel': '',
    'last_group': '',
    'last_content_type': 'images',
    'last_beats_folder': '',
    'name_template': '[Type] {name} | Free for Profit',  # SEO: {name}, {channel}, {group}
    'overlay_enabled': False,
    'overlay_text': '{name} Type Beat',
    'cta_enabled': False,
    'cta_text': 'Like | Subscribe | Link in description',
    'vertical_enabled': False,
    'channels': {}  # Canales: { "nombre": { "groups": [...] } }
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

def _sanitize_filename(s):
    """Elimina caracteres no válidos para nombres de archivo."""
    for c in '\\/:*?"<>|':
        s = s.replace(c, '_')
    return s[:200].strip() or 'video'


def _escape_drawtext(s):
    """Escapa texto para drawtext de FFmpeg (comillas y dos puntos)."""
    if not s:
        return ''
    return s.replace('\\', '\\\\').replace("'", "\\'").replace(':', '\\:')


def _get_available_video_codec(ffmpeg_path):
    """Detecta si h264_nvenc está disponible, retorna el codec a usar (h264_nvenc o libx264 fallback)."""
    try:
        result = subprocess.run([ffmpeg_path, "-codecs"], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=5)
        if "h264_nvenc" in result.stdout:
            print("✓ Aceleración GPU (h264_nvenc) detectada")
            return "h264_nvenc"
    except:
        pass
    print("ℹ Usando codec por defecto (libx264)")
    return "libx264"


def _build_vf_with_overlays(base_vf, overlay_display=None, cta_text=None, audio_duration=None):
    """Añade overlay de título y CTA (último 15% del video) al filtro de video. Sin escape_text (no soportado en todas las builds de FFmpeg)."""
    vf = base_vf
    if overlay_display:
        vf += ",drawtext=text='{}':fontsize=32:fontcolor=white:bordercolor=black:borderw=2:x=(w-tw)/2:y=80".format(_escape_drawtext(overlay_display))
    if cta_text and audio_duration is not None and audio_duration > 0:
        t0 = audio_duration * 0.85
        t1 = audio_duration + 1
        vf += ",drawtext=text='{}':fontsize=24:fontcolor=white:bordercolor=black:borderw=1:x=(w-tw)/2:y=h-60:enable='between(t,{},{})'".format(_escape_drawtext(cta_text), t0, t1)
    return vf


VERTICAL_CLIP_SECONDS = 45  # Duración objetivo del clip vertical (rango válido 30-60 s)
VERTICAL_START_RATIO = 0.2  # El clip arranca al 20% del beat (evita la intro)


def _vertical_clip_window(audio_duration):
    """Devuelve (inicio, duración) en segundos para el clip vertical.
    Duración 45 s (30-60 s); si el beat es más corto se usa completo."""
    dur = float(VERTICAL_CLIP_SECONDS)
    if not audio_duration or audio_duration <= dur:
        return 0.0, (audio_duration or dur)
    start = min(audio_duration * VERTICAL_START_RATIO, audio_duration - dur)
    return max(start, 0.0), dur


def _build_vertical_cmd(ffmpeg_path, content_path, audio_path, output_file, content_type, audio_duration):
    """Comando FFmpeg para un clip 1080x1920 (9:16) con recorte centrado."""
    start, dur = _vertical_clip_window(audio_duration)
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    fade_out_at = max(dur - 1.5, 0)
    af = f"afade=t=in:d=0.5,afade=t=out:st={fade_out_at:.3f}:d=1.5"
    if content_type == "videos":
        video_in = ["-stream_loop", "-1", "-i", content_path]
    else:
        video_in = ["-loop", "1", "-i", content_path]
    cmd = [ffmpeg_path] + video_in + ["-ss", f"{start:.3f}", "-i", audio_path,
        "-map", "0:v", "-map", "1:a",
        "-vf", vf, "-af", af,
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", "-y", output_file]
    if content_type != "videos":
        cmd[cmd.index("-preset") + 2:cmd.index("-preset") + 2] = ["-tune", "stillimage"]
    return cmd


class VideoGeneratorWorker(QThread):
    """Clase para procesar la generación de videos en un hilo separado."""
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, beats_folder, images_folder, output_folder, beats_info, content_type="images", main_window=None, name_template=None,
                 overlay_enabled=False, overlay_text=None, cta_enabled=False, cta_text=None, vertical_enabled=False):
        super().__init__()
        self.vertical_enabled = vertical_enabled
        self.beats_folder = beats_folder
        self.images_folder = images_folder
        self.output_folder = output_folder
        self.beats_info = beats_info
        self.content_type = content_type
        self.main_window = main_window
        self.name_template = name_template or '[Type] {name} | Free for Profit'
        self.overlay_enabled = overlay_enabled
        self.overlay_text = overlay_text or '{name} Type Beat'
        self.cta_enabled = cta_enabled
        self.cta_text = cta_text or 'Like | Subscribe | Link in description'
        self.stop_processing = False
        self.metadata_entries = []
    
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
                
                # Usar nombre personalizado o plantilla SEO
                if custom_name:
                    base_output_name = _sanitize_filename(custom_name)
                else:
                    base = os.path.splitext(beat_file)[0]
                    base_output_name = _sanitize_filename(
                        self.name_template.replace('{name}', base).replace('{channel}', channel).replace('{group}', group)
                    )
                    if not base_output_name:
                        base_output_name = f"{base}_{channel}_{group}"
                
                overlay_display = (self.overlay_text.replace('{name}', base_output_name.replace('_', ' '))) if self.overlay_enabled else None
                cta = self.cta_text if self.cta_enabled else None
                success = self._generate_video(content_file, audio_file, channel, group_output_folder, base_output_name, self.content_type,
                                               overlay_display=overlay_display, cta_text=cta)
                
                if success:
                    successful_videos += 1
                    if self.vertical_enabled:
                        self.progress_updated.emit(progress, f"Clip vertical 9:16: {beat_file} ({i+1}/{total_beats})")
                        self._generate_vertical_clip(content_file, audio_file, group_output_folder,
                                                     f"{base_output_name}_vertical", self.content_type)
                    # Metadata para YouTube (título, descripción, tags)
                    title = base_output_name.replace('_', ' ')
                    desc = f"Free type beat - {title}\n\nLink in description.\nSubscribe for more."
                    tags = f"type beat, free beat, {group}, {channel}"
                    self.metadata_entries.append({
                        'video_file': f"{base_output_name}.mp4",
                        'beat_file': beat_file,
                        'channel': channel,
                        'group': group,
                        'path': os.path.join(group_output_folder, f"{base_output_name}.mp4"),
                        'title': title,
                        'description': desc,
                        'tags': tags
                    })
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
                self.finished.emit(True, f"✅ Listos para publicar: {successful_videos} videos.")
            else:
                self.finished.emit(True, f"⚠️ Listos para publicar: {successful_videos} de {total_beats} videos (revisa los que faltaron).")
            
        except Exception as e:
            self.finished.emit(False, f"Error en el procesamiento: {str(e)}")
    
    def _find_image_for_beat(self, channel, group):
        """Busca una imagen apropiada para el beat."""
        # Buscar en carpeta específica del canal y grupo
        channel_group_path = os.path.join(self.images_folder, channel, group)
        
        if os.path.exists(channel_group_path):
            images = [f for f in os.listdir(channel_group_path)
                     if f.lower().endswith(IMAGE_EXTENSIONS)]
            if images:
                return os.path.join(channel_group_path, random.choice(images))
        
        # Buscar en carpeta del canal (cualquier grupo)
        channel_path = os.path.join(self.images_folder, channel)
        if os.path.exists(channel_path):
            for subdir in os.listdir(channel_path):
                subdir_path = os.path.join(channel_path, subdir)
                if os.path.isdir(subdir_path):
                    images = [f for f in os.listdir(subdir_path)
                             if f.lower().endswith(IMAGE_EXTENSIONS)]
                    if images:
                        return os.path.join(subdir_path, random.choice(images))
        
        # Buscar en carpeta general
        if os.path.exists(self.images_folder):
            images = [f for f in os.listdir(self.images_folder)
                     if f.lower().endswith(IMAGE_EXTENSIONS)]
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
    
    def _generate_video(self, content_path, audio_path, channel, output_folder, base_name, content_type="images", overlay_display=None, cta_text=None):
        """Genera un video combinando imagen/video con audio. Opcional: overlay de texto y CTA en el último 15%."""
        try:
            output_file = os.path.join(output_folder, f"{base_name}.mp4")

            ffmpeg_path = os.path.join("bin", "ffmpeg.exe") if os.name == 'nt' else "ffmpeg"
            video_codec = _get_available_video_codec(ffmpeg_path)
            audio_duration = self._get_media_duration(audio_path)
            duration_args = []
            if audio_duration is not None:
                duration_args = ["-t", f"{audio_duration:.3f}"]

            base_vf_images = "scale=-1:1080,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
            base_vf_videos = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
            vf_images = _build_vf_with_overlays(base_vf_images, overlay_display, cta_text, audio_duration)
            vf_videos = _build_vf_with_overlays(base_vf_videos, overlay_display, cta_text, audio_duration)

            if content_type == "videos":
                cmd = [
                    ffmpeg_path,
                    "-stream_loop", "-1",
                    "-i", content_path,
                    "-i", audio_path,
                    "-map", "0:v",
                    "-map", "1:a",
                    "-vf", vf_videos,
                    "-c:v", video_codec,
                    "-preset", "fast",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                ] + duration_args + [
                    "-y",
                    output_file
                ]
            else:
                cmd = [
                    ffmpeg_path,
                    "-loop", "1",
                    "-i", content_path,
                    "-i", audio_path,
                    "-vf", vf_images,
                    "-c:v", video_codec,
                    "-preset", "fast",
                    "-tune", "stillimage",
                    "-c:a", "aac",
                    "-b:a", "192k",
                    "-shortest",
                ] + duration_args + [
                    "-y",
                    output_file
                ]

            # Ejecutar comando (encoding utf-8 para evitar UnicodeDecodeError con salida de FFmpeg)
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

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

    def _generate_vertical_clip(self, content_path, audio_path, output_folder, base_name, content_type="images"):
        """Genera un clip vertical 1080x1920 de 30-60 s con recorte centrado."""
        try:
            output_file = os.path.join(output_folder, f"{base_name}.mp4")
            ffmpeg_path = os.path.join("bin", "ffmpeg.exe") if os.name == 'nt' else "ffmpeg"
            cmd = _build_vertical_cmd(ffmpeg_path, content_path, audio_path, output_file,
                                      content_type, self._get_media_duration(audio_path))
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
            if result.returncode == 0:
                print(f"✓ Clip vertical generado: {os.path.basename(output_file)}")
                return True
            print(f"✗ Error FFmpeg (vertical): {result.stderr}")
            return False
        except Exception as e:
            print(f"Error generando clip vertical: {e}")
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
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
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
        self.btn_connect_youtube = QPushButton("🔗 Conectar canal (YouTube)")
        self.btn_connect_youtube.clicked.connect(self.connect_youtube)
        left_panel.addWidget(self.btn_connect_youtube)
        self.youtube_status = QLabel("")
        self.youtube_status.setStyleSheet("color: #aaa; font-size: 11px;")
        left_panel.addWidget(self.youtube_status)
        
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
        self._update_youtube_status(channel_name)

    def _update_youtube_status(self, channel_name):
        if not channel_name:
            self.youtube_status.setText("")
        elif youtube.is_connected(channel_name):
            self.youtube_status.setText("✅ Conectado a YouTube")
        else:
            self.youtube_status.setText("⚪ Sin conectar a YouTube")

    def connect_youtube(self):
        """Autoriza una cuenta de Google para el canal seleccionado (abre el navegador)."""
        item = self.channels_list.currentItem()
        if not item:
            QMessageBox.warning(self, "Advertencia", "Selecciona un canal primero.")
            return
        channel = item.text()
        if youtube.is_connected(channel):
            reply = QMessageBox.question(self, "Reconectar",
                f"'{channel}' ya está conectado. ¿Conectar otra cuenta de Google?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        QMessageBox.information(self, "Conectar canal",
            "Se abrirá el navegador: elegí la cuenta de Google del canal "
            f"'{channel}' y aceptá los permisos.")
        self.btn_connect_youtube.setEnabled(False)
        self.youtube_status.setText("⏳ Esperando autorización en el navegador...")
        self._connect_worker = ConnectChannelWorker(channel, self)
        self._connect_worker.finished_ok.connect(self._on_youtube_connected)
        self._connect_worker.failed.connect(self._on_youtube_connect_failed)
        self._connect_worker.start()

    def _on_youtube_connected(self, channel, yt_title):
        self.btn_connect_youtube.setEnabled(True)
        self._update_youtube_status(channel)
        QMessageBox.information(self, "Canal conectado",
            f"'{channel}' quedó conectado al canal de YouTube: {yt_title or '(sin título)'}")

    def _on_youtube_connect_failed(self, channel, error):
        self.btn_connect_youtube.setEnabled(True)
        self._update_youtube_status(channel)
        QMessageBox.warning(self, "Error al conectar", error)
    
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
            "Agrega imágenes (JPG, JPEG, JFIF, PNG, WebP, GIF, BMP, etc.) a esta carpeta.\n"
            "Se recomiendan 10-30 imágenes por grupo para mayor variedad."
        )
    
    def accept(self):
        """Guarda la configuración al aceptar."""
        self.save_config()
        super().accept()


class OnboardingWizard(QDialog):
    """Wizard de 3 pasos para nuevos usuarios (sin canales configurados)."""
    
    def __init__(self, parent=None, config_file=None):
        super().__init__(parent)
        self.config_file = config_file or CONFIG_FILE
        self.channel_name = ""
        self.setWindowTitle("Bienvenido - Configura tu primer canal")
        self.setMinimumSize(500, 380)
        self.setModal(True)
        self._setup_ui()
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        self.stacked = QTabWidget()
        # Paso 1: Nombre del canal
        step1 = QWidget()
        step1_layout = QVBoxLayout(step1)
        step1_layout.addWidget(QLabel("Paso 1: Crea tu primer canal"))
        step1_layout.addWidget(QLabel("Nombre del canal (ej: tu nombre o marca):"))
        self.channel_edit = QLineEdit()
        self.channel_edit.setPlaceholderText("Ej: MiCanalBeats")
        step1_layout.addWidget(self.channel_edit)
        self.btn_step1 = QPushButton("Crear canal y continuar")
        self.btn_step1.clicked.connect(self._on_step1_next)
        step1_layout.addWidget(self.btn_step1)
        step1_layout.addStretch()
        self.stacked.addTab(step1, "1. Canal")
        
        # Paso 2: Subir contenido
        step2 = QWidget()
        step2_layout = QVBoxLayout(step2)
        step2_layout.addWidget(QLabel("Paso 2: Contenido visual"))
        step2_layout.addWidget(QLabel("Sube al menos 10 imágenes o 5 videos para este canal.\nAbre la carpeta y agrega los archivos, luego continúa."))
        self.btn_open_content = QPushButton("Abrir carpeta de contenido")
        self.btn_open_content.clicked.connect(self._open_content_folder)
        step2_layout.addWidget(self.btn_open_content)
        self.btn_step2 = QPushButton("Continuar")
        self.btn_step2.clicked.connect(self._on_step2_next)
        step2_layout.addWidget(self.btn_step2)
        step2_layout.addStretch()
        self.stacked.addTab(step2, "2. Contenido")
        
        # Paso 3: Listo
        step3 = QWidget()
        step3_layout = QVBoxLayout(step3)
        step3_layout.addWidget(QLabel("Paso 3: Generar videos"))
        step3_layout.addWidget(QLabel("Ya puedes cargar beats (recomendado: 10), asignarlos a tu canal y pulsar GENERAR VIDEOS.\n\n¡Listo para publicar en minutos!"))
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.accept)
        step3_layout.addWidget(self.btn_close)
        step3_layout.addStretch()
        self.stacked.addTab(step3, "3. Listo")
        
        layout.addWidget(self.stacked)
    
    def _on_step1_next(self):
        name = self.channel_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Nombre vacío", "Escribe el nombre de tu canal.")
            return
        try:
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            config = DEFAULT_CONFIG.copy()
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config.update(json.load(f))
            channels = config.get('channels', {})
            if not isinstance(channels, dict):
                channels = {}
            if name in channels:
                QMessageBox.information(self, "Canal existente", "Ese canal ya existe. Pasando al paso 2.")
            else:
                channels[name] = {'groups': ['Principal']}
                config['channels'] = channels
                config['last_channel'] = name
                config['last_group'] = 'Principal'
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(config, f, indent=2, ensure_ascii=False)
                os.makedirs(os.path.join("images", name, "Principal"), exist_ok=True)
                os.makedirs(os.path.join("videos", name, "Principal"), exist_ok=True)
            self.channel_name = name
            self.stacked.setCurrentIndex(1)
            self._update_step2_folder()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear el canal: {e}")
    
    def _update_step2_folder(self):
        self._content_folder = os.path.join("images", self.channel_name, "Principal") if self.channel_name else ""
    
    def _open_content_folder(self):
        if not self.channel_name:
            self._on_step1_next()
            if not self.channel_name:
                return
        folder = os.path.join("images", self.channel_name, "Principal")
        os.makedirs(folder, exist_ok=True)
        if os.name == 'nt':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.run(['open', folder])
        else:
            subprocess.run(['xdg-open', folder])
        QMessageBox.information(self, "Carpeta abierta",
            "Agrega aquí al menos 10 imágenes (JPG/PNG) o sube videos en la app después.\nLuego haz clic en Continuar.")
    
    def _on_step2_next(self):
        self.stacked.setCurrentIndex(2)
    
    def run_wizard(self):
        self.stacked.setCurrentIndex(0)
        self.exec()


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
        self._restore_last_channel_group()
        
        # Onboarding: si no hay canales, mostrar wizard de primer uso
        if self.channel_combo.count() <= 1:
            wizard = OnboardingWizard(self, CONFIG_FILE)
            wizard.run_wizard()
            self._load_channels()
            self._restore_last_channel_group()
        
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
        beats_title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(beats_title)
        
        # Botones de gestión de beats
        beats_buttons = QHBoxLayout()
        self.btn_load_beats = QPushButton("📂 Cargar Beats")
        self.btn_load_beats.clicked.connect(self._load_beats_from_files)
        self.btn_delete_beats = QPushButton("🗑️ Eliminar")
        self.btn_delete_beats.clicked.connect(self._delete_selected_beats)
        
        beats_buttons.addWidget(self.btn_load_beats)
        beats_buttons.addWidget(self.btn_delete_beats)
        self.btn_library = QPushButton("📚 Biblioteca")
        self.btn_library.clicked.connect(self._open_library)
        beats_buttons.addWidget(self.btn_library)
        left_layout.addLayout(beats_buttons)
        
        # Lista de beats disponibles
        beats_label = QLabel("📁 Beats Disponibles:")
        beats_label.setStyleSheet("font-weight: bold; padding: 5px;")
        left_layout.addWidget(beats_label)
        self.recommended_label = QLabel("Recomendado: 10 beats")
        self.recommended_label.setStyleSheet("color: #3498DB; font-size: 11px; padding: 2px 5px;")
        left_layout.addWidget(self.recommended_label)
        
        # Control de selección múltiple
        selection_layout = QHBoxLayout()
        self.select_all_checkbox = QCheckBox("Seleccionar todos")
        self.select_all_checkbox.stateChanged.connect(self._toggle_select_all_beats)
        selection_layout.addWidget(self.select_all_checkbox)
        self.btn_select_all = QPushButton("✓ Todos")
        self.btn_select_all.setToolTip("Seleccionar todos los beats de la lista")
        self.btn_select_all.clicked.connect(lambda: self._toggle_select_all_beats(Qt.Checked))
        selection_layout.addWidget(self.btn_select_all)
        self.btn_deselect_all = QPushButton("Ninguno")
        self.btn_deselect_all.setToolTip("Quitar la selección")
        self.btn_deselect_all.clicked.connect(lambda: self._toggle_select_all_beats(Qt.Unchecked))
        selection_layout.addWidget(self.btn_deselect_all)
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
        
        # Guardar selección en carpeta (MP3) para reutilizar sin volver a subir
        self.btn_save_to_mp3_folder = QPushButton("📁 Guardar selección en carpeta MP3...")
        self.btn_save_to_mp3_folder.setToolTip("Copia los beats seleccionados a una carpeta (en MP3 si es posible) para cargarlos otra vez sin re-subir.")
        self.btn_save_to_mp3_folder.clicked.connect(self._save_selection_to_mp3_folder)
        left_layout.addWidget(self.btn_save_to_mp3_folder)
        
        left_layout.addStretch()
        
        # === COLUMNA 2: CONFIGURACIÓN DE CANALES ===
        center_panel = QFrame()
        center_panel.setMaximumWidth(400)
        center_layout = QVBoxLayout(center_panel)
        
        # Título de la columna
        config_title = QLabel("📺 Configuración de Canales")
        config_title.setStyleSheet("font-size: 16px; font-weight: bold; padding: 10px; text-align: center;")
        config_title.setAlignment(Qt.AlignCenter)
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
        process_title.setAlignment(Qt.AlignCenter)
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
        
        # Plantilla de nombres SEO (título/archivo)
        name_tpl_label = QLabel("Plantilla nombres (SEO):")
        name_tpl_label.setStyleSheet("font-weight: bold; padding: 5px; margin-top: 8px;")
        right_layout.addWidget(name_tpl_label)
        self.name_template_edit = QLineEdit()
        self.name_template_edit.setPlaceholderText("[Type] {name} | Free for Profit")
        self.name_template_edit.setToolTip("Usa {name}, {channel}, {group}. Ejemplo: [Type] {name} | Free for Profit")
        self.name_template_edit.editingFinished.connect(self._on_name_template_changed)
        right_layout.addWidget(self.name_template_edit)
        
        # Opción de texto en el video (desactivado por defecto)
        self.check_overlay_text = QCheckBox("Añadir texto en el video (título y CTA)")
        self.check_overlay_text.setStyleSheet("color: #aaa; font-size: 11px;")
        self.check_overlay_text.setToolTip("Si está marcado, se dibuja el nombre del beat y un CTA al final. Desmarcado = solo imagen/video y audio.")
        self.check_overlay_text.stateChanged.connect(self._on_overlay_check_changed)
        right_layout.addWidget(self.check_overlay_text)
        
        self.check_vertical = QCheckBox("Generar también clip vertical 9:16 (45 s, 1080x1920)")
        self.check_vertical.setStyleSheet("color: #aaa; font-size: 11px;")
        self.check_vertical.setToolTip("Crea además un clip vertical de 30-60 s (Shorts/Reels/TikTok) con recorte centrado: <nombre>_vertical.mp4")
        self.check_vertical.stateChanged.connect(self._on_vertical_check_changed)
        right_layout.addWidget(self.check_vertical)
        
        # Botones principales
        main_buttons = QVBoxLayout()
        
        self.check_use_defaults = QCheckBox("Generar sin preguntar (usar imagen/video por defecto)")
        self.check_use_defaults.setStyleSheet("color: #aaa; font-size: 11px;")
        self.check_use_defaults.setToolTip("Si está marcado, no se abre el diálogo de elegir imágenes vs videos; se usa la última opción.")
        main_buttons.addWidget(self.check_use_defaults)

        self.check_youtube_upload = QCheckBox("Subir a YouTube al terminar (privado)")
        self.check_youtube_upload.setStyleSheet("color: #aaa; font-size: 11px;")
        self.check_youtube_upload.setToolTip("Sube cada video al canal asignado (hay que conectarlo antes en Gestión de Canales).")
        main_buttons.addWidget(self.check_youtube_upload)
        
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
                    self.last_channel = config.get('last_channel', '')
                    self.last_group = config.get('last_group', '')
                    self.last_content_type = config.get('last_content_type', 'images')
                    self.last_beats_folder = config.get('last_beats_folder', '')
                    self.name_template = config.get('name_template', '[Type] {name} | Free for Profit')
                    self.overlay_enabled = config.get('overlay_enabled', False)
                    self.overlay_text = config.get('overlay_text', '{name} Type Beat')
                    self.cta_enabled = config.get('cta_enabled', False)
                    self.cta_text = config.get('cta_text', 'Like | Subscribe | Link in description')
                    self.vertical_enabled = config.get('vertical_enabled', False)
            else:
                self.last_channel = ''
                self.last_group = ''
                self.last_content_type = 'images'
                self.last_beats_folder = ''
                self.name_template = '[Type] {name} | Free for Profit'
                self.overlay_enabled = False
                self.overlay_text = '{name} Type Beat'
                self.cta_enabled = False
                self.cta_text = 'Like | Subscribe | Link in description'
        except Exception as e:
            print(f"Error cargando config: {e}")
            self.last_channel = ''
            self.last_group = ''
            self.last_content_type = 'images'
            self.last_beats_folder = ''
            self.name_template = '[Type] {name} | Free for Profit'
            self.overlay_enabled = False
            self.overlay_text = '{name} Type Beat'
            self.cta_enabled = False
            self.cta_text = 'Like | Subscribe | Link in description'
        if hasattr(self, 'name_template_edit'):
            self.name_template_edit.setText(self.name_template)
        if hasattr(self, 'check_vertical'):
            self.check_vertical.blockSignals(True)
            self.check_vertical.setChecked(bool(getattr(self, 'vertical_enabled', False)))
            self.check_vertical.blockSignals(False)
        if hasattr(self, 'check_overlay_text'):
            self.check_overlay_text.blockSignals(True)
            self.check_overlay_text.setChecked(bool(self.overlay_enabled))
            self.check_overlay_text.blockSignals(False)
    
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
            config['last_channel'] = getattr(self, 'last_channel', '') or ''
            config['last_group'] = getattr(self, 'last_group', '') or ''
            config['last_content_type'] = getattr(self, 'last_content_type', 'images') or 'images'
            config['last_beats_folder'] = getattr(self, 'last_beats_folder', '') or ''
            config['name_template'] = getattr(self, 'name_template', '[Type] {name} | Free for Profit') or '[Type] {name} | Free for Profit'
            config['overlay_enabled'] = getattr(self, 'overlay_enabled', False)
            config['overlay_text'] = getattr(self, 'overlay_text', '{name} Type Beat') or '{name} Type Beat'
            config['cta_enabled'] = getattr(self, 'cta_enabled', False)
            config['vertical_enabled'] = bool(getattr(self, 'vertical_enabled', False))
            config['cta_text'] = getattr(self, 'cta_text', 'Like | Subscribe | Link in description') or 'Like | Subscribe | Link in description'
            
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
        initial_dir = getattr(self, 'last_beats_folder', '') or ""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Seleccionar archivos de beat",
            initial_dir,
            "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac)"
        )
        
        if files:
            # Guardar carpeta de origen para próxima vez
            first_dir = os.path.dirname(files[0])
            if first_dir:
                self.last_beats_folder = first_dir
                self.save_config()
            
            copied_files = 0
            for file in files:
                try:
                    filename = os.path.basename(file)
                    dest_path = os.path.join(self.beats_folder, filename)
                    if not os.path.exists(dest_path):
                        shutil.copy2(file, dest_path)
                        copied_files += 1
                    library.import_beat(file)
                except Exception as e:
                    print(f"Error copiando {file}: {e}")
            
            self._load_beats()
            
            # Auto-asignar todos los beats al canal/grupo por defecto si está configurado
            channel = getattr(self, 'last_channel', '')
            group = getattr(self, 'last_group', '')
            if channel and group and self.channel_combo.findText(channel) >= 0:
                self._on_channel_changed(channel)
                if self.group_combo.findText(group) >= 0:
                    self.group_combo.setCurrentIndex(self.group_combo.findText(group))
                    # Asignar todos los beats de la lista al canal por defecto
                    self.beats_list.selectAll()
                    self._assign_channel_to_beats_silent(channel, group)
                    self.beats_list.clearSelection()
                    self._update_selection_count()
            
            self.status_label.setText(f"Se copiaron {copied_files} archivos nuevos")
    
    def _open_library(self):
        """Abre la biblioteca y carga los beats elegidos en el flujo normal."""
        dlg = LibraryDialog([self.channel_combo.itemText(i) for i in range(self.channel_combo.count()) if self.channel_combo.itemText(i) != 'Sin asignar'], self)
        if dlg.exec_() == QDialog.Accepted and dlg.selected_paths:
            for path in dlg.selected_paths:
                dest = os.path.join(self.beats_folder, os.path.basename(path))
                if not os.path.exists(dest):
                    shutil.copy2(path, dest)
            self._load_beats()
            self.status_label.setText(f"{len(dlg.selected_paths)} beats cargados desde la biblioteca")

    def _save_selection_to_mp3_folder(self):
        """Copia los beats a una carpeta ordenada: [base] / [mes] / [género]. El usuario elige base y escribe el género (ej. sad emotional beats)."""
        selected = self.beats_list.selectedItems()
        if not selected:
            if self.beats_list.count() == 0:
                QMessageBox.warning(self, "Sin beats", "No hay beats en la lista. Carga beats primero.")
                return
            beat_files = [self.beats_list.item(i).text() for i in range(self.beats_list.count())]
        else:
            beat_files = [item.text() for item in selected]
        
        # 1) Carpeta base (donde se creará el archivo por mes)
        base_folder = QFileDialog.getExistingDirectory(
            self,
            "Carpeta base para archivo de beats (aquí se crean Mes y Género)",
            getattr(self, 'last_beats_folder', '') or os.path.expanduser("~")
        )
        if not base_folder:
            return
        
        # 2) Carpeta del mes (ej. 2025-02)
        month_folder_name = datetime.now().strftime("%Y-%m")
        
        # 3) Nombre del género/categoría (lo que el usuario quiera: "sad emotional beats", "trap", etc.)
        genre_name, ok = QInputDialog.getText(
            self,
            "Género o categoría",
            "Nombre de la carpeta del género (ej. sad emotional beats, trap, lo-fi):",
            QLineEdit.Normal,
            ""
        )
        if not ok:
            return
        genre_name = genre_name.strip()
        if not genre_name:
            QMessageBox.warning(self, "Nombre vacío", "Escribe un nombre para el género o categoría (ej. sad emotional beats).")
            return
        
        # Sanitizar nombre de carpeta (sin caracteres inválidos)
        for c in '\\/:*?"<>|':
            genre_name = genre_name.replace(c, "_")
        genre_folder_name = genre_name.strip() or "beats"
        
        # Ruta final: base / mes / género
        folder = os.path.join(base_folder, month_folder_name, genre_folder_name)
        try:
            os.makedirs(folder, exist_ok=True)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"No se pudo crear la carpeta:\n{folder}\n{e}")
            return
        
        ffmpeg_path = os.path.join("bin", "ffmpeg.exe") if os.name == 'nt' else "ffmpeg"
        if not os.path.isfile(ffmpeg_path) and os.name == 'nt':
            ffmpeg_path = "ffmpeg"
        
        copied = 0
        converted = 0
        errors = []
        for beat_file in beat_files:
            src = os.path.join(self.beats_folder, beat_file)
            if not os.path.isfile(src):
                errors.append(beat_file)
                continue
            base, ext = os.path.splitext(beat_file)
            dest_mp3 = os.path.join(folder, base + ".mp3")
            ext_lower = ext.lower()
            try:
                if ext_lower == ".mp3":
                    shutil.copy2(src, dest_mp3)
                    copied += 1
                else:
                    cmd = [
                        ffmpeg_path, "-y", "-i", src,
                        "-acodec", "libmp3lame", "-q:a", "2",
                        dest_mp3
                    ]
                    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
                    if r.returncode == 0:
                        converted += 1
                    else:
                        shutil.copy2(src, os.path.join(folder, beat_file))
                        copied += 1
            except Exception as e:
                errors.append(f"{beat_file}: {e}")
        
        if errors:
            QMessageBox.warning(self, "Algunos fallos", f"Guardados: {copied} copiados, {converted} convertidos a MP3.\nErrores: {len(errors)}.")
        else:
            QMessageBox.information(
                self, "Carpeta lista",
                f"Se guardaron {copied + converted} beats en:\n{folder}\n\n({copied} copiados, {converted} convertidos a MP3).\nEstructura: [mes] / [género]."
            )
        self.status_label.setText(f"Guardados {copied + converted} beats en {month_folder_name}/{genre_folder_name}")
    
    def _load_channels(self):
        """Carga los canales desde la configuración."""
        self.channel_combo.clear()
        self.channel_combo.addItem("Seleccionar canal...")
        
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    channels = config.get('channels', {})
                    if not isinstance(channels, dict):
                        channels = {}
                    for channel_name in sorted(channels.keys()):
                        self.channel_combo.addItem(channel_name)
        except Exception as e:
            print(f"Error cargando canales: {e}")
    
    def _on_name_template_changed(self):
        """Guarda la plantilla de nombres al editar."""
        t = self.name_template_edit.text().strip()
        if t:
            self.name_template = t
            self.save_config()
    
    def _on_vertical_check_changed(self, state):
        self.vertical_enabled = bool(self.check_vertical.isChecked())
        self.save_config()

    def _on_overlay_check_changed(self, state):
        """Activa o desactiva el texto en el video (título y CTA)."""
        self.overlay_enabled = self.cta_enabled = (state == Qt.Checked)
        self.save_config()
    
    def _restore_last_channel_group(self):
        """Restaura el canal y grupo por defecto desde la configuración."""
        channel = getattr(self, 'last_channel', '')
        group = getattr(self, 'last_group', '')
        if not channel or not group:
            return
        idx = self.channel_combo.findText(channel)
        if idx >= 0:
            self.channel_combo.setCurrentIndex(idx)
            self._on_channel_changed(channel)
            gidx = self.group_combo.findText(group)
            if gidx >= 0:
                self.group_combo.setCurrentIndex(gidx)
                self._update_images_info()
    
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
        image_count = 0
        for file in os.listdir(images_path):
            if any(file.lower().endswith(ext) for ext in IMAGE_EXTENSIONS_LIST):
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
    
    def _assign_channel_to_beats_silent(self, channel, group):
        """Asigna todos los beats de la lista al canal/grupo sin preguntar (para auto-asignación)."""
        for i in range(self.beats_list.count()):
            beat_file = self.beats_list.item(i).text()
            # Quitar si ya estaba asignado
            self.beats_info = [b for b in self.beats_info if b['beat_file'] != beat_file]
            self.beats_info.append({
                'beat_file': beat_file,
                'channel': channel,
                'group': group,
                'custom_name': ''
            })
        self._update_process_list()
    
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
        
        image_count = sum(1 for f in os.listdir(images_path) if any(f.lower().endswith(ext) for ext in IMAGE_EXTENSIONS_LIST))
        
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
        
        # Guardar como canal/grupo por defecto para próximas sesiones
        self.last_channel = channel
        self.last_group = group
        self.save_config()
        
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
        # PyQt5: state es int (0=Unchecked, 1=PartiallyChecked, 2=Checked)
        if state == Qt.Checked:
            self.beats_list.selectAll()
        else:
            self.beats_list.clearSelection()
        self._update_selection_count()
    
    def _update_selection_count(self):
        """Actualiza el contador de beats seleccionados."""
        selected_count = len(self.beats_list.selectedItems())
        total_count = self.beats_list.count()
        
        self.selected_count_label.setText(f"{selected_count} de {total_count} seleccionados")
        
        # Actualizar estado del checkbox sin disparar la señal (PyQt5: Qt.Unchecked, Qt.Checked, Qt.PartiallyChecked)
        if selected_count == 0:
            self.select_all_checkbox.blockSignals(True)
            self.select_all_checkbox.setCheckState(Qt.Unchecked)
            self.select_all_checkbox.blockSignals(False)
        elif selected_count == total_count and total_count > 0:
            self.select_all_checkbox.blockSignals(True)
            self.select_all_checkbox.setCheckState(Qt.Checked)
            self.select_all_checkbox.blockSignals(False)
        else:
            self.select_all_checkbox.blockSignals(True)
            self.select_all_checkbox.setCheckState(Qt.PartiallyChecked)
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
            file_filter = "Imágenes (*.jpg *.jpeg *.jfif *.png *.gif *.bmp *.webp *.tiff *.tif *.heic)"
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
    
    def _validate_ready_to_publish(self):
        """Validación pre-export: checklist para 'listo para publicar'. Devuelve (ok, lista de mensajes)."""
        messages = []
        if not self.beats_info:
            messages.append("❌ No hay beats en la lista de procesamiento.")
            return False, messages
        first_beat = self.beats_info[0]
        channel = first_beat['channel']
        group = first_beat['group']
        mixed = any(b['channel'] != channel or b['group'] != group for b in self.beats_info)
        if mixed:
            messages.append("❌ Todos los beats deben tener el mismo canal y grupo.")
            return False, messages
        messages.append("✅ Canal y grupo asignados correctamente.")
        image_count, video_count = self._get_content_counts(channel, group)
        beats_count = len(self.beats_info)
        use_defaults = self.check_use_defaults.isChecked()
        content_type = getattr(self, 'last_content_type', 'images') if use_defaults else None
        if content_type == 'videos':
            if video_count < 1:
                messages.append(f"❌ No hay videos en {channel}/{group}. Agrega al menos 1 video.")
                return False, messages
            reuse = " (se reutilizará)" if video_count < beats_count else ""
            messages.append(f"✅ Contenido suficiente: {video_count} video(s) para {beats_count} beats{reuse}.")
        elif content_type == 'images':
            if image_count < 1:
                messages.append(f"❌ No hay imágenes en {channel}/{group}. Agrega al menos 1 imagen.")
                return False, messages
            reuse = " (se reutilizará)" if image_count < beats_count else ""
            messages.append(f"✅ Contenido suficiente: {image_count} imagen(es) para {beats_count} beats{reuse}.")
        else:
            # Usuario elegirá en el diálogo: debe haber al menos 1 imagen o 1 video
            if image_count < 1 and video_count < 1:
                messages.append(f"❌ No hay imágenes ni videos en {channel}/{group}. Agrega al menos 1 imagen o 1 video.")
                return False, messages
            reuse = " (se reutilizarán)" if (image_count < beats_count and video_count < beats_count) else ""
            messages.append(f"✅ Contenido suficiente (imágenes: {image_count}, videos: {video_count}) para {beats_count} beats{reuse}.")
        if not os.path.exists(self.output_folder):
            try:
                os.makedirs(self.output_folder, exist_ok=True)
            except Exception:
                messages.append("❌ No se pudo crear la carpeta de salida.")
                return False, messages
        messages.append("✅ Carpeta de salida lista.")
        return True, messages
    
    def _start_generation(self):
        """Inicia el proceso de generación de videos con selección de contenido."""
        ok, check_messages = self._validate_ready_to_publish()
        if not ok:
            QMessageBox.warning(
                self, "Listo para publicar",
                "Revisa antes de generar:\n\n" + "\n".join(check_messages)
            )
            return
        
        # Obtener canal y grupo predominante o del primer beat
        first_beat = self.beats_info[0]
        channel = first_beat['channel']
        group = first_beat['group']
        
        # Guardar como último canal/grupo usado
        self.last_channel = channel
        self.last_group = group
        self.save_config()
        
        # Verificar que todos los beats usen el mismo canal/grupo (ya validado, pero por si acaso)
        mixed_channels = any(beat['channel'] != channel or beat['group'] != group for beat in self.beats_info)
        if mixed_channels:
            QMessageBox.warning(self, "Canales mixtos", 
                              "Todos los beats deben usar el mismo canal y grupo para poder seleccionar el tipo de contenido.\n"
                              "Organiza tus beats por canal/grupo antes de generar.")
            return
        
        # Contar contenido disponible
        image_count, video_count = self._get_content_counts(channel, group)
        beats_count = len(self.beats_info)
        
        use_defaults = self.check_use_defaults.isChecked()
        if use_defaults:
            self.current_content_type = getattr(self, 'last_content_type', 'images')
            if self.current_content_type == 'images':
                if image_count < 1:
                    QMessageBox.warning(self, "Contenido insuficiente",
                        f"No hay imágenes en {channel}/{group}.\n"
                        "Agrega al menos 1 imagen. Se reutilizará para todos los beats.")
                    return
            else:
                if video_count < 1:
                    QMessageBox.warning(self, "Contenido insuficiente",
                        f"No hay videos en {channel}/{group}.\n"
                        "Agrega al menos 1 video. Se reutilizará para todos los beats.")
                    return
        else:
            # Mostrar diálogo de selección
            dialog = ContentSelectionDialog(channel, group, image_count, video_count, beats_count, self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return  # Usuario canceló
            self.current_content_type = dialog.get_selected_content_type()
            self.last_content_type = self.current_content_type
            self.save_config()
        
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
        name_template = (self.name_template_edit.text().strip() or getattr(self, 'name_template', '[Type] {name} | Free for Profit'))
        self.worker = VideoGeneratorWorker(
            self.beats_folder,
            self.images_folder,
            self.output_folder,
            self.beats_info,
            self.current_content_type,
            self,
            name_template=name_template,
            overlay_enabled=self.check_overlay_text.isChecked() if hasattr(self, 'check_overlay_text') else getattr(self, 'overlay_enabled', False),
            overlay_text=getattr(self, 'overlay_text', '{name} Type Beat'),
            cta_enabled=self.check_overlay_text.isChecked() if hasattr(self, 'check_overlay_text') else getattr(self, 'cta_enabled', False),
            cta_text=getattr(self, 'cta_text', 'Like | Subscribe | Link in description'),
            vertical_enabled=self.check_vertical.isChecked()
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
            self._record_generated_in_library()
            if self.check_youtube_upload.isChecked():
                self._start_youtube_upload(list(getattr(self.worker, 'metadata_entries', []) or []))
            # Exportar metadata para YouTube si hay entradas
            metadata_path = None
            if self.worker and getattr(self.worker, 'metadata_entries', None):
                try:
                    metadata_path = os.path.join(self.output_folder, 'metadata_youtube.csv')
                    with open(metadata_path, 'w', newline='', encoding='utf-8') as f:
                        w = csv.DictWriter(f, fieldnames=['video_file', 'title', 'description', 'tags'])
                        w.writeheader()
                        for e in self.worker.metadata_entries:
                            w.writerow({k: e.get(k, '') for k in ['video_file', 'title', 'description', 'tags']})
                except Exception as e:
                    print(f"Error escribiendo metadata: {e}")
            
            # Mensaje con opción de abrir carpeta (UX: feedback rápido)
            msg = message
            if metadata_path and os.path.exists(metadata_path):
                msg += f"\n\nMetadata para YouTube guardada en:\n{metadata_path}"
            
            reply = QMessageBox.question(
                self, "Listos para publicar",
                msg + "\n\n¿Abrir carpeta de videos?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._open_output_folder()
        else:
            QMessageBox.warning(self, "Error", message)
    
    def _record_generated_in_library(self):
        """Registra en el historial de la biblioteca cada video generado."""
        for e in getattr(self.worker, 'metadata_entries', []) or []:
            try:
                beat = library.find_beat_by_path(os.path.join(self.beats_folder, e['beat_file']))
                if beat:
                    library.record_upload(beat['id'], e['channel'], e['group'],
                                          titulo=e['title'], estado='generado')
            except Exception as ex:
                print(f"Error registrando en biblioteca: {ex}")

    def _start_youtube_upload(self, entries):
        """Prepara y lanza la subida a YouTube de los videos generados."""
        jobs, sin_conectar, duplicados = [], set(), []
        for e in entries:
            if not youtube.is_connected(e['channel']):
                sin_conectar.add(e['channel'])
                continue
            beat = None
            try:
                beat = library.find_beat_by_path(os.path.join(self.beats_folder, e['beat_file']))
            except Exception as ex:
                print(f"Error buscando beat en biblioteca: {ex}")
            beat = beat or {}
            name = beat.get('nombre') or os.path.splitext(e['beat_file'])[0]
            desc = description.render_for_channel(
                e['channel'], name, beat.get('bpm'), beat.get('key'),
                beat.get('beatstars_url') or '', e.get('tags', ''))
            thumb = os.path.splitext(e['path'])[0] + '_imagen.jpg'
            job = {'channel': e['channel'], 'group': e['group'], 'path': e['path'],
                   'title': e['title'], 'description': desc, 'tags': e.get('tags', ''),
                   'thumbnail': thumb if os.path.exists(thumb) else None,
                   'privacy': 'private', 'beat_id': beat.get('id')}
            previas = library.youtube_uploads(beat['id'], e['channel']) if beat.get('id') else []
            if previas:
                duplicados.append((job, previas[0]))
            jobs.append(job)
        if sin_conectar:
            QMessageBox.warning(self, "Canales sin conectar",
                "No se subirán los videos de estos canales (conectalos en Gestión de Canales):\n- "
                + "\n- ".join(sorted(sin_conectar)))
        if duplicados:
            lineas = [f"- {j['title']} → {j['channel']}: {library.humanize_ago(p['subido_en'])} ({p['url']})"
                      for j, p in duplicados]
            reply = QMessageBox.question(self, "Beats ya subidos",
                "Estos beats ya se subieron a ese canal:\n" + "\n".join(lineas)
                + "\n\n¿Subirlos igual? (No = omitirlos)",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel, QMessageBox.No)
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.No:
                omitir = {id(j) for j, _ in duplicados}
                jobs = [j for j in jobs if id(j) not in omitir]
        if not jobs:
            return
        self._upload_worker = YouTubeUploadWorker(jobs, self)
        self._upload_worker.progress.connect(self.status_label.setText)
        self._upload_worker.finished_all.connect(self._youtube_upload_finished)
        self._upload_worker.start()

    def _youtube_upload_finished(self, done, errors):
        msg = f"Subidos a YouTube: {len(done)} videos (privados; publicalos desde YouTube Studio)."
        if done:
            msg += "\n\n" + "\n".join(f"- {d['title']}: {d['url']}" for d in done)
        self.status_label.setText(f"Subidos a YouTube: {len(done)}")
        if errors:
            msg += "\n\nProblemas:\n" + "\n".join(f"- {e}" for e in errors)
            QMessageBox.warning(self, "Subida a YouTube", msg)
        else:
            QMessageBox.information(self, "Subida a YouTube", msg)

    def _open_output_folder(self):
        """Abre la carpeta de salida en el explorador del sistema."""
        if not os.path.exists(self.output_folder):
            return
        if os.name == 'nt':
            os.startfile(self.output_folder)
        elif sys.platform == 'darwin':
            subprocess.run(['open', self.output_folder])
        else:
            subprocess.run(['xdg-open', self.output_folder])
    
    def _set_ui_processing(self, is_processing):
        """Habilita/deshabilita elementos de la interfaz durante el procesamiento."""
        self.btn_load_beats.setEnabled(not is_processing)
        self.btn_delete_beats.setEnabled(not is_processing)
        self.btn_save_to_mp3_folder.setEnabled(not is_processing)
        self.btn_assign_channel.setEnabled(not is_processing)
        self.btn_manage_channels.setEnabled(not is_processing)
        self.btn_upload_images.setEnabled(not is_processing)
        self.btn_browse_output.setEnabled(not is_processing)
        self.btn_generate.setEnabled(not is_processing)
        self.check_use_defaults.setEnabled(not is_processing)
        self.check_overlay_text.setEnabled(not is_processing)
        self.check_vertical.setEnabled(not is_processing)
        self.btn_cancel.setEnabled(is_processing)
        self.beats_list.setEnabled(not is_processing)
        self.process_list.setEnabled(not is_processing)
        self.btn_edit_name.setEnabled(not is_processing)
        self.btn_remove_from_process.setEnabled(not is_processing)
        self.btn_clear_process.setEnabled(not is_processing)
    
    # ========== FUNCIONES DE DETECCIÓN DE CONTENIDO ==========
    
    def _get_content_counts(self, channel, group):
        """Cuenta las imágenes y videos disponibles para un canal/grupo."""
        video_extensions = ['.mp4', '.mov', '.avi', '.mkv', '.wmv']
        
        # Contar imágenes (incl. jfif, webp, etc.)
        images_path = os.path.join(self.images_folder, channel, group)
        image_count = 0
        if os.path.exists(images_path):
            image_count = sum(1 for f in os.listdir(images_path) 
                            if any(f.lower().endswith(ext) for ext in IMAGE_EXTENSIONS_LIST))
        
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
            extensions = IMAGE_EXTENSIONS_LIST
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