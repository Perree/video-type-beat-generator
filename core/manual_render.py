# -*- coding: utf-8 -*-
"""Modo manual: beats locales -> video + miniatura + texto, sin nube. Sin Qt.

El estilo de cada canal (fondo, título, descripción, tags, miniatura) y sus fondos viven en la
carpeta local de canales (normalmente ``<Dropbox>/TypeBeat Local``); ver ``core.channel_profile``.

Por cada beat deja en ``<salida>/<canal>/``: ``<título>.mp4``, ``<título>.jpg`` (1280x720)
y ``<título>.txt`` (título, descripción y tags). Nada se sube a YouTube ni a Dropbox.
"""
import json
import os
import random
import re
import subprocess
import tempfile
import time

from core import channel_profile as cp
from core import channel_templates, description, dropbox_local
from core.ffmpeg_util import get_available_video_codec, get_media_duration, resolve_tool

AUDIO_SUFFIXES = ('.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg')
MODE_IMAGE, MODE_VIDEO = cp.MODE_IMAGE, cp.MODE_VIDEO
SETTINGS_FILE = os.path.join('config', 'manual_mode.json')
OUTPUT_DIRNAME = 'Type Beat Videos'
FRAME = (1920, 1080)
STILL_FPS = 6  # foto fija: menos cuadros = render mucho más rápido, se ve igual
THUMB = (1280, 720)


class ManualError(Exception):
    """Error apto para mostrar en la UI."""


class Cancelled(Exception):
    """El usuario canceló la tanda."""


# --- Entrada ---

def collect_audio(paths):
    """Audios de ``paths`` (archivos o carpetas, con subcarpetas), sin repetir, en orden."""
    found, seen = [], set()

    def add(path):
        key = os.path.normcase(os.path.abspath(path))
        if path.lower().endswith(AUDIO_SUFFIXES) and key not in seen:
            seen.add(key)
            found.append(os.path.abspath(path))

    for path in paths:
        if os.path.isdir(path):
            for folder, dirs, files in os.walk(path):
                dirs.sort()
                for name in sorted(files):
                    add(os.path.join(folder, name))
        elif os.path.isfile(path):
            add(path)
    return found


def _read_json(path):
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def beat_name(audio):
    return os.path.splitext(os.path.basename(audio))[0]


_BPM = re.compile(r'(\d{2,3}(?:\.\d)?)\s*bpm', re.I)
_KEY = re.compile(r'\bkey\s*[:\-]?\s*([A-G](?:\s*(?:#|b|sharp|flat))?(?:\s*(?:minor|major|min|maj|m))?)(?![A-Za-z])',
                  re.I)


def beat_info(name):
    """``(bpm, tono)`` sacados del nombre del archivo (``160bpm``, ``key A Sharp Minor``), o None."""
    bpm = _BPM.search(name)
    key = _KEY.search(name)
    return (float(bpm.group(1)) if bpm else None), (key.group(1).strip() if key else None)


def default_output_folder():
    return os.path.join(os.path.expanduser('~'), 'Desktop', OUTPUT_DIRNAME)


class Rotation:
    """Elige al azar sin repetir hasta usar todos (como el modo manual de antes)."""

    def __init__(self, files, rng=None):
        self.files = list(files)
        self.rng = rng or random.Random()
        self.used = []

    def next(self):
        if not self.files:
            return None
        unused = [f for f in self.files if f not in self.used]
        if not unused:
            self.used.clear()
            unused = list(self.files)
        choice = self.rng.choice(unused)
        self.used.append(choice)
        return choice


def unique_base(folder, base):
    """``base`` o ``base (2)``... para no pisar un video ya generado."""
    candidate, n = base, 2
    while any(os.path.exists(os.path.join(folder, candidate + ext)) for ext in ('.mp4', '.jpg', '.txt')):
        candidate, n = f'{base} ({n})', n + 1
    return candidate


# --- Imágenes (Pillow) ---

def fit_image(source, target, size, title=None):
    """Recorta ``source`` a ``size`` (sin barras) y lo guarda; con ``title``, agrega la franja."""
    from PIL import Image, ImageOps
    try:
        with Image.open(source) as img:
            img.load()
            picture = ImageOps.fit(ImageOps.exif_transpose(img).convert('RGB'), size)
    except Exception:
        raise ManualError(f'No se pudo abrir la imagen {os.path.basename(source)}.') from None
    if title:
        _draw_title(picture, title)
    if str(target).lower().endswith('.png'):
        picture.save(target, 'PNG')
    else:
        picture.save(target, 'JPEG', quality=90)


def _draw_title(picture, title):
    """Franja oscura abajo con el título (hasta 3 líneas), proporcional al tamaño."""
    from PIL import ImageDraw, ImageFont
    w, h = picture.size
    px = max(16, int(h * 0.054))
    for name in ('arialbd.ttf', 'DejaVuSans-Bold.ttf', 'arial.ttf', 'DejaVuSans.ttf'):
        try:
            font = ImageFont.truetype(name, px)
            break
        except OSError:
            continue
    else:
        font = ImageFont.load_default()
    draw = ImageDraw.Draw(picture)
    margin, limit = int(w * 0.047), int(w * 0.906)
    lines, line = [], ''
    for word in title.split():
        trial = (line + ' ' + word).strip()
        if line and draw.textlength(trial, font=font) > limit:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    if len(lines) > 3:
        lines = lines[:3]
        lines[-1] = lines[-1].rstrip('.') + '...'
    gap = int(px * 0.25)
    block = len(lines) * px + (len(lines) - 1) * gap
    pad = margin // 2
    top = h - block - 2 * pad
    draw.rectangle((0, top, w, h), fill=(15, 15, 20))
    draw.multiline_text((margin, top + pad), '\n'.join(lines), font=font, fill='white',
                        spacing=gap)


# --- FFmpeg ---

class Tools:
    def __init__(self, ffmpeg=None, ffprobe=None):
        self.ffmpeg = ffmpeg or resolve_tool('ffmpeg')
        if not self.ffmpeg:
            raise ManualError('No se encontró FFmpeg (ni en bin/ ni en el PATH).')
        self.codec = get_available_video_codec(self.ffmpeg)

    def run(self, args, cancelled=lambda: False, timeout=3600):
        """Corre ffmpeg; corta el proceso si el usuario cancela."""
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        proc = subprocess.Popen([self.ffmpeg, '-nostdin', '-hide_banner', '-loglevel', 'error', *args],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE, creationflags=flags)
        deadline = time.monotonic() + timeout
        try:
            while True:
                try:
                    _, err = proc.communicate(timeout=0.3)
                    break
                except subprocess.TimeoutExpired:
                    if cancelled():
                        proc.kill()
                        proc.communicate()
                        raise Cancelled()
                    if time.monotonic() > deadline:
                        proc.kill()
                        proc.communicate()
                        raise ManualError('FFmpeg tardó demasiado.')
        finally:
            if proc.poll() is None:
                proc.kill()
        if proc.returncode != 0:
            detail = (err or b'').decode('utf-8', 'replace').strip().splitlines()
            raise ManualError('FFmpeg falló' + (f': {detail[-1][:200]}' if detail else '.'))

    def encode_args(self, still=False):
        # Video stock: veryfast tarda la mitad que fast y pesa menos; la foto fija ya es liviana.
        preset = 'fast' if still or self.codec != 'libx264' else 'veryfast'
        args = ['-c:v', self.codec, '-preset', preset]
        if still and self.codec == 'libx264':
            args += ['-tune', 'stillimage']
        return args + ['-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '192k',
                       '-movflags', '+faststart']

    def video_frame(self, video, target, at, cancelled=lambda: False):
        self.run(['-y', '-ss', f'{at:.2f}', '-i', video, '-frames:v', '1', target], cancelled, 120)


def render_beat(audio, mode, content, title, out_folder, tools, thumbnail_source=None,
                title_on_thumbnail=False, text='', cancelled=lambda: False):
    """Genera ``<título>.mp4``, ``.jpg`` y ``.txt`` en ``out_folder``. Devuelve sus rutas."""
    seconds = get_media_duration(audio)
    if not seconds or seconds <= 0:
        raise ManualError(f'No se pudo leer la duración de {os.path.basename(audio)}.')
    os.makedirs(out_folder, exist_ok=True)
    base = unique_base(out_folder, channel_templates.sanitize_filename(title))
    video_out = os.path.join(out_folder, base + '.mp4')
    thumb_out = os.path.join(out_folder, base + '.jpg')
    text_out = os.path.join(out_folder, base + '.txt')
    partial = video_out + '.part'
    with tempfile.TemporaryDirectory(prefix='manual-beat-') as tmp:
        if mode == MODE_IMAGE:
            frame = os.path.join(tmp, 'frame.png')
            fit_image(content, frame, FRAME)
            args = ['-y', '-loop', '1', '-framerate', str(STILL_FPS), '-i', frame, '-i', audio,
                    '-map', '0:v:0', '-map', '1:a:0', *tools.encode_args(still=True)]
            thumb_from = thumbnail_source or content
        elif mode == MODE_VIDEO:
            vf = ('scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,'
                  'setsar=1,fps=30,format=yuv420p')
            args = ['-y', '-stream_loop', '-1', '-i', content, '-i', audio,
                    '-map', '0:v:0', '-map', '1:a:0', '-vf', vf, *tools.encode_args()]
            thumb_from = thumbnail_source
            if not thumb_from:
                thumb_from = os.path.join(tmp, 'thumb.png')
                length = get_media_duration(content) or 0
                tools.video_frame(content, thumb_from, min(length * 0.1, 5.0), cancelled)
        else:
            raise ManualError('Modo desconocido.')
        try:
            tools.run([*args, '-t', f'{seconds:.3f}', '-f', 'mp4', partial], cancelled)
            # Dentro del with: el cuadro sacado del video vive en la carpeta temporal.
            fit_image(thumb_from, thumb_out, THUMB, title if title_on_thumbnail else None)
        except BaseException:
            for leftover in (partial, thumb_out):
                if os.path.exists(leftover):
                    os.remove(leftover)
            raise
    os.replace(partial, video_out)
    with open(text_out, 'w', encoding='utf-8') as f:
        f.write(f'{title}\n\n{text.strip()}\n')
    return {'video': video_out, 'thumbnail': thumb_out, 'text': text_out}


def beat_title(profile, name, channel):
    """Título del perfil para el beat, con tope de 100 caracteres (límite de YouTube)."""
    title = channel_templates.render_title(profile['titulo'], name, channel).strip()
    return cp.fit_title(title or name)


def beat_text(profile, name, channel):
    """Descripción del perfil con BPM, tono y tags; agrega los tags si la plantilla no los usa."""
    bpm, key = beat_info(name)
    tags = ', '.join(cp.render_tags(profile, name, channel))
    body = description.render(profile['descripcion'], name, bpm, key, tags=tags,
                              socials=profile['socials'], hashtags=profile['hashtags']).strip()
    if '{tags}' not in profile['descripcion'] and tags:
        body = f'{body}\n\nTags: {tags}'.strip()
    return body


def run_batch(beats, channel, local_root, output_root, profile=None,
              progress=lambda done, total, text: None, cancelled=lambda: False,
              tools=None, rng=None):
    """Genera todos los beats con el perfil del canal. Devuelve ``(resultados, errores)``.

    Un beat con error no corta la tanda.
    """
    profile = profile or cp.load(local_root, channel)
    mode = profile['fondo']
    contents, remote = cp.media(local_root, channel, mode)
    if not contents:
        kind = 'imágenes' if mode == MODE_IMAGE else 'videos'
        folder = os.path.join(cp.channel_dir(local_root, channel), cp.BACKGROUNDS_DIR)
        extra = f' ({len(remote)} todavía sin bajar de Dropbox)' if remote else ''
        raise ManualError(f'No hay {kind} en {folder}{extra}.')
    tools = tools or Tools()
    rng = rng or random.Random()
    picks = Rotation(contents, rng)
    thumbs = Rotation(cp.media(local_root, channel, 'thumbnail')[0], rng)
    out_folder = os.path.join(output_root, channel_templates.sanitize_filename(channel))
    results, errors = [], []
    for index, audio in enumerate(beats):
        if cancelled():
            raise Cancelled()
        name = beat_name(audio)
        progress(index, len(beats), f'Generando {name} ({index + 1}/{len(beats)})')
        try:
            results.append(render_beat(audio, mode, picks.next(), beat_title(profile, name, channel),
                                       out_folder, tools, thumbs.next(),
                                       profile['miniatura_con_titulo'],
                                       beat_text(profile, name, channel), cancelled))
        except ManualError as exc:
            errors.append((name, str(exc)))
    progress(len(beats), len(beats), 'Listo')
    return results, errors


# --- Preferencias de esta pestaña (solo esta PC) ---

def load_settings(path=SETTINGS_FILE):
    data = _read_json(path)
    data.setdefault('output_folder', default_output_folder())
    data.setdefault('local_root', dropbox_local.default_local_root() or '')
    return data


def save_settings(data, path=SETTINGS_FILE):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
