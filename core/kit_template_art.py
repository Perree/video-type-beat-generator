# -*- coding: utf-8 -*-
"""Portada completa con IA a partir de una portada modelo y un fondo (``cover_mode: template``).

La API de imágenes (``/images/edits``, vía ``kit_art.api_client``) recibe dos imágenes, en
este orden: la portada modelo del género y un fondo. Devuelve la portada cuadrada terminada,
con el título ya escrito; el compositor de ``kit_cover`` no interviene.

En Dropbox, bajo ``art.refs_root``: ``<genero>/modelo.png`` y ``<genero>/fondos/``. Un fondo no
se repite dentro de ``ref_cooldown_days``.

Cada pedido se cobra: antes de cada uno se consulta el tope (``kit_spend``) y después se anota.
No hay reintentos ante un error de la API. El único reintento es cuando un modelo con visión
lee en la portada un título distinto del pedido; si vuelve a fallar se usa esa imagen y se
avisa. La clave viaja solo en el header Authorization y no aparece en mensajes ni avisos, y
los avisos tampoco llevan títulos, nombres de kit ni de archivo.
"""
import base64
import inspect
import io
import json
import os
import tempfile
import unicodedata
import urllib.parse
import urllib.request
from core import kit_http
from functools import partial

from PIL import Image

from core import dropbox_client, kit_art, kit_cloud, kit_llm, kit_notify, kit_source, kit_spend

MARKER = '{titulo}'
OUT_NAME = 'kit_cover_ai.png'
ENV_LLM_KEY = 'KIT_LLM_API_KEY'
IMAGE_EXTENSIONS = ('.png', '.jpg', '.jpeg', '.jfif', '.webp')
DEFAULTS = {
    'base_url': 'https://api.openai.com/v1',
    'model': 'gpt-image-1',
    'size': '1024x1024',
    'quality': 'high',
    'input_fidelity': 'high',
    'n': 1,
    'timeout': 300,
    'ref_cooldown_days': 30,
    'ref_max_side': 1536,
    'model_name': 'modelo',       # archivo de la portada modelo, sin extensión
    'backgrounds_dir': 'fondos',  # subcarpeta con los fondos del género
}
VERIFY_DEFAULTS = {
    'enabled': True,
    'model': 'gpt-4o-mini',
    'timeout': 60,
    'max_side': 768,
    'detail': 'low',
    'max_tokens': 60,
}

DEFAULT_PROMPT = (
    "La imagen 1 es la portada modelo: replicala exacta en composición, tipografía, logos, "
    "sellos, código de barras y textura del borde. La imagen 2 es el nuevo fondo y sujeto. "
    "Cambiá solo dos cosas: el fondo y sujeto, que salen de la imagen 2, y el título grande, "
    "que ahora es \"{titulo}\". Escribí ese título exacto, tal como está entre comillas, "
    "respetando ortografía, mayúsculas, números y símbolos, con la misma tipografía y estilo "
    "del modelo, y escalalo para que entre completo y con margen. Mantené igual todo el texto "
    "chico del modelo. No agregues texto extra ni marcas de agua, no dejes texto mal escrito "
    "y no hagas un fondo ancho desenfocado. Salida cuadrada 1:1.")

_VERIFY_PROMPT = (
    "Read the large main title printed on this cover image. Reply with only that title, "
    "exactly as written, with no quotes and no other words.")
_QUOTES = '"\'“”‘’«»`'

_FALLBACK_TEXT = ("Loop kits: no se generó la portada con IA ({}). "
                  "Los videos salen con la imagen del kit o con una portada sin IA.")
_REVIEW_TEXT = ("Loop kits: el título de una portada generada no coincide con el pedido, "
                "incluso después de un reintento. Se usó igual: revisala antes de programar "
                "el video.")
_REVIEW_NO_RETRY_TEXT = ("Loop kits: el título de una portada generada no coincide con el "
                         "pedido y el reintento no se pudo hacer ({}). Se usó la primera "
                         "imagen: revisala antes de programar el video.")


KitArtBudget = kit_art.KitArtBudget


# --- Prompt ---

def render_prompt(template, title):
    """Prompt final: ``{titulo}`` se reemplaza por ``title`` tal cual llega.

    Sin plantilla se usa ``DEFAULT_PROMPT``. Si la plantilla no trae el marcador, el título
    se agrega al final para que nunca falte.
    """
    title = str(title or '')
    if not title.strip():
        raise kit_art.KitArtConfig("Falta el título de la portada.")
    template = str(template or '').strip() or DEFAULT_PROMPT
    if MARKER in template:
        return template.replace(MARKER, title)
    return f'{template}\nTítulo grande, exacto: "{title}"'


def _title_key(text):
    """Letras y números del título, sin acentos, mayúsculas, espacios ni signos (``&`` = ``and``)."""
    text = unicodedata.normalize('NFKC', str(text or '')).strip().strip(_QUOTES)
    text = unicodedata.normalize('NFKD', text.replace('&', ' and '))
    return ''.join(c for c in text.casefold() if c.isalnum() and not unicodedata.combining(c))


def _loose_key(text):
    text = unicodedata.normalize('NFKC', str(text or '')).strip().strip(_QUOTES)
    return ''.join(text.casefold().split())


def titles_match(expected, read):
    """Compara dos títulos sin distinguir mayúsculas, acentos, espacios ni signos.

    El modelo con visión puede leer ``Nuit and Fog`` por ``Nuit & Fog`` o perder un acento: eso
    no justifica generar (y cobrar) otra imagen. Un título sin letras ni números (solo
    símbolos) se compara por su texto, sin distinguir mayúsculas ni espacios.
    """
    key = _title_key(expected)
    if key:
        return key == _title_key(read)
    loose = _loose_key(expected)
    return bool(loose) and loose == _loose_key(read)


# --- Dropbox: portada modelo y fondos ---

def list_folder(folder, dbx=None):
    """Entradas de una carpeta (``name``, ``path``, ``is_folder``), incluidos los ``.jfif``."""
    return [dropbox_client._item_from_entry(e)
            for e in dropbox_client._raw_entries(folder, dbx=dbx)]


def _is_image(name):
    return str(name).lower().endswith(IMAGE_EXTENSIONS)


def find_assets(refs_root, genre, cfg=None, dbx=None):
    """``(ruta de la portada modelo, fondos)`` del género; ``fondos`` es ``[{name, path}]``."""
    cfg = {**DEFAULTS, **(cfg or {})}
    folder = kit_art.genre_folder(refs_root, genre)
    stem = str(cfg['model_name']).casefold()
    models = sorted(
        (e for e in list_folder(folder, dbx=dbx)
         if not e['is_folder'] and _is_image(e['name'])
         and os.path.splitext(e['name'])[0].casefold() == stem),
        key=lambda e: (not e['name'].lower().endswith('.png'), e['name'].lower()))
    if not models:
        raise kit_art.KitArtConfig("Falta la portada modelo del género.")
    backgrounds = [{'name': e['name'], 'path': e['path']}
                   for e in list_folder(f"{folder}/{cfg['backgrounds_dir']}", dbx=dbx)
                   if not e['is_folder'] and _is_image(e['name'])]
    return models[0]['path'], backgrounds


# --- Verificación del título (modelo con visión) ---

def _host(url):
    try:
        return (urllib.parse.urlsplit(str(url or '')).hostname or '').lower()
    except ValueError:
        return ''


def verify_settings(art_cfg):
    """Config de la verificación: ``art.verify`` sobre los defaults y la URL de la API de imágenes."""
    art_cfg = {**DEFAULTS, **(art_cfg or {})}
    raw = art_cfg.get('verify')
    raw = raw if isinstance(raw, dict) else {}
    cfg = {**VERIFY_DEFAULTS, 'base_url': art_cfg['base_url'], **raw}
    # La clave de imágenes solo viaja al mismo host que la API de imágenes.
    cfg['same_host'] = _host(cfg['base_url']) == _host(art_cfg['base_url'])
    if cfg['same_host'] and not cfg.get('key_file'):
        cfg['key_file'] = art_cfg.get('key_file')
    return cfg


def _verify_key(cfg):
    key = kit_cloud.secret(kit_art.ENV_KEY if cfg.get('same_host') else ENV_LLM_KEY)
    if key:
        return key
    try:
        return kit_llm.read_key(cfg)
    except kit_llm.KitLlmError:
        raise kit_art.KitArtConfig("No hay clave para verificar el título.") from None


def vision_client(image_path, cfg, key=None):
    """Devuelve el título que un modelo con visión lee en la portada (chat/completions).

    ``cfg`` es la salida de ``verify_settings``. La imagen se manda achicada y en JPEG.
    Un solo intento; los errores no llevan la URL, las cabeceras ni la respuesta.
    """
    try:
        base_url = kit_llm.check_base_url(cfg.get('base_url'), 'de la verificación')
    except kit_llm.KitLlmError as e:
        raise kit_art.KitArtConfig(str(e)) from None
    key = key or _verify_key(cfg)
    with Image.open(image_path) as img:
        img = img.convert('RGB')
        side = int(cfg.get('max_side') or VERIFY_DEFAULTS['max_side'])
        img.thumbnail((side, side), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, 'JPEG', quality=85)
    data_url = 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode('ascii')
    body = json.dumps({
        'model': cfg['model'],
        'messages': [{'role': 'user', 'content': [
            {'type': 'text', 'text': _VERIFY_PROMPT},
            {'type': 'image_url', 'image_url': {'url': data_url,
                                                'detail': cfg.get('detail') or 'low'}}]}],
        'max_tokens': int(cfg.get('max_tokens') or VERIFY_DEFAULTS['max_tokens']),
    }).encode('utf-8')
    req = urllib.request.Request(
        base_url + '/chat/completions', data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'})
    try:
        with kit_http.open_request(req, timeout=cfg.get('timeout') or 60) as resp:
            text = json.loads(kit_http.read_response(resp).decode('utf-8'))['choices'][0]['message']['content']
    except Exception as e:
        raise kit_art.KitArtError(
            f"La verificación del título no respondió ({type(e).__name__}).") from None
    if not isinstance(text, str):
        raise kit_art.KitArtError("La verificación del título no devolvió texto.")
    return text


# --- Llamadas pagas ---

def _paid_image(client, prompt, images, cfg, budget):
    """Un pedido a la API de imágenes, con el tope antes y el gasto anotado después."""
    data = kit_art.charged_call(client, prompt, images, cfg, budget)
    try:
        return Image.open(io.BytesIO(data)).convert('RGB')
    except Exception:
        raise kit_art.KitArtError("La API de imágenes no devolvió una imagen válida.") from None


def _title_ok(path, title, cfg, verify, budget):
    """True/False según lo que lee el modelo con visión; None si no se pudo verificar."""
    if cfg.get('enabled', True) is False:
        return None
    cost = budget.verify_cost()
    if budget.blocked(cost):
        return None
    try:
        text = verify(path, cfg)
    except Exception as exc:
        if getattr(exc, 'billable', True):
            budget.charge(cost, verifications=1)
        return None
    budget.charge(cost, verifications=1)
    return titles_match(title, text)


def cover(title, model, backgrounds, used, rng, client=None, *, cfg=None, out_dir=None,
          now=None, fetch=None, dbx=None, report=None, budget=None, verify=None):
    """Genera la portada completa de un video y devuelve la ruta local del PNG.

    Args:
        title: título grande de la portada; llega al prompt sin cambios.
        model: ruta en Dropbox de la portada modelo del género.
        backgrounds: fondos del género, ``[{name, path}]`` (ver ``find_assets``).
        used: ``{path: fecha del último uso}`` (ver ``kit_art.used_refs``).
        client: ``client(prompt, [modelo, fondo], cfg) -> bytes``; por defecto la API real.
        cfg: ``kit_preview.art`` (API, ``prompt``, ``ref_cooldown_days``, ``verify``).
        fetch: ``fetch(paths, dest_dir) -> rutas locales``; por defecto baja de Dropbox.
        report: dict opcional que recibe ``refs`` (el fondo elegido), ``warnings``,
            ``prompt``, ``verified`` (True, False o None), ``retried`` y, si el reintento no
            llegó a hacerse, ``retry_failed`` (motivo, sin datos privados).
        budget: ``kit_spend.Budget``; por defecto uno que solo cuenta esta llamada.
        verify: ``verify(image_path, cfg) -> título leído``; por defecto ``vision_client``.

    Raises:
        KitArtBudget si el tope no deja hacer el primer pedido; KitArtRejected / KitArtError
        si la API lo rechaza o falla (no se reintenta). Los archivos bajados se borran siempre.
    """
    cfg = {**DEFAULTS, **(cfg or {})}
    chosen, warnings = kit_art.choose_refs(
        backgrounds, used, rng, now=now, cooldown_days=int(cfg['ref_cooldown_days']), max_refs=1)
    prompt = render_prompt(cfg.get('prompt'), title)
    info = report if report is not None else {}
    info.update(refs=chosen, warnings=warnings, prompt=prompt, verified=None, retried=False)
    budget = budget or kit_spend.Budget()
    client = client or kit_art.api_client
    verify = verify or vision_client
    vcfg = verify_settings(cfg)
    fetch = fetch or partial(kit_source.download_pack_files, dbx=dbx)
    out_dir = out_dir or tempfile.mkdtemp(prefix='kit_cover_ai_')
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, OUT_NAME)
    with tempfile.TemporaryDirectory(prefix='kit_template_') as tmp:
        try:
            # Carpetas separadas: el modelo y el fondo pueden llamarse igual.
            sources = [fetch([path], os.path.join(tmp, f'raw{i}'))[0]
                       for i, path in enumerate([model, chosen[0]])]
            # PNG achicado, sin metadatos y con nombre genérico (también convierte .jfif).
            images = [kit_art._prepare_ref(src, os.path.join(tmp, f'img{i}.png'),
                                           int(cfg['ref_max_side']))
                      for i, src in enumerate(sources)]
        except Exception as e:
            raise kit_art.KitArtConfig(
                f"No se pudieron preparar el modelo y el fondo ({type(e).__name__}).") from None
        _paid_image(client, prompt, images, cfg, budget).save(out, 'PNG')
        info['verified'] = _title_ok(out, title, vcfg, verify, budget)
        if info['verified'] is False:
            # Un solo reintento; si falla o el tope lo frena, queda la primera imagen.
            info['retried'] = True
            try:
                second = _paid_image(client, prompt, images, cfg, budget)
            except Exception as exc:
                info['retry_failed'] = (str(exc) if isinstance(exc, KitArtBudget)
                                        else type(exc).__name__)
                return out
            second.save(out, 'PNG')
            info['verified'] = _title_ok(out, title, vcfg, verify, budget)
    return out


# --- Entrada del worker ---

def _accepts_photo(send):
    """True si ``send`` recibe ``photo`` (por nombre o con ``**kwargs``)."""
    try:
        params = inspect.signature(send).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(p.name == 'photo' or p.kind is inspect.Parameter.VAR_KEYWORD for p in params)


def _warn(notify, text, photo=None):
    send = notify or kit_notify.send
    try:
        # Se mira la firma, no se atrapa TypeError: uno de adentro mandaría el aviso dos veces.
        if photo and _accepts_photo(send):
            send(text, photo=photo)
        else:
            send(text)
    except Exception as exc:
        print(f"Aviso por Telegram no enviado ({type(exc).__name__}).")


def for_video(kit_cfg, title, fallback_image, store, rng, work_dir, dbx=None, client=None,
              notify=None, now=None, budget=None, verify=None):
    """Portada completa del video: ``(ruta, [fondo usado], True)``.

    El género sale de ``art.genre`` (o ``names.genre``) y las carpetas de ``art.refs_root``.
    Si falta config, la API rechaza o falla, o se llega al tope de gasto, ese video cae a
    manual: devuelve ``(fallback_image, [], False)`` y avisa por Telegram; nunca levanta. Por
    el tope se avisa una sola vez por corrida. Si el título leído no coincide después del
    reintento, la portada se usa igual y el aviso lleva la imagen para revisarla.
    """
    kit_cfg = kit_cfg or {}
    art = kit_cfg.get('art') or {}
    genre = str(art.get('genre') or (kit_cfg.get('names') or {}).get('genre') or '').strip()
    budget = budget or kit_spend.Budget(kit_spend.settings(kit_cfg), store, now)
    report = {}
    try:
        if not genre or not art.get('refs_root'):
            raise kit_art.KitArtConfig("Falta art.refs_root o el género en la config.")
        model, backgrounds = find_assets(art['refs_root'], genre, art, dbx=dbx)
        usage = getattr(store, 'ref_usage', None)
        path = cover(title, model, backgrounds, usage() if usage else {}, rng, client,
                     cfg=art, out_dir=work_dir, now=now, dbx=dbx, report=report,
                     budget=budget, verify=verify)
    except Exception as exc:
        if isinstance(exc, KitArtBudget):
            reason, once = str(exc), exc.reason
        else:
            reason, once = ('pedido rechazado' if isinstance(exc, kit_art.KitArtRejected)
                            else type(exc).__name__), kit_art._API_FAILED
        print(f"Portada con IA no generada ({reason}); se usa la imagen del kit o la portada sin IA.")
        if once not in budget.notified:
            if once:
                budget.notified.add(once)
            _warn(notify, _FALLBACK_TEXT.format(reason))
        return fallback_image, [], False
    for warning in report.get('warnings') or []:
        print(f"warning: {warning}")
    if report.get('verified') is False:
        print("warning: el título de la portada no coincide con el pedido.")
        failed = report.get('retry_failed')
        _warn(notify, _REVIEW_NO_RETRY_TEXT.format(failed) if failed else _REVIEW_TEXT,
              photo=path)
    elif verify_settings(art).get('enabled', True) is not False:
        print("warning: el título de la portada no se pudo verificar.")
    return path, list(report.get('refs') or []), True
