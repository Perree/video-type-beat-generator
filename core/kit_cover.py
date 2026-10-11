# -*- coding: utf-8 -*-
"""Portada cuadrada para los videos de loop kits y su cuadro 16:9.

``compose`` arma la portada a partir de un fondo y un título; ``to_video_frame`` pone esa
portada centrada sobre una copia desenfocada de sí misma. Todas las medidas, colores,
textos y fuentes viven en ``DEFAULT_TEMPLATE``; la plantilla que se pasa a ``compose`` se
mezcla encima (dict anidado, solo hace falta indicar lo que cambia). Las posiciones y los
tamaños son fracciones del lado de la portada. Fuentes: ``assets/kit_cover/`` (SIL OFL).
"""
import copy
import itertools
import os
import zlib

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONTS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         'assets', 'kit_cover')

DEFAULT_TEMPLATE = {
    'size': 1500,
    'seed': None,                 # None: se deriva del título (misma portada para el mismo título)
    'fonts': {
        'dir': FONTS_DIR,
        'title': 'Oswald.ttf',
        'title_weight': 700,      # eje de peso de la fuente variable
        'mono': 'CourierPrime-Bold.ttf',
    },
    'background': {
        'saturation': 0.55,
        'brightness': 0.6,
        'contrast': 1.1,
        'tint': '#2b1d12',
        'tint_amount': 0.18,
    },
    'vignette': {'strength': 0.75, 'start': 0.35, 'power': 1.8},
    'grain': {'amount': 0.09, 'cell': 1.4},
    'title': {
        'box': [0.08, 0.26, 0.92, 0.72],   # x0, y0, x1, y1
        'color': '#efe6d2',
        'shadow_color': '#000000',
        'shadow_opacity': 0.55,
        'shadow_offset': 0.006,
        'max_size': 0.30,                  # tope del cuerpo de letra
        'max_lines': 4,
        'line_spacing': 1.28,              # sobre la altura de mayúscula
        'stretch_x': 0.86,                 # < 1 condensa
        'uppercase': True,
        'wear': {
            'blotch_cell': 0.012, 'blotch_threshold': 0.8, 'blotch_softness': 0.08,
            'speckle': 0.018, 'scratches': 8, 'scratch_width': 0.0014,
        },
    },
    'brand': {
        'text': 'BRAND NAME', 'y': 0.075, 'size': 0.036, 'tracking': 0.28,
        'color': '#efe6d2', 'opacity': 0.9,
    },
    'label': {
        'text': 'LOOP KIT', 'y': 0.955, 'size': 0.085, 'tracking': 0.12,
        'color': '#efe6d2', 'opacity': 0.95, 'stretch_x': 0.86,
    },
    'stamp': {
        'text': 'ORIGINAL\nSAMPLES', 'center': [0.155, 0.84], 'radius': 0.085,
        'ring_width': 0.0045, 'angle': -14, 'color': '#d9b26a', 'opacity': 0.85,
        'text_size': 0.016,
    },
    'barcode': {
        'box': [0.70, 0.785, 0.92, 0.885], 'paper': '#efe6d2', 'ink': '#15110d',
        'opacity': 0.9, 'bars': 46, 'digits': 12, 'digits_size': 0.016, 'margin': 0.012,
    },
    'border': {
        'width': 0.022, 'color': '#e8dcc0', 'roughness': 0.010, 'opacity': 0.92,
        'wear_cell': 0.02, 'wear_threshold': 0.8, 'speckle': 0.02,
    },
}

FRAME_DEFAULTS = {
    'size': [1920, 1080],
    'cover_height': 0.9,       # alto de la portada sobre el alto del cuadro
    'blur_radius': 0.04,       # sobre el alto del cuadro
    'brightness': 0.5,
    'shadow_opacity': 0.5,
}


def _merge(base, over):
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _font(tpl, which, px):
    f = tpl['fonts']
    font = ImageFont.truetype(os.path.join(f['dir'], f[which]), max(1, int(round(px))))
    if which == 'title' and f.get('title_weight'):
        try:
            font.set_variation_by_axes([f['title_weight']])
        except Exception:  # fuente estática o FreeType sin variaciones: se usa el peso por defecto
            pass
    return font


def _cap_height(font):
    box = font.getbbox('H', anchor='ls')
    return -box[1]


def _noise_field(rng, w, h, cell):
    cell = max(1.0, cell)
    small = rng.random((int(h / cell) + 2, int(w / cell) + 2)).astype(np.float32)
    img = Image.fromarray((small * 255).astype(np.uint8)).resize((w, h), Image.BICUBIC)
    arr = np.asarray(img, dtype=np.float32) / 255.0
    lo, hi = arr.min(), arr.max()
    return (arr - lo) / max(hi - lo, 1e-6)


def _erosion(rng, w, h, wear, size):
    """Mapa 0..1 donde 1 es 'pintura perdida' (manchas, puntos y rayones)."""
    field = _noise_field(rng, w, h, wear['blotch_cell'] * size)
    soft = max(wear['blotch_softness'], 1e-4)
    blotch = np.clip((field - wear['blotch_threshold']) / soft, 0, 1)
    speckle = (rng.random((h, w)) < wear['speckle']).astype(np.float32)
    scratch = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(scratch)
    lw = max(1, int(round(wear['scratch_width'] * size)))
    for _ in range(int(wear['scratches'])):
        x0, y0 = rng.random() * w, rng.random() * h
        ang = rng.random() * np.pi
        ln = (0.15 + rng.random() * 0.5) * max(w, h)
        d.line([(x0, y0), (x0 + np.cos(ang) * ln, y0 + np.sin(ang) * ln)], fill=255, width=lw)
    return np.maximum.reduce([blotch, speckle, np.asarray(scratch, dtype=np.float32) / 255.0])


def _overlay(img, color, mask, opacity=1.0):
    """Pinta ``color`` sobre ``img`` (RGB) con ``mask`` (L) por ``opacity``."""
    if opacity < 1.0:
        mask = mask.point(lambda v: int(v * opacity))
    img.paste(Image.new('RGB', img.size, color), (0, 0), mask)


def _tracked_width(font, text, tracking_px):
    return sum(font.getlength(c) for c in text) + tracking_px * max(len(text) - 1, 0)


def _text_mask(size_wh, text, font, cx, baseline, tracking_px=0.0, stretch=1.0):
    """Máscara con ``text`` centrado en ``cx`` sobre ``baseline``, con tracking y estiramiento en x."""
    w, h = size_wh
    width = _tracked_width(font, text, tracking_px)
    pad = int(font.size * 0.5) + 2
    line = Image.new('L', (int(width) + 2 * pad, int(font.size * 2) + 2 * pad), 0)
    d = ImageDraw.Draw(line)
    x = pad
    base = pad + int(font.size * 1.3)
    for c in text:
        d.text((x, base), c, font=font, fill=255, anchor='ls')
        x += font.getlength(c) + tracking_px
    if stretch != 1.0:
        line = line.resize((max(1, int(line.width * stretch)), line.height), Image.LANCZOS)
    mask = Image.new('L', (w, h), 0)
    mask.paste(line, (int(cx - line.width / 2), int(baseline - base)))
    return mask


def _partitions(words, n):
    if n == 1:
        yield [' '.join(words)]
        return
    for cuts in itertools.combinations(range(1, len(words)), n - 1):
        idx = (0,) + cuts + (len(words),)
        yield [' '.join(words[idx[i]:idx[i + 1]]) for i in range(n)]


def _fit_title(tpl, text, box_w, box_h):
    """Elige líneas y cuerpo de letra: el mayor que entra en ``box_w`` x ``box_h``."""
    t = tpl['title']
    words = text.split() or ['']
    ref = 100
    font = _font(tpl, 'title', ref)
    cap_ref = _cap_height(font)
    stretch = t['stretch_x']
    best = None
    for n in range(1, min(int(t['max_lines']), len(words)) + 1):
        for lines in _partitions(words, n):
            w_ref = max(font.getlength(s) for s in lines) * stretch
            h_ref = cap_ref * (1 + (n - 1) * t['line_spacing'])
            size = min(box_w / max(w_ref, 1e-6), box_h / max(h_ref, 1e-6)) * ref
            if best is None or size > best[0]:
                best = (size, lines)
    size = int(min(best[0], t['max_size'] * tpl['size']))
    lines = best[1]
    while size > 1:  # el hinting no es lineal: se corrige hasta que entre de verdad
        f = _font(tpl, 'title', size)
        cap = _cap_height(f)
        if (max(f.getlength(s) for s in lines) * stretch <= box_w
                and cap * (1 + (len(lines) - 1) * t['line_spacing']) <= box_h):
            break
        size -= 1
    return lines, _font(tpl, 'title', size)


def _background(path, tpl):
    from PIL import ImageEnhance
    size = tpl['size']
    img = Image.open(path).convert('RGB')
    side = min(img.size)
    left, top = (img.width - side) // 2, (img.height - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((size, size), Image.LANCZOS)
    b = tpl['background']
    img = ImageEnhance.Color(img).enhance(b['saturation'])
    img = ImageEnhance.Contrast(img).enhance(b['contrast'])
    img = ImageEnhance.Brightness(img).enhance(b['brightness'])
    if b['tint_amount'] > 0:
        img = Image.blend(img, Image.new('RGB', img.size, b['tint']), b['tint_amount'])
    return img


def _vignette(img, v):
    n = img.width
    ax = np.linspace(-1, 1, n, dtype=np.float32)
    r = np.sqrt(ax[None, :] ** 2 + ax[:, None] ** 2) / np.sqrt(2)
    k = np.clip((r - v['start']) / max(1 - v['start'], 1e-6), 0, 1) ** v['power']
    arr = np.asarray(img, dtype=np.float32) * (1 - v['strength'] * k)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _grain(img, g, rng):
    n = img.width
    noise = _noise_field(rng, n, n, g['cell']) - 0.5
    arr = np.asarray(img, dtype=np.float32) + (noise * 2 * g['amount'] * 255)[..., None]
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))


def _draw_title(img, tpl, text, rng):
    t, n = tpl['title'], tpl['size']
    x0, y0, x1, y1 = [v * n for v in t['box']]
    text = text.upper() if t['uppercase'] else text
    lines, font = _fit_title(tpl, ' '.join(text.split()), x1 - x0, y1 - y0)
    cap = _cap_height(font)
    step = cap * t['line_spacing']
    block_h = cap + step * (len(lines) - 1)
    top = y0 + ((y1 - y0) - block_h) / 2
    mask = Image.new('L', img.size, 0)
    for i, s in enumerate(lines):
        mask = Image.fromarray(np.maximum(
            np.asarray(mask),
            np.asarray(_text_mask(img.size, s, font, (x0 + x1) / 2, top + cap + i * step,
                                  stretch=t['stretch_x']))))
    erase = _erosion(rng, n, n, t['wear'], n)
    worn = Image.fromarray((np.asarray(mask, dtype=np.float32) * (1 - erase)).astype(np.uint8))
    off = int(round(t['shadow_offset'] * n))
    shadow = worn.filter(ImageFilter.GaussianBlur(max(1, off))).transform(
        img.size, Image.AFFINE, (1, 0, -off, 0, 1, -off))
    _overlay(img, t['shadow_color'], shadow, t['shadow_opacity'])
    _overlay(img, t['color'], worn)
    return lines, font


def _draw_label(img, tpl, key, font_key, rng=None):
    c, n = tpl[key], tpl['size']
    if not c['text']:
        return
    font = _font(tpl, font_key, c['size'] * n)
    mask = _text_mask(img.size, c['text'].upper(), font, n / 2, c['y'] * n,
                      tracking_px=c['tracking'] * font.size, stretch=c.get('stretch_x', 1.0))
    _overlay(img, c['color'], mask, c['opacity'])


def _draw_stamp(img, tpl, rng):
    s, n = tpl['stamp'], tpl['size']
    if not s['text'] or s['radius'] <= 0:
        return
    cx, cy, r = s['center'][0] * n, s['center'][1] * n, s['radius'] * n
    layer = Image.new('L', img.size, 0)
    d = ImageDraw.Draw(layer)
    rw = max(1, int(round(s['ring_width'] * n)))
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=255, width=rw)
    r2 = r - rw * 3
    d.ellipse([cx - r2, cy - r2, cx + r2, cy + r2], outline=255, width=max(1, rw // 2))
    font = _font(tpl, 'mono', s['text_size'] * n)
    rows = s['text'].upper().split('\n')
    lh = font.size * 1.35
    y = cy - lh * (len(rows) - 1) / 2
    for row in rows:
        d.text((cx, y), row, font=font, fill=255, anchor='mm')
        y += lh
    layer = layer.rotate(s['angle'], center=(cx, cy), resample=Image.BICUBIC)
    erase = _erosion(rng, n, n, {'blotch_cell': 0.01, 'blotch_threshold': 0.78,
                                 'blotch_softness': 0.1, 'speckle': 0.04,
                                 'scratches': 0, 'scratch_width': 0.001}, n)
    layer = Image.fromarray((np.asarray(layer, dtype=np.float32) * (1 - erase)).astype(np.uint8))
    _overlay(img, s['color'], layer, s['opacity'])


def _draw_barcode(img, tpl, rng):
    b, n = tpl['barcode'], tpl['size']
    if b['bars'] <= 0:
        return
    x0, y0, x1, y1 = [v * n for v in b['box']]
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rectangle([x0, y0, x1, y1], fill=b['paper'])
    m = b['margin'] * n
    font = _font(tpl, 'mono', b['digits_size'] * n)
    digits_h = font.size * 1.3 if b['digits'] else 0
    widths = rng.integers(1, 4, size=int(b['bars']))
    gaps = rng.integers(1, 3, size=int(b['bars']))
    unit = (x1 - x0 - 2 * m) / float((widths + gaps).sum())
    x = x0 + m
    for w_, g_ in zip(widths, gaps):
        d.rectangle([x, y0 + m, x + w_ * unit, y1 - m - digits_h], fill=b['ink'])
        x += (w_ + g_) * unit
    if b['digits']:
        digits = ''.join(str(int(v)) for v in rng.integers(0, 10, size=int(b['digits'])))
        d.text(((x0 + x1) / 2, y1 - m), digits, font=font, fill=b['ink'], anchor='ms')
    alpha = layer.getchannel('A').point(lambda v: int(v * b['opacity']))
    img.paste(layer.convert('RGB'), (0, 0), alpha)


def _draw_border(img, tpl, rng):
    b, n = tpl['border'], tpl['size']
    if b['width'] <= 0:
        return img
    ax = np.arange(n, dtype=np.float32)
    dist = np.minimum.reduce([ax[None, :] + 0 * ax[:, None], (n - 1 - ax)[None, :] + 0 * ax[:, None],
                              ax[:, None] + 0 * ax[None, :], (n - 1 - ax)[:, None] + 0 * ax[None, :]])
    rough = (_noise_field(rng, n, n, 0.01 * n) - 0.5) * 2 * b['roughness'] * n
    band = (dist + rough) < b['width'] * n
    field = _noise_field(rng, n, n, b['wear_cell'] * n)
    erased = (field > b['wear_threshold']) | (rng.random((n, n)) < b['speckle'])
    alpha = (band & ~erased).astype(np.float32) * b['opacity']
    layer = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8))
    _overlay(img, b['color'], layer)
    return img


def compose(background_path, title, out_path, template=None):
    """Genera la portada cuadrada en ``out_path`` y devuelve la ruta."""
    tpl = _merge(DEFAULT_TEMPLATE, template)
    seed = tpl['seed']
    if seed is None:
        seed = zlib.crc32(str(title).encode('utf-8'))
    rng = np.random.default_rng(seed)
    img = _vignette(_background(background_path, tpl), tpl['vignette'])
    _draw_stamp(img, tpl, rng)
    _draw_barcode(img, tpl, rng)
    _draw_label(img, tpl, 'brand', 'mono')
    _draw_label(img, tpl, 'label', 'title')
    _draw_title(img, tpl, str(title), rng)
    img = _grain(img, tpl['grain'], rng)
    img = _draw_border(img, tpl, rng)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path)
    return out_path


def to_video_frame(cover, out_path, frame=None):
    """Cuadro 16:9: la portada centrada sobre una copia desenfocada y oscurecida de sí misma."""
    from PIL import ImageEnhance
    cfg = _merge(FRAME_DEFAULTS, frame)
    fw, fh = cfg['size']
    src = Image.open(cover).convert('RGB')
    scale = max(fw / src.width, fh / src.height)
    bg = src.resize((int(src.width * scale) + 1, int(src.height * scale) + 1), Image.LANCZOS)
    left, top = (bg.width - fw) // 2, (bg.height - fh) // 2
    bg = bg.crop((left, top, left + fw, top + fh))
    bg = bg.filter(ImageFilter.GaussianBlur(cfg['blur_radius'] * fh))
    bg = ImageEnhance.Brightness(bg).enhance(cfg['brightness'])
    side = int(fh * cfg['cover_height'])
    front = src.resize((side, side), Image.LANCZOS)
    pos = ((fw - side) // 2, (fh - side) // 2)
    shadow = Image.new('L', (fw, fh), 0)
    ImageDraw.Draw(shadow).rectangle([pos[0], pos[1], pos[0] + side, pos[1] + side], fill=255)
    shadow = shadow.filter(ImageFilter.GaussianBlur(0.02 * fh))
    _overlay(bg, '#000000', shadow, cfg['shadow_opacity'])
    bg.paste(front, pos)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    bg.save(out_path)
    return out_path


def for_video(cfg, background, title, work_dir):
    """Cuadro y miniatura de un video a partir de ``kit_preview.cover`` de la config.

    ``cfg`` es ``{'enabled': bool, 'template': {...}, 'frame': {...}}``. Sin ``cfg`` (o con
    ``enabled`` falso) no cambia nada: devuelve ``(background, None)``. Si no, devuelve
    ``(cuadro_16_9, miniatura)``; ambos son la misma imagen, la miniatura en JPEG liviano.
    """
    if not cfg or cfg.get('enabled', True) is False:
        return background, None
    cover = compose(background, title, os.path.join(work_dir, 'kit_cover.png'),
                    cfg.get('template'))
    return frame_for_video(cfg, cover, work_dir)


def frame_for_video(cfg, cover, work_dir):
    """Cuadro 16:9 y miniatura a partir de una portada cuadrada ya terminada.

    La usa la portada completa con IA (``cover_mode: template``), que no pasa por
    ``compose``. De ``cfg`` (``kit_preview.cover``, puede faltar) solo se lee ``frame``.
    """
    frame = to_video_frame(cover, os.path.join(work_dir, 'kit_frame.png'),
                           (cfg or {}).get('frame'))
    thumb = os.path.join(work_dir, 'kit_thumb.jpg')
    Image.open(frame).convert('RGB').save(thumb, quality=88)
    return frame, thumb
