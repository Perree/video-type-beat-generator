"""Lógica de generación de videos, independiente de la interfaz (sin PyQt).

La usan tanto la GUI (main.py) como la CLI (cli.py).
"""
import csv
import os
import random
import shutil
import subprocess

# Extensiones de imagen (Pinterest y descargas: jfif, webp, etc.; FFmpeg las soporta)
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.jfif', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic')
IMAGE_EXTENSIONS_LIST = list(IMAGE_EXTENSIONS)
VIDEO_EXTENSIONS = ('.mp4', '.mov', '.avi', '.mkv', '.wmv')
AUDIO_EXTENSIONS = ('.mp3', '.wav', '.m4a', '.aac', '.flac')

DEFAULT_NAME_TEMPLATE = '[Type] {name} | Free for Profit'
DEFAULT_OVERLAY_TEXT = '{name} Type Beat'
DEFAULT_CTA_TEXT = 'Like | Subscribe | Link in description'
METADATA_FIELDS = ['video_file', 'title', 'description', 'tags']


def sanitize_filename(s):
    """Elimina caracteres no válidos para nombres de archivo."""
    for c in '\\/:*?"<>|':
        s = s.replace(c, '_')
    return s[:200].strip() or 'video'


def escape_drawtext(s):
    """Escapa texto para drawtext de FFmpeg (comillas y dos puntos)."""
    if not s:
        return ''
    return s.replace('\\', '\\\\').replace("'", "\\'").replace(':', '\\:')


def build_vf_with_overlays(base_vf, overlay_display=None, cta_text=None, audio_duration=None):
    """Añade overlay de título y CTA (último 15% del video) al filtro de video. Sin escape_text (no soportado en todas las builds de FFmpeg)."""
    vf = base_vf
    if overlay_display:
        vf += ",drawtext=text='{}':fontsize=32:fontcolor=white:bordercolor=black:borderw=2:x=(w-tw)/2:y=80".format(escape_drawtext(overlay_display))
    if cta_text and audio_duration is not None and audio_duration > 0:
        t0 = audio_duration * 0.85
        t1 = audio_duration + 1
        vf += ",drawtext=text='{}':fontsize=24:fontcolor=white:bordercolor=black:borderw=1:x=(w-tw)/2:y=h-60:enable='between(t,{},{})'".format(escape_drawtext(cta_text), t0, t1)
    return vf


def get_media_duration(media_path):
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
                except ValueError:
                    return None
        return None
    except Exception:
        return None


def generate_video(content_path, audio_path, output_folder, base_name, content_type="images",
                   overlay_display=None, cta_text=None):
    """Genera un video combinando imagen/video con audio. Opcional: overlay de texto y CTA en el último 15%."""
    try:
        output_file = os.path.join(output_folder, f"{base_name}.mp4")

        ffmpeg_path = os.path.join("bin", "ffmpeg.exe") if os.name == 'nt' else "ffmpeg"
        audio_duration = get_media_duration(audio_path)
        duration_args = []
        if audio_duration is not None:
            duration_args = ["-t", f"{audio_duration:.3f}"]

        base_vf_images = "scale=-1:1080,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
        base_vf_videos = "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black"
        vf_images = build_vf_with_overlays(base_vf_images, overlay_display, cta_text, audio_duration)
        vf_videos = build_vf_with_overlays(base_vf_videos, overlay_display, cta_text, audio_duration)

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

        # encoding utf-8 para evitar UnicodeDecodeError con salida de FFmpeg
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')

        if result.returncode == 0:
            content_name = "video looped" if content_type == "videos" else "imagen"
            print(f"✓ Video generado con {content_name}: {os.path.basename(output_file)}")
            return True
        print(f"✗ Error FFmpeg: {result.stderr}")
        return False

    except Exception as e:
        print(f"Error generando video: {e}")
        return False


def list_content(images_folder, videos_folder, channel, group, content_type):
    """Lista los archivos de contenido de un canal/grupo según el tipo ('images' o 'videos')."""
    if content_type == "images":
        extensions = IMAGE_EXTENSIONS
        base_path = os.path.join(images_folder, channel, group)
    else:
        extensions = VIDEO_EXTENSIONS
        base_path = os.path.join(videos_folder, channel, group)
    if not os.path.exists(base_path):
        return []
    return [os.path.join(base_path, f) for f in os.listdir(base_path) if f.lower().endswith(extensions)]


class ContentPicker:
    """Selecciona contenido al azar sin repetir hasta agotar todos los archivos."""

    def __init__(self, images_folder, videos_folder="videos"):
        self.images_folder = images_folder
        self.videos_folder = videos_folder
        self.used = []

    def __call__(self, channel, group, content_type):
        available = list_content(self.images_folder, self.videos_folder, channel, group, content_type)
        if not available:
            return None
        unused = [f for f in available if f not in self.used]
        if not unused:
            self.used.clear()
            unused = available
        selected = random.choice(unused)
        self.used.append(selected)
        return selected


def list_beat_files(beats_folder):
    """Devuelve los archivos de audio de la carpeta de beats, ordenados."""
    if not os.path.isdir(beats_folder):
        return []
    return sorted(f for f in os.listdir(beats_folder) if f.lower().endswith(AUDIO_EXTENSIONS))


def write_metadata_csv(output_folder, entries):
    """Escribe metadata_youtube.csv y devuelve su ruta (None si no hay entradas o falla)."""
    if not entries:
        return None
    path = os.path.join(output_folder, 'metadata_youtube.csv')
    try:
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=METADATA_FIELDS)
            w.writeheader()
            for e in entries:
                w.writerow({k: e.get(k, '') for k in METADATA_FIELDS})
        return path
    except Exception as e:
        print(f"Error escribiendo metadata: {e}")
        return None


def generate_batch(beats_info, beats_folder, output_folder, content_type="images", pick_content=None,
                   name_template=None, overlay_enabled=False, overlay_text=None,
                   cta_enabled=False, cta_text=None, progress=None, should_stop=None, metadata_entries=None):
    """Genera un video por beat. Devuelve (videos_ok, total).

    beats_info: lista de dicts {'beat_file', 'channel', 'group', 'custom_name'}.
    pick_content(channel, group, content_type) -> ruta o None.
    progress(percent, message) y should_stop() son opcionales.
    metadata_entries: lista donde se acumulan las entradas de metadata para YouTube.
    """
    name_template = name_template or DEFAULT_NAME_TEMPLATE
    overlay_text = overlay_text or DEFAULT_OVERLAY_TEXT
    cta_text = cta_text or DEFAULT_CTA_TEXT
    if metadata_entries is None:
        metadata_entries = []
    total = len(beats_info)
    ok_count = 0

    for i, beat_info in enumerate(beats_info):
        if should_stop and should_stop():
            break

        beat_file = beat_info['beat_file']
        channel = beat_info['channel']
        group = beat_info['group']
        custom_name = beat_info.get('custom_name', '')

        if progress:
            progress(int((i / total) * 100), f"Procesando: {beat_file} ({i+1}/{total})")

        content_file = pick_content(channel, group, content_type) if pick_content else None
        if not content_file:
            content_name = "video" if content_type == "videos" else "imagen"
            print(f"⚠️ No se encontró {content_name} para {beat_file} en {channel}/{group}")
            continue

        group_output_folder = os.path.join(output_folder, channel, group)
        os.makedirs(group_output_folder, exist_ok=True)

        audio_file = os.path.join(beats_folder, beat_file)

        # Nombre personalizado o plantilla SEO
        if custom_name:
            base_output_name = sanitize_filename(custom_name)
        else:
            base = os.path.splitext(beat_file)[0]
            base_output_name = sanitize_filename(
                name_template.replace('{name}', base).replace('{channel}', channel).replace('{group}', group)
            )
            if not base_output_name:
                base_output_name = f"{base}_{channel}_{group}"

        overlay_display = overlay_text.replace('{name}', base_output_name.replace('_', ' ')) if overlay_enabled else None
        cta = cta_text if cta_enabled else None
        success = generate_video(content_file, audio_file, group_output_folder, base_output_name, content_type,
                                 overlay_display=overlay_display, cta_text=cta)

        if success:
            ok_count += 1
            # Metadata para YouTube (título, descripción, tags)
            title = base_output_name.replace('_', ' ')
            metadata_entries.append({
                'video_file': f"{base_output_name}.mp4",
                'path': os.path.join(group_output_folder, f"{base_output_name}.mp4"),
                'title': title,
                'description': f"Free type beat - {title}\n\nLink in description.\nSubscribe for more.",
                'tags': f"type beat, free beat, {group}, {channel}",
            })
            # Copiar imagen utilizada para referencia (los videos no, por tamaño)
            if content_type == "images":
                try:
                    shutil.copy2(content_file, os.path.join(group_output_folder, f"{base_output_name}_imagen.jpg"))
                except Exception:
                    pass
        else:
            print(f"❌ Error generando video para {beat_file}")

    return ok_count, total
