"""Test A/B de miniaturas con y sin logo (prodbySSJBeatzz).

``visual.thumbnail_logo = {logo, cycle: [con, sin], corner?}``: las primeras ``con``
subidas del canal llevan el logo, las ``sin`` siguientes no, y el ciclo se repite.
El número de subida es la cantidad de subidas ``uploaded`` previas del canal al
renderizar por primera vez; se congela en ``job['thumbnail_snapshot']`` para que un
reintento del mismo job vuelva a usar la misma variante.

El logo (cromado sobre negro) se limpia como en la intro (fondo -> negro puro), se
escala a ~24 % del ancho y se mezcla en modo ``screen``: el negro no tapa la foto.
"""
from core.beat_download import dropbox_path
from core.beat_http import BeatError

VARIANTS = ('logo', 'sin_logo')
CORNERS = ('top_left', 'top_right', 'bottom_left', 'bottom_right')
# Arriba a la izquierda: en las fotos de recital suele ser fondo; abajo choca con el sujeto.
DEFAULT_CORNER = 'top_left'
SHADOW = .55             # oscurecimiento máximo bajo el logo (contraste en zonas claras)
LOGO_SHARE = .24          # ancho del logo / ancho de la miniatura
MARGIN_SHARE = .03        # margen a los bordes / ancho de la miniatura
# fixed_bars deja franjas negras de 344/1920 del ancho: el margen se mide desde la foto.
BAR_SHARE = 344 / 1920


def logo_options(raw):
    """Valida ``visual.thumbnail_logo``; devuelve None si no hay test."""
    if raw is None:
        return None
    if not isinstance(raw, dict) or set(raw) - {'logo', 'cycle', 'corner'}:
        raise ValueError('invalid_thumbnail_logo')
    logo, cycle, corner = raw.get('logo'), raw.get('cycle', [7, 7]), raw.get('corner', DEFAULT_CORNER)
    if not isinstance(logo, str) or not logo:
        raise ValueError('invalid_thumbnail_logo')
    try:
        dropbox_path(logo)
    except BeatError:
        raise ValueError('invalid_thumbnail_logo') from None
    if (not isinstance(cycle, list) or len(cycle) != 2
            or any(type(n) is not int or not 0 <= n <= 100 for n in cycle) or sum(cycle) == 0):
        raise ValueError('invalid_thumbnail_logo')
    if corner not in CORNERS:
        raise ValueError('invalid_thumbnail_logo')
    return {'logo': logo, 'cycle': list(cycle), 'corner': corner}


def variant_for(index, cycle):
    """Variante de la subida número ``index`` (desde 0)."""
    with_logo, without = cycle
    return 'logo' if index % (with_logo + without) < with_logo else 'sin_logo'


def upload_index(state, job):
    """Subidas ya publicadas del canal, sin contar este job."""
    return sum(1 for row in state['jobs'].values()
               if row['channel'] == job['channel'] and row['id'] != job['id']
               and row['status'] == 'uploaded')


def plan(settings, state, job):
    """Snapshot de la miniatura: reutiliza el congelado o calcula uno nuevo."""
    frozen = job.get('thumbnail_snapshot')
    if frozen:
        return dict(frozen)
    index = upload_index(state, job)
    return {'variant': variant_for(index, settings['cycle']), 'upload_index': index}


def prepared_logo(path, width):
    """Logo limpio (negro puro de fondo), recortado y escalado a ``width`` px."""
    from PIL import Image
    from core.beat_intro import prepared_logo as cleaned
    try:
        logo = cleaned(path)
    except BeatError:
        raise BeatError('thumbnail_logo_rejected') from None
    height = round(logo.height * width / logo.width)
    return logo.resize((width, height), Image.LANCZOS)


def place(size, logo_size, corner):
    """Esquina superior izquierda del logo dentro de la foto central (fixed_bars)."""
    width, height = size
    bar = round(width * BAR_SHARE)
    margin = round(width * MARGIN_SHARE)
    x = bar + margin if corner.endswith('left') else width - bar - margin - logo_size[0]
    y = margin if corner.startswith('top') else height - margin - logo_size[1]
    return x, y


def apply_logo(thumbnail, logo_path, corner=DEFAULT_CORNER):
    """Mezcla el logo en ``thumbnail`` (JPEG 1280x720) en modo screen, en su lugar."""
    from PIL import Image, ImageChops, ImageFilter
    try:
        with Image.open(thumbnail) as source:
            picture = source.convert('RGB')
    except Exception:
        raise BeatError('image_decode_failed') from None
    logo = prepared_logo(logo_path, round(picture.width * LOGO_SHARE))
    x, y = place(picture.size, logo.size, corner)
    # Sombra difusa con la forma del logo (con aire alrededor para que no se corte en un
    # rectángulo): oscurece la foto debajo y después se suma el cromado en modo screen.
    pad = 24
    canvas = Image.new('L', (logo.width + 2 * pad, logo.height + 2 * pad), 0)
    canvas.paste(logo.convert('L').point(lambda v: 255 if v > 40 else 0), (pad, pad))
    shade = canvas.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(10))
    shade = shade.point(lambda v: round(v * SHADOW))
    box = (x - pad, y - pad, x + logo.width + pad, y + logo.height + pad)
    region = picture.crop(box)
    region = Image.composite(Image.new('RGB', region.size, 'black'), region, shade)
    lit = Image.new('RGB', region.size, 'black')
    lit.paste(logo, (pad, pad))
    picture.paste(ImageChops.screen(region, lit), box[:2])
    picture.save(thumbnail, 'JPEG', quality=90)
