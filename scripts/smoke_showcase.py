#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: seno de 5 s marca energía; silencio no. Sin red, sin video."""

import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import clip_select as cs
from core import showcase as sc

FIXTURE = os.path.join(ROOT, 'scripts', 'fixtures', 'transcript_sample.json')
CFG = {'clip_min_s': 20, 'clip_max_s': 60, 'clip_count': 6, 'language': 'es'}
SR = 16000
DURATION_S = 5.0


def fail(msg, *extra):
    print("FAIL:", msg, *extra)
    return 1


def _write_wav(path, samples):
    """PCM 16-bit mono con la stdlib; no depende de soundfile para escribir."""
    import wave
    import numpy as np
    pcm = np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
    frames = (pcm * 32767.0).astype(np.int16).tobytes()
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(frames)


def _sine_and_silence(folder):
    import numpy as np
    n = int(DURATION_S * SR)
    t = np.arange(n, dtype=np.float32) / SR
    sine = (0.5 * np.sin(2 * np.pi * 440.0 * t)).astype(np.float32)
    silence = np.zeros(n, dtype=np.float32)
    sine_path = os.path.join(folder, 'sine_5s.wav')
    silence_path = os.path.join(folder, 'silence_5s.wav')
    _write_wav(sine_path, sine)
    _write_wav(silence_path, silence)
    return sine_path, silence_path


def main() -> int:
    folder = tempfile.mkdtemp(prefix='smoke_showcase_')
    sine_path, silence_path = _sine_and_silence(folder)

    # 1) Seno de 5 s: hay energía y no hay voz → al menos un intervalo.
    hits = sc.find_candidates(sine_path)
    if not hits:
        return fail("seno 5 s no marcó energía", hits)
    covered = sum(c['end'] - c['start'] for c in hits)
    if covered < 2.0:
        return fail("seno cubrió demasiado poco", hits)
    if any(c['end'] <= c['start'] for c in hits):
        return fail("intervalo invertido", hits)

    # 2) Silencio: no hay candidatos.
    quiet = sc.find_candidates(silence_path)
    if quiet:
        return fail("silencio no debía marcar energía", quiet)

    # 3) Misma energía pero voz cubriendo todo: no inventa showcase.
    spoken = sc.find_candidates(sine_path, words=[{'t0': 0.0, 't1': 5.0, 'w': 'voz'}])
    if spoken:
        return fail("voz densa no debía marcar showcase", spoken)

    # 4) Rechaza video: no cargar más que el wav.
    try:
        sc.find_candidates(os.path.join(folder, 'clip.mp4'))
        return fail("debía rechazar .mp4")
    except ValueError:
        pass

    # 5) Prompt: con pista aparece el tramo; sin pista no se menciona showcase.
    with open(FIXTURE, encoding='utf-8') as f:
        fx = json.load(f)
    words, duration = fx['words'], fx['duration']
    _, user_plain = cs.build_prompt(words, CFG, duration)
    if 'showcase' in user_plain.lower() or 'Pistas opcionales' in user_plain:
        return fail("prompt sin pistas no debía mencionar showcase")
    hint = [{'start': 12.0, 'end': 18.0}]
    _, user_hint = cs.build_prompt(words, CFG, duration, showcase=hint)
    if '[12.00-18.00]' not in user_hint or 'Pistas opcionales' not in user_hint:
        return fail("prompt no incluyó la pista", user_hint[-400:])
    if 'orden' not in user_hint.lower() and 'No son una orden' not in user_hint:
        return fail("la pista debía aclarar que no es una orden")

    print("OK smoke_showcase")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
