#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: lavfi sine de 2 s -> WAV 16000 Hz mono, sin bajar el modelo.

SMOKE_LIVE_WHISPER=1 corre faster-whisper sobre ese wav (CPU, modelo
SMOKE_WHISPER_MODEL o "tiny") y sí descarga pesos. Por defecto no se ejecuta.
"""

import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.ffmpeg_util import resolve_tool
from core.transcribe import extract_wav


def _probe(ffprobe, path):
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels:format=duration",
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

    folder = tempfile.mkdtemp(prefix="smoke_wav_")
    src = os.path.join(folder, "sine_stereo.wav")
    dst = os.path.join(folder, "sine_16k.wav")
    # Origen a 48 kHz estéreo: extract_wav tiene que bajar a 16 kHz mono.
    gen = subprocess.run(
        [ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-ac", "2", "-ar", "48000", src],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if gen.returncode != 0 or not os.path.isfile(src):
        print("FAIL: no se generó el seno", gen.stderr)
        return 1

    extract_wav(ffmpeg, src, dst)
    info = _probe(ffprobe, dst)
    if not info or not info.get("streams"):
        print("FAIL: sin stream", info)
        return 1
    stream = info["streams"][0]
    rate = int(stream.get("sample_rate") or 0)
    channels = int(stream.get("channels") or 0)
    duration = float((info.get("format") or {}).get("duration") or 0)
    if rate != 16000 or channels != 1 or not (1.8 <= duration <= 2.2):
        print(f"FAIL: esperado 16000 Hz mono ~2s, llegó {rate} Hz, {channels} ch, {duration}s")
        return 1

    # SMOKE_LIVE_WHISPER=1 baja el modelo y transcribe el seno. No corre por defecto.
    if os.environ.get("SMOKE_LIVE_WHISPER") == "1":
        from core.transcribe import transcribe
        words = transcribe(dst, {
            "whisper_model": os.environ.get("SMOKE_WHISPER_MODEL", "tiny"),
            "whisper_device": "cpu",
            "compute_type": "int8",
            "language": "es",
            "initial_prompt": "",
        })
        if not isinstance(words, list):
            print("FAIL: transcribe no devolvió lista", words)
            return 1
        print(f"LIVE whisper palabras={len(words)}")

    print("OK smoke_transcribe_extract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
