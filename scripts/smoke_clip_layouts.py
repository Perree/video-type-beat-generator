#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: layouts recorte y split en 1080x1920 (lavfi de colores distintos)."""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.clip_render import build_render_cmd
from core.ffmpeg_util import resolve_tool


def _fail(msg):
    print("FAIL:", msg)
    return 1


def _video_size(ffprobe, path):
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height",
        "-of", "json", path,
    ]
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        return None
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        return None
    return int(streams[0]["width"]), int(streams[0]["height"])


def _run_ffmpeg(ffmpeg, cmd):
    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if result.returncode != 0:
        print(result.stderr)
    return result.returncode == 0


def main() -> int:
    ffmpeg = resolve_tool("ffmpeg")
    ffprobe = resolve_tool("ffprobe")
    if not ffmpeg or not ffprobe:
        return _fail("falta ffmpeg o ffprobe (bin/ o PATH)")

    folder = tempfile.mkdtemp(prefix="smoke_layouts_")
    screen = os.path.join(folder, "screen.mp4")
    camera = os.path.join(folder, "camera.mp4")
    out_recorte = os.path.join(folder, "recorte.mp4")
    out_split = os.path.join(folder, "split.mp4")

    if not _run_ffmpeg(ffmpeg, [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=red:s=1920x1080:d=4",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", screen,
    ]):
        return _fail("no se generó el lavfi rojo (recorte)")

    if not _run_ffmpeg(ffmpeg, [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=0x00FF00:s=640x360:d=4",
        "-f", "lavfi", "-i", "sine=frequency=880:duration=4",
        "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", camera,
    ]):
        return _fail("no se generó el lavfi verde (cámara split)")

    layouts = {
        "obs_unico": {"margin_v": 400},
        "recorte": {"x": 0, "y": 0, "w": 1920, "h": 1080, "margin_v": 400},
        "split": {
            "camera_region": {"x": 0, "y": 0, "w": 640, "h": 360},
            "screen_region": {"x": 0, "y": 0, "w": 1920, "h": 1080},
            "margin_v": 860,
        },
    }

    cmd_recorte = build_render_cmd(
        ffmpeg, screen, out_recorte, 0.0, 3.0, "recorte", layouts,
        video_codec="libx264",
    )
    if "-filter_complex" not in cmd_recorte:
        return _fail("recorte sin filter_complex")
    if not _run_ffmpeg(ffmpeg, cmd_recorte):
        return _fail("ffmpeg recorte falló")
    size_r = _video_size(ffprobe, out_recorte)
    if size_r != (1080, 1920):
        return _fail(f"recorte debe ser 1080x1920, llegó {size_r}")

    blue_screen = os.path.join(folder, "screen_blue.mp4")
    if not _run_ffmpeg(ffmpeg, [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "lavfi", "-i", "color=c=blue:s=1920x1080:d=4",
        "-f", "lavfi", "-i", "sine=frequency=220:duration=4",
        "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", blue_screen,
    ]):
        return _fail("no se generó el lavfi azul (pantalla split)")

    cmd_split = build_render_cmd(
        ffmpeg, blue_screen, out_split, 0.0, 3.0, "split", layouts,
        camera_path=camera, offset_ms=0, video_codec="libx264",
    )
    inputs = [cmd_split[i + 1] for i, a in enumerate(cmd_split) if a == "-i"]
    if len(inputs) != 2:
        return _fail(f"split debe tener 2 entradas de video, tiene {inputs}")
    if "vstack" not in " ".join(cmd_split):
        return _fail("split debe usar vstack")
    if not _run_ffmpeg(ffmpeg, cmd_split):
        return _fail("ffmpeg split falló")
    size_s = _video_size(ffprobe, out_split)
    if size_s != (1080, 1920):
        return _fail(f"split debe ser 1080x1920, llegó {size_s}")

    print("OK smoke_clip_layouts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
