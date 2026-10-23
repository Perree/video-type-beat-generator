# -*- coding: utf-8 -*-
"""Rutas de FFmpeg/ffprobe, prueba de NVENC y duración de un medio.

Los binarios locales viven en bin/ y no van en el repo. VideoGeneratorWorker
sigue usando estas mismas funciones (importadas desde main.py).
"""
import os
import math
import shutil
import subprocess


def resolve_tool(name):
    """Devuelve la ruta de ffmpeg o ffprobe.

    Primero busca en bin/ (copia local). Si no está, usa el que haya en el PATH.
    Los binarios no van en el repo; sin esta búsqueda subprocess lanza WinError 2.

    Args:
        name: "ffmpeg" o "ffprobe" (sin extensión).

    Returns:
        Ruta al ejecutable, o None si no está.
    """
    exe = f"{name}.exe" if os.name == "nt" else name
    local = os.path.join("bin", exe)
    if os.path.isfile(local):
        return local
    return shutil.which(name)


def get_available_video_codec(ffmpeg_path):
    """Retorna h264_nvenc solo si una codificación de prueba funciona; si no, libx264.

    Que el encoder figure en `-codecs` no basta: con drivers NVIDIA viejos falla al abrirlo.

    Args:
        ffmpeg_path: ejecutable ffmpeg.

    Returns:
        "h264_nvenc" o "libx264".
    """
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
             "-i", "color=c=black:s=256x256:d=0.1", "-frames:v", "1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
        if result.returncode == 0:
            _log("Aceleracion GPU (h264_nvenc) detectada")
            return "h264_nvenc"
        _log("h264_nvenc no funciona en este equipo (driver NVIDIA desactualizado?): "
             + (result.stderr.strip().splitlines() or [""])[-1])
    except Exception:
        pass
    _log("Usando codec por defecto (libx264)")
    return "libx264"


def _log(message):
    """Imprime sin tumbar el proceso si la consola no es UTF-8 (cp1252 en Windows)."""
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"))


def escape_filter_path(path):
    """Ruta absoluta para un filtro FFmpeg (ass/subtitles), entre comillas simples.

    En el filtergraph `\\` es escape y `:` separa opciones. En Windows `C:`
    tiene que llegar como `C\\:` y las barras como `/`. El .ass vive en
    shorts_cache/ (nombre ASCII) para no meter acentos en el filtro; el mp4
    de salida sí puede llevarlos.

    Args:
        path: archivo que el filtro va a abrir. Vacío devuelve "".

    Returns:
        Ruta escapada, sin las comillas que pone quien arma el filtro.
        Escapa ' y :; si no, un apóstrofe corta el ass='...' del filtergraph.
    """
    if not path:
        return ""
    normalized = os.path.abspath(path).replace("\\", "/")
    return normalized.replace("'", r"\'").replace(":", r"\:")


def ffmpeg_has_ass_filter(ffmpeg_path):
    """True si este ffmpeg lista el filtro `ass` (libass).

    Args:
        ffmpeg_path: ejecutable ffmpeg.

    Returns:
        True solo si el nombre del filtro es exactamente ass.
    """
    if not ffmpeg_path:
        return False
    try:
        result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-filters"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=20)
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in (result.stdout or "").splitlines():
        # Cada filtro es una fila: banderas, nombre, dirección, descripción.
        parts = line.split()
        if "ass" in parts:
            return True
    return False


def get_media_duration(media_path):
    """Devuelve la duración en segundos (float) de un archivo multimedia, o None si falla.

    Args:
        media_path: audio o video que ffprobe pueda leer.

    Returns:
        Segundos, o None si ffprobe no está o la salida no es un número.
    """
    try:
        ffprobe_path = resolve_tool("ffprobe")
        if not ffprobe_path:
            return None
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            media_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                timeout=30, stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode == 0:
            out = result.stdout.strip()
            if out:
                try:
                    seconds = float(out)
                    return seconds if math.isfinite(seconds) and seconds > 0 else None
                except Exception:
                    return None
        return None
    except Exception:
        return None


# Nombres históricos que main.py ya llama.
_resolve_tool = resolve_tool
_get_available_video_codec = get_available_video_codec
_get_media_duration = get_media_duration
