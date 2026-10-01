#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: argumentos de FFmpeg de los presets de core/clips.py (no codifica video)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import clips
from core.clips import Framing, build_clip_cmd


def _inputs(cmd):
    return [cmd[i + 1] for i, a in enumerate(cmd) if a == '-i']


def _after(cmd, flag):
    return cmd[cmd.index(flag) + 1]


def _fail(msg):
    print("FAIL:", msg)
    return 1


def main() -> int:
    framing = Framing(src_w=1920, src_h=1080, zoom=1.5, offset_x=0.25, offset_y=0.5)

    # Hook: 5 y 6 s, sin audio, 1080x1920 y con el texto
    for secs in (5, 6):
        cmd = build_clip_cmd(clips.PRESET_HOOK, 'ffmpeg', 'fondo.png', 'out.mp4', framing,
                             hook_text="Mi hook: 50% off", hook_seconds=secs)
        if len(_inputs(cmd)) != 1:
            return _fail(f"hook {secs}s no debe tener entrada de audio: {_inputs(cmd)}")
        if '-an' not in cmd:
            return _fail("hook debe llevar -an")
        if any(a in ('0:a:0', '0:a:0?', '1:a:0') for a in cmd):
            return _fail("hook no debe mapear audio")
        if float(_after(cmd, '-t')) != float(secs) or float(cmd[cmd.index('-t', cmd.index('-i')) + 1]) != float(secs):
            return _fail(f"duración del hook != {secs}")
        vf = _after(cmd, '-vf')
        if f"crop={clips.OUT_W}:{clips.OUT_H}:" not in vf:
            return _fail("hook sin crop 1080x1920")
        if "drawtext=" not in vf or "Mi hook\\: 50\\% off" not in vf:
            return _fail(f"hook sin el texto escapado: {vf}")
    for bad in (4, 7):
        try:
            build_clip_cmd(clips.PRESET_HOOK, 'ffmpeg', 'f.png', 'o.mp4', framing,
                           hook_text='x', hook_seconds=bad)
            return _fail(f"hook de {bad}s debería rechazarse")
        except ValueError:
            pass

    # Estudio: audio del beat y duración <= 30
    cmd = build_clip_cmd(clips.PRESET_ESTUDIO, 'ffmpeg', 'toma.mp4', 'out.mp4', framing,
                         start=2.0, end=100.0, audio_path='beat.mp3', audio_start=10.0)
    if _inputs(cmd) != ['toma.mp4', 'beat.mp3']:
        return _fail(f"estudio entradas: {_inputs(cmd)}")
    if '1:a:0' not in cmd or '0:a:0' in cmd or '0:a:0?' in cmd:
        return _fail("estudio debe usar solo el audio del beat")
    if float(cmd[cmd.index('-t', cmd.index('beat.mp3') - 4) + 1]) > 30:
        return _fail("estudio supera 30 s")
    if clips.clip_duration(clips.PRESET_ESTUDIO, 0, 100) != 30.0:
        return _fail("clip_duration estudio no limita a 30")
    if clips.clip_duration(clips.PRESET_ESTUDIO, 0, 12) != 12.0:
        return _fail("clip_duration estudio corto")

    # Loop: conserva el audio de la toma (una sola entrada, sin audio externo)
    cmd = build_clip_cmd(clips.PRESET_LOOP, 'ffmpeg', 'toma.mp4', 'out.mp4', framing,
                         start=1.0, end=9.0)
    if _inputs(cmd) != ['toma.mp4']:
        return _fail(f"loop no debe agregar audio externo: {_inputs(cmd)}")
    if '0:a:0?' not in cmd or '-an' in cmd:
        return _fail("loop debe conservar el audio de la toma")
    if abs(float(_after(cmd, '-t')) - 8.0) > 1e-6:
        return _fail("loop: duración != fin - inicio")

    # Encuadre: el recorte siempre cabe dentro de la imagen escalada
    for zoom in (1.0, 2.5, 99):
        for ox, oy in ((0, 0), (1, 1), (0.5, 0.5), (-3, 7)):
            f = Framing(1920, 1080, zoom, ox, oy)
            sw, sh = clips.scaled_size(f)
            x, y = clips.crop_origin(f)
            if x < 0 or y < 0 or x + clips.OUT_W > sw or y + clips.OUT_H > sh:
                return _fail(f"crop fuera de la imagen: zoom={zoom} off=({ox},{oy})")

    print("OK smoke_clips_cmd")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
