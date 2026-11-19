"""Nombre del beat en cursiva arriba y al centro: PNG transparente hecho con PIL
(sin depender de libfreetype en FFmpeg) que la pasada final superpone con fundidos."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

FONT_DIR = Path(__file__).resolve().parent.parent / 'assets' / 'fonts'
# Fuentes OFL de Google Fonts; licencias junto a cada archivo en assets/fonts.
FONTS = {'great_vibes': 'GreatVibes-Regular.ttf', 'dancing_script': 'DancingScript-Variable.ttf',
         'kaushan_script': 'KaushanScript-Regular.ttf'}
MAX_WIDTH = 1700
FADE = 1


def title_options(raw):
    """``{font, size, y}``: ``y`` es el borde superior del texto en un cuadro de 1920x1080,
    o ``'center'`` para centrarlo también en vertical."""
    if type(raw) is not dict or not set(raw) <= {'font', 'size', 'y'} or 'font' not in raw:
        raise ValueError('invalid_title_overlay')
    result = {'size': 96, 'y': 60, **raw}
    if (type(result['font']) is not str or result['font'] not in FONTS
            or type(result['size']) is not int or not 32 <= result['size'] <= 220
            or not (result['y'] == 'center' if type(result['y']) is str
                    else type(result['y']) is int and 0 <= result['y'] <= 800)):
        raise ValueError('invalid_title_overlay')
    return result


def create_title(text, options, path):
    """Blanco con sombra suave; achica la fuente si el nombre no entra en MAX_WIDTH."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError('invalid_title_text')
    text = ' '.join(text.split())[:80].rstrip()
    size = options['size']
    while True:
        font = ImageFont.truetype(str(FONT_DIR / FONTS[options['font']]), size)
        left, top, right, bottom = font.getbbox(text)
        if right - left <= MAX_WIDTH or size <= 24:
            break
        size -= 4
    x = (1920 - (right - left)) // 2 - left
    y = (1080 - (bottom - top)) // 2 - top if options['y'] == 'center' else options['y'] - top
    shadow = Image.new('RGBA', (1920, 1080), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((x + 3, y + 5), text, font=font, fill=(0, 0, 0, 190))
    layer = shadow.filter(ImageFilter.GaussianBlur(7))
    ImageDraw.Draw(layer).text((x, y), text, font=font, fill=(255, 255, 255, 255))
    layer.save(path)
    return path


def overlay_inputs(path):
    return ['-loop', '1', '-framerate', '30', '-protocol_whitelist', 'file',
            '-f', 'image2', '-c:v', 'png', '-i', str(path)]


def overlay_chain(base, index, start, seconds):
    """Grafo que funde el título (entrada ``index``) sobre ``[base]`` entre ``start`` y el final."""
    end = max(start, seconds - FADE)
    return (f'[{index}:v:0]format=rgba,fade=t=in:st={start}:d={FADE}:alpha=1,'
            f'fade=t=out:st={end}:d={FADE}:alpha=1[title];'
            f'[{base}][title]overlay=0:0:format=auto:shortest=1,format=yuv420p[v]')
