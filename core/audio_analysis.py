# -*- coding: utf-8 -*-
"""Detección de BPM y tonalidad con librosa (solo los primeros segundos)."""

ANALYSIS_SECONDS = 60
BPM_MIN, BPM_MAX = 70.0, 160.0

NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
# Perfiles Krumhansl-Schmuckler
_MAJOR = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def fix_tempo(bpm, low=BPM_MIN, high=BPM_MAX):
    """Corrige doble/mitad de tempo llevando el valor al rango [low, high)."""
    if not bpm or bpm <= 0:
        return 0.0
    while bpm < low:
        bpm *= 2
    while bpm >= high:
        bpm /= 2
    return bpm


def estimate_key(chroma_mean):
    """Devuelve la tonalidad (ej. 'A minor') a partir de un vector chroma de 12 valores."""
    import numpy as np
    chroma = np.asarray(chroma_mean, dtype=float)
    best, best_score = None, -2.0
    for mode, profile in (('major', _MAJOR), ('minor', _MINOR)):
        prof = np.asarray(profile)
        for i in range(12):
            score = np.corrcoef(chroma, np.roll(prof, i))[0, 1]
            if score > best_score:
                best, best_score = f"{NOTES[i]} {mode}", score
    return best


def analyze(path, seconds=ANALYSIS_SECONDS):
    """Devuelve (bpm, key). bpm es float redondeado a 1 decimal; el resultado siempre es editable."""
    import librosa
    y, sr = librosa.load(path, sr=22050, mono=True, duration=seconds)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    bpm = fix_tempo(float(tempo[0] if hasattr(tempo, '__len__') else tempo))
    chroma = librosa.feature.chroma_cqt(y=librosa.effects.harmonic(y), sr=sr).mean(axis=1)
    return round(bpm, 1), estimate_key(chroma)
