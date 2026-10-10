# -*- coding: utf-8 -*-
"""Render 16:9 de un preview de kit: imagen fija + uno o más wav.

Un solo wav es toda la pista. Varios se concatenan en orden (concat demuxer).
La duración la marca el audio; acá no se corta por silencio.
"""
import os
import subprocess
import tempfile

from core.ffmpeg_util import (
    get_available_video_codec,
    get_media_duration,
    resolve_tool,
)

FRAME_W = 1920
FRAME_H = 1080
# Misma idea que el pad de beats: encajar y rellenar con negro, sin recortar.
SCALE_PAD = (
    f"scale={FRAME_W}:{FRAME_H}:force_original_aspect_ratio=decrease,"
    f"pad={FRAME_W}:{FRAME_H}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p"
)


class KitRenderError(Exception):
    """No se pudo armar el mp4 (ffmpeg, entradas o duración)."""


def render(image, wavs, output, ffmpeg=None):
    """Junta una imagen fija 1920x1080 con la pista de audio y escribe un mp4.

    Args:
        image: jpg/png/webp de fondo (se loopea).
        wavs: uno o más wav en el orden de la pista. Un elemento = archivo entero.
        output: mp4 de destino.
        ffmpeg: ejecutable; default resolve_tool.

    Returns:
        output.

    Raises:
        KitRenderError: sin ffmpeg, lista vacía, o FFmpeg con error.
    """
    if not wavs:
        raise KitRenderError("Hace falta al menos un wav")
    ffmpeg = ffmpeg or resolve_tool("ffmpeg")
    if not ffmpeg:
        raise KitRenderError("No está ffmpeg en bin/ ni en PATH")
    if not image or not os.path.isfile(image):
        raise KitRenderError(f"No está la imagen: {image}")
    for path in wavs:
        if not path or not os.path.isfile(path):
            raise KitRenderError(f"No está el wav: {path}")

    duration = _total_duration_sec(wavs)
    parent = os.path.dirname(os.path.abspath(output))
    if parent:
        os.makedirs(parent, exist_ok=True)

    codec = get_available_video_codec(ffmpeg)
    concat_path = None
    try:
        audio_input, concat_path = _audio_input_args(wavs)
        cmd = [
            ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
            "-loop", "1",
            "-i", os.path.abspath(image),
        ]
        cmd.extend(audio_input)
        cmd.extend([
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-vf", SCALE_PAD,
            "-c:v", codec,
            "-preset", "fast",
        ])
        # stillimage es de libx264; NVENC lo rechaza.
        if codec == "libx264":
            cmd.extend(["-tune", "stillimage"])
        cmd.extend([
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-shortest",
            "-t", f"{duration:.3f}",
            os.path.abspath(output),
        ])
        _run_ffmpeg(cmd)
    finally:
        if concat_path:
            try:
                os.remove(concat_path)
            except OSError:
                pass
    if not os.path.isfile(output):
        raise KitRenderError(f"FFmpeg no escribió {output}")
    return output


def _total_duration_sec(wavs):
    """Suma las duraciones de los wav. Falla si alguna no se puede leer."""
    total = 0.0
    for path in wavs:
        seconds = get_media_duration(path)
        if seconds is None:
            raise KitRenderError(f"No se pudo leer la duración de {path}")
        total += seconds
    if total <= 0:
        raise KitRenderError("La pista de audio no tiene duración")
    return total


def _audio_input_args(wavs):
    """Argumentos -i del audio: el wav solo, o concat demuxer si hay varios.

    Returns:
        (lista de args, ruta del listado concat o None).
    """
    if len(wavs) == 1:
        return ["-i", os.path.abspath(wavs[0])], None
    handle, concat_path = tempfile.mkstemp(prefix="kit_concat_", suffix=".txt")
    os.close(handle)
    with open(concat_path, "w", encoding="utf-8", newline="\n") as list_file:
        for path in wavs:
            list_file.write(_concat_file_line(path) + "\n")
    return ["-f", "concat", "-safe", "0", "-i", concat_path], concat_path


def _concat_file_line(path):
    """Línea `file '...'` del concat demuxer, con ruta absoluta usable en Windows.

    El prefijo `file:` evita que `C:` se lea como protocolo. Las comillas
    simples del path se cierran y reabren (`'\\''`) como pide ffmpeg.
    """
    normalized = os.path.abspath(path).replace("\\", "/")
    escaped = normalized.replace("'", "'\\''")
    return f"file 'file:{escaped}'"


def _run_ffmpeg(cmd):
    """Ejecuta ffmpeg; lanza KitRenderError si falla o se cuelga."""
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=300,
        )
    except subprocess.TimeoutExpired as exc:
        raise KitRenderError("ffmpeg tardó demasiado en el render del kit") from exc
    except OSError as exc:
        raise KitRenderError(f"No se pudo ejecutar ffmpeg: {exc}") from exc
    if result.returncode != 0:
        tail = (result.stderr or "").strip().splitlines()[-5:]
        detail = " | ".join(tail) if tail else f"código {result.returncode}"
        raise KitRenderError(f"ffmpeg falló: {detail}")
