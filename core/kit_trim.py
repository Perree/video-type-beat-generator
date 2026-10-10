# -*- coding: utf-8 -*-
"""Corta un loop al primer silencio real y tira el audio que viene después.

silencedetect corre con ffmpeg (bin/ o PATH). El corte es el primer
silence_start que deja al menos min_preview segundos: un clic al inicio
no cierra la preview. Sin silencio usable, el archivo corto se usa entero;
uno más largo que max_preview no se adivina.
"""
import os
import re
import subprocess

from core.ffmpeg_util import resolve_tool

# silence_start puede ir con decimales o entero; a veces es 0 al inicio del archivo.
_SILENCE_START = re.compile(r"silence_start:\s*(-?\d+(?:\.\d+)?)")
_SILENCE_EVENT = re.compile(r"silence_(start|end):\s*(-?\d+(?:\.\d+)?)")
_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


class KitTrimError(Exception):
    """El archivo no se puede cortar con las reglas de preview (silencio o tope)."""


def _ffmpeg():
    """Ruta a ffmpeg, o error claro si no está en bin/ ni en el PATH."""
    path = resolve_tool("ffmpeg")
    if not path:
        raise KitTrimError("No está ffmpeg en bin/ ni en PATH")
    return path


def _parse_duration_sec(stderr):
    """Lee `Duration: HH:MM:SS.xx` del banner de ffmpeg. None si no está."""
    match = _DURATION.search(stderr or "")
    if not match:
        return None
    hours = int(match.group(1))
    minutes = int(match.group(2))
    seconds = float(match.group(3))
    return hours * 3600 + minutes * 60 + seconds


def _silence_starts(stderr):
    """Todos los silence_start del log, en el orden en que ffmpeg los emite."""
    return [float(value) for value in _SILENCE_START.findall(stderr or "")]


def _run_silencedetect(path, noise_db, min_silence):
    """Pasa el archivo por silencedetect y devuelve stderr (ahí va el log).

    Args:
        path: audio de entrada.
        noise_db: umbral en dB (típicamente negativo).
        min_silence: segundos mínimos para que ffmpeg reporte un silencio.

    Returns:
        Texto de stderr.

    Raises:
        KitTrimError: ffmpeg ausente, timeout o código distinto de 0.
    """
    ffmpeg = _ffmpeg()
    # El filtro separa opciones con ':'. El número va en punto, no coma de locale.
    audio_filter = f"silencedetect=n={float(noise_db):.6g}dB:d={float(min_silence):.6g}"
    cmd = [
        ffmpeg, "-hide_banner", "-i", path,
        "-af", audio_filter,
        "-f", "null", "-",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise KitTrimError(f"ffmpeg silencedetect tardó demasiado en {path}") from exc
    except OSError as exc:
        raise KitTrimError(f"No se pudo ejecutar ffmpeg: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-3:]
        detail = " | ".join(tail) if tail else f"código {result.returncode}"
        raise KitTrimError(f"ffmpeg silencedetect falló: {detail}")
    return result.stderr or ""


def silence_points(path, noise_db=-40, min_silence=0.35):
    """Silencios del archivo como lista de (inicio, fin) en segundos, en orden.

    Un silencio que llega al final del archivo puede venir sin silence_end:
    se cierra con la duración.

    Returns:
        (duración, [(inicio, fin), ...]). La duración es None si ffmpeg no la informa.

    Raises:
        KitTrimError: ffmpeg ausente, timeout o código distinto de 0.
    """
    log = _run_silencedetect(path, noise_db, min_silence)
    duration = _parse_duration_sec(log)
    points = []
    open_start = None
    for kind, value in _SILENCE_EVENT.findall(log):
        if kind == "start":
            open_start = max(0.0, float(value))
        elif open_start is not None:
            if float(value) > open_start:
                points.append((open_start, float(value)))
            open_start = None
    if open_start is not None and duration is not None and duration > open_start:
        points.append((open_start, duration))
    return duration, points


def preview_end_sec(path, noise_db=-40, min_silence=0.35, min_preview=1.5, max_preview=40):
    """Segundo en el que termina la preview: inicio del primer silencio útil.

    Args:
        path: mp3 o wav del loop.
        noise_db: umbral de silencedetect en dB.
        min_silence: el silencio tiene que durar al menos esto para contarse.
        min_preview: se ignoran cortes anteriores (un clic al inicio no es el fin).
        max_preview: si no hay silencio, solo se acepta el archivo entero hasta este tope.

    Returns:
        Segundos desde el inicio. Sin silencio usable y duración <= max_preview,
        la duración completa.

    Raises:
        KitTrimError: sin silencio y más largo que max_preview, o ffmpeg no usable.
    """
    log = _run_silencedetect(path, noise_db, min_silence)
    for start in _silence_starts(log):
        # El detector marca el comienzo del hueco, no el final: lo de después se descarta.
        if start >= min_preview:
            return start
    duration = _parse_duration_sec(log)
    if duration is None:
        raise KitTrimError(f"No se leyó la duración de {path} y no hay un silencio usable")
    if duration <= max_preview:
        return duration
    raise KitTrimError(
        f"Sin silencio que deje al menos {min_preview}s y el audio dura {duration:.2f}s "
        f"(máximo {max_preview}s). No se adivina el corte."
    )


def trim_to_wav(src, dest, noise_db=-40, min_silence=0.35, min_preview=1.5, max_preview=40):
    """Escribe un wav PCM con el tramo [0, corte]. No incluye audio posterior.

    Args:
        src: audio de origen.
        dest: wav de salida (se crea la carpeta si falta).
        noise_db, min_silence, min_preview, max_preview: mismos criterios que preview_end_sec.

    Returns:
        dest.

    Raises:
        KitTrimError: el corte no se puede decidir o ffmpeg no escribe el wav.
    """
    end = preview_end_sec(
        src,
        noise_db=noise_db,
        min_silence=min_silence,
        min_preview=min_preview,
        max_preview=max_preview,
    )
    ffmpeg = _ffmpeg()
    parent = os.path.dirname(os.path.abspath(dest))
    if parent:
        os.makedirs(parent, exist_ok=True)
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", src,
        "-t", f"{end:.6f}",
        "-vn",
        "-c:a", "pcm_s16le",
        # Mismo formato en todos los cortes: el render los une con concat.
        "-ar", "44100", "-ac", "2",
        dest,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise KitTrimError(f"ffmpeg tardó demasiado al cortar {src}") from exc
    except OSError as exc:
        raise KitTrimError(f"No se pudo ejecutar ffmpeg: {exc}") from exc
    if result.returncode != 0 or not os.path.isfile(dest):
        tail = (result.stderr or "").strip().splitlines()[-3:]
        detail = " | ".join(tail) if tail else f"código {result.returncode}"
        raise KitTrimError(f"No se pudo escribir {dest}: {detail}")
    return dest
