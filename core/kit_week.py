# -*- coding: utf-8 -*-
"""Semana del worker de loop kits: qué kits pueden salir y cómo se arma cada video.

Une los módulos que deciden cada parte: ``kit_catalog`` (kits activos y con link),
``kit_cycle`` (ciclo, descanso y orden de uso), ``kit_audio`` (tramos por duración),
``kit_names`` / ``kit_art`` / ``kit_cover`` (nombre, fondo y portada) y ``kit_publish``.
Los avisos que devuelve no llevan nombres de kit ni de archivo.
"""
import os
import tempfile
from datetime import timedelta

from core import (kit_art, kit_audio, kit_catalog, kit_cloud, kit_cover, kit_cycle, kit_names,
                  kit_settings, kit_source)
from core.kit_publish import publish_preview
from core.kit_render import render as kit_render


class KitSkip(Exception):
    """Este kit no puede dar un video ahora; el worker prueba con el siguiente."""


def load_catalog(app_config, dbx=None, path=None):
    """``kits.json`` de Dropbox ya validado, o None si todavía no existe.

    ``path`` es el catálogo de otro canal; sin él, el del canal por defecto.
    """
    data = kit_cloud.read_json(path or kit_settings.KITS_PATH, dbx=dbx)
    if data is None:
        return None
    return kit_catalog.validate(data, kit_catalog.configured_genres(app_config))


def candidates(packs, catalog, require_images=True):
    """Packs que pueden dar un video y la entrada del catálogo de cada uno.

    Quedan afuera las carpetas que empiezan con ``_`` (automatización, referencias), los
    kits que el catálogo no deja pasar y los que no tienen loops. Sin imágenes un kit solo
    entra cuando ``require_images`` es falso (``cover_mode: auto`` genera el fondo).

    Returns:
        ``(pool, entries, warnings)``; ``entries`` es ``{dropbox_path: entrada}`` (vacío
        sin catálogo: se usan todas las carpetas y el link del canal).
    """
    warnings = []
    packs = [p for p in packs or [] if not p['name'].startswith('_')]
    entries = {}
    if catalog is None:
        warnings.append("No hay kits.json: se usan todas las carpetas y el link del canal.")
    else:
        eligible = kit_catalog.eligible(catalog, packs)
        for pack in packs:
            keys = {kit_catalog._norm(pack['name']), kit_catalog._norm(pack['dropbox_path'])}
            entry = next((e for e in eligible if kit_catalog._norm(e['folder']) in keys), None)
            if entry:
                entries[pack['dropbox_path']] = entry
        wanted = sum(1 for e in catalog
                     if e.get('active') is True and kit_catalog.is_valid_link(e.get('payhip_url')))
        if wanted > len(eligible):
            warnings.append(f"{wanted - len(eligible)} kit(s) activos del catálogo no tienen "
                            "carpeta en Dropbox (¿se renombró?).")
        packs = [p for p in packs if p['dropbox_path'] in entries]
    pool = [p for p in packs
            if p.get('loops') and (p.get('images') or not require_images)]
    if len(pool) < len(packs):
        warnings.append(f"{len(packs) - len(pool)} kit(s) sin loops"
                        + (" o sin imágenes" if require_images else "") + " quedan afuera.")
    return pool, entries, warnings


def open_week(app_config, state, history, now, rng, *, dbx=None, exclude=(), list_packs_fn=None,
              kits_path=None):
    """Kits de la semana en orden de prioridad (primero el que hace más que no sale).

    Entre kits con la misma prioridad manda el orden del recorrido: las categorías de
    ``kit_preview.scan_folders`` y, dentro de cada una, el orden de las carpetas.

    Returns:
        dict ``{queue, entries, warnings}``; ``queue`` son selecciones de ``kit_cycle.pick_week``.
    """
    kit_cfg = app_config.get('kit_preview') or {}
    root = str(kit_cfg.get('dropbox_root') or '').strip()
    if not root:
        raise ValueError("Falta kit_preview.dropbox_root en la config.")
    packs = (list_packs_fn or kit_source.list_packs)(
        root, local_images_root=kit_cfg.get('local_images_root'), dbx=dbx,
        scan=kit_source.scan_settings(kit_cfg))
    # Con portada automática el fondo se genera: el kit no necesita imágenes propias.
    require_images = kit_art.mode(kit_cfg) != kit_art.MODE_AUTO
    pool, entries, warnings = candidates(
        packs, load_catalog(app_config, dbx=dbx, path=kits_path), require_images)
    picked = kit_cycle.pick_week(
        pool, state, history, now, rng, kit_cycle.settings(kit_cfg), exclude=exclude,
        require_images=require_images, limit=len(pool), keep_order=True)
    return {'queue': picked['selections'], 'entries': entries, 'warnings': warnings}


def _image_local(image, dest_dir, dbx):
    if image.get('source') == 'local':
        return image['path']
    return kit_source.download_pack_files([image['path']], dest_dir, dbx=dbx)[0]


def make_video(selection, entry, *, kit_cfg, channel, channel_templates, slots_cfg, slot, now,
               state, store, rng, output_dir, dbx=None, tz=None, hooks=None):
    """Arma, sube y registra el video de un kit para ``slot``.

    Args:
        selection: una selección de ``open_week`` (pack e imagen; la imagen es None en un
            kit sin imágenes con portada automática).
        entry: entrada del catálogo del kit (nombre, link y género), o None sin catálogo.
        slots_cfg: horarios de ``kit_preview.slots``; ``slot`` es el que le toca al video.
        now: momento de la corrida (naive, hora local); desde ahí se cuenta el ciclo.
        state: estado leído al empezar la corrida (ciclo y tramos usados del kit).
        hooks: reemplazos para pruebas: ``end_fn``, ``cut_fn``, ``render_fn``,
            ``cover_fn``, ``llm_call``, ``art_client``, ``art_notify``.

    Returns:
        dict ``{youtube_id, title, pack_path, warnings}``.

    Raises:
        KitSkip: el kit no dio un video antes de subir nada (audio insuficiente, descarga,
            render). Un error al subir o al registrar sale tal cual: ahí la corrida se corta.
    """
    hooks = hooks or {}
    pack, image = selection['pack'], selection['image']
    path = pack['dropbox_path']
    cycle_cfg = kit_cycle.settings(kit_cfg)
    saved = ((state or {}).get('packs') or {}).get(path) or {}
    genre = str((entry or {}).get('genre') or '').strip()
    warnings = []

    with tempfile.TemporaryDirectory(prefix='kit_week_') as tmp:
        try:
            audio_cfg = kit_audio.settings(kit_cfg)
            src_dir = os.path.join(tmp, 'src')
            os.makedirs(src_dir)
            local_fn = kit_audio.downloader(src_dir, dbx=dbx)
            plan = kit_audio.plan_audio(
                pack, kit_cycle.used_segments(state, path, now, cycle_cfg), rng,
                audio_cfg['target_min_s'], audio_cfg['target_max_s'],
                short_min=audio_cfg['short_min_s'], min_loops=audio_cfg['min_loops'],
                trim=kit_cfg.get('trim'), local_fn=local_fn, end_fn=hooks.get('end_fn'))
            if not plan['ok']:
                raise KitSkip('audio')
            warnings += plan['warnings']
            wavs = (hooks.get('cut_fn') or kit_audio.cut_segments)(
                plan, os.path.join(tmp, 'cut'), local_fn=local_fn)
            image_local = _image_local(image, tmp, dbx) if image else None
            pack_id = store.upsert_pack(path, pack['name'])

            base_name = (entry or {}).get('name') or pack['name']
            names_cfg = kit_cfg.get('names')
            if names_cfg and genre:
                names_cfg = {**names_cfg, 'genre': genre}
            video_name, used_names = kit_names.for_pack(
                base_name, path, names_cfg, store, llm_call=hooks.get('llm_call'))
            if (names_cfg and names_cfg.get('enabled', True) is not False
                    and str(names_cfg.get('genre') or '').strip() and not video_name):
                warnings.append("Un video salió sin nombre generado (falló el LLM).")
            display_name = video_name or base_name
            link = (entry or {}).get('payhip_url') or channel_templates.get('link') or ''
            tracking_id, templates = None, channel_templates
            if link:
                tracking_id = kit_names.new_tracking_id()
                templates = {**channel_templates, 'link': kit_names.track_link(link, tracking_id)}

            art_cfg = kit_cfg
            if genre:
                art_cfg = {**kit_cfg, 'art': {**(kit_cfg.get('art') or {}), 'genre': genre}}
            background, ref_images = kit_art.for_video(
                art_cfg, pack['name'], image_local, store, rng, tmp, dbx=dbx,
                client=hooks.get('art_client'), notify=hooks.get('art_notify'), now=now)
            if not background:
                # Sin imagen propia y sin fondo generado no hay con qué armar la portada.
                raise KitSkip('cover')
            frame, thumbnail = (hooks.get('cover_fn') or kit_cover.for_video)(
                kit_cfg.get('cover'), background, display_name, tmp)
            os.makedirs(output_dir, exist_ok=True)
            video = os.path.join(output_dir, f"kit_{slot.strftime('%Y%m%d_%H%M')}.mp4")
            (hooks.get('render_fn') or kit_render)(frame, wavs, video)
        except KitSkip:
            raise
        except Exception as exc:
            raise KitSkip(type(exc).__name__) from None

        pub = publish_preview(
            channel, video, thumbnail, display_name, slots_cfg, templates,
            pack_id=pack_id, audio_mode=plan['mode'], now=slot - timedelta(minutes=1),
            image_path=image.get('path') if image else None, loops_json=plan['segments'], store=store, tz=tz,
            video_name=video_name, tracking_id=tracking_id, ref_images=ref_images)

    if pub.get('thumbnail_error'):
        warnings.append("YouTube no aceptó la miniatura de un video.")
    kit_names.remember(store, path, used_names, video_name)
    try:
        # Un video corto, o el que deja al kit sin loops para otro, cierra el ciclo.
        store.update_cycle(path, **kit_cycle.advance(
            saved.get('cycle'), now, cycle_cfg, close=plan['short'] or plan['exhausted'],
            last_used_at=saved.get('last_used_at')))
    except Exception:
        warnings.append("No se pudo guardar el ciclo de un kit.")
    return {'youtube_id': pub.get('youtube_id'), 'title': pub.get('title'),
            'pack_path': path, 'warnings': warnings}
