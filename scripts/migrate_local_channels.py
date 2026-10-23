#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Copia los canales del modo manual viejo a ``<Dropbox>/TypeBeat Local``.

Uso:
    py -3 scripts/migrate_local_channels.py                 # muestra lo que haría
    py -3 scripts/migrate_local_channels.py --apply         # copia (nunca borra ni pisa)
    py -3 scripts/migrate_local_channels.py --root "D:/otra/carpeta" --apply
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import dropbox_local, local_migration  # noqa: E402


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--root', help='Carpeta local de canales (por defecto <Dropbox>/TypeBeat Local).')
    parser.add_argument('--apply', action='store_true', help='Copiar de verdad.')
    args = parser.parse_args(argv)
    root = args.root or dropbox_local.default_local_root()
    if not root:
        print('No se encontró la carpeta de Dropbox: pasá --root.')
        return 2
    actions = local_migration.plan(ROOT, root)
    print(f'Destino: {root}')
    for line in local_migration.summary(actions):
        print(line)
    if not args.apply:
        print('\nNo se copió nada (dry-run). Repetí con --apply para copiar.')
        return 0
    result = local_migration.apply(actions, root)
    print(f"\nListo: {result['canales']} canales nuevos, {result['archivos']} archivos copiados.")
    for error in result['errores']:
        print('✗', error)
    return 1 if result['errores'] else 0


if __name__ == '__main__':
    sys.exit(main())
