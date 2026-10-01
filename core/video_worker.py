# -*- coding: utf-8 -*-
"""
Worker (QThread) que genera los videos con FFmpeg.
"""
import os
import random
import shutil
import subprocess

from PyQt5.QtCore import QThread, pyqtSignal

from core.config import IMAGE_EXTENSIONS
from core.ffmpeg_utils import _sanitize_filename, _build_vf_with_overlays


class VideoGeneratorWorker(QThread):
    """Clase para procesar la generación de videos en un hilo separado."""
    progress_updated = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)
    
    def __init__(self, beats_folder, images_folder, output_folder, beats_info, content_type="images", main_window=None, name_template=None,
                 overlay_enabled=False, overlay_text=None, cta_enabled=False, cta_text=None):
        super().__init__()
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
                    # Metadata para YouTube (título, descripción, tags)
                    title = base_output_name.replace('_', ' ')
                    desc = f"Free type beat - {title}\n\nLink in description.\nSubscribe for more."
                    tags = f"type beat, free beat, {group}, {channel}"
                    self.metadata_entries.append({
                        'video_file': f"{base_output_name}.mp4",
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
                cmd = [
                    ffmpeg_path,
                    "-loop", "1",
                    "-i", content_path,
                    "-i", audio_path,
                    "-vf", vf_images,
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
