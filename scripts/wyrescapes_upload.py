"""WyreScapes: conecta AllusionBeatz y sube la mixtape programada a las 12:00 de Argentina.

Uso:
    python scripts/wyrescapes_upload.py --connect          # una vez: OAuth en el navegador
    python scripts/wyrescapes_upload.py --check            # verifica el token (canal correcto)
    python scripts/wyrescapes_upload.py --video V.mp4 --meta meta.json [--dry-run]

``meta.json``: ``{"title": ..., "description": ..., "tags": [...], "pinned_comment": ...}``.
La imagen (miniatura) sale del ``.json`` que deja el render al lado del video, o de --image.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # tokens/ y config/ relativos al proyecto
from core import wyrescapes_upload as wu


def _safe_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass


def _sidecar_image(video):
    try:
        with open(os.path.splitext(video)[0] + '.json', 'r', encoding='utf-8') as fh:
            return json.load(fh).get('image')
    except (OSError, ValueError, AttributeError):
        return None


def main(argv=None):
    _safe_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--connect', action='store_true', help='Autorizar el canal (navegador)')
    parser.add_argument('--check', action='store_true', help='Verificar el token guardado')
    parser.add_argument('--video')
    parser.add_argument('--meta', help='JSON con title, description, tags, pinned_comment')
    parser.add_argument('--image', help='Imagen para la miniatura (por defecto, la del render)')
    parser.add_argument('--log', default=wu.DEFAULT_LOG_PATH)
    parser.add_argument('--dry-run', action='store_true', help='Muestra qué se subiría')
    args = parser.parse_args(argv)

    try:
        if args.connect:
            print(f'Conectado: {wu.connect()} ({wu.CHANNEL_ID})')
            return 0
        if args.check:
            found = wu.token_channel_id()
            print('Token OK: AllusionBeatz' if found == wu.CHANNEL_ID
                  else f'El token es de otro canal: {found}')
            return 0 if found == wu.CHANNEL_ID else 1
        if not args.video or not args.meta:
            parser.error('--video y --meta son obligatorios para subir')
        with open(args.meta, 'r', encoding='utf-8') as fh:
            meta = wu.validate_meta(json.load(fh))
        image = args.image or _sidecar_image(args.video)
        slot = wu.next_publish_time()
        print(f'Video: {args.video}\nImagen: {image or "(sin miniatura)"}\n'
              f'Programado: {slot:%Y-%m-%d %H:%M} AR ({wu.publish_at_utc(slot)})\n'
              f'Título: {meta["title"]}\nTags: {", ".join(meta["tags"])}\n'
              f'Descripción:\n{meta["description"]}')
        if args.dry_run:
            return 0
        entry = wu.upload_scheduled(args.video, meta, image, slot, log_path=args.log,
                                    progress=lambda p: print(f'  {p}%', flush=True))
    except (wu.UploadError, wu.youtube.YouTubeError, OSError, ValueError) as exc:
        print(f'Error: {exc}')
        return 1
    print(f'Subido (privado, se publica {slot:%d/%m %H:%M} AR): {entry["url"]}')
    if entry['thumbnail_error']:
        print(f'Aviso: {entry["thumbnail_error"]}')
    if entry['pinned_comment_file']:
        print(f'Comentario para fijar a mano: {entry["pinned_comment_file"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
