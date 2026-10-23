# -*- coding: utf-8 -*-
"""Modo manual: beats locales -> video + miniatura + texto, sin nube. Sin Qt.

El estilo de cada canal (fondo, título, descripción, tags, miniatura) y sus fondos viven en la
carpeta local de canales (normalmente ``<Dropbox>/TypeBeat Local``); ver ``core.channel_profile``.

Por cada beat deja ``<salida>/<fecha>/<canal>/<título>/`` con ``<título>.mp4``,
``<título> - miniatura.jpg`` (1280x720) y ``<título>.txt`` (bloques TÍTULO / DESCRIPCIÓN / TAGS),
y suma una fila a ``<salida>/<fecha>/pendientes.csv``. Nada se sube a YouTube ni a Dropbox.
"""
import csv
import json
import os
import random
import shutil
import subprocess
import tempfile
import time
from datetime import datetime

from core import channel_profile as cp
from core import beat_title as bt
from core import channel_templates, description, dropbox_local, stock_cache
from core import style as st
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


def beat_info(name):
    """``(bpm, tono)`` sacados del nombre del archivo (``160bpm``, ``key A Sharp Minor``), o None."""
    info = bt.parse(name)
    return (float(info['bpm']) if info['bpm'] else None), (info['key'] or None)


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
    def __init__(self, ffmpeg=None, ffprobe=None, cache=None):
        """``cache``: ``StockCache`` para videos stock; None = la de esta PC; False = sin caché."""
        self.ffmpeg = ffmpeg or resolve_tool('ffmpeg')
        if not self.ffmpeg:
            raise ManualError('No se encontró FFmpeg (ni en bin/ ni en el PATH).')
        self.codec = get_available_video_codec(self.ffmpeg)
        if cache is None:
            gb = load_settings()['cache_max_gb']  # «cache_max_gb» en config/manual_mode.json
            cache = stock_cache.StockCache(max_bytes=int(gb * 1024 ** 3))
        self.cache = cache or None

    def cached_stock(self, source, cancelled=lambda: False, framing='recortar'):
        """Video stock convertido a 1080p30 (de la caché), o None si no hay caché o falló."""
        if self.cache is None:
            return None
        try:
            return self.cache.ensure(source, self, cancelled, framing)
        except Cancelled:
            raise
        except (ManualError, OSError):
            return None  # se usa el método de siempre (más lento, pero anda)

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


def safe_name(title):
    """Nombre de archivo/carpeta para el título (Windows no acepta " : usa comillas simples)."""
    return channel_templates.sanitize_filename(
        title.replace('"', "'").replace('“', "'").replace('”', "'")).rstrip(' .') or 'video'


def unique_folder(parent, base):
    """``base`` o ``base (2)``... que todavía no exista dentro de ``parent``."""
    candidate, n = base, 2
    while os.path.exists(os.path.join(parent, candidate)):
        candidate, n = f'{base} ({n})', n + 1
    return candidate


def upload_text(title, description_text, tags):
    """Texto en bloques para copiar y pegar en YouTube Studio."""
    return (f'TÍTULO\n{title}\n\nDESCRIPCIÓN\n{description_text.strip()}\n\n'
            f'TAGS\n{", ".join(tags)}\n')


def render_beat(audio, mode, content, title, channel_folder, tools, thumbnail_source=None,
                title_on_thumbnail=False, description_text='', tags=(), cancelled=lambda: False,
                style=None, logo_path=None):
    """Genera una carpeta ``<título>/`` con el video, la miniatura y el texto para subir a mano.

    ``style``: estilo del canal (``core.style``); sin estilo, como siempre (``title_on_thumbnail``
    elige la franja en la miniatura). Los archivos llevan el título como nombre: YouTube Studio usa
    el nombre del archivo como título inicial. Si algo falla, la carpeta del video se borra entera.
    """
    if style is None:
        style = st.from_profile({'miniatura_con_titulo': title_on_thumbnail})
    seconds = get_media_duration(audio)
    if not seconds or seconds <= 0:
        raise ManualError(f'No se pudo leer la duración de {os.path.basename(audio)}.')
    os.makedirs(channel_folder, exist_ok=True)
    base = unique_folder(channel_folder, safe_name(title))
    folder = os.path.join(channel_folder, base)
    os.makedirs(folder)
    try:
        return _render_into(audio, mode, content, title, folder, base, seconds, tools, thumbnail_source,
                            style, logo_path, description_text, tags, cancelled)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


def _fades(seconds, video=True):
    """Filtros de fundido (1 s al entrar, 1,5 s al salir)."""
    out = max(0.0, seconds - 1.5)
    if video:
        return f'fade=t=in:st=0:d=1,fade=t=out:st={out:.3f}:d=1.5'
    return f'afade=t=in:st=0:d=1,afade=t=out:st={out:.3f}:d=1.5'


def _image_args(frame, audio, seconds, style, tools):
    v = style['video']
    if v['zoom']:
        frames = max(1, int(seconds * 30))
        step = 0.15 / frames  # llega a 1.15 al final, lento y parejo
        chain = (f"zoompan=z='min(1+on*{step:.8f},1.15)':d={frames}:x='iw/2-(iw/zoom/2)':"
                 f"y='ih/2-(ih/zoom/2)':s=1920x1080:fps=30")
        if v['fundido']:
            chain += ',' + _fades(seconds)
        args = ['-y', '-i', frame, '-i', audio, '-filter_complex', f'[0:v]{chain},format=yuv420p[v]',
                '-map', '[v]', '-map', '1:a:0', *tools.encode_args()]
    else:
        args = ['-y', '-loop', '1', '-framerate', str(STILL_FPS), '-i', frame, '-i', audio,
                '-map', '0:v:0', '-map', '1:a:0']
        if v['fundido']:
            args += ['-vf', _fades(seconds) + ',format=yuv420p']
        args += tools.encode_args(still=True)
    if v['fundido']:
        args += ['-af', _fades(seconds, video=False)]
    return args


def _video_args(content, audio, seconds, style, tools, tmp, title, logo_path, cancelled):
    """Video stock: copia rápida si no hay nada encima; si hay, se procesa con la capa del estilo."""
    v = style['video']
    framing = v['encuadre']
    cached = tools.cached_stock(content, cancelled, framing)
    if not st.video_overlays(style):
        if cached:
            # Ya está en 1080p30: se repite y se copia sin recodificar (≈10 veces más rápido).
            return ['-y', '-stream_loop', '-1', '-i', cached, '-i', audio, '-map', '0:v:0', '-map', '1:a:0',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart'], cached
        return ['-y', '-stream_loop', '-1', '-i', content, '-i', audio, '-map', '0:v:0', '-map', '1:a:0',
                '-vf', stock_cache.FILTERS[framing], *tools.encode_args()], None
    layer = os.path.join(tmp, 'capa.png')
    st.overlay_layer(style, title, logo_path).save(layer, 'PNG')
    source = cached or content
    base = '[0:v]' if cached else f'[0:v]{stock_cache.FILTERS[framing]}[b];[b]'
    chain = f'{base}[2:v]overlay=0:0,format=yuv420p'
    if v['fundido']:
        chain += ',' + _fades(seconds)
    args = ['-y', '-stream_loop', '-1', '-i', source, '-i', audio, '-loop', '1', '-i', layer,
            '-filter_complex', chain + '[v]', '-map', '[v]', '-map', '1:a:0', *tools.encode_args()]
    if v['fundido']:
        args += ['-af', _fades(seconds, video=False)]
    return args, cached


def _render_into(audio, mode, content, title, folder, base, seconds, tools, thumbnail_source,
                 style, logo_path, description_text, tags, cancelled):
    video_out = os.path.join(folder, base + '.mp4')
    thumb_out = os.path.join(folder, base + ' - miniatura.jpg')
    text_out = os.path.join(folder, base + '.txt')
    partial = video_out + '.part'
    origin = style['miniatura']['origen']
    with tempfile.TemporaryDirectory(prefix='manual-beat-') as tmp:
        if mode == MODE_IMAGE:
            frame = os.path.join(tmp, 'frame.png')
            try:
                st.render_frame(content, style, title, logo_path).save(frame, 'PNG')
            except (OSError, ValueError):
                raise ManualError(f'No se pudo abrir la imagen {os.path.basename(content)}.') from None
            args = _image_args(frame, audio, seconds, style, tools)
            thumb_from = content
        elif mode == MODE_VIDEO:
            args, cached = _video_args(content, audio, seconds, style, tools, tmp, title, logo_path, cancelled)
            thumb_from = os.path.join(tmp, 'thumb.png')
            frame_source = cached or content
            length = get_media_duration(frame_source) or 0
            tools.video_frame(frame_source, thumb_from, min(length * 0.1, 5.0), cancelled)
        else:
            raise ManualError('Modo desconocido.')
        if origin == 'miniaturas' and thumbnail_source:
            thumb_from = thumbnail_source
        tools.run([*args, '-t', f'{seconds:.3f}', '-f', 'mp4', partial], cancelled)
        # Dentro del with: el cuadro sacado del video vive en la carpeta temporal.
        try:
            st.render_thumbnail(thumb_from, style, title, logo_path).save(thumb_out, 'JPEG', quality=90)
        except (OSError, ValueError):
            raise ManualError(f'No se pudo armar la miniatura con {os.path.basename(thumb_from)}.') from None
    os.replace(partial, video_out)
    with open(text_out, 'w', encoding='utf-8') as f:
        f.write(upload_text(title, description_text, tags))
    return {'video': video_out, 'thumbnail': thumb_out, 'text': text_out, 'folder': folder,
            'title': title}


def beat_values(profile, name, channel):
    """Variables de plantilla para un beat: name, artist, bpm, key, mood y channel."""
    return dict(bt.parse(name, profile.get('artistas', ())), channel=channel)


def beat_title(profile, name, channel):
    """Título del perfil para el beat, con tope de 100 caracteres (límite de YouTube)."""
    values = beat_values(profile, name, channel)
    return cp.fit_title(bt.fill(profile['titulo'], values) or values['name'] or name)


def beat_tags(profile, name, channel):
    """Tags del perfil para el beat (lista, hasta 500 caracteres en total)."""
    return cp.render_tags(profile, beat_values(profile, name, channel))


def beat_text(profile, name, channel):
    """Descripción del perfil con las variables del beat (los tags van aparte, en su bloque)."""
    values = beat_values(profile, name, channel)
    tags = ', '.join(cp.render_tags(profile, values))
    filled = bt.fill(profile['descripcion'], values, tidy='gaps')
    return description.render(filled, values['name'], tags=tags, socials=profile['socials'],
                              hashtags=profile['hashtags']).strip()


PENDING_CSV = 'pendientes.csv'


def day_folder(output_root, today=None):
    return os.path.join(output_root, (today or datetime.now()).strftime('%Y-%m-%d'))


def add_pending(day_dir, channel, result):
    """Agrega el video a ``pendientes.csv`` del día (para llevar control de lo que falta subir)."""
    os.makedirs(day_dir, exist_ok=True)
    path = os.path.join(day_dir, PENDING_CSV)
    new = not os.path.exists(path)
    with open(path, 'a', encoding='utf-8-sig' if new else 'utf-8', newline='') as f:
        writer = csv.writer(f)
        if new:
            writer.writerow(['canal', 'título', 'carpeta', 'subido'])
        writer.writerow([channel, result['title'], os.path.normpath(result['folder']), ''])


def run_batch(beats, channel, local_root, output_root, profile=None,
              progress=lambda done, total, text: None, cancelled=lambda: False,
              tools=None, rng=None, titles=None, today=None,
              on_done=lambda audio, result: None, on_error=lambda audio, message: None):
    """Genera todos los beats con el perfil del canal. Devuelve ``(resultados, errores)``.

    Salida: ``<output_root>/<fecha>/<canal>/<título>/`` y una fila en ``<fecha>/pendientes.csv``.
    ``titles``: ``{ruta_audio: título}`` editados a mano para esta tanda (se cortan a 100).
    Un beat con error no corta la tanda; ``on_done``/``on_error`` se llaman por beat.
    """
    titles = titles or {}
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
    style = st.from_profile(profile)
    if 'estilo' not in profile and thumbs.files:
        style['miniatura']['origen'] = 'miniaturas'  # como siempre: si hay miniaturas propias, se usan
    logo_path = os.path.join(cp.channel_dir(local_root, channel), st.LOGO_FILE)
    framing = style['video']['encuadre']
    day_dir = day_folder(output_root, today)
    out_folder = os.path.join(day_dir, safe_name(channel))
    results, errors = [], []
    for index, audio in enumerate(beats):
        if cancelled():
            raise Cancelled()
        name = beat_name(audio)
        progress(index, len(beats), f'Generando {name} ({index + 1}/{len(beats)})')
        content = picks.next()
        cache = getattr(tools, 'cache', None)
        if mode == MODE_VIDEO and cache is not None and not os.path.isfile(cache.path_for(content, framing)):
            progress(index, len(beats), f'Preparando el video stock {os.path.basename(content)} '
                                        '(solo la primera vez, puede tardar un minuto)…')
        try:
            title = cp.fit_title(titles[audio]) if titles.get(audio, '').strip() else beat_title(profile, name, channel)
            result = render_beat(audio, mode, content, title, out_folder, tools, thumbs.next(),
                                 profile['miniatura_con_titulo'], beat_text(profile, name, channel),
                                 beat_tags(profile, name, channel), cancelled, style=style, logo_path=logo_path)
            add_pending(day_dir, channel, result)
            results.append(result)
            on_done(audio, result)
        except ManualError as exc:
            errors.append((name, str(exc)))
            on_error(audio, str(exc))
    progress(len(beats), len(beats), 'Listo')
    return results, errors


# --- Preferencias de esta pestaña (solo esta PC) ---

def load_settings(path=SETTINGS_FILE):
    data = _read_json(path)
    data.setdefault('output_folder', default_output_folder())
    data.setdefault('local_root', dropbox_local.default_local_root() or '')
    try:
        data['cache_max_gb'] = max(0.5, float(data.get('cache_max_gb', stock_cache.DEFAULT_MAX_GB)))
    except (TypeError, ValueError):
        data['cache_max_gb'] = stock_cache.DEFAULT_MAX_GB
    return data


def save_settings(data, path=SETTINGS_FILE):
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
