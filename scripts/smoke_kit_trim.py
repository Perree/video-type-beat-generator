#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del corte al primer silencio. Sin ffmpeg en bin/ ni PATH: SKIP y exit 0."""

import math
import os
import struct
import sys
import tempfile
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.ffmpeg_util import resolve_tool
from core.kit_trim import KitTrimError, preview_end_sec, trim_to_wav

SAMPLE_RATE = 22050
FREQ = 440.0
AMPLITUDE = 0.5


def _write_wav(path, parts):
    """Escribe mono 16-bit. parts es una lista de (segundos, silencio)."""
    frames = bytearray()
    offset = 0
    for seconds, silent in parts:
        count = int(round(seconds * SAMPLE_RATE))
        if silent:
            frames += b"\x00\x00" * count
        else:
            chunk = bytearray()
            for i in range(count):
                t = (offset + i) / SAMPLE_RATE
                sample = int(AMPLITUDE * 32767 * math.sin(2 * math.pi * FREQ * t))
                chunk += struct.pack("<h", sample)
            frames += chunk
        offset += count
    with wave.open(path, "w") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(frames)
    return offset / SAMPLE_RATE


def _wav_duration(path):
    with wave.open(path, "r") as handle:
        return handle.getnframes() / float(handle.getframerate())


def main() -> int:
    # resolve_tool busca bin/ relativo al cwd.
    os.chdir(ROOT)
    if not resolve_tool("ffmpeg"):
        print("SKIP: no hay ffmpeg en bin/ ni en PATH")
        return 0

    folder = tempfile.mkdtemp(prefix="smoke_kit_trim_")
    layered = os.path.join(folder, "layered.wav")
    short = os.path.join(folder, "short.wav")
    long_tone = os.path.join(folder, "long.wav")
    trimmed = os.path.join(folder, "trimmed.wav")

    # 3 s de tono + 0,5 s de silencio + 3 s de tono (capas que no deben entrar).
    _write_wav(layered, [(3.0, False), (0.5, True), (3.0, False)])
    end = preview_end_sec(layered)
    if not (2.7 <= end <= 3.3):
        print(f"FAIL: corte del loop con silencio = {end:.3f}s, se esperaba 2.7–3.3")
        return 1
    trim_to_wav(layered, trimmed)
    trimmed_dur = _wav_duration(trimmed)
    if not (2.7 <= trimmed_dur <= 3.3):
        print(f"FAIL: el wav cortado dura {trimmed_dur:.3f}s e incluye audio posterior")
        return 1
    print(f"OK corte con silencio: {end:.3f}s, wav {trimmed_dur:.3f}s")

    short_dur = _write_wav(short, [(2.0, False)])
    end_short = preview_end_sec(short)
    if abs(end_short - short_dur) > 0.05:
        print(f"FAIL: el tono de 2s debía usarse entero, devolvió {end_short:.3f}s")
        return 1
    print(f"OK sin silencio corto: {end_short:.3f}s")

    _write_wav(long_tone, [(50.0, False)])
    try:
        preview_end_sec(long_tone)
    except KitTrimError as exc:
        print(f"OK sin silencio de 50s: {exc}")
        return 0
    print("FAIL: un audio de 50s sin silencio no lanzó excepción")
    return 1


if __name__ == "__main__":
    sys.exit(main())
