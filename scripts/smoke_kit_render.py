#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del render 1920x1080 con 1 o 2 wav. Sin ffmpeg: SKIP y exit 0."""

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import wave
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.ffmpeg_util import get_media_duration, resolve_tool
from core.kit_render import KitRenderError, render

SAMPLE_RATE = 22050
FREQ = 440.0
AMPLITUDE = 0.5
TOLERANCE_S = 0.3


def _write_wav(path, seconds):
    """Escribe un tono mono 16-bit y devuelve la duración en segundos."""
    count = int(round(seconds * SAMPLE_RATE))
    frames = bytearray()
    for i in range(count):
        t = i / SAMPLE_RATE
        sample = int(AMPLITUDE * 32767 * math.sin(2 * math.pi * FREQ * t))
        frames += struct.pack("<h", sample)
    with wave.open(path, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)
    return count / SAMPLE_RATE


def _write_png(path, width, height, rgb):
    """PNG RGB mínimo con zlib/struct (sin Pillow)."""
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xffffffff
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = b"".join(b"\x00" + (bytes(rgb) * width) for _ in range(height))
    with open(path, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)))
        handle.write(chunk(b"IDAT", zlib.compress(raw, 9)))
        handle.write(chunk(b"IEND", b""))


def _probe_video(ffprobe, path):
    """width, height y duration del mp4, o None si ffprobe falla."""
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
    data = json.loads(result.stdout)
    stream = (data.get("streams") or [{}])[0]
    duration = float((data.get("format") or {}).get("duration") or 0)
    return int(stream.get("width") or 0), int(stream.get("height") or 0), duration


def _assert_mp4(ffprobe, path, expected_dur, label):
    """Falla el smoke si el mp4 no es 1920x1080 o la duración se aleja > 0,3 s."""
    probed = _probe_video(ffprobe, path)
    if not probed:
        return 1
    width, height, duration = probed
    if width != 1920 or height != 1080:
        print(f"FAIL {label}: {width}x{height}, se esperaba 1920x1080")
        return 1
    if abs(duration - expected_dur) > TOLERANCE_S:
        print(
            f"FAIL {label}: duración {duration:.3f}s, "
            f"esperada {expected_dur:.3f}s ± {TOLERANCE_S}"
        )
        return 1
    print(f"OK {label}: {width}x{height} {duration:.3f}s (ref {expected_dur:.3f}s)")
    return 0


def main() -> int:
    os.chdir(ROOT)
    if not resolve_tool("ffmpeg"):
        print("SKIP: no hay ffmpeg en bin/ ni en PATH")
        return 0
    ffprobe = resolve_tool("ffprobe")
    if not ffprobe:
        print("FAIL: hay ffmpeg pero no ffprobe")
        return 1

    folder = tempfile.mkdtemp(prefix="smoke_kit_render_")
    png = os.path.join(folder, "still.png")
    wav_a = os.path.join(folder, "a.wav")
    wav_b = os.path.join(folder, "b.wav")
    wav_one = os.path.join(folder, "one.wav")
    out_concat = os.path.join(folder, "two.mp4")
    out_one = os.path.join(folder, "one.mp4")

    # 640x480 fuerza pad; si el scale estuviera mal, no saldría 1920x1080.
    _write_png(png, 640, 480, (32, 96, 192))
    dur_a = _write_wav(wav_a, 0.6)
    dur_b = _write_wav(wav_b, 0.9)
    dur_one = _write_wav(wav_one, 0.8)

    try:
        render(png, [wav_a, wav_b], out_concat)
        render(png, [wav_one], out_one)
    except KitRenderError as exc:
        print(f"FAIL: render {exc}")
        return 1

    if _assert_mp4(ffprobe, out_concat, dur_a + dur_b, "caso A (dos wav)") != 0:
        return 1
    if _assert_mp4(ffprobe, out_one, dur_one, "caso B (un wav)") != 0:
        return 1

    # Doble chequeo con la misma función que usa el render.
    concat_dur = get_media_duration(out_concat)
    if concat_dur is None or abs(concat_dur - (dur_a + dur_b)) > TOLERANCE_S:
        print(f"FAIL: get_media_duration concat = {concat_dur}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
