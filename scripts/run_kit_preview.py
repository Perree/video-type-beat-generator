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
from datetime import datetime
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
from core.sections import SECTION_LOOP_KITS, filter_channels_by_section

CONFIG_FILE = os.path.join('config', 'app_config.json')
DEFAULT_OUTPUT = os.path.join('exported_videos', 'loop_kits')


def load_app_config(path: Optional[str] = None) -> dict:
    """Lee app_config.json."""
    cfg_path = path or CONFIG_FILE
    with open(cfg_path, encoding='utf-8') as f:
        return json.load(f)


def resolve_channel(app_config: dict, channel_arg: Optional[str]) -> tuple:
    """Canal loop_kits y su dict de plantillas."""
    channels = app_config.get('channels') or {}
    kits = filter_channels_by_section(channels, SECTION_LOOP_KITS)
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
) -> Dict[str, Any]:
    """Ejecuta la corrida o dry-run. Parámetros inyectables para smokes.

    Returns:
        dict con skipped, dry_run, audio_mode, selection, publish, trim_calls, etc.

    ``store`` (default ``kit_store``) es el módulo de estado; ``kit_state`` va con el worker.
    ``tz`` se usa para armar publishAt; ``exclude_paths`` saca packs de la elección.
    """
    store = store or kit_store
    when = now or datetime.now()
    kit_cfg = app_config.get('kit_preview') or {}
    slots = kit_cfg.get('slots') or list(DEFAULT_SLOTS)
    slot = next_slot(when, slots)
    publish_iso = local_to_youtube_publish_at(True, slot, tz=tz)

    if store.has_scheduled_run(publish_iso, db_path=db_path):
        return {
            'skipped': True,
            'reason': 'already_scheduled',
            'publish_at': publish_iso,
            'slot': slot,
        }

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
            now=when,
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
    run_preview(
        app_config=app_config,
        channel=channel,
        channel_templates=templates,
        dry_run=args.dry_run,
        seed=args.seed,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
