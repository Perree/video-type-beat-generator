"""Intro con logo animado (estilo prodbyDSI): desenfocado -> nítido, pulso y corte.

El logo se limpia (fondo gris texturado -> negro puro), se recorta a su contenido y se
escala a ~43 % del ancho. Los cuadros se dibujan con Pillow y FFmpeg los codifica a
1920x1080/30 FPS sin audio. La intro se cachea por canal + hash del logo + segundos.
"""
import hashlib
import math
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from core.beat_download import dropbox_path
from core.beat_http import BeatError

FPS = 30
WIDTH, HEIGHT = 1920, 1080
LOGO_SHARE = .43          # ancho del logo / ancho del cuadro
FLOOR = 70                # niveles: todo lo más oscuro que esto queda negro puro
BLUR_SECONDS = .9         # tramo de entrada (desenfocado -> nítido)
MAX_BLUR = 28
VERSION = 1               # subir si cambia la animación (invalida la caché)


def intro_options(raw):
    """Valida ``visual.intro = {logo, seconds}``; devuelve None si no hay intro."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) - {'logo', 'seconds'}:
        raise ValueError('invalid_intro')
    logo, seconds = raw.get('logo'), raw.get('seconds', 3.5)
    if not isinstance(logo, str) or not logo:
        raise ValueError('invalid_intro')
    try:
        dropbox_path(logo)
    except BeatError:
        raise ValueError('invalid_intro') from None
    if (isinstance(seconds, bool) or not isinstance(seconds, (int, float))
            or not math.isfinite(seconds) or not 1.5 <= seconds <= 8):
        raise ValueError('invalid_intro')
    # Cuadros enteros: la intro dura exactamente lo que dice la ficha (redondeado a 1/30 s).
    return {'logo': logo, 'seconds': frame_count(seconds) / FPS}


def frame_count(seconds):
    return round(seconds * FPS)


def default_cache():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(Path.home(), '.cache')
    return Path(base) / 'TypeBeat' / 'cache' / 'intros'


def prepared_logo(path):
    """Logo limpio (fondo negro puro) y recortado a su contenido, en RGB."""
    from PIL import Image, ImageFilter, ImageOps
    try:
        with Image.open(path) as source:
            if source.format not in {'PNG', 'JPEG', 'WEBP'} or source.width * source.height > 25_000_000:
                raise BeatError('intro_logo_rejected')
            source.load()
            image = ImageOps.exif_transpose(source)
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGBA')
                flat = Image.new('RGB', image.size, 'black')
                flat.paste(image, mask=image.getchannel('A'))
                image = flat
            image = image.convert('RGB')
    except BeatError:
        raise
    except Exception:
        raise BeatError('intro_logo_rejected') from None
    scale = 255 / (255 - FLOOR)
    # Niveles + gamma suave: fondo a negro puro y cromado más brillante (como el logo blanco de DSI).
    image = image.point(lambda v: 0 if v <= FLOOR else min(255, round(255 * ((v - FLOOR) * scale / 255) ** .8)))
    # Recorte al contenido: solo píxeles brillantes, y se ignoran motas sueltas de los bordes.
    mask = image.convert('L').point(lambda v: 255 if v > 140 else 0).filter(ImageFilter.MinFilter(3))
    box = mask.getbbox()
    if not box:
        raise BeatError('intro_logo_rejected')
    pad = 24
    box = (max(0, box[0] - pad), max(0, box[1] - pad),
           min(image.width, box[2] + pad), min(image.height, box[3] + pad))
    image = image.crop(box)
    width = round(WIDTH * LOGO_SHARE)
    height = round(image.height * width / image.width)
    if height > HEIGHT * .8:
        height = round(HEIGHT * .8)
        width = round(image.width * height / image.height)
    return image.resize((width, height), Image.LANCZOS)


def frame_state(index, total):
    """(escala, desenfoque, brillo) del cuadro ``index``."""
    t = index / FPS
    entry = min(1.0, t / BLUR_SECONDS)
    ease = 1 - (1 - entry) ** 3
    blur = MAX_BLUR * (1 - ease)
    brightness = .25 + .75 * ease
    # Zoom lento continuo + pulso (dos latidos después de la entrada).
    zoom = .94 + .06 * ease + .05 * (index / max(1, total - 1))
    after = max(0.0, t - BLUR_SECONDS)
    pulse = math.sin(math.pi * min(1.0, (after % 1.1) / .35)) if after > 0 else 0
    zoom += .025 * max(0.0, pulse)
    brightness = min(1.0, brightness + .12 * max(0.0, pulse))
    return zoom, blur, brightness


def draw_frame(logo, index, total):
    from PIL import Image, ImageEnhance, ImageFilter
    zoom, blur, brightness = frame_state(index, total)
    size = (max(2, round(logo.width * zoom)), max(2, round(logo.height * zoom)))
    picture = logo.resize(size, Image.BICUBIC)
    if brightness < 1:
        picture = ImageEnhance.Brightness(picture).enhance(brightness)
    margin = math.ceil(blur * 3) + 2
    canvas = Image.new('RGB', (size[0] + 2 * margin, size[1] + 2 * margin), 'black')
    canvas.paste(picture, (margin, margin))
    if blur > .3:
        canvas = canvas.filter(ImageFilter.GaussianBlur(blur))
    frame = Image.new('RGB', (WIDTH, HEIGHT), 'black')
    x, y = (WIDTH - canvas.width) // 2, (HEIGHT - canvas.height) // 2
    frame.paste(canvas, (x, y))  # puede salirse del cuadro; Pillow recorta
    return frame


def render_intro(logo_path, seconds, output, tools):
    """Codifica la intro (silenciosa, h264 yuv420p, 1920x1080/30) en ``output``."""
    total = frame_count(seconds)
    logo = prepared_logo(logo_path)
    with TemporaryDirectory(prefix='intro-') as folder:
        root = Path(folder)
        for index in range(total):
            draw_frame(logo, index, total).save(root / f'f{index:04d}.png', compress_level=1)
        partial = Path(str(output) + '.part.mp4')
        tools._call([tools.ffmpeg, '-nostdin', '-v', 'error', '-y', '-framerate', str(FPS),
            '-protocol_whitelist', 'file', '-f', 'image2', '-i', str(root / 'f%04d.png'),
            '-frames:v', str(total), '-c:v', 'libx264', '-preset', 'fast', '-pix_fmt', 'yuv420p',
            '-r', str(FPS), '-map_metadata', '-1', str(partial)], 300)
        if not partial.is_file() or not partial.stat().st_size:
            raise BeatError('intro_render_failed')
        os.replace(partial, output)
    return output


def cached_intro(channel_id, logo_path, seconds, tools, cache=None):
    """Ruta de la intro para este canal/logo/duración; la genera si no existe."""
    if not isinstance(channel_id, str) or not channel_id.replace('-', '').replace('_', '').isalnum():
        raise BeatError('intro_channel_invalid')
    digest = hashlib.sha256(Path(logo_path).read_bytes()).hexdigest()[:16]
    folder = Path(cache) if cache else default_cache()
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f'{channel_id}-{digest}-{frame_count(seconds)}f-v{VERSION}.mp4'
    if target.is_file() and target.stat().st_size:
        return target
    return render_intro(logo_path, seconds, target, tools)
