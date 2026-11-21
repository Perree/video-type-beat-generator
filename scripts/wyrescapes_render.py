"""WyreScapes: arma la mixtape del día (cada track una vez, orden nuevo) y la renderiza.

Uso:
    python scripts/wyrescapes_render.py --image "C:/.../Imagenes/foto.jfif"
    python scripts/wyrescapes_render.py --image foto.jfif --dry-run   # solo muestra el plan

El estado de uso se guarda solo si el render sale bien.
"""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core import mixtape
from core.mixtape_render import MixtapeRenderError, render, track_durations

BASE = Path.home() / 'Desktop' / 'WyreScapes'


def _fmt(seconds):
    seconds = int(round(seconds))
    return f'{seconds // 3600}:{seconds % 3600 // 60:02d}:{seconds % 60:02d}'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--image', required=True, help='Imagen fija del video')
    parser.add_argument('--tracks', default=str(BASE / 'Tracks'))
    parser.add_argument('--out-dir', default=str(BASE / 'Videos'))
    parser.add_argument('--state', default=str(ROOT / mixtape.DEFAULT_STATE_PATH))
    parser.add_argument('--max-minutes', type=float, default=mixtape.DEFAULT_MAX_SECONDS / 60)
    parser.add_argument('--dry-run', action='store_true', help='No renderiza ni guarda estado')
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
    if args.dry_run:
        return 0

    by_name = {os.path.basename(p): p for p in paths}
    out = os.path.join(args.out_dir, f"wyrescapes_{datetime.now():%Y%m%d_%H%M%S}.mp4")
    try:
        render([by_name[n] for n in order], args.image, out, total)
    except MixtapeRenderError as exc:
        print(f'Error: {exc}')
        return 1
    mixtape.save_state(mixtape.record_use(state, order), args.state)
    print(f'Listo: {out}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
