"""WyreScapes: flujo diario (prepare → metadata.json → publish a las 12:00 AR).

Uso:
    python scripts/wyrescapes_daily.py status  [--date AAAA-MM-DD]   # uploaded/prepared/rendered/pending
    python scripts/wyrescapes_daily.py prepare [--date AAAA-MM-DD] [--no-record]
    python scripts/wyrescapes_daily.py publish [--date AAAA-MM-DD] [--dry-run]

prepare: elige imagen, renderiza la mixtape y deja Videos/<día>/ con el .mp4, imagen.txt,
info.json y metadata.json vacío. publish: valida metadata.json y sube programado para las
12:00 AR de ese día (si ya pasó, publica ~15 min después). Si el día ya se subió, no vuelve a
subir. Los días sin video (PC apagada todo el día) se anotan en el registro y no se recuperan.
"""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # tokens/ y config/ relativos al proyecto
from core import wyrescapes_daily as wd
from core import wyrescapes_upload as wu
from core.mixtape_render import MixtapeRenderError


def _safe_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors='replace')
        except (AttributeError, ValueError):
            pass


def main(argv=None):
    _safe_console()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('step', choices=('status', 'prepare', 'publish'))
    parser.add_argument('--date', help='Día (AAAA-MM-DD); por defecto hoy')
    parser.add_argument('--base', default=wd.BASE, help='Carpeta WyreScapes')
    parser.add_argument('--no-record', action='store_true',
                        help='prepare de prueba: no toca los estados de tracks e imágenes')
    parser.add_argument('--dry-run', action='store_true', help='publish: valida sin subir')
    args = parser.parse_args(argv)
    try:
        day = wd.parse_day(args.date)
        if not args.date:
            for missed in wd.record_missed_days(day):
                print(f'Aviso: el {missed.isoformat()} no tuvo video (PC apagada); no se recupera.')
        if args.step == 'status':
            print(json.dumps(wd.status(day, base=args.base), ensure_ascii=False, indent=2))
            return 0
        if args.step == 'prepare':
            info = wd.prepare(day, base=args.base, record=not args.no_record)
            for warning in info['warnings']:
                print(f'Aviso: {warning}')
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0
        status, detail = wd.publish(day, base=args.base, dry_run=args.dry_run)
    except (wd.DailyError, wu.UploadError, MixtapeRenderError, OSError, ValueError) as exc:
        print(f'Error: {exc}')
        return 1
    if status == 'already':
        print(f'Ya subido, no se vuelve a subir: {detail.get("url")}')
    elif status == 'dry-run':
        print('DRY-RUN (no se subió nada):')
        print(json.dumps(detail, ensure_ascii=False, indent=2))
    else:
        print(f'Subido (privado, se publica {detail["publish_at"]}): {detail["url"]}')
        if detail.get('thumbnail_error'):
            print(f'Aviso: {detail["thumbnail_error"]}')
        if detail.get('pinned_comment_file'):
            print(f'Comentario para fijar a mano: {detail["pinned_comment_file"]}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
