# -*- coding: utf-8 -*-
"""Lógica del panel de configuración de loop kits (sin Qt).

Lee y escribe en Dropbox, vía ``kit_cloud``, dos JSON: ``kits.json`` (catálogo) y la config
del worker, de la que solo toca las claves ``kit_preview.{channel, slots, genres, cover_mode,
dropbox_root, scan_folders, loops_dirs, ignore_names, scan_max_depth}``,
``kit_preview.art.{refs_root, prompt}``, ``kit_preview.spend.{monthly_cap_usd,
max_images_per_run}``, ``kit_preview.seo`` (ficha de SEO por género) y
``kit_preview.names.vary_name``. Los secretos (Telegram, YouTube, Dropbox, claves de API) viven
en variables de entorno / secretos de GitHub: aquí solo se pregunta si están presentes, sin
leer su valor hacia ningún JSON ni mensaje.
"""
import copy
import os
from urllib.parse import urlparse

from core import (kit_catalog, kit_cloud, kit_notify, kit_seo, kit_source, kit_spend,
                  kit_state)

CONFIG_PATH = os.environ.get('KIT_CONFIG_PATH') or '/loop_kits/_automation/config.json'
KITS_PATH = os.environ.get('KIT_CATALOG_PATH') or '/loop_kits/_automation/kits.json'
STATE_PATH = kit_state.STATE_PATH

WEEKDAYS = ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo')
COVER_MODES = ('manual', 'auto', 'template')
KIT_FIELDS = ('folder', 'name', 'payhip_url', 'genre', 'description', 'active')
SCAN_KEYS = ('scan_folders', 'loops_dirs', 'ignore_names', 'scan_max_depth')
SPEND_KEYS = ('monthly_cap_usd', 'max_images_per_run')
MAX_SCAN_DEPTH = 6
MAX_PROMPT = 4000
MAX_MONTHLY_CAP = 1000
MAX_IMAGES_PER_RUN = 50


class SettingsError(ValueError):
    """Entrada inválida; el mensaje es apto para mostrar al usuario."""


def _text(value):
    return value.strip() if isinstance(value, str) else ''


# --- Kits ---

def prune_blank(rows):
    """Quita filas sin ningún dato (``active`` solo no cuenta)."""
    return [r for r in rows if any(_text(r.get(k)) for k in KIT_FIELDS if k != 'active')]


def validate_kits(rows, genres=None):
    """Valida las filas de la tabla y devuelve la lista lista para ``kits.json``.

    Reglas de ``kit_catalog`` (https, género configurado, carpetas sin repetir) más: el
    género es obligatorio y el link no puede llevar usuario ni clave. Un link vacío se
    admite (el kit queda sin elegir). Los mensajes nombran la fila por número.
    """
    rows = [{'folder': _text(r.get('folder')), 'name': _text(r.get('name')),
             'payhip_url': _text(r.get('payhip_url')), 'genre': _text(r.get('genre')),
             'description': _text(r.get('description')),
             'active': bool(r.get('active', True))} for r in rows]
    for i, row in enumerate(rows, 1):
        if not row['genre']:
            raise SettingsError(f'Kit {i}: falta el género.')
        if row['payhip_url']:
            try:
                parsed = urlparse(row['payhip_url'])
            except ValueError:
                raise SettingsError(f'Kit {i}: el link no es válido.') from None
            if parsed.username or parsed.password:
                raise SettingsError(f'Kit {i}: el link no puede llevar usuario ni clave.')
    try:
        return kit_catalog.validate(rows, genres or None)
    except kit_catalog.KitCatalogError as exc:
        raise SettingsError(str(exc).replace('kits.json entrada', 'Kit')) from None


# --- Config del worker ---

def parse_genres(text):
    """Un género por línea (o separados por coma), sin vacíos ni repetidos."""
    out, seen = [], set()
    for part in str(text or '').replace(',', '\n').splitlines():
        part = ' '.join(part.split())
        if part and part.lower() not in seen:
            seen.add(part.lower())
            out.append(part)
    return out


def parse_names(text):
    """Nombres separados por coma o por línea, sin vacíos ni repetidos."""
    if not isinstance(text, str):
        text = '\n'.join(str(item) for item in text or [])
    return parse_genres(text)


def _validate_scan(form):
    """Carpeta raíz y reglas de recorrido; solo las claves que trae el formulario."""
    out = {}
    if 'dropbox_root' in form:
        root = _text(form.get('dropbox_root')).rstrip('/')
        # Vacía se admite: la config guardada conserva la suya.
        if root and not root.startswith('/'):
            raise SettingsError('La carpeta raíz de kits debe ser una ruta de Dropbox que '
                                'empiece con "/".')
        out['dropbox_root'] = root
    if 'scan_folders' in form:
        out['scan_folders'] = parse_names(form.get('scan_folders'))
    if 'loops_dirs' in form:
        out['loops_dirs'] = parse_names(form.get('loops_dirs'))
        if not out['loops_dirs']:
            raise SettingsError('Cargá al menos un nombre de carpeta de loops.')
    if 'ignore_names' in form:
        out['ignore_names'] = parse_names(form.get('ignore_names'))
    if 'scan_max_depth' in form:
        try:
            depth = int(form.get('scan_max_depth'))
        except (TypeError, ValueError):
            raise SettingsError('Profundidad de búsqueda inválida.') from None
        if not 1 <= depth <= MAX_SCAN_DEPTH:
            raise SettingsError(f'La profundidad de búsqueda va de 1 a {MAX_SCAN_DEPTH}.')
        out['scan_max_depth'] = depth
    return out


def default_prompt():
    """Prompt de la portada por plantilla que usa el worker si la config no trae uno."""
    from core import kit_template_art
    return kit_template_art.DEFAULT_PROMPT


def _validate_template(form):
    """Prompt de la portada y topes de gasto; solo las claves que trae el formulario."""
    out = {}
    if 'art_prompt' in form:
        prompt = _text(form.get('art_prompt'))
        # Sin {titulo} el worker agrega el título al final (kit_template_art.render_prompt).
        if len(prompt) > MAX_PROMPT:
            raise SettingsError(f'El prompt de la portada admite hasta {MAX_PROMPT} caracteres.')
        # Igual al de fábrica no se guarda: así el worker sigue las mejoras del código.
        out['art_prompt'] = '' if prompt == default_prompt() else prompt
    if 'monthly_cap_usd' in form:
        try:
            cap = round(float(form.get('monthly_cap_usd')), 2)
        except (TypeError, ValueError):
            raise SettingsError('Tope mensual inválido.') from None
        if not 0 <= cap <= MAX_MONTHLY_CAP:
            raise SettingsError(f'El tope mensual va de 0 a {MAX_MONTHLY_CAP} USD.')
        out['monthly_cap_usd'] = cap
    if 'max_images_per_run' in form:
        try:
            count = int(form.get('max_images_per_run'))
        except (TypeError, ValueError):
            raise SettingsError('Máximo de imágenes por corrida inválido.') from None
        if not 0 <= count <= MAX_IMAGES_PER_RUN:
            raise SettingsError(f'El máximo de imágenes por corrida va de 0 a '
                                f'{MAX_IMAGES_PER_RUN}.')
        out['max_images_per_run'] = count
    return out


def _validate_seo(form, genres):
    """Fichas de SEO por género y "variar el nombre"; solo las claves que trae el formulario.

    Solo se validan las fichas de los géneros de la lista. Una ficha sin frase se guarda
    como está cargada (el worker no la usa). La de un género que ya no está en la lista se
    conserva si es válida y, si no, se descarta: no puede trabar el guardado porque el panel
    ya no la muestra.
    """
    out = {}
    if 'seo' in form:
        table = form.get('seo')
        if not isinstance(table, dict):
            raise SettingsError('Las fichas de SEO no tienen el formato esperado.')
        out['seo'] = {}
        for genre, raw in table.items():
            if kit_seo.is_empty(raw):
                continue  # una ficha sin nada cargado no es una ficha
            listed = kit_seo.find_key({g: None for g in genres}, genre) is not None
            try:
                out['seo'][str(genre)] = kit_seo.to_config(kit_seo.validate(raw, partial=True))
            except kit_seo.KitSeoError as exc:
                if listed:
                    raise SettingsError(f'SEO de "{genre}": {exc}') from None
    if 'vary_name' in form:
        out['vary_name'] = bool(form.get('vary_name'))
    return out


def validate_settings(form):
    """Valida el formulario de configuración y devuelve un dict normalizado.

    Args:
        form: ``{channel, slots: [{weekday, hour, minute}], genres: [str], refs_root,
            cover_mode}`` y, opcionales, ``dropbox_root``, ``scan_folders``, ``loops_dirs``,
            ``ignore_names``, ``scan_max_depth``, ``art_prompt``, ``monthly_cap_usd``,
            ``max_images_per_run``, ``seo`` (``{genero: ficha}``) y ``vary_name`` (las que
            falten no se tocan al guardar).
    """
    slots, seen = [], set()
    for i, slot in enumerate(form.get('slots') or [], 1):
        try:
            item = {'weekday': int(slot['weekday']), 'hour': int(slot['hour']),
                    'minute': int(slot['minute'])}
        except (KeyError, TypeError, ValueError):
            raise SettingsError(f'Horario {i}: valores inválidos.') from None
        if not (0 <= item['weekday'] <= 6 and 0 <= item['hour'] <= 23
                and 0 <= item['minute'] <= 59):
            raise SettingsError(f'Horario {i}: fuera de rango.')
        key = tuple(item.values())
        if key in seen:
            raise SettingsError(f'Horario {i}: repetido.')
        seen.add(key)
        slots.append(item)
    if not slots:
        raise SettingsError('Hace falta al menos un horario.')
    genres = parse_genres('\n'.join(form.get('genres') or []))
    if not genres:
        raise SettingsError('Cargá al menos un género.')
    refs_root = _text(form.get('refs_root')).rstrip('/')
    if refs_root and (not refs_root.startswith('/') or any(c.isspace() for c in refs_root)):
        raise SettingsError('La carpeta de referencias debe ser una ruta de Dropbox que '
                            'empiece con "/" y no tenga espacios.')
    cover_mode = _text(form.get('cover_mode')).lower() or 'manual'
    if cover_mode not in COVER_MODES:
        raise SettingsError('Modo de portada inválido.')
    if cover_mode == 'auto' and not refs_root:
        raise SettingsError('El modo auto necesita la carpeta de referencias.')
    if cover_mode == 'template' and not refs_root:
        raise SettingsError('El modo plantilla + fondo necesita la carpeta de referencias.')
    return {'channel': _text(form.get('channel')), 'slots': slots, 'genres': genres,
            'refs_root': refs_root, 'cover_mode': cover_mode, **_validate_scan(form),
            **_validate_template(form), **_validate_seo(form, genres)}


def apply_to_config(config, settings):
    """Copia de ``config`` con solo las claves propias de ``settings`` actualizadas."""
    new = copy.deepcopy(config) if isinstance(config, dict) else {}
    kit = new.get('kit_preview')
    if not isinstance(kit, dict):
        kit = new['kit_preview'] = {}
    kit['slots'] = [dict(s) for s in settings['slots']]
    kit['genres'] = list(settings['genres'])
    kit['cover_mode'] = settings['cover_mode']
    if settings['channel']:
        kit['channel'] = settings['channel']
    else:
        kit.pop('channel', None)
    art = kit.get('art')
    if settings['refs_root']:
        if not isinstance(art, dict):
            art = kit['art'] = {}
        art['refs_root'] = settings['refs_root']
    elif isinstance(art, dict):
        art.pop('refs_root', None)
    if settings.get('dropbox_root'):
        kit['dropbox_root'] = settings['dropbox_root']
    for key in SCAN_KEYS:
        if key in settings:
            kit[key] = copy.deepcopy(settings[key])
    if 'art_prompt' in settings:
        art = kit.get('art')
        if settings['art_prompt']:
            if not isinstance(art, dict):
                art = kit['art'] = {}
            art['prompt'] = settings['art_prompt']
        elif isinstance(art, dict):
            art.pop('prompt', None)
    if any(key in settings for key in SPEND_KEYS):
        spend = kit.get('spend')
        if not isinstance(spend, dict):
            spend = kit['spend'] = {}
        spend.update({key: settings[key] for key in SPEND_KEYS if key in settings})
    if 'seo' in settings:
        if settings['seo']:
            kit['seo'] = copy.deepcopy(settings['seo'])
        else:
            kit.pop('seo', None)
    if 'vary_name' in settings:
        names = kit.get('names')
        if isinstance(names, dict):
            names['vary_name'] = settings['vary_name']
        elif settings['vary_name']:
            # Sin el modelo de texto no hay con qué proponer nombres: no se crea a medias.
            raise SettingsError('"Variar también el nombre" necesita el modelo de texto '
                                'configurado (kit_preview.names, ver docs/KIT_WEEKLY.md).')
    return new


def form_from_config(config):
    """Valores iniciales del formulario a partir de la config (con defaults del worker)."""
    from core.kit_publish import DEFAULT_SLOTS
    kit = (config or {}).get('kit_preview') or {}
    art = kit.get('art') if isinstance(kit.get('art'), dict) else {}
    from core import channel_kind
    channels = [name for name, c in ((config or {}).get('channels') or {}).items()
                if channel_kind.is_loops_section(c)]
    scan = kit_source.scan_settings(kit)
    spend = kit_spend.settings(kit)
    prompt = art.get('prompt')
    seo = kit.get('seo') if isinstance(kit.get('seo'), dict) else {}
    names = kit.get('names') if isinstance(kit.get('names'), dict) else {}
    return {'seo': {str(genre): kit_seo.form(raw) for genre, raw in seo.items()},
            'vary_name': names.get('vary_name') is True,
            'channel': str(kit.get('channel') or ''), 'channels': channels,
            'slots': [dict(s) for s in (kit.get('slots') or DEFAULT_SLOTS)],
            'genres': list(kit.get('genres') or []),
            'refs_root': str(art.get('refs_root') or ''),
            'cover_mode': kit.get('cover_mode') if kit.get('cover_mode') in COVER_MODES
            else 'manual',
            'art_prompt': prompt.strip() if isinstance(prompt, str) and prompt.strip()
            else default_prompt(),
            'monthly_cap_usd': min(spend['monthly_cap_usd'], MAX_MONTHLY_CAP),
            'max_images_per_run': min(spend['max_images_per_run'], MAX_IMAGES_PER_RUN),
            'dropbox_root': str(kit.get('dropbox_root') or ''),
            'scan_folders': scan['scan_folders'], 'loops_dirs': scan['loops_dirs'],
            'ignore_names': scan['ignore_names'],
            'scan_max_depth': min(scan['max_depth'], MAX_SCAN_DEPTH)}


def reference_folders(refs_root, genres):
    """Carpeta de referencias de cada género, tal como la usa ``kit_art``."""
    from core import kit_art
    return [kit_art.genre_folder(refs_root, g) for g in genres] if refs_root else []


# --- Telegram (solo estado) ---

def telegram_configured(env=None):
    """True si el token y el chat de Telegram están presentes en el entorno de esta PC."""
    env = os.environ if env is None else env
    return bool(_text(env.get(kit_notify.ENV_TOKEN)) and _text(env.get(kit_notify.ENV_CHAT)))


# --- Dropbox ---

def load_all(dbx=None, paths=None):
    """Lee catálogo y config con sus ``rev``. Archivos que no existen vienen como None.

    ``paths`` (``kit_channel.paths``) elige el canal; sin él, el canal por defecto.
    """
    kits, kits_rev = kit_cloud.read_json_rev(paths.kits if paths else KITS_PATH, dbx=dbx)
    if kits is not None and not isinstance(kits, list):
        raise kit_cloud.KitCloudError('kits.json no tiene el formato esperado.')
    config, config_rev = kit_cloud.read_json_rev(paths.config if paths else CONFIG_PATH, dbx=dbx)
    if config is not None and not isinstance(config, dict):
        raise kit_cloud.KitCloudError('La config del worker no tiene el formato esperado.')
    return {'kits': kits, 'kits_rev': kits_rev, 'config': config, 'config_rev': config_rev}


def save_kits(catalog, rev, dbx=None, paths=None):
    """Guarda ``kits.json``. ``rev`` es el de la última lectura (None si no existía)."""
    return kit_cloud.write_json(paths.kits if paths else KITS_PATH, catalog,
                                rev=rev or kit_cloud.NEW, dbx=dbx)


def save_config(settings, dbx=None, paths=None):
    """Relee la config, cambia solo las claves propias y la guarda sin pisar otras ediciones."""
    path = paths.config if paths else CONFIG_PATH
    config, rev = kit_cloud.read_json_rev(path, dbx=dbx)
    if not isinstance(config, dict):
        raise SettingsError('No hay config del worker en Dropbox: subí primero la config '
                            'completa (ver docs/KIT_WEEKLY.md).')
    return kit_cloud.write_json(path, apply_to_config(config, settings), rev=rev, dbx=dbx)


def save_kits_merged(catalog, base, rev, dbx=None, paths=None):
    """``kits.json`` por CAS; ante un conflicto relee y fusiona por kit (``folder``).

    Returns:
        ``(catalogo_guardado, rev)``. ``cloud_merge.MergeConflict`` si el mismo campo cambió
        en las dos PCs.
    """
    from core import cloud_merge
    path = paths.kits if paths else KITS_PATH
    return cloud_merge.save_merged(
        lambda: kit_cloud.read_json_rev(path, dbx=dbx),
        lambda doc, current: kit_cloud.write_json(path, doc, rev=current or kit_cloud.NEW, dbx=dbx),
        base if base is not None else [], catalog, rev, (kit_cloud.KitCloudConflict,))


def save_config_merged(settings, base, rev, dbx=None, paths=None):
    """Aplica los ajustes sobre la config leída (``base``, con su ``rev``) y la guarda por CAS.

    Ante un conflicto relee y fusiona campo por campo: solo choca si otra PC cambió lo mismo.
    """
    from core import cloud_merge
    path = paths.config if paths else CONFIG_PATH
    if not isinstance(base, dict) or rev is None:
        raise SettingsError('No hay config del worker en Dropbox: subí primero la config '
                            'completa (ver docs/KIT_WEEKLY.md).')

    def read():
        doc, current = kit_cloud.read_json_rev(path, dbx=dbx)
        if not isinstance(doc, dict):
            raise SettingsError('La config del worker desapareció de Dropbox; recargá.')
        return doc, current

    return cloud_merge.save_merged(
        read, lambda doc, current: kit_cloud.write_json(path, doc, rev=current, dbx=dbx),
        base, apply_to_config(base, settings), rev, (kit_cloud.KitCloudConflict,))


def seo_notes(seo_table):
    """Avisos para mostrar después de guardar: artistas que no pueden ir de principal."""
    notes = []
    for genre, raw in (seo_table or {}).items():
        if kit_seo.is_blank(raw):
            continue
        try:
            out = kit_seo.unfit_artists(kit_seo.validate(raw))
        except kit_seo.KitSeoError:
            continue
        if out:
            notes.append(f'SEO de "{genre}": {len(out)} artista(s) no dejan la frase dentro de '
                         f'los primeros {kit_seo.PHRASE_WITHIN} caracteres y no van a salir en '
                         f'el título ({", ".join(out)}).')
    return notes


def last_state_lines(state, limit=5, now=None, cap=None):
    """Resumen legible del estado: sin nombres de kit ni de video.

    Incluye el gasto estimado de portadas del mes de ``now`` (con ``cap``, contra el tope).
    """
    runs = sorted((state or {}).get('runs') or [], key=lambda r: r.get('id', 0), reverse=True)
    lock = (state or {}).get('lock')
    lines = [f'Corridas registradas: {len(runs)}',
             'Hay un lock registrado (worker en curso o corrida cortada).' if lock
             else 'Sin lock activo.',
             kit_spend.summary_line(state, now, cap)]
    for run in runs[:limit]:
        lines.append(f"#{run.get('id')} · {run.get('estado') or '?'} · "
                     f"{run.get('publish_at') or 'sin fecha'} · {run.get('youtube_id') or '-'}")
    return lines
