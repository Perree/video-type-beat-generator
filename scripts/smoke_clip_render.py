#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: lavfi color+sine 8 s, 4 palabras, mp4 1080x1920 de ~4-8 s.

Si el ffmpeg no trae el filtro ass (libass), sale 1 con un mensaje claro.
No usa red ni la base de la app.
"""
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.clip_render import ASS_MISSING, render_clip
from core.ffmpeg_util import ffmpeg_has_ass_filter, resolve_tool

WORDS = [
    {"t0": 0.4, "t1": 1.0, "w": "hola"},
    {"t0": 1.1, "t1": 1.8, "w": "esto"},
    {"t0": 1.9, "t1": 2.6, "w": "es"},
    {"t0": 2.7, "t1": 3.6, "w": "prueba"},
]


def _probe(ffprobe, path):
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height:format=duration",
        "-of", "json", path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print("FAIL: ffprobe", result.stderr)
        return None
    return json.loads(result.stdout)


def main() -> int:
    ffmpeg = resolve_tool("ffmpeg")
    ffprobe = resolve_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        print("FAIL: falta ffmpeg o ffprobe (bin/ o PATH)")
        return 1
    if not ffmpeg_has_ass_filter(ffmpeg):
        print(ASS_MISSING)
        return 1

    folder = tempfile.mkdtemp(prefix="smoke_clip_")
    src = os.path.join(folder, "color_sine.mp4")
    dst = os.path.join(folder, "short.mp4")
    ass_path = os.path.join(folder, "c0.ass")
    gen = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "color=c=0x2244aa:s=1280x720:r=30:d=8",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000:duration=8",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", src],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if gen.returncode != 0 or not os.path.isfile(src):
        print("FAIL: no se generó el video de prueba", gen.stderr)
        return 1

    try:
        render_clip(
            src, dst, 0.0, 6.0, WORDS,
            {"subtitles": {"font": "Arial", "size": 64, "margin_v": 400}},
            ass_path=ass_path, ffmpeg=ffmpeg,
        )
    except Exception as exc:
        print("FAIL: render", exc)
        return 1

    info = _probe(ffprobe, dst)
    if not info or not info.get("streams"):
        print("FAIL: sin stream de video", info)
        return 1
    stream = info["streams"][0]
    width = int(stream.get("width") or 0)
    height = int(stream.get("height") or 0)
    duration = float((info.get("format") or {}).get("duration") or 0)
    if width != 1080 or height != 1920 or not (4.0 <= duration <= 8.0):
        print(f"FAIL: esperado 1080x1920 y 4-8 s, llegó {width}x{height}, {duration:.3f}s")
        return 1
    ass_text = open(ass_path, encoding="utf-8-sig").read()
    if any(word["w"] not in ass_text for word in WORDS) or r"\c" not in ass_text:
        print("FAIL: el ASS no tiene las 4 palabras o el color de la palabra activa")
        return 1

    print(f"OK smoke_clip_render {width}x{height} {duration:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
