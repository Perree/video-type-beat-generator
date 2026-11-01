# -*- coding: utf-8 -*-
"""Fondo de portada generado con IA a partir de imágenes de referencia por género.

``background`` elige 1-2 referencias que no se usaron en los últimos días, las manda como
entrada de edición a una API de imágenes estilo OpenAI (``/images/edits``, urllib) y guarda
el resultado en disco. ``for_video`` es la entrada del worker: con ``cover_mode: auto`` usa
ese fondo y, si la API rechaza la referencia o falla, vuelve a la imagen manual del pack y
avisa por Telegram sin cortar la corrida.

``cover_mode: dropbox`` no usa IA: cada video toma una imagen de Dropbox del género
(``<refs_root>/<genero>/fondos/`` o, si no hay, la carpeta del género), rotando. Es también
el respaldo cuando la IA falla (``for_cover``).

El prompt describe solo estética y nunca lleva el nombre del kit ni el de las referencias.
La clave viaja solo en el header Authorization: no se imprime ni aparece en los errores.
Se hace un único pedido por video (sin reintentos: cada pedido se cobra).
"""
import base64
import colorsys
import hashlib
import io
import json
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.request
import uuid
from datetime import date, datetime
from functools import partial

from PIL import Image, ImageEnhance, ImageOps

from core import dropbox_client, kit_cloud, kit_http, kit_llm, kit_notify, kit_source, kit_spend

ENV_KEY = 'KIT_IMAGE_API_KEY'
MODE_AUTO, MODE_MANUAL = 'auto', 'manual'
MODE_TEMPLATE = 'template'  # portada completa a partir de un modelo y un fondo (kit_template_art)
MODE_DROPBOX = 'dropbox'    # sin IA: una imagen de Dropbox del género, rotando
BACKGROUNDS_DIR = 'fondos'  # subcarpeta del género con las imágenes a usar tal cual
DEFAULTS = {
    'base_url': 'https://api.openai.com/v1',
    'model': 'gpt-image-1',
    'size': '1024x1024',
    'timeout': 180,
    'ref_cooldown_days': 30,
    'refs_per_video': 2,       # tope; se usan entre 1 y este número
    'ref_max_side': 1536,      # las referencias se achican antes de enviarlas
}
OUT_NAME = 'kit_art.png'

# Estética por género (se puede pisar o ampliar con ``styles`` en la config).
STYLES = {
    'reggaeton house': {
        'palette': 'warm sunset orange, magenta and deep teal',
        'motifs': ['neon haze', 'palm silhouettes', 'wet street reflections at night'],
        'colors': ['#e8662a', '#0f4c5c'],
    },
    'guitarras': {
        'palette': 'faded amber, dusty brown and muted olive',
        'motifs': ['worn wooden textures', 'soft window light', 'dust floating in the air'],
        'colors': ['#b07a3a', '#3d3a24'],
    },
}
DEFAULT_STYLE = {
    'palette': 'muted warm tones with deep shadows',
    'motifs': ['soft light leaks', 'abstract out of focus shapes'],
}

_PROMPT = (
    "Create a square abstract background image for a music cover. Use the reference images "
    "only for mood: color palette, lighting, texture and composition. Palette: {palette}. "
    "Motifs: {motifs}. Analog film grain, soft bokeh, shallow depth of field, cinematic light, "
    "slightly underexposed, with a calm center that leaves room for a title added later. "
    "No text, letters, numbers, logos, watermarks or signatures anywhere. No people, faces or "
    "bodies, and do not reproduce the likeness of any real person, even if one appears in a "
    "reference image: replace any person with scenery or abstract shapes.")

_FALLBACK_TEXT = ("Loop kits: no se pudo generar el fondo con IA ({}). "
                  "Los videos salen con una imagen de Dropbox del género (o la del kit).")
FREE_NAME = 'kit_free.png'
FREE_SIZE = 1024
_API_FAILED = 'api_failed'  # motivo de aviso (uno por corrida) cuando la IA falla


class KitArtError(Exception):
    # Un fallo que no deja claro si la API llegó a cobrar se cuenta como cobrado.
    billable = True


class KitArtRejected(KitArtError):
    """La API rechazó el pedido (referencia o prompt no aceptados)."""
    billable = False


class KitArtConfig(KitArtError):
    """Falta algo de la config o la clave: el pedido no llegó a salir."""
    billable = False


class KitArtBudget(KitArtConfig):
    """El tope de gasto no deja hacer el pedido. ``reason`` es un ``kit_spend.REASON_*``."""

    def __init__(self, reason):
        super().__init__(kit_spend.REASON_TEXT.get(reason, 'tope de gasto'))
        self.reason = reason


def charged_call(client, prompt, images, cfg, budget):
    """Un pedido a la API de imágenes con el tope antes y el gasto anotado después.

    Devuelve los bytes de la imagen. Con ``budget`` en None no controla nada. Si no está claro
    que la API no cobró (timeout, 5xx), el pedido se cuenta como cobrado.
    """
    if budget is None:
        return client(prompt, images, cfg)
    count = image_count(cfg)
    cost = budget.image_cost(count)
    reason = budget.blocked(cost, images=count)
    if reason:
        raise KitArtBudget(reason)
    try:
        data = client(prompt, images, cfg)
    except Exception as exc:
        if getattr(exc, 'billable', True):
            budget.charge(cost, images=count)
        raise
    budget.charge(cost, images=count)
    return data


# --- Referencias ---

def _norm(text):
    text = unicodedata.normalize('NFKD', str(text or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return ' '.join(text.casefold().replace('_', ' ').split())


def _ref_path(ref):
    return ref['path'] if isinstance(ref, dict) else str(ref)


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _days_since(value, today):
    """Días desde el último uso. Una fecha ilegible cuenta como usada hoy."""
    used = _as_date(value)
    return 0 if used is None else (today - used).days


def genre_folder(refs_root, genre):
    """Carpeta de referencias del género: ``<refs_root>/<genero_en_minusculas_con_guiones_bajos>``."""
    return f"{(refs_root or '').rstrip('/')}/{_norm(genre).replace(' ', '_')}"


def list_refs(refs_root, genre, dbx=None):
    """Imágenes de la carpeta de referencias del género: ``[{name, path}]``."""
    return [{'name': e['name'], 'path': e['path']}
            for e in dropbox_client.list_folder_entries(genre_folder(refs_root, genre), dbx=dbx)
            if not e['is_folder'] and dropbox_client.is_image(e['name'])]


def used_refs(state):
    """Último uso de cada referencia según las corridas del estado: ``{path: iso}``."""
    last = {}
    for run in (state or {}).get('runs') or []:
        when = run.get('subido_en') or ''
        for path in run.get('ref_images') or []:
            if when > last.get(path, ''):
                last[path] = when
    return last


def choose_refs(refs, used, rng, now=None, cooldown_days=30, max_refs=2):
    """Elige 1..``max_refs`` referencias sin uso en los últimos ``cooldown_days`` días.

    Args:
        refs: lista de ``{name, path}`` o de rutas.
        used: ``{path: fecha del último uso}`` (ISO, date o datetime).

    Returns:
        ``(elegidas, warnings)``. Si no queda ninguna libre se relaja la regla: va la que
        hace más que no se usa, con un warning. Los plazos se cuentan por fecha de calendario.
    """
    paths = sorted({_ref_path(r) for r in refs or []})
    if not paths:
        raise KitArtError("No hay imágenes de referencia para el género.")
    today = (now or datetime.now()).date()
    used = used or {}
    age = {p: _days_since(used[p], today) for p in paths if p in used}
    fresh = [p for p in paths if p not in age or age[p] >= cooldown_days]
    want = rng.randint(1, max(1, int(max_refs)))
    if fresh:
        return sorted(rng.sample(fresh, min(want, len(fresh)))), []
    oldest = max(paths, key=lambda p: (age[p], p))
    return [oldest], [f"Todas las referencias del género se usaron en los últimos "
                      f"{cooldown_days} días: se repite la más antigua."]


# --- Prompt ---

def _banned_words(kit, extra=()):
    name = kit.get('name') if isinstance(kit, dict) else kit
    words = set()
    for text in [name, *(extra or [])]:
        words.update(w for w in re.split(r'[^a-z0-9]+', _norm(text)) if len(w) >= 3)
    return words


def _clean_terms(values, banned):
    """Términos de estética en minúsculas, solo letras; fuera los que traen una palabra vetada."""
    if isinstance(values, str):
        values = values.split(',')
    terms = []
    for value in values or []:
        term = ' '.join(re.sub(r'[^a-z -]', ' ', _norm(value)).split())[:60]
        if term and not (set(re.split(r'[ -]+', term)) & banned) and term not in terms:
            terms.append(term)
    return terms


def _style(genre, styles):
    table = {_norm(k): v for k, v in {**STYLES, **(styles or {})}.items()}
    key = _norm(genre)
    if key in table:
        return table[key]
    return next((v for k, v in sorted(table.items()) if k and k in key), DEFAULT_STYLE)


def build_prompt(kit, genre, cfg=None):
    """Prompt de solo estética: paleta y motivos del género más los ``motifs`` del kit.

    El nombre del kit nunca entra: solo sirve para descartar motivos que lo contengan
    (igual que ``banned_words`` de la config). Sin texto en la imagen y sin personas.
    """
    cfg = cfg or {}
    banned = _banned_words(kit, cfg.get('banned_words'))
    style = _style(genre, cfg.get('styles'))
    kit_motifs = kit.get('motifs') if isinstance(kit, dict) else None
    palette = _clean_terms(style.get('palette'), banned) or _clean_terms(
        DEFAULT_STYLE['palette'], set())
    motifs = _clean_terms(list(style.get('motifs') or []) + list(kit_motifs or []), banned)
    motifs = motifs or _clean_terms(DEFAULT_STYLE['motifs'], set())
    return _PROMPT.format(palette=', '.join(palette), motifs=', '.join(motifs))


# --- API de imágenes ---

def _read_key(cfg):
    key = kit_cloud.secret(ENV_KEY)
    if key:
        return key
    try:
        return kit_llm.read_key(cfg)
    except kit_llm.KitLlmError:
        raise KitArtConfig("No hay clave para la API de imágenes.") from None


def _multipart(fields, images):
    boundary = uuid.uuid4().hex
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        .encode('utf-8') for name, value in fields.items()]
    field = 'image[]' if len(images) > 1 else 'image'
    for i, path in enumerate(images):
        with open(path, 'rb') as f:
            data = f.read()
        # Nombre genérico: el del archivo original no sale de esta máquina.
        parts.append(
            (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; '
             f'filename="ref{i}.png"\r\nContent-Type: image/png\r\n\r\n').encode('utf-8')
            + data + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode('utf-8'))
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def image_count(cfg):
    """Imágenes que se piden por llamada (``n``; 1 si falta o no es válido)."""
    try:
        return max(1, int((cfg or {}).get('n') or 1))
    except (TypeError, ValueError):
        return 1


def api_client(prompt, image_paths, cfg=None, key=None):
    """Pide una edición a ``<base_url>/images/edits`` y devuelve los bytes de la imagen.

    ``cfg``: ``base_url`` (https, host permitido por ``kit_llm.check_base_url``), ``model``,
    ``size``, opcionales ``quality``, ``input_fidelity``, ``n``, ``timeout`` y ``key_file``.
    Las imágenes van en el orden recibido y siempre se usa la primera respuesta.
    La clave sale de ``key``, de
    ``KIT_IMAGE_API_KEY`` o, solo fuera de la nube, de ``key_file``.
    Un solo intento. HTTP 400 → KitArtRejected; cualquier otro fallo → KitArtError.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    try:
        # Mismo control que el LLM: la clave solo sale hacia un host permitido.
        base_url = kit_llm.check_base_url(cfg['base_url'], 'de la API de imágenes')
    except kit_llm.KitLlmError as e:
        raise KitArtConfig(str(e)) from None
    key = key or _read_key(cfg)
    fields = {'model': cfg['model'], 'prompt': prompt, 'n': image_count(cfg)}
    for name in ('size', 'quality', 'input_fidelity'):
        if cfg.get(name):
            fields[name] = cfg[name]
    body, ctype = _multipart(fields, image_paths)
    req = urllib.request.Request(
        base_url + '/images/edits', data=body,
        headers={'Content-Type': ctype, 'Authorization': f'Bearer {key}'})
    try:
        with kit_http.open_request(req, timeout=cfg['timeout']) as resp:
            item = json.loads(kit_http.read_response(resp).decode('utf-8'))['data'][0]
        if item.get('b64_json'):
            data = base64.b64decode(item['b64_json'], validate=True)
            if len(data) > kit_http.IMAGE_LIMIT:
                raise kit_http.HttpRejected('response_limit')
            return data
        url = kit_http.image_url(item.get('url') or '', base_url)
        # A fresh request never forwards the provider's Authorization header.
        with kit_http.open_request(urllib.request.Request(url), timeout=cfg['timeout']) as resp:
            return kit_http.read_response(resp, kit_http.IMAGE_LIMIT)
    except urllib.error.HTTPError as e:
        # Solo el código: el cuerpo y las cabeceras no van a ningún mensaje.
        if e.code == 400:
            raise KitArtRejected("La API de imágenes rechazó el pedido (HTTP 400).") from None
        error = KitArtError(f"La API de imágenes falló (HTTP {e.code}).")
        error.billable = not 400 <= e.code < 500   # un 4xx no llega a generar nada
        raise error from None
    except Exception as e:
        raise KitArtError(f"La API de imágenes no respondió ({type(e).__name__}).") from None


def _prepare_ref(src, dest, max_side):
    """Copia la referencia como PNG achicado y sin metadatos."""
    with Image.open(src) as img:
        img = img.convert('RGB')
        img.thumbnail((max_side, max_side), Image.LANCZOS)
        img.save(dest, 'PNG')
    return dest


def background(kit, genre, refs, used, rng, client=None, *, cfg=None, out_dir=None,
               now=None, fetch=None, dbx=None, report=None, budget=None):
    """Genera el fondo de un video y devuelve la ruta local del PNG.

    Args:
        kit: nombre del kit o ``{'name', 'motifs'}``. El nombre no entra en el prompt.
        genre: género (elige la estética de ``STYLES`` / ``cfg['styles']``).
        refs: referencias del género, ``[{name, path}]`` (ver ``list_refs``).
        used: ``{path: fecha del último uso}`` (ver ``used_refs``).
        rng: ``random.Random``.
        client: ``client(prompt, image_paths, cfg) -> bytes``; por defecto ``api_client``.
        cfg: ``kit_preview.art`` (API, ``ref_cooldown_days``, ``refs_per_video``, ``styles``).
        out_dir: dónde dejar el PNG; por defecto un directorio temporal que borra el llamador.
        fetch: ``fetch(paths, dest_dir) -> rutas locales``; por defecto baja de Dropbox.
        report: dict opcional que recibe ``refs`` (rutas elegidas), ``warnings`` y ``prompt``.
        budget: ``kit_spend.Budget``; si viene, el pedido respeta el tope y se anota el gasto.

    Raises:
        KitArtBudget si el tope no deja hacer el pedido; KitArtRejected si la API rechaza el
        pedido; KitArtError ante cualquier otro fallo.
        Las referencias descargadas se borran siempre.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    chosen, warnings = choose_refs(
        refs, used, rng, now=now, cooldown_days=int(cfg['ref_cooldown_days']),
        max_refs=int(cfg['refs_per_video']))
    prompt = build_prompt(kit, genre, cfg)
    if report is not None:
        report.update(refs=chosen, warnings=warnings, prompt=prompt)
    client = client or api_client
    fetch = fetch or partial(kit_source.download_pack_files, dbx=dbx)
    with tempfile.TemporaryDirectory(prefix='kit_art_refs_') as tmp:
        try:
            local = fetch(chosen, os.path.join(tmp, 'raw'))
            prepared = [_prepare_ref(src, os.path.join(tmp, f'ref{i}.png'),
                                     int(cfg['ref_max_side']))
                        for i, src in enumerate(local)]
        except Exception as e:
            raise KitArtError(
                f"No se pudieron preparar las referencias ({type(e).__name__}).") from None
        data = charged_call(client, prompt, prepared, cfg, budget)
    try:
        img = Image.open(io.BytesIO(data)).convert('RGB')
    except Exception:
        raise KitArtError("La API de imágenes no devolvió una imagen válida.") from None
    out_dir = out_dir or tempfile.mkdtemp(prefix='kit_art_')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, OUT_NAME)
    img.save(out, 'PNG')
    return out


# --- Entrada del worker ---

def mode(kit_cfg):
    """``auto``, ``template`` o ``dropbox`` si ``kit_preview.cover_mode`` lo dice; si no, manual."""
    value = str((kit_cfg or {}).get('cover_mode') or '').strip().lower()
    return value if value in (MODE_AUTO, MODE_TEMPLATE, MODE_DROPBOX) else MODE_MANUAL


def generates(kit_cfg):
    """True si la portada no sale del pack (IA o Dropbox): el kit no necesita imágenes propias."""
    return mode(kit_cfg) != MODE_MANUAL


def _warn(notify, text):
    try:
        (notify or kit_notify.send)(text)
    except Exception as exc:
        print(f"Aviso por Telegram no enviado ({type(exc).__name__}).")


def for_video(kit_cfg, kit, fallback_image, store, rng, work_dir, dbx=None, client=None,
              notify=None, now=None, budget=None):
    """Fondo del video: ``(ruta, referencias usadas)``.

    Con ``cover_mode`` manual (o sin la clave) devuelve ``(fallback_image, [])`` sin llamar a
    nada. En auto genera el fondo con las referencias del género (``art.genre`` o, si falta,
    ``names.genre``) bajo ``art.refs_root``. Si la API rechaza la referencia o algo falla, ese
    video cae a manual: devuelve ``(fallback_image, [])`` y avisa por Telegram (``notify(text)``,
    por defecto ``kit_notify.send``); nunca levanta. El aviso no lleva nombres ni mensajes de error.
    El uso previo sale de ``store.ref_usage()`` si el store lo tiene. Respeta el tope de gasto
    (``kit_spend``): sin ``budget`` usa uno de la config y del estado del ``store``; al llegar
    al tope ese video sale con la imagen manual y el aviso se manda una sola vez por corrida.
    """
    if mode(kit_cfg) != MODE_AUTO:
        return fallback_image, []
    art = kit_cfg.get('art') or {}
    genre = str(art.get('genre') or (kit_cfg.get('names') or {}).get('genre') or '').strip()
    budget = budget or kit_spend.Budget(kit_spend.settings(kit_cfg), store, now)
    report = {}
    try:
        if not genre or not art.get('refs_root'):
            raise KitArtError("Falta art.refs_root o el género en la config.")
        refs = list_refs(art['refs_root'], genre, dbx=dbx)
        usage = getattr(store, 'ref_usage', None)
        path = background(kit, genre, refs, usage() if usage else {}, rng, client,
                          cfg=art, out_dir=work_dir, now=now, dbx=dbx, report=report,
                          budget=budget)
    except Exception as exc:
        if isinstance(exc, KitArtBudget):
            reason, once = str(exc), exc.reason
        else:
            reason, once = ('pedido rechazado' if isinstance(exc, KitArtRejected)
                            else type(exc).__name__), _API_FAILED
        print(f"Fondo con IA no generado ({reason}); se usa una imagen de Dropbox (o la del kit).")
        if once not in budget.notified:
            if once:
                budget.notified.add(once)
            _warn(notify, _FALLBACK_TEXT.format(reason))
        return fallback_image, []
    for warning in report.get('warnings') or []:
        print(f"warning: {warning}")
    return path, list(report.get('refs') or [])


def for_cover(kit_cfg, kit, title, fallback_image, store, rng, work_dir, dbx=None, client=None,
              notify=None, now=None, budget=None, verify=None):
    """Imagen de portada del video: ``(ruta, referencias usadas, completa)``.

    - ``manual``: la imagen del pack (``fallback_image``).
    - ``dropbox``: una imagen de Dropbox del género, tal cual, rotando (sin IA ni costo).
    - ``auto``: fondo con IA al que el compositor le pone el título.
    - ``template``: la API devuelve la portada ya terminada con ``title`` (``completa`` True).

    Si la IA falla, se rechaza o se llega al tope de gasto, ese video sale con una imagen de
    Dropbox del género; si no hay, con la del pack; si tampoco, con un degradado. Así un fallo
    de la IA (sin saldo, clave vencida) nunca deja la corrida sin videos.
    """
    current = mode(kit_cfg)
    if current == MODE_MANUAL:
        return fallback_image, [], False
    path, refs, complete = None, [], False
    if current == MODE_AUTO:
        path, refs = for_video(kit_cfg, kit, None, store, rng, work_dir, dbx=dbx,
                               client=client, notify=notify, now=now, budget=budget)
    elif current == MODE_TEMPLATE:
        from core import kit_template_art
        path, refs, complete = kit_template_art.for_video(
            kit_cfg, title, None, store, rng, work_dir, dbx=dbx, client=client,
            notify=notify, now=now, budget=budget, verify=verify)
    if path:
        return path, refs, complete
    path, refs = dropbox_image(kit_cfg, store, rng, work_dir, dbx=dbx, now=now)
    if path:
        return path, refs, False
    if fallback_image:
        return fallback_image, [], False
    path, refs = free_background(kit_cfg, store, rng, work_dir, dbx=dbx, now=now)
    return path, refs, False


# --- Respaldo sin IA ---

def _hex_rgb(value):
    text = str(value or '').strip().lstrip('#')
    if not re.fullmatch(r'[0-9a-fA-F]{6}', text):
        return None
    return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))


def genre_colors(genre, styles=None):
    """Dos colores RGB del género: ``colors`` del estilo o, si faltan, unos fijos por nombre."""
    style = _style(genre, styles) if genre else DEFAULT_STYLE
    colors = [c for c in (_hex_rgb(v) for v in style.get('colors') or []) if c]
    if len(colors) >= 2:
        return colors[0], colors[1]
    # Sin colores en el estilo: un tono estable derivado del nombre del género.
    hue = int(hashlib.sha256(_norm(genre).encode('utf-8')).hexdigest()[:8], 16) / 0xFFFFFFFF
    light = colorsys.hsv_to_rgb(hue, 0.65, 0.75)
    dark = colorsys.hsv_to_rgb((hue + 0.12) % 1.0, 0.7, 0.22)
    return (tuple(int(c * 255) for c in light), tuple(int(c * 255) for c in dark))


def gradient_background(genre, dest, styles=None, rng=None, size=FREE_SIZE):
    """Fondo cuadrado en degradado con los colores del género, grano suave y viñeta."""
    first, second = genre_colors(genre, styles)
    if rng is not None and rng.random() < 0.5:
        first, second = second, first
    # Máscara el doble de grande, girada y recortada al centro: sin esquinas vacías.
    mask = Image.linear_gradient('L').resize((size * 2, size * 2))
    if rng is not None:
        mask = mask.rotate(rng.choice((0, 45, 90, 135, 180, 225, 270, 315)),
                           resample=Image.BICUBIC)
    mask = mask.crop((size // 2, size // 2, size // 2 + size, size // 2 + size))
    img = Image.composite(Image.new('RGB', (size, size), second),
                          Image.new('RGB', (size, size), first), mask)
    grain = Image.effect_noise((size, size), 18).convert('RGB')
    img = Image.blend(img, grain, 0.06)
    _vignette(img).save(dest, 'PNG')
    return dest


def _vignette(img):
    """Oscurece los bordes: el centro queda limpio para el título."""
    edge = Image.radial_gradient('L').resize(img.size)          # 0 en el centro, 255 en el borde
    edge = edge.point(lambda v: int(v * 0.45))
    return Image.composite(Image.new('RGB', img.size, (0, 0, 0)), img, edge)


def _prepare_cover(src, dest, size=FREE_SIZE):
    """Recorta al cuadrado y oscurece apenas los bordes (lugar para el título); PNG sin metadatos."""
    with Image.open(src) as raw:
        img = ImageOps.fit(ImageOps.exif_transpose(raw).convert('RGB'), (size, size),
                           Image.LANCZOS)
    img = ImageEnhance.Brightness(img).enhance(0.85)
    _vignette(img).save(dest, 'PNG')
    return dest


def _images(entries):
    return [{'name': e['name'], 'path': e['path']}
            for e in entries if not e['is_folder'] and dropbox_client.is_image(e['name'])]


def dropbox_candidates(art, genre, dbx=None):
    """Imágenes de Dropbox para la portada sin IA.

    Las de ``<refs_root>/<genero>/fondos/`` si esa subcarpeta tiene alguna; si no, las de la
    carpeta del género (las mismas referencias que usa la IA).
    """
    # ``art.backgrounds_folder``: carpeta fija del canal (se ignora el género).
    folder = str(art.get('backgrounds_folder') or '').rstrip('/') or genre_folder(art['refs_root'], genre)
    entries = dropbox_client.list_folder_entries(folder, dbx=dbx)
    sub = str(art.get('backgrounds_dir') or BACKGROUNDS_DIR).strip('/')
    if any(e['is_folder'] and e['name'].casefold() == sub.casefold() for e in entries):
        found = _images(dropbox_client.list_folder_entries(f"{folder}/{sub}", dbx=dbx))
        if found:
            return found
    return _images(entries)


def dropbox_image(kit_cfg, store, rng, work_dir, dbx=None, now=None, fetch=None):
    """Portada sin IA con una imagen de Dropbox del género: ``(ruta, [imagen usada])``.

    Rota igual que las referencias de la IA: no repite una usada en los últimos
    ``ref_cooldown_days`` días mientras haya otras. Sin config, sin imágenes o si Dropbox
    falla devuelve ``(None, [])``; nunca levanta.
    """
    kit_cfg = kit_cfg or {}
    art = kit_cfg.get('art') or {}
    genre = str(art.get('genre') or (kit_cfg.get('names') or {}).get('genre') or '').strip()
    if not genre or not art.get('refs_root'):
        return None, []
    try:
        images = dropbox_candidates(art, genre, dbx)
        if not images:
            print("Portada sin IA: no hay imágenes del género en Dropbox.")
            return None, []
        usage = getattr(store, 'ref_usage', None)
        cooldown = int({**DEFAULTS, **art}['ref_cooldown_days'])
        chosen, _ = choose_refs(images, usage() if usage else {}, rng, now=now,
                                cooldown_days=cooldown, max_refs=1)
        chosen = chosen[:1]
        os.makedirs(work_dir, exist_ok=True)
        out = os.path.join(work_dir, FREE_NAME)
        with tempfile.TemporaryDirectory(prefix='kit_free_') as tmp:
            local = (fetch or partial(kit_source.download_pack_files, dbx=dbx))(chosen, tmp)
            _prepare_cover(local[0], out)
    except Exception as exc:
        print(f"Portada sin IA: no se pudo usar una imagen de Dropbox ({type(exc).__name__}).")
        return None, []
    print("Portada sin IA: imagen de Dropbox del género.")
    return out, chosen


def free_background(kit_cfg, store, rng, work_dir, dbx=None, now=None, fetch=None):
    """Fondo sin IA y sin costo: ``(ruta, referencias usadas)``. Nunca levanta.

    Primero una imagen de Dropbox del género (``dropbox_image``); si no hay ninguna o no se
    puede bajar, un degradado con los colores del género.
    """
    path, chosen = dropbox_image(kit_cfg, store, rng, work_dir, dbx=dbx, now=now, fetch=fetch)
    if path:
        return path, chosen
    kit_cfg = kit_cfg or {}
    art = kit_cfg.get('art') or {}
    genre = str(art.get('genre') or (kit_cfg.get('names') or {}).get('genre') or '').strip()
    os.makedirs(work_dir, exist_ok=True)
    out = os.path.join(work_dir, FREE_NAME)
    gradient_background(genre, out, art.get('styles'), rng)
    print("Portada sin IA: degradado con los colores del género.")
    return out, []
