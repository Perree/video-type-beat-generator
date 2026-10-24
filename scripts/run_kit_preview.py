#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Corrida completa de preview de loop kit: elegir pack, loops, render y subida.

Entry point: ``python scripts/run_kit_preview.py`` (ver docs/KIT_PREVIEW.md).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_art, kit_cover, kit_names, kit_source, kit_store
from core.kit_publish import DEFAULT_SLOTS, next_slot, publish_preview
from core.kit_render import render as kit_render
from core.kit_select import KitSelectError, choose
from core.kit_trim import trim_to_wav
from core.publish_at import local_to_youtube_publish_at
from core.publish_calendar import next_free_slots, occupied_days, slot_day
from core import channel_kind
from core.sections import SECTION_LOOP_KITS

CONFIG_FILE = os.path.join('config', 'app_config.json')
DEFAULT_OUTPUT = os.path.join('exported_videos', 'loop_kits')
# Recorrido máximo para buscar un día libre: con un cron semanal, 4 semanas sobran.
HORIZON_DAYS = 28
# Pasado este tiempo desde la lectura, se relee el calendario antes de videos.insert.
CALENDAR_MAX_AGE_S = 20 * 60


def free_slot(slot, when, slots, calendar_fn, channel, tz=None):
    """Slot del preview salteando los días ocupados en YouTube.

    Parámetros: slot (``next_slot(when, slots)``); when (hora de la corrida, naive en ``tz``
    o con zona); slots (cron del canal); calendar_fn (callable(channel) -> filas de
    ``youtube.list_channel_calendar``); channel (canal que sube, con su token); tz (zona de
    los datetimes naive; None = la del sistema, la misma que usa publishAt).
    Devuelve el mismo ``slot`` si su día está libre, el próximo día libre del cron dentro de
    HORIZON_DAYS, o None si no hay ninguno. Un error de lectura se propaga: sin calendario
    no se sube nada.
    """
    zone = tz or datetime.now().astimezone().tzinfo
    aware = when if when.tzinfo is not None else when.replace(tzinfo=zone)
    # Una lectura alcanza: el preview elige y sube en la misma corrida, sin búfer de días
    # (run_preview relee solo si el render tardó más de CALENDAR_MAX_AGE_S).
    days = occupied_days(calendar_fn(channel), aware)
    if slot_day(slot, zone) not in days:
        return slot
    found = next_free_slots(slots, when, days, 1, HORIZON_DAYS, tz=zone)
    return found[0] if found else None


def load_app_config(path: Optional[str] = None) -> dict:
    """Lee app_config.json."""
    cfg_path = path or CONFIG_FILE
    with open(cfg_path, encoding='utf-8') as f:
        return json.load(f)


def resolve_channel(app_config: dict, channel_arg: Optional[str]) -> tuple:
    """Canal loop_kits y su dict de plantillas."""
    channels = app_config.get('channels') or {}
    # Tipo vía channel_kind: un canal sin section nunca es Beats ni Loops. Se avisa por
    # stderr y es un error solo si es el canal que corre (o si no queda ninguno).
    kits, untyped = {}, []
    for name, cfg in channels.items():
        try:
            if channel_kind.is_loops_section(cfg):
                kits[name] = cfg
        except channel_kind.ChannelKindError:
            untyped.append(name)
    if untyped:
        print(f"Aviso: {len(untyped)} canal(es) sin section en la config; se ignoran.",
              file=sys.stderr)
    if channel_arg in untyped or (not kits and untyped):
        raise SystemExit("Canal sin tipo definido (section ausente o desconocida).")
    if channel_arg:
        if channel_arg not in kits:
            raise SystemExit(
                f"El canal {channel_arg!r} no tiene section={SECTION_LOOP_KITS}.")
        return channel_arg, kits[channel_arg]
    if len(kits) == 1:
        name = next(iter(kits))
        return name, kits[name]
    if not kits:
        raise SystemExit(
            f"No hay canales con section={SECTION_LOOP_KITS} en {CONFIG_FILE}.")
    names = ', '.join(sorted(kits))
    raise SystemExit(f"Varios canales loop_kits; use --channel ({names}).")


def _resolve_image_local(image: dict, dest_dir: str, dbx=None) -> str:
    """Ruta local de la imagen (descarga si viene de Dropbox)."""
    if image.get('source') == 'local':
        return image['path']
    return kit_source.download_pack_files([image['path']], dest_dir, dbx=dbx)[0]


def _trim_settings(kit_cfg: dict) -> dict:
    """Parámetros de kit_trim desde config (con defaults)."""
    trim = kit_cfg.get('trim') or {}
    return {
        'noise_db': trim.get('noise_db', -40),
        'min_silence': trim.get('min_silence', 0.35),
        'min_preview': trim.get('min_preview', 1.5),
        'max_preview': trim.get('max_preview', 40),
    }


def run_preview(
    *,
    app_config: dict,
    channel: str,
    channel_templates: dict,
    dry_run: bool = False,
    now: Optional[datetime] = None,
    seed: Optional[int] = None,
    db_path: Optional[str] = None,
    list_packs_fn: Optional[Callable[..., List[dict]]] = None,
    dbx=None,
    trim_fn: Optional[Callable[..., str]] = None,
    render_fn: Optional[Callable[..., str]] = None,
    publish_fn: Optional[Callable[..., dict]] = None,
    output_dir: Optional[str] = None,
    store=None,
    tz=None,
    exclude_paths=(),
    cover_fn: Optional[Callable[..., tuple]] = None,
    llm_call: Optional[Callable[[str, str], str]] = None,
    art_client: Optional[Callable[..., bytes]] = None,
    art_notify: Optional[Callable[[str], Any]] = None,
    calendar_fn: Optional[Callable[[str], List[dict]]] = None,
) -> Dict[str, Any]:
    """Ejecuta la corrida o dry-run. Parámetros inyectables para smokes.

    Returns:
        dict con skipped, dry_run, audio_mode, selection, publish, trim_calls, etc.

    ``store`` (default ``kit_store``) es el módulo de estado; ``kit_state`` va con el worker.
    ``tz`` se usa para armar publishAt; ``exclude_paths`` saca packs de la elección.
    ``calendar_fn(channel)`` lee el calendario de YouTube del canal; si el día de
    ``next_slot`` está ocupado se pasa al próximo día libre del cron. En dry-run no se usa.
    """
    store = store or kit_store
    when = now or datetime.now()
    kit_cfg = app_config.get('kit_preview') or {}
    slots = kit_cfg.get('slots') or list(DEFAULT_SLOTS)
    slot = next_slot(when, slots)
    publish_iso = local_to_youtube_publish_at(True, slot, tz=tz)

    def already(iso, at):
        return {'skipped': True, 'reason': 'already_scheduled', 'publish_at': iso, 'slot': at}

    # Primero el estado del kit: si este mismo preview ya está programado, su propio video
    # ocupa el día en YouTube y no hay que avanzar a otro.
    if store.has_scheduled_run(publish_iso, db_path=db_path):
        return already(publish_iso, slot)
    first_slot = slot
    read_at = time.monotonic()
    if calendar_fn is not None and not dry_run:
        try:
            slot = free_slot(slot, when, slots, calendar_fn, channel, tz)
        except Exception as exc:
            raise SystemExit(f"No se pudo leer el calendario de YouTube ({type(exc).__name__}); "
                             "no se subió nada.") from None
        if slot is None:
            return {'skipped': True, 'reason': 'calendar_full', 'publish_at': None,
                    'slot': first_slot}
        publish_iso = local_to_youtube_publish_at(True, slot, tz=tz)
        if slot != first_slot and store.has_scheduled_run(publish_iso, db_path=db_path):
            return already(publish_iso, slot)

    list_packs = list_packs_fn or kit_source.list_packs
    packs = list_packs(
        kit_cfg.get('dropbox_root') or '',
        local_images_root=kit_cfg.get('local_images_root'),
        dbx=dbx,
        scan=kit_source.scan_settings(kit_cfg),
    )
    if exclude_paths:
        packs = [p for p in packs if p['dropbox_path'] not in set(exclude_paths)]
    history = store.selection_history(db_path=db_path)
    rng = random.Random(seed)
    try:
        selection = choose(
            packs,
            history,
            when,
            rng,
            cooldown_days=int(kit_cfg.get('pack_cooldown_days', 30)),
            loops_min=int(kit_cfg.get('loops_min', 6)),
            loops_max=int(kit_cfg.get('loops_max', 8)),
            require_image=not kit_art.generates(kit_cfg),
        )
    except KitSelectError as exc:
        raise SystemExit(str(exc)) from exc

    pack = selection['pack']
    audio_mode = selection['audio_mode']
    audio_files = selection['audio_files']
    image = selection['image']

    result: Dict[str, Any] = {
        'skipped': False,
        'dry_run': dry_run,
        'audio_mode': audio_mode,
        'pack': pack['name'],
        'pack_path': pack['dropbox_path'],
        'audio_files': [a['name'] for a in audio_files],
        'image': image['name'] if image else None,
        'warnings': selection.get('warnings') or [],
        'publish_at': publish_iso,
        'slot': slot,
        'trim_calls': 0,
    }

    if dry_run:
        print(f"audio_mode={audio_mode}")
        print(f"pack={pack['name']}")
        print(f"audio={[a['name'] for a in audio_files]}")
        print(f"image={image['name'] if image else '(fondo generado)'}")
        for w in result['warnings']:
            print(f"warning: {w}")
        return result

    trim_impl = trim_fn or trim_to_wav
    render_impl = render_fn or kit_render
    publish_impl = publish_fn or publish_preview
    trim_kw = _trim_settings(kit_cfg)
    out_dir = output_dir or kit_cfg.get('output_dir') or DEFAULT_OUTPUT
    os.makedirs(out_dir, exist_ok=True)
    safe_name = ''.join(c if c.isalnum() or c in ' -_' else '_' for c in pack['name'])
    video_out = os.path.join(
        out_dir, f"{safe_name.strip()}_{when.strftime('%Y%m%d_%H%M%S')}.mp4")

    pack_id = store.upsert_pack(pack['dropbox_path'], pack['name'], db_path=db_path)

    names_cfg = kit_cfg.get('names')
    video_name, used_names = kit_names.for_pack(
        pack['name'], pack['dropbox_path'], names_cfg, store, llm_call=llm_call)
    display_name = video_name or pack['name']
    tracking_id, templates = None, channel_templates
    if names_cfg and names_cfg.get('enabled', True) is not False:
        tracking_id = kit_names.new_tracking_id()
        if channel_templates.get('link'):
            templates = {**channel_templates,
                         'link': kit_names.track_link(channel_templates['link'], tracking_id)}

    with tempfile.TemporaryDirectory(prefix='kit_preview_') as tmp:
        image_local = _resolve_image_local(image, tmp, dbx=dbx) if image else None
        wavs: List[str] = []
        paths = [a['path'] for a in audio_files]
        locals_audio = kit_source.download_pack_files(paths, tmp, dbx=dbx)
        for i, local in enumerate(locals_audio):
            dest = os.path.join(tmp, f"trim_{i:02d}.wav")
            trim_impl(local, dest, **trim_kw)
            result['trim_calls'] += 1
            wavs.append(dest)

        # cover_mode auto: fondo con IA; si falla vuelve a la imagen manual y la corrida sigue.
        # cover_mode template: la portada llega completa y solo se arma el cuadro 16:9. Con el
        # estado local (kit_store) el tope de gasto cuenta solo lo de esta corrida.
        background_local, ref_images, complete = kit_art.for_cover(
            kit_cfg, pack['name'], display_name, image_local, store, rng, tmp, dbx=dbx,
            client=art_client, notify=art_notify)
        if not background_local:
            raise SystemExit("El kit no tiene imágenes y no se pudo generar el fondo.")
        if complete:
            frame_local, thumbnail = kit_cover.frame_for_video(
                kit_cfg.get('cover'), background_local, tmp)
        else:
            frame_local, thumbnail = (cover_fn or kit_cover.for_video)(
                kit_cfg.get('cover'), background_local, display_name, tmp)
        render_impl(frame_local, wavs, video_out)
        if calendar_fn is not None and time.monotonic() - read_at >= CALENDAR_MAX_AGE_S:
            # Render largo: el día pudo ocuparse a mano mientras tanto. Se relee antes del insert.
            try:
                still_free = free_slot(slot, when, slots, calendar_fn, channel, tz) == slot
            except Exception as exc:
                raise SystemExit(f"No se pudo releer el calendario de YouTube "
                                 f"({type(exc).__name__}); no se subió nada.") from None
            if not still_free:
                raise SystemExit("El día elegido se ocupó en YouTube durante el render; "
                                 "no se subió nada.")
        loops_meta = [{'name': a['name'], 'path': a['path']} for a in audio_files]
        pub = publish_impl(
            channel,
            video_out,
            thumbnail,
            display_name,
            slots,
            templates,
            pack_id=pack_id,
            audio_mode=audio_mode,
            db_path=db_path,
            # publish_preview recalcula next_slot(now): un minuto antes del slot elegido
            # devuelve ese mismo slot aunque se haya salteado un día ocupado.
            now=when if slot == first_slot else slot - timedelta(minutes=1),
            image_path=(image.get('path') if image else None) or image_local,
            loops_json=loops_meta,
            **({'video_name': video_name, 'tracking_id': tracking_id} if tracking_id else {}),
            **({'ref_images': ref_images} if ref_images else {}),
            **({'store': store, 'tz': tz} if (store is not kit_store or tz) else {}),
        )
        result['publish'] = pub
        kit_names.remember(store, pack['dropbox_path'], used_names, video_name)
        result['video'] = video_out
    return result


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Genera y sube un preview de loop kit.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Solo elige pack y loops; sin FFmpeg de video ni YouTube.')
    parser.add_argument('--channel', help='Canal loop_kits (obligatorio si hay varios).')
    parser.add_argument('--config', default=CONFIG_FILE, help='Ruta a app_config.json.')
    parser.add_argument('--seed', type=int, help='Semilla para elegir pack/loops/imagen.')
    args = parser.parse_args(argv)

    app_config = load_app_config(args.config)
    channel, templates = resolve_channel(app_config, args.channel)
    calendar_fn = None
    if not args.dry_run:
        from core import youtube
        calendar_fn = youtube.list_channel_calendar
    run_preview(
        app_config=app_config,
        channel=channel,
        channel_templates=templates,
        dry_run=args.dry_run,
        seed=args.seed,
        calendar_fn=calendar_fn,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
