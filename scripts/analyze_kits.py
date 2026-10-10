#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Análisis de solo lectura de los packs de loop kits (no sube ni escribe nada).

Uso: ``py -3 scripts/analyze_kits.py [--pack N] [--max-loops N] [--show-names]``.
Escribe exported_videos/loop_kits/analysis.json. Los packs se rotulan pack-NN
(orden alfabético) salvo con --show-names.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_source
from core.kit_analyze import VIDEO_MAX_SEC, VIDEO_MIN_SEC, analyze_pack

CONFIG_FILE = os.path.join(ROOT, 'config', 'app_config.json')
DEFAULT_OUT = os.path.join(ROOT, 'exported_videos', 'loop_kits', 'analysis.json')


def _fmt(sec):
    return '-' if sec is None else f'{sec:.1f}s'


def analyze_all(packs, pack_filter=None, max_loops=None, show_names=False, dbx=None,
                analyze_fn=analyze_pack):
    """Analiza los packs elegidos y devuelve la lista de resultados."""
    results = []
    for index, pack in enumerate(packs, start=1):
        label = f'pack-{index:02d}'
        if pack_filter and pack_filter.lower() not in (pack['name'].lower(), label):
            continue
        res = analyze_fn(pack, dbx=dbx, max_loops=max_loops)
        res['label'] = label
        if show_names:
            res['name'] = pack['name']
        results.append(res)
    return results


def format_table(results):
    """Tabla de texto legible, sin rutas."""
    head = f"{'pack':<10}{'loops':>6}{'prev?':>7}{'prev dur':>10}{'suma prev':>11}{'videos':>8}{'techo':>7}{'err':>5}"
    lines = [head, '-' * len(head)]
    for r in results:
        title = r.get('name') or r['label']
        v = r['videos']
        lines.append(
            f"{r['label']:<10}{r['loops_total']:>6}{('si' if r['preview_file'] else 'no'):>7}"
            f"{_fmt(r['preview_sec']):>10}{_fmt(r['preview_total_sec']):>11}"
            f"{v['videos']:>8}{v['upper_bound']:>7}{r['errors']:>5}"
            + (f'  {title}' if r.get('name') else ''))
    total = sum(r['videos']['videos'] for r in results)
    lines.append(f'Videos de {VIDEO_MIN_SEC:.0f}-{VIDEO_MAX_SEC:.0f}s armables sin repetir: {total}')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--pack', help='analiza un solo pack (nombre exacto o pack-NN)')
    parser.add_argument('--max-loops', type=int, help='mide solo los primeros N loops de cada pack')
    parser.add_argument('--show-names', action='store_true', help='incluye nombres de pack')
    parser.add_argument('--out', default=DEFAULT_OUT, help='ruta del JSON')
    args = parser.parse_args(argv)

    with open(CONFIG_FILE, encoding='utf-8') as f:
        kit_cfg = json.load(f).get('kit_preview') or {}
    packs = kit_source.list_packs(
        kit_cfg.get('dropbox_root') or '', local_images_root=kit_cfg.get('local_images_root'))
    results = analyze_all(packs, args.pack, args.max_loops, args.show_names)
    if not results:
        print('Ningún pack coincide.')
        return 1
    print(format_table(results))
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump({'packs': results}, f, ensure_ascii=False, indent=2)
    print('JSON guardado en exported_videos/loop_kits/analysis.json')
    return 0


if __name__ == '__main__':
    sys.exit(main())
