# -*- coding: utf-8 -*-
"""Rutas de FFmpeg/ffprobe, prueba de NVENC y duración de un medio.

Los binarios locales viven en bin/ y no van en el repo. VideoGeneratorWorker
sigue usando estas mismas funciones (importadas desde main.py).
"""
import os
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
            print("✓ Aceleración GPU (h264_nvenc) detectada")
            return "h264_nvenc"
        print("ℹ h264_nvenc no funciona en este equipo (¿driver NVIDIA desactualizado?): "
              + (result.stderr.strip().splitlines() or [""])[-1])
    except Exception:
        pass
    print("ℹ Usando codec por defecto (libx264)")
    return "libx264"


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
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode == 0:
            out = result.stdout.strip()
            if out:
                try:
                    return float(out)
                except Exception:
                    return None
        return None
    except Exception:
        return None


# Nombres históricos que main.py ya llama.
_resolve_tool = resolve_tool
_get_available_video_codec = get_available_video_codec
_get_media_duration = get_media_duration
