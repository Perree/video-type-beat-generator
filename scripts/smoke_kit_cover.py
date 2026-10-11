#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: kit_cover (portada 1500x1500, título largo dentro del cuadro, plantilla sin medidas fijas)."""

import os
import sys
import tempfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_cover

FAILS = []

LONG_TITLE = "Una portada con un titulo extremadamente largo para probar el ajuste de tamano"

# Solo el título: sin piezas fijas, borde, grano, viñeta ni sombra, sobre fondo negro.
BARE = {
    'brand': {'text': ''}, 'label': {'text': ''}, 'stamp': {'text': ''},
    'barcode': {'bars': 0}, 'border': {'width': 0}, 'grain': {'amount': 0},
    'vignette': {'strength': 0},
    'background': {'brightness': 1, 'tint_amount': 0, 'saturation': 1, 'contrast': 1},
    'title': {'shadow_opacity': 0},
}


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _make_background(path, w=1200, h=800):
    x = np.linspace(0, 255, w, dtype=np.float32)[None, :]
    y = np.linspace(0, 255, h, dtype=np.float32)[:, None]
    rng = np.random.default_rng(1)
    arr = np.stack([x + 0 * y, y + 0 * x, (x + y) / 2 + rng.random((h, w)) * 20], -1)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(path)


def _bright_bbox(path):
    arr = np.asarray(Image.open(path).convert('L'))
    ys, xs = np.nonzero(arr > 40)
    if not len(xs):
        return None
    return xs.min(), ys.min(), xs.max() + 1, ys.max() + 1


def _inside(bbox, box, size, tol=2):
    x0, y0, x1, y1 = [v * size for v in box]
    return (bbox[0] >= x0 - tol and bbox[1] >= y0 - tol
            and bbox[2] <= x1 + tol and bbox[3] <= y1 + tol)


def _check_default(tmp, bg):
    out = kit_cover.compose(bg, "Sunset Drive", os.path.join(tmp, 'cover.png'))
    check(out == os.path.join(tmp, 'cover.png') and os.path.exists(out), "compose no devolvió la ruta")
    check(Image.open(out).size == (1500, 1500), "la portada no es 1500x1500")
    again = kit_cover.compose(bg, "Sunset Drive", os.path.join(tmp, 'cover2.png'))
    check(np.array_equal(np.asarray(Image.open(out)), np.asarray(Image.open(again))),
          "mismo título y fondo no da la misma portada")
    other = kit_cover.compose(bg, "Otro Titulo", os.path.join(tmp, 'cover3.png'))
    check(not np.array_equal(np.asarray(Image.open(out)), np.asarray(Image.open(other))),
          "otro título dio la misma portada")
    return out


def _check_long_title(tmp):
    black = os.path.join(tmp, 'black.png')
    Image.new('RGB', (400, 400), 'black').save(black)
    box = kit_cover.DEFAULT_TEMPLATE['title']['box']
    for title in (LONG_TITLE, "Supercalifragilisticexpialidocious", "A"):
        out = kit_cover.compose(black, title, os.path.join(tmp, 'long.png'), BARE)
        bbox = _bright_bbox(out)
        check(bbox is not None, "el título no se dibujó: %r" % title[:12])
        if bbox:
            check(_inside(bbox, box, 1500), "el título se sale de su caja: %r %s" % (title[:12], bbox))
    # el título largo termina con un cuerpo menor que el corto
    lines_long, font_long = kit_cover._fit_title(
        kit_cover._merge(kit_cover.DEFAULT_TEMPLATE, None), LONG_TITLE.upper(), 1200, 650)
    lines_short, font_short = kit_cover._fit_title(
        kit_cover._merge(kit_cover.DEFAULT_TEMPLATE, None), "SUNSET", 1200, 650)
    check(font_long.size < font_short.size, "el título largo no achicó el cuerpo")
    check(len(lines_long) <= kit_cover.DEFAULT_TEMPLATE['title']['max_lines'], "demasiadas líneas")
    return black


def _check_template_drives_everything(tmp, bg, black):
    # Otro tamaño y otra caja: todo sigue a la plantilla.
    tpl = dict(BARE, size=800, title={'shadow_opacity': 0, 'box': [0.2, 0.1, 0.6, 0.5]})
    out = kit_cover.compose(black, LONG_TITLE, os.path.join(tmp, 'small.png'), tpl)
    check(Image.open(out).size == (800, 800), "el tamaño de la plantilla no se respeta")
    bbox = _bright_bbox(out)
    check(bbox is not None and _inside(bbox, [0.2, 0.1, 0.6, 0.5], 800),
          "la caja del título de la plantilla no se respeta %s" % (bbox,))
    # Cambiar textos, colores y posiciones de las piezas fijas cambia el resultado.
    base = kit_cover.compose(bg, "Titulo", os.path.join(tmp, 'a.png'))
    variants = {
        'brand': {'brand': {'text': 'OTRA MARCA'}},
        'label': {'label': {'text': 'DRUM KIT', 'y': 0.9}},
        'stamp': {'stamp': {'text': 'HECHO\nA MANO', 'center': [0.8, 0.2]}},
        'barcode': {'barcode': {'box': [0.1, 0.1, 0.4, 0.2]}},
        'border': {'border': {'width': 0.06, 'color': '#ff0000'}},
        'grain': {'grain': {'amount': 0.3}},
        'vignette': {'vignette': {'strength': 0.1}},
        'color': {'title': {'color': '#ff00ff'}},
    }
    a = np.asarray(Image.open(base))
    for name, extra in variants.items():
        out = kit_cover.compose(bg, "Titulo", os.path.join(tmp, 'v_%s.png' % name), extra)
        check(not np.array_equal(a, np.asarray(Image.open(out))),
              "la plantilla no controla %r" % name)
    # Piezas fijas apagables por plantilla.
    out = kit_cover.compose(bg, "Titulo", os.path.join(tmp, 'off.png'), BARE)
    check(not np.array_equal(a, np.asarray(Image.open(out))), "apagar piezas no cambia nada")


def _check_frame(tmp, cover):
    out = kit_cover.to_video_frame(cover, os.path.join(tmp, 'frame.png'))
    im = Image.open(out)
    check(im.size == (1920, 1080), "el cuadro 16:9 no es 1920x1080")
    arr = np.asarray(im.convert('RGB')).astype(np.int32)
    cov = np.asarray(Image.open(cover).convert('RGB').resize((972, 972))).astype(np.int32)
    center = arr[54:54 + 972, 474:474 + 972]
    check(np.abs(center - cov).mean() < 3, "la portada no está centrada en el cuadro")
    check(np.abs(arr[:, :300] - arr[:, :300].mean(axis=(0, 1))).mean() < 60, "el fondo no es difuso")
    out = kit_cover.to_video_frame(cover, os.path.join(tmp, 'frame2.png'),
                                   {'size': [1280, 720], 'cover_height': 0.5})
    check(Image.open(out).size == (1280, 720), "el tamaño del cuadro no sigue a la configuración")


def _check_finished_cover(tmp, cover):
    """Portada completa (cover_mode template): cuadro y miniatura sin pasar por compose."""
    real = kit_cover.compose

    def forbidden(*_a, **_k):
        raise AssertionError('compose no debe correr')
    kit_cover.compose = forbidden
    try:
        for i, cfg in enumerate((None, {'enabled': False}, {'frame': {'size': [640, 360]}})):
            work = os.path.join(tmp, f'finished{i}')
            os.makedirs(work)
            frame, thumb = kit_cover.frame_for_video(cfg, cover, work)
            size = (640, 360) if cfg and cfg.get('frame') else (1920, 1080)
            check(Image.open(frame).size == size, f"frame_for_video: cuadro {size} con cfg={cfg}")
            check(thumb.endswith('.jpg') and Image.open(thumb).size == size,
                  "frame_for_video: falta la miniatura")
    finally:
        kit_cover.compose = real


def main():
    with tempfile.TemporaryDirectory() as tmp:
        bg = os.path.join(tmp, 'bg.png')
        _make_background(bg)
        cover = _check_default(tmp, bg)
        black = _check_long_title(tmp)
        _check_template_drives_everything(tmp, bg, black)
        _check_frame(tmp, cover)
        _check_finished_cover(tmp, cover)
    if FAILS:
        for f in FAILS:
            print("FAIL:", f)
        return 1
    print("OK smoke_kit_cover")
    return 0


if __name__ == '__main__':
    sys.exit(main())
