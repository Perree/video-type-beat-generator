# -*- coding: utf-8 -*-
"""Estilo visual de un canal (video y miniatura): esquema, estilos listos y dibujo con Pillow. Sin Qt.

Vive en el perfil del canal (``perfil.json`` → ``estilo``). Sin estilo guardado, el canal sale como
siempre (recorte simple; miniatura con o sin franja según ``miniatura_con_titulo``).

- Video: encuadre (recortar / centrado con fondo difuminado), oscurecer, tinte, grano, título en el
  video (arriba / centro / abajo), logo, zoom lento (solo imagen fija) y fundido de entrada/salida.
- Miniatura: plantilla (solo imagen / franja abajo / título grande / con logo), fuente, color,
  tamaño, contorno y de dónde sale la imagen (el fondo, la carpeta de miniaturas o un cuadro del video).
"""
import os
import random
from copy import deepcopy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS_DIR = os.path.join(ROOT, 'assets', 'kit_cover')
FRAME = (1920, 1080)
THUMB = (1280, 720)

# nombre visible → candidatos (incluidas en el proyecto primero; si no, las de Windows)
FONTS = {
    'Oswald': (os.path.join(FONTS_DIR, 'Oswald.ttf'),),
    'Arial negrita': ('arialbd.ttf', 'DejaVuSans-Bold.ttf'),
    'Impact': ('impact.ttf', os.path.join(FONTS_DIR, 'Oswald.ttf')),
    'Courier Prime': (os.path.join(FONTS_DIR, 'CourierPrime-Bold.ttf'),),
}
FRAMINGS = ('recortar', 'difuminado')
POSITIONS = ('arriba', 'centro', 'abajo')
TEMPLATES = ('solo', 'franja', 'grande', 'logo')
SOURCES = ('fondo', 'miniaturas', 'video')
LOGO_FILE = 'logo.png'  # en la carpeta del canal

DEFAULT = {
    'video': {'encuadre': 'recortar', 'oscurecer': 0, 'tinte': '', 'grano': False, 'titulo': False,
              'titulo_pos': 'abajo', 'logo': False, 'zoom': False, 'fundido': False},
    'miniatura': {'plantilla': 'solo', 'fuente': 'Arial negrita', 'color': '#ffffff', 'tamano': 100,
                  'contorno': False, 'origen': 'fondo'},
}

PRESETS = {
    'Limpio': {'video': {}, 'miniatura': {'plantilla': 'solo'}},
    'Franja oscura': {'video': {}, 'miniatura': {'plantilla': 'franja', 'fuente': 'Arial negrita'}},
    'Título grande': {'video': {'oscurecer': 25}, 'miniatura': {'plantilla': 'grande', 'fuente': 'Oswald',
                                                                'tamano': 120, 'contorno': True}},
    'Neón': {'video': {'oscurecer': 35, 'tinte': '#7b2ff7', 'grano': True},
             'miniatura': {'plantilla': 'grande', 'fuente': 'Impact', 'color': '#39ff14', 'contorno': True}},
    'Cine': {'video': {'encuadre': 'difuminado', 'oscurecer': 15, 'fundido': True},
             'miniatura': {'plantilla': 'franja', 'fuente': 'Oswald'}},
}


class StyleError(ValueError):
    """Estilo inválido; el mensaje es apto para la UI."""


def _color(value):
    if not isinstance(value, str):
        return False
    value = value.strip()
    return value == '' or (len(value) == 7 and value[0] == '#' and all(c in '0123456789abcdefABCDEF' for c in value[1:]))


def preset(name):
    style = deepcopy(DEFAULT)
    for part, values in PRESETS[name].items():
        style[part].update(values)
    return style


def from_profile(profile):
    """Estilo del perfil; si no tiene, uno equivalente a cómo salía antes."""
    raw = profile.get('estilo') if isinstance(profile, dict) else None
    if isinstance(raw, dict):
        return validate(raw)
    style = deepcopy(DEFAULT)
    if isinstance(profile, dict) and profile.get('miniatura_con_titulo'):
        style['miniatura']['plantilla'] = 'franja'
    return style


def validate(raw):
    """Copia completa y válida del estilo (completa lo que falte) o StyleError."""
    if not isinstance(raw, dict):
        raise StyleError('Estilo inválido.')
    style = deepcopy(DEFAULT)
    for part in ('video', 'miniatura'):
        values = raw.get(part) or {}
        if not isinstance(values, dict):
            raise StyleError('Estilo inválido.')
        unknown = set(values) - set(DEFAULT[part])
        if unknown:
            raise StyleError(f'Opción de estilo desconocida: {sorted(unknown)[0]}.')
        style[part].update(values)
    v, m = style['video'], style['miniatura']
    checks = [
        (v['encuadre'] in FRAMINGS, 'encuadre'), (v['titulo_pos'] in POSITIONS, 'posición del título'),
        (isinstance(v['oscurecer'], int) and 0 <= v['oscurecer'] <= 80, 'oscurecer (0 a 80)'),
        (_color(v['tinte']), 'tinte'), (m['plantilla'] in TEMPLATES, 'plantilla de miniatura'),
        (m['fuente'] in FONTS, 'fuente'), (_color(m['color']) and m['color'], 'color del texto'),
        (isinstance(m['tamano'], int) and 50 <= m['tamano'] <= 200, 'tamaño (50 a 200)'),
        (m['origen'] in SOURCES, 'origen de la miniatura'),
    ] + [(type(v[k]) is bool, k) for k in ('grano', 'titulo', 'logo', 'zoom', 'fundido')] + [
        (type(m['contorno']) is bool, 'contorno')]
    for ok, name in checks:
        if not ok:
            raise StyleError(f'Valor inválido en el estilo: {name}.')
    return style


def video_overlays(style):
    """True si el video stock necesita procesarse (algo dibujado encima o fundido): es más lento."""
    v = style['video']
    return bool(v['oscurecer'] or v['tinte'] or v['titulo'] or v['logo'] or v['fundido'])


# --- Dibujo ---

def font(name, px):
    from PIL import ImageFont
    for candidate in FONTS.get(name, ()) + FONTS['Oswald']:
        try:
            return ImageFont.truetype(candidate, px)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=px)
    except TypeError:
        return ImageFont.load_default()


def _rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))


def frame_image(source, size, framing='recortar'):
    """Imagen ``size`` desde ``source`` (ruta o PIL.Image): recortada, o centrada sobre su versión difuminada."""
    from PIL import Image, ImageFilter, ImageOps
    if isinstance(source, Image.Image):
        img = source
    else:
        with Image.open(source) as opened:
            opened.load()
            img = ImageOps.exif_transpose(opened).convert('RGB')
    img = img.convert('RGB')
    if framing == 'difuminado':
        back = ImageOps.fit(img, size).filter(ImageFilter.GaussianBlur(radius=max(size) // 40))
        front = ImageOps.contain(img, size)
        back.paste(front, ((size[0] - front.width) // 2, (size[1] - front.height) // 2))
        return back
    return ImageOps.fit(img, size)


def _darken_tint_grain(img, video, seed=0):
    from PIL import Image
    if video['tinte']:
        tint = Image.new('RGB', img.size, _rgb(video['tinte']))
        img = Image.blend(img, tint, 0.25)
    if video['oscurecer']:
        img = Image.blend(img, Image.new('RGB', img.size, (0, 0, 0)), video['oscurecer'] / 100)
    if video['grano']:
        rng = random.Random(seed)
        noise = Image.effect_noise((img.width // 2, img.height // 2), 40).resize(img.size).convert('RGB')
        img = Image.blend(img, noise, 0.08 + rng.random() * 0.02)
    return img


def _wrap(draw, text, fnt, limit, max_lines=3):
    lines, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if line and draw.textlength(trial, font=fnt) > limit:
            lines.append(line)
            line = word
        else:
            line = trial
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip('.') + '…'
    return lines


def _text_block(img, text, fnt_name, px, color, position, outline, band=False, max_lines=3):
    """Texto centrado en ``position`` (arriba/centro/abajo); con ``band``, franja oscura detrás."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    w, h = img.size
    fnt = font(fnt_name, px)
    margin = int(w * 0.05)
    lines = _wrap(draw, text, fnt, w - 2 * margin, max_lines)
    gap = int(px * 0.2)
    heights = [fnt.getbbox(line)[3] - fnt.getbbox(line)[1] for line in lines]
    block = sum(heights) + gap * (len(lines) - 1)
    pad = int(px * 0.5)
    if position == 'arriba':
        top = margin
    elif position == 'centro':
        top = (h - block) // 2
    else:
        top = h - block - margin
    if band:
        draw.rectangle((0, top - pad, w, min(h, top + block + pad)), fill=(15, 15, 20))
    stroke = max(2, px // 14) if outline else 0
    y = top
    for line, height in zip(lines, heights):
        x = (w - draw.textlength(line, font=fnt)) / 2
        draw.text((x, y - fnt.getbbox(line)[1]), line, font=fnt, fill=color,
                  stroke_width=stroke, stroke_fill=(0, 0, 0))
        y += height + gap
    return img


def _paste_logo(img, logo_path, corner='abajo-derecha'):
    from PIL import Image
    if not logo_path or not os.path.isfile(logo_path):
        return img
    with Image.open(logo_path) as logo:
        logo = logo.convert('RGBA')
        target = int(img.width * 0.12)
        logo.thumbnail((target, target))
        margin = int(img.width * 0.03)
        pos = (img.width - logo.width - margin, img.height - logo.height - margin)
        base = img.convert('RGBA')
        base.alpha_composite(logo, pos)
        return base.convert('RGB')


def render_frame(source, style, title, logo_path=None, seed=0):
    """Cuadro de video 1920x1080 (fondo + efectos + título/logo si van en el video)."""
    v = style['video']
    img = frame_image(source, FRAME, v['encuadre'])
    img = _darken_tint_grain(img, v, seed)
    if v['titulo'] and title:
        img = _text_block(img, title, style['miniatura']['fuente'], 64, style['miniatura']['color'],
                          v['titulo_pos'], outline=True, band=False, max_lines=2)
    if v['logo']:
        img = _paste_logo(img, logo_path)
    return img


def overlay_layer(style, title, logo_path=None, size=FRAME):
    """Capa transparente con oscurecer/tinte/título/logo para poner encima de un video stock."""
    from PIL import Image
    v = style['video']
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    if v['tinte']:
        layer = Image.alpha_composite(layer, Image.new('RGBA', size, _rgb(v['tinte']) + (64,)))
    if v['oscurecer']:
        layer = Image.alpha_composite(layer, Image.new('RGBA', size, (0, 0, 0, int(255 * v['oscurecer'] / 100))))
    if v['titulo'] and title:
        text = Image.new('RGBA', size, (0, 0, 0, 0))
        text = _text_block(text, title, style['miniatura']['fuente'], 64, style['miniatura']['color'],
                           v['titulo_pos'], outline=True, band=False, max_lines=2)
        layer = Image.alpha_composite(layer, text)
    if v['logo'] and logo_path and os.path.isfile(logo_path):
        with Image.open(logo_path) as logo:
            logo = logo.convert('RGBA')
            target = int(size[0] * 0.12)
            logo.thumbnail((target, target))
            margin = int(size[0] * 0.03)
            layer.alpha_composite(logo, (size[0] - logo.width - margin, size[1] - logo.height - margin))
    return layer


def render_thumbnail(source, style, title, logo_path=None):
    """Miniatura 1280x720 según la plantilla del estilo."""
    m = style['miniatura']
    img = frame_image(source, THUMB, 'recortar')
    px = int(THUMB[1] * 0.075 * m['tamano'] / 100)
    if m['plantilla'] == 'grande' and title:
        from PIL import Image
        img = Image.blend(img, Image.new('RGB', img.size, (0, 0, 0)), 0.3)  # el texto grande se lee mejor
    if m['plantilla'] == 'franja' and title:
        img = _text_block(img, title, m['fuente'], px, m['color'], 'abajo', m['contorno'], band=True)
    elif m['plantilla'] == 'grande' and title:
        img = _text_block(img, title, m['fuente'], int(px * 1.6), m['color'], 'centro', True, max_lines=3)
    elif m['plantilla'] == 'logo':
        img = _paste_logo(img, logo_path)
    return img
