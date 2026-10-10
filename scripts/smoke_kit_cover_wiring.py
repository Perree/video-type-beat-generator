#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: la portada se conecta a run_preview (render y miniatura) solo si hay kit_preview.cover."""

import os
import sys
import tempfile
from datetime import datetime

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, 'scripts')):
    if p not in sys.path:
        sys.path.insert(0, p)

from core import kit_source
from run_kit_preview import run_preview

NOW = datetime(2026, 10, 5, 10, 0)
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _fake_download(paths, dest_dir, dbx=None):
    out = []
    for i, p in enumerate(paths):
        dest = os.path.join(dest_dir, f"dl_{i}.wav")
        open(dest, 'wb').close()
        out.append(dest)
    return out


def _run(tmp, cover_cfg, seed=1):
    bg = os.path.join(tmp, 'bg.png')
    Image.new('RGB', (900, 600), (120, 90, 60)).save(bg)
    pack = [{
        'name': 'PackPreview', 'dropbox_path': '/kits/PackPreview',
        'loops': [{'name': 'L1.wav', 'path': '/kits/PackPreview/l1.wav'}],
        'named_previews': [{'name': 'Preview.wav', 'path': '/kits/PackPreview/Preview.wav'}],
        'images': [{'name': 'bg.png', 'path': bg, 'source': 'local'}],
    }]
    kit_cfg = {'dropbox_root': '/loop_kits', 'prefer_named_preview': True}
    if cover_cfg is not None:
        kit_cfg['cover'] = cover_cfg
    seen = {}

    def render(image, wavs, out):
        im = Image.open(image)
        seen['render'] = (image, im.size)
        return out

    def publish(channel, video, thumbnail, name, slots, templates, **kw):
        seen['thumb'] = thumbnail
        seen['thumb_size'] = Image.open(thumbnail).size if thumbnail else None
        seen['image_path'] = kw.get('image_path')
        return {'youtube_id': 'x', 'title': 't'}

    out = run_preview(
        app_config={'kit_preview': kit_cfg, 'channels': {'c': {'section': 'loop_kits'}}},
        channel='c', channel_templates={'title_template': '{name}'}, now=NOW, seed=seed,
        db_path=os.path.join(tmp, 'k.db'),
        list_packs_fn=lambda *_a, **_k: pack, render_fn=render, publish_fn=publish,
        output_dir=os.path.join(tmp, 'out'))
    return bg, seen, out


def main():
    real = kit_source.download_pack_files
    kit_source.download_pack_files = _fake_download
    try:
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            bg, seen, out = _run(tmp, {'template': {'brand': {'text': 'TEST BRAND'}}})
            check(not out.get('skipped'), "la corrida se saltó")
            check(seen['render'][1] == (1920, 1080), "el render no recibió el cuadro 16:9 de la portada")
            check(seen['render'][0] != bg, "el render recibió la imagen original")
            check(seen['thumb'] and seen['thumb'].endswith('.jpg') and seen['thumb_size'] == (1920, 1080),
                  "falta la miniatura 1920x1080")
            check(seen['image_path'] == bg, "image_path del historial debe seguir siendo la imagen original")

        for label, cfg in (('sin cover', None), ('enabled false', {'enabled': False})):
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                bg, seen, _ = _run(tmp, cfg)
                check(seen['render'][0] == bg, f"{label}: el render debía recibir la imagen original")
                check(seen['thumb'] is None, f"{label}: no debía haber miniatura")
    finally:
        kit_source.download_pack_files = real

    if FAILS:
        for f in FAILS:
            print("FAIL:", f)
        return 1
    print("OK smoke_kit_cover_wiring")
    return 0


if __name__ == '__main__':
    sys.exit(main())
