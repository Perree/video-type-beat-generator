"""Miniatura estilo Taigen (ey mat): Parental Advisory, firma en cursiva y textura.

``visual.thumbnail_badges = {advisory, signature, font, grain, vignette}`` se aplica a la
miniatura fixed_bars (1280x720) después del logo:

- grano monocromo con semilla fija y viñeta sobre la foto central, para que imágenes de
  fuentes distintas se vean de la misma serie (las franjas negras siguen negras);
- Parental Advisory oficial (``assets/thumbnail``) abajo a la izquierda de la foto;
- firma (por defecto «ey mat») en la misma cursiva del video, arriba a la derecha.

Las posiciones salen de ``beat_thumb_logo.place``, que ya descuenta la franja de 344 px.
"""
from pathlib import Path
from core.beat_http import BeatError
from core.beat_thumb_logo import place
from core.beat_title_overlay import FONT_DIR, FONTS

ADVISORY = Path(__file__).resolve().parent.parent / 'assets' / 'thumbnail' / 'parental_advisory.png'
DEFAULTS = {'advisory': True, 'signature': 'ey mat', 'font': 'great_vibes', 'grain': .035, 'vignette': .35}
ADVISORY_SHARE = .12      # ancho del Parental Advisory / ancho de la miniatura
SIGNATURE_SHARE = .075    # alto de la letra de la firma / alto de la miniatura
GRAIN_SEED = 7            # misma textura en todos los renders: reintentos idénticos


def badge_options(raw):
    """Valida ``visual.thumbnail_badges``; devuelve la configuración completa."""
    if type(raw) is not dict or not set(raw) <= set(DEFAULTS):
        raise ValueError('invalid_thumbnail_badges')
    result = {**DEFAULTS, **raw}
    signature = result['signature']
    if (type(result['advisory']) is not bool
            or type(signature) is not str or len(signature) > 30
            or any(ord(c) < 32 for c in signature)
            or type(result['font']) is not str or result['font'] not in FONTS):
        raise ValueError('invalid_thumbnail_badges')
    for key, top in (('grain', .3), ('vignette', .8)):
        value = result[key]
        if type(value) not in (int, float) or not 0 <= value <= top:
            raise ValueError('invalid_thumbnail_badges')
        result[key] = float(value)
    return result


def advisory_label(width):
    """Parental Advisory oficial (PNG de Wikimedia Commons, dominio público) escalado a ``width``."""
    from PIL import Image
    with Image.open(ADVISORY) as source:
        label = source.convert('RGB')
    return label.resize((width, round(label.height * width / label.width)), Image.LANCZOS)


def signature_layer(text, font_key, height):
    """Firma blanca con sombra suave, en RGBA recortada a su contenido."""
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    font = ImageFont.truetype(str(FONT_DIR / FONTS[font_key]), height)
    probe = ImageDraw.Draw(Image.new('L', (1, 1)))
    x0, y0, x1, y1 = probe.textbbox((0, 0), text, font=font)
    pad = max(6, height // 4)
    size = (x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)
    mask = Image.new('L', size, 0)
    ImageDraw.Draw(mask).text((pad - x0, pad - y0), text, font=font, fill=255)
    shadow = mask.filter(ImageFilter.GaussianBlur(max(2, height // 12))).point(lambda v: round(v * .75))
    layer = Image.new('RGBA', size, (0, 0, 0, 0))
    layer.putalpha(shadow)
    white = Image.new('RGBA', size, (255, 255, 255, 0))
    white.putalpha(mask)
    return Image.alpha_composite(layer, white)


def texture(picture, grain, vignette):
    """Viñeta elíptica centrada en la foto y grano monocromo; las franjas quedan negras."""
    import numpy as np
    from PIL import Image
    from core.beat_thumb_logo import BAR_SHARE
    pixels = np.asarray(picture, dtype=np.float32)
    height, width = pixels.shape[:2]
    if vignette:
        half_w = width * (1 - 2 * BAR_SHARE) / 2
        ys, xs = np.mgrid[0:height, 0:width]
        r = np.sqrt(((xs - width / 2) / half_w) ** 2 + ((ys - height / 2) / (height / 2)) ** 2) / np.sqrt(2)
        falloff = np.clip((r - .35) / .65, 0, 1) ** 1.6
        pixels *= (1 - vignette * falloff)[..., None]
    if grain:
        noise = np.random.default_rng(GRAIN_SEED).normal(0, 255 * grain, (height, width))
        pixels += noise[..., None] * (pixels.mean(axis=2, keepdims=True) > 4)
    return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), 'RGB')


def apply_badges(thumbnail, settings):
    """Aplica textura, Parental Advisory y firma a ``thumbnail`` (JPEG fixed_bars), en su lugar."""
    from PIL import Image
    try:
        with Image.open(thumbnail) as source:
            picture = source.convert('RGB')
    except Exception:
        raise BeatError('image_decode_failed') from None
    picture = texture(picture, settings['grain'], settings['vignette'])
    if settings['advisory']:
        label = advisory_label(round(picture.width * ADVISORY_SHARE))
        picture.paste(label, place(picture.size, label.size, 'bottom_left'))
    if settings['signature'].strip():
        layer = signature_layer(settings['signature'], settings['font'], round(picture.height * SIGNATURE_SHARE))
        # El acolchado de la sombra no cuenta para el margen.
        pad = max(6, round(picture.height * SIGNATURE_SHARE) // 4)
        x, y = place(picture.size, (layer.width - 2 * pad, layer.height - 2 * pad), 'top_right')
        picture.paste(layer, (x - pad, y - pad), layer)
    picture.save(thumbnail, 'JPEG', quality=90)
