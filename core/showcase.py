# -*- coding: utf-8 -*-
"""Pistas de showcase: tramos con beat (alta energía) y poca voz.

No crea clips. El LLM las ve como orientación opcional en el prompt.
Trabaja solo sobre el wav 16 kHz de transcripción, nunca sobre el video.
"""
import os

WINDOW_S = 2.0
MIN_TAIL_S = 1.0
MAX_INTERVALS = 8
# Umbral absoluto: el silencio queda debajo; un seno o un beat típico, arriba.
ENERGY_FLOOR = 0.02
# Fracción máxima del tramo que puede solaparse con palabras (VAD de Whisper).
VOICE_MAX = 0.30


def _spans(items):
    """Normaliza dicts {start,end} o pares (start, end) a tuplas float."""
    out = []
    for item in items or []:
        if isinstance(item, dict):
            out.append((float(item['start']), float(item['end'])))
        else:
            out.append((float(item[0]), float(item[1])))
    return out


def _pcm_windows(wav_path, window_s=WINDOW_S, min_tail_s=MIN_TAIL_S):
    """Lee un wav PCM s16 de a ventanas. Solo una ventana vive en RAM.

    Yields:
        (t0, t1, muestras float32 en [-1, 1], sample_rate).
    La cola entra si dura al menos `min_tail_s`. Un archivo más corto no yield.

    Raises:
        ValueError: si no es PCM de 16 bit (el wav de transcripción sí lo es).
    """
    import wave
    import numpy as np

    try:
        wf = wave.open(wav_path, 'rb')
    except wave.Error as exc:
        raise ValueError(f"showcase espera un wav PCM, no el video: {exc}") from exc
    with wf:
        sr = wf.getframerate()
        nch = wf.getnchannels()
        sw = wf.getsampwidth()
        if sr <= 0 or nch <= 0 or sw != 2:
            raise ValueError(
                "showcase espera el wav PCM 16-bit de la transcripción "
                f"(llegó {sr} Hz, {nch} canales, {sw * 8} bit).")
        win = int(window_s * sr)
        min_tail = int(min_tail_s * sr)
        if win <= 0:
            return
        t = 0.0
        while True:
            raw = wf.readframes(win)
            if not raw:
                break
            n = len(raw) // (sw * nch)
            # Archivo corto, o resto menor a 1 s: no alcanza para un tramo.
            if n < min_tail:
                break
            samples = np.frombuffer(raw, dtype='<i2', count=n * nch)
            if nch > 1:
                samples = samples.reshape(n, nch).mean(axis=1)
            y = np.asarray(samples, dtype=np.float32) / 32768.0
            t1 = t + n / sr
            yield t, t1, y, sr
            t = t1
            if n < win:
                break


def _voice_fraction(t0, t1, words):
    """Cuánto del intervalo [t0, t1] cubren las palabras del VAD (0–1)."""
    length = t1 - t0
    if length <= 0 or not words:
        return 0.0
    overlap = 0.0
    for w in words:
        overlap += max(0.0, min(t1, float(w['t1'])) - max(t0, float(w['t0'])))
    return overlap / length


def _merge_windows(windows, gap_s=0.05):
    """Une ventanas consecutivas en intervalos más largos."""
    if not windows:
        return []
    ordered = sorted(windows, key=lambda w: w['start'])
    merged = [{'start': ordered[0]['start'], 'end': ordered[0]['end'],
               'score': ordered[0]['score']}]
    for w in ordered[1:]:
        prev = merged[-1]
        if w['start'] <= prev['end'] + gap_s:
            prev['end'] = max(prev['end'], w['end'])
            prev['score'] = max(prev['score'], w['score'])
        else:
            merged.append({'start': w['start'], 'end': w['end'], 'score': w['score']})
    return merged


def format_hint(intervals):
    """Texto para el prompt: pista, no orden. Vacío si no hay intervalos."""
    spans = _spans(intervals)
    if not spans:
        return ''
    lines = '\n'.join(f'[{a:.2f}-{b:.2f}]' for a, b in spans)
    return (
        '\n\nPistas opcionales de showcase (tramos con beat y poca voz). '
        'No son una orden ni clips listos: si alguno encaja en un Short '
        'autocontenido de 20-60 s, puedes usarlo; no inventes un clip solo por la pista.\n'
        f'{lines}'
    )


def find_candidates(wav_path, words=None, max_intervals=MAX_INTERVALS):
    """Detecta hasta `max_intervals` tramos de alta energía y poca voz.

    Lee el wav de a ventanas de 2 s (PCM 16-bit) y en cada una mide RMS y
    onset. No abre el video ni deja el wav entero en RAM. Cruza con los
    huecos del VAD (timestamps de `words`). Sin palabras se asume que no hay voz.

    Args:
        wav_path: wav PCM 16-bit de la transcripción (16 kHz mono). No pasar el video.
        words: lista `{t0, t1, w}` de la transcripción, o None.
        max_intervals: tope de intervalos devueltos (default 8).

    Returns:
        Lista de `{start, end}` en segundos, ordenada por tiempo. Vacía si
        no hay energía (silencio) o si la voz cubre casi todo.

    Raises:
        ValueError: si la ruta no es un .wav PCM de 16 bit.
    """
    if not wav_path or not str(wav_path).lower().endswith('.wav'):
        raise ValueError("showcase espera un wav 16 kHz, no el video original.")
    if not os.path.isfile(wav_path):
        raise FileNotFoundError(wav_path)

    import librosa
    import numpy as np

    windows = []
    for t0, t1, seg, sr in _pcm_windows(wav_path):
        rms = float(np.sqrt(np.mean(seg * seg))) if seg.size else 0.0
        if rms < ENERGY_FLOOR:
            continue
        if _voice_fraction(t0, t1, words) > VOICE_MAX:
            continue
        # Onset solo de esta ventana: rankea un beat frente a un tono plano
        # sin armar el espectrograma del archivo entero. No veta al seno.
        onset_env = librosa.onset.onset_strength(y=seg, sr=sr)
        onset_mean = float(np.mean(onset_env)) if onset_env.size else 0.0
        windows.append({
            'start': round(t0, 3),
            'end': round(t1, 3),
            'rms': rms,
            'onset_mean': onset_mean,
        })

    peak = max((w['onset_mean'] for w in windows), default=0.0)
    for w in windows:
        onset_norm = w['onset_mean'] / peak if peak > 0 else 0.0
        w['score'] = w['rms'] * (1.0 + onset_norm)

    merged = _merge_windows(windows)
    merged.sort(key=lambda w: -w['score'])
    top = merged[: max(0, int(max_intervals))]
    top.sort(key=lambda w: w['start'])
    return [{'start': w['start'], 'end': w['end']} for w in top]
