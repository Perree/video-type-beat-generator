# -*- coding: utf-8 -*-
"""Análisis de solo lectura de packs de loop kits: duraciones y videos posibles.

Cada loop se descarga de a uno a un directorio temporal que se borra siempre.
No sube nada ni toca Dropbox o la biblioteca.
"""
import os
import subprocess
import tempfile
import wave

from core import kit_source
from core.ffmpeg_util import resolve_tool
from core.kit_trim import _parse_duration_sec, preview_end_sec

VIDEO_MIN_SEC = 135.0
VIDEO_MAX_SEC = 195.0
SEGMENT_MAX_SEC = 45.0


def media_duration_sec(path):
    """Duración en segundos (ffmpeg; wav sin ffmpeg por stdlib). None si no se puede leer."""
    ffmpeg = resolve_tool("ffmpeg")
    if ffmpeg:
        try:
            result = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", path],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=120,
            )
            found = _parse_duration_sec(result.stderr)
            if found is not None:
                return found
        except (subprocess.TimeoutExpired, OSError):
            pass
    if path.lower().endswith(".wav"):
        try:
            with wave.open(path, "r") as handle:
                return handle.getnframes() / float(handle.getframerate())
        except (wave.Error, EOFError, OSError):
            return None
    return None


def split_segments(duration, segment_max=SEGMENT_MAX_SEC):
    """Parte una duración en tramos de a lo sumo segment_max (el último puede ser corto)."""
    if duration <= 0:
        return []
    pieces = []
    remaining = float(duration)
    while remaining > 1e-9:
        piece = min(segment_max, remaining)
        pieces.append(piece)
        remaining -= piece
    return pieces


def plan_videos(loop_durations, min_sec=VIDEO_MIN_SEC, max_sec=VIDEO_MAX_SEC,
                segment_max=SEGMENT_MAX_SEC):
    """Cuántos videos de min_sec-max_sec salen juntando previews, sin repetir tramos.

    Cada preview se parte en tramos de a lo sumo segment_max y los tramos se
    acumulan en orden hasta llegar a min_sec; como ningún tramo pasa segment_max,
    el video queda por debajo de max_sec. Un tramo no se usa en dos videos.

    Args:
        loop_durations: segundos de preview de cada loop (None/0 se ignora).
        segment_max: tope de un tramo; debe ser <= max_sec - min_sec (se valida).

    Returns:
        dict ``{videos, upper_bound, leftover_sec, split_loops, video_secs}``.
        upper_bound es el techo teórico total // min_sec.
    """
    if segment_max > max_sec - min_sec:
        # El video se pasa de min_sec por menos de segment_max: debe entrar en el rango.
        raise ValueError("segment_max demasiado grande para el rango de duración")
    durations = [d for d in loop_durations if d and d > 0]
    pieces = []
    split_loops = 0
    for d in durations:
        parts = split_segments(d, segment_max)
        if len(parts) > 1:
            split_loops += 1
        pieces.extend(parts)
    total = sum(pieces)
    video_secs = []
    acc = 0.0
    for piece in pieces:
        acc += piece
        if acc >= min_sec:
            video_secs.append(round(acc, 2))
            acc = 0.0
    return {
        "videos": len(video_secs),
        "upper_bound": int(total // min_sec),
        "leftover_sec": round(acc, 2),
        "split_loops": split_loops,
        "video_secs": video_secs,
    }


def analyze_pack(pack, dbx=None, max_loops=None, download_fn=None, end_fn=None,
                 duration_fn=None):
    """Mide un pack de kit_source.list_packs. Solo lectura.

    Args:
        pack: dict de kit_source.list_packs.
        max_loops: analiza solo los primeros N loops (el conteo real se informa aparte).
        download_fn / end_fn / duration_fn: inyectables para pruebas sin red ni ffmpeg.

    Returns:
        dict con loops_total, loops_analyzed, preview_file, preview_sec,
        loop_preview_secs, errors, preview_total_sec y videos.
    """
    download = download_fn or kit_source.download_pack_files
    end_of = end_fn or preview_end_sec
    duration_of = duration_fn or media_duration_sec

    loops = list(pack["loops"])
    chosen = loops if max_loops is None else loops[:max(0, int(max_loops))]
    previews = pack.get("named_previews") or []
    preview_sec = None
    errors = 0
    secs = []

    # El directorio temporal se borra al salir, haya o no excepción.
    with tempfile.TemporaryDirectory(prefix="kit_analyze_") as tmp:
        if previews:
            local = download([previews[0]["path"]], tmp, dbx=dbx)[0]
            try:
                preview_sec = duration_of(local)
            finally:
                _remove(local)
        for loop in chosen:
            local = None
            try:
                local = download([loop["path"]], tmp, dbx=dbx)[0]
                secs.append(float(end_of(local)))
            except Exception:  # un loop malo (red, ffmpeg, silencio) no corta el análisis
                errors += 1
                secs.append(None)
            finally:
                if local:
                    _remove(local)

    valid = [s for s in secs if s]
    return {
        "loops_total": len(loops),
        "loops_analyzed": len(chosen),
        "preview_file": bool(previews),
        "preview_sec": None if preview_sec is None else round(preview_sec, 2),
        "loop_preview_secs": [None if s is None else round(s, 2) for s in secs],
        "errors": errors,
        "preview_total_sec": round(sum(valid), 2),
        "videos": plan_videos(valid),
    }


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass
