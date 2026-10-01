"""Modo CLI (sin ventanas): python cli.py --canal X --grupo Y

Asigna todos los beats de la carpeta al canal/grupo indicado y genera los videos.
"""
import argparse
import json
import os
import sys

import generator

CONFIG_FILE = os.path.join('config', 'app_config.json')


def load_config():
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Genera videos de type beats sin abrir la interfaz.")
    p.add_argument('--canal', required=True, help="Nombre del canal (debe existir en la config)")
    p.add_argument('--grupo', required=True, help="Nombre del grupo dentro del canal")
    p.add_argument('--tipo', choices=['images', 'videos'], help="Tipo de contenido (por defecto: el último usado en la config)")
    p.add_argument('--beats', default='beats', help="Carpeta de beats (default: beats)")
    p.add_argument('--salida', help="Carpeta de salida (default: la de la config)")
    p.add_argument('--plantilla', help="Plantilla de nombre, con {name}, {channel}, {group}")
    p.add_argument('--overlay', action='store_true', help="Activa overlay de título y CTA")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    cfg = load_config()

    groups = cfg.get('channels', {}).get(args.canal, {}).get('groups')
    if groups is None:
        print(f"Error: el canal '{args.canal}' no existe. Canales: {', '.join(cfg.get('channels', {})) or '(ninguno)'}", file=sys.stderr)
        return 2
    if args.grupo not in groups:
        print(f"Error: el grupo '{args.grupo}' no existe en '{args.canal}'. Grupos: {', '.join(groups) or '(ninguno)'}", file=sys.stderr)
        return 2

    beats_folder = os.path.abspath(args.beats)
    images_folder = os.path.abspath('images')
    output_folder = os.path.abspath(args.salida or cfg.get('last_output_folder') or 'exported_videos')
    content_type = args.tipo or cfg.get('last_content_type', 'images')

    beat_files = generator.list_beat_files(beats_folder)
    if not beat_files:
        print(f"Error: no hay beats en {beats_folder}", file=sys.stderr)
        return 2

    picker = generator.ContentPicker(images_folder)
    if not generator.list_content(images_folder, 'videos', args.canal, args.grupo, content_type):
        print(f"Error: no hay contenido de tipo '{content_type}' en {args.canal}/{args.grupo}", file=sys.stderr)
        return 2

    os.makedirs(output_folder, exist_ok=True)
    beats_info = [{'beat_file': b, 'channel': args.canal, 'group': args.grupo, 'custom_name': ''} for b in beat_files]
    entries = []
    ok, total = generator.generate_batch(
        beats_info, beats_folder, output_folder, content_type, pick_content=picker,
        name_template=args.plantilla or cfg.get('name_template'),
        overlay_enabled=args.overlay or cfg.get('overlay_enabled', False),
        overlay_text=cfg.get('overlay_text'),
        cta_enabled=args.overlay or cfg.get('cta_enabled', False),
        cta_text=cfg.get('cta_text'),
        progress=lambda pct, msg: print(f"[{pct:3d}%] {msg}"),
        metadata_entries=entries,
    )
    meta = generator.write_metadata_csv(output_folder, entries)
    if meta:
        print(f"Metadata: {meta}")
    print(f"Listo: {ok} de {total} videos en {output_folder}")
    return 0 if ok == total else 1


if __name__ == '__main__':
    sys.exit(main())
