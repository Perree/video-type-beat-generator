"""WyreScapes: arma la mixtape del día (cada track una vez, orden nuevo) y la renderiza.

Uso:
    python scripts/wyrescapes_render.py                    # imagen = la siguiente de la rotación
    python scripts/wyrescapes_render.py --image foto.jfif  # imagen elegida a mano
    python scripts/wyrescapes_render.py --dry-run          # solo muestra el plan
    python scripts/wyrescapes_render.py --no-record        # render de prueba, no toca el estado

El estado de uso (tracks e imagen) se guarda solo si el render sale bien.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import image_rotation, mixtape
from core.mixtape_render import MixtapeRenderError, render, track_durations

BASE = Path.home() / 'Desktop' / 'WyreScapes'


def _fmt(seconds):
    seconds = int(round(seconds))
    return f'{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}'


def _safe_console():
    """Nombres con emoji (p. ej. «🌊.jfif») no deben romper una consola cp1252."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _safe_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--image', help='Imagen fija del video (por defecto, la rotación)')
    parser.add_argument('--images', default=str(BASE / 'Imagenes'),
                        help='Carpeta de imágenes (sin subcarpetas: Refes nunca entra)')
    parser.add_argument('--image-state', default=str(ROOT / image_rotation.DEFAULT_STATE_PATH))
    parser.add_argument('--tracks', default=str(BASE / 'Tracks'))
    parser.add_argument('--out-dir', default=str(BASE / 'Videos'))
    parser.add_argument('--state', default=str(ROOT / mixtape.DEFAULT_STATE_PATH))
    parser.add_argument('--max-minutes', type=float, default=mixtape.DEFAULT_MAX_SECONDS / 60)
    parser.add_argument('--dry-run', action='store_true', help='No renderiza ni guarda estado')
    parser.add_argument('--no-record', action='store_true',
                        help='Renderiza pero no guarda estado (prueba)')
    args = parser.parse_args(argv)

    paths = mixtape.scan_tracks(args.tracks)
    durations = track_durations(paths)
    state = mixtape.load_state(args.state)
    order = mixtape.plan_mixtape(list(durations), durations, state,
                                 max_seconds=args.max_minutes * 60)
    if not order:
        print(f'No hay tracks legibles en {args.tracks}')
        return 1
    total = sum(durations[n] for n in order)
    print(f'{len(order)} de {len(paths)} tracks, {_fmt(total)}:')
    for name in order:
        print(f'  {name}  ({_fmt(durations[name])})')

    image, image_state = args.image, None
    if not image:
        image, image_state, warnings = image_rotation.pick_image(
            image_rotation.scan_images(args.images), image_rotation.load_state(args.image_state))
        for warning in warnings:
            print(f'Aviso: {warning}')
        if not image:
            print(f'No hay imágenes utilizables en {args.images}')
            return 1
    print(f'Imagen: {image}')
    if args.dry_run:
        return 0

    by_name = {os.path.basename(p): p for p in paths}
    out = os.path.join(args.out_dir, f"wyrescapes_{datetime.now():%Y%m%d_%H%M%S}.mp4")
    try:
        render([by_name[n] for n in order], image, out, total)
    except MixtapeRenderError as exc:
        print(f'Error: {exc}')
        return 1
    with open(os.path.splitext(out)[0] + '.json', 'w', encoding='utf-8') as fh:
        json.dump({'image': os.path.abspath(image), 'tracks': order,
                   'seconds': round(total, 3)}, fh, ensure_ascii=False, indent=2)
    if args.no_record:
        print(f'Listo (prueba, estado sin cambios): {out}')
        return 0
    mixtape.save_state(mixtape.record_use(state, order), args.state)
    if image_state is not None:
        image_rotation.save_state(image_state, args.image_state)
    print(f'Listo: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
