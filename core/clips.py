# -*- coding: utf-8 -*-
"""Comandos FFmpeg para clips 9:16 de Marca personal (funciones puras, no ejecutan nada)."""
import os
from dataclasses import dataclass

PRESET_ESTUDIO = 'estudio'
PRESET_LOOP = 'loop'
PRESET_HOOK = 'hook'
ALL_PRESETS = (PRESET_ESTUDIO, PRESET_LOOP, PRESET_HOOK)

OUT_W, OUT_H = 1080, 1920
MAX_ESTUDIO_SECONDS = 30.0
HOOK_SECONDS_OPTIONS = (5, 6)
MAX_ZOOM = 4.0
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.jfif', '.png', '.gif', '.bmp', '.webp', '.tiff', '.tif', '.heic')


@dataclass(frozen=True)
class Framing:
    """Encuadre sobre el material de origen: zoom >= 1 y offsets 0..1 (0.5 = centrado)."""
    src_w: int
    src_h: int
    zoom: float = 1.0
    offset_x: float = 0.5
    offset_y: float = 0.5


def _clamp(value, low, high):
    return max(low, min(high, value))


def scaled_size(framing):
    """Tamaño del origen escalado para cubrir 1080x1920 y luego ampliado por el zoom."""
    if framing.src_w <= 0 or framing.src_h <= 0:
        raise ValueError("Dimensiones de origen inválidas")
    zoom = _clamp(framing.zoom, 1.0, MAX_ZOOM)
    s = max(OUT_W / framing.src_w, OUT_H / framing.src_h) * zoom
    return max(OUT_W, round(framing.src_w * s)), max(OUT_H, round(framing.src_h * s))


def crop_origin(framing):
    """Esquina (x, y) del recorte 1080x1920 dentro de la imagen escalada."""
    sw, sh = scaled_size(framing)
    x = round((sw - OUT_W) * _clamp(framing.offset_x, 0.0, 1.0))
    y = round((sh - OUT_H) * _clamp(framing.offset_y, 0.0, 1.0))
    return x, y


def framing_filter(framing):
    """Cadena de filtros scale+crop que deja el video en 1080x1920."""
    sw, sh = scaled_size(framing)
    x, y = crop_origin(framing)
    return f"scale={sw}:{sh},crop={OUT_W}:{OUT_H}:{x}:{y},setsar=1"


def escape_drawtext(text):
    """Escapa texto para drawtext (comillas, dos puntos, % y barras)."""
    text = (text or '').replace('\r\n', '\n').replace('\r', '\n')
    return (text.replace('\\', '\\\\').replace("'", "\\'")
            .replace(':', '\\:').replace('%', '\\%'))


def is_image(path):
    return os.path.splitext(path or '')[1].lower() in IMAGE_EXTENSIONS


def clip_duration(preset, start, end, hook_seconds=5):
    """Duración final en segundos según el preset."""
    if preset == PRESET_HOOK:
        if hook_seconds not in HOOK_SECONDS_OPTIONS:
            raise ValueError("El hook dura 5 o 6 segundos")
        return float(hook_seconds)
    length = (end or 0.0) - start
    if length <= 0:
        raise ValueError("El fin debe ser mayor que el inicio")
    if preset == PRESET_ESTUDIO:
        return min(length, MAX_ESTUDIO_SECONDS)
    if preset == PRESET_LOOP:
        return length
    raise ValueError(f"Preset desconocido: {preset}")


def _encode_args(video_codec):
    return ["-c:v", video_codec, "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", "30"]


def build_clip_cmd(preset, ffmpeg, source, output, framing, *, start=0.0, end=None,
                   audio_path=None, audio_start=0.0, hook_text='', hook_seconds=5,
                   video_codec='libx264', fontfile=None):
    """Arma la lista de argumentos de FFmpeg para el preset (no la ejecuta).

    estudio: video propio + audio de un beat (audio_path), hasta 30 s.
    loop:    video propio con el audio de la toma, de start a end.
    hook:    imagen o video de fondo + texto, 5 o 6 s, sin audio.
    """
    duration = clip_duration(preset, start, end, hook_seconds)
    vf = framing_filter(framing)
    cmd = [ffmpeg, "-y"]

    if preset == PRESET_ESTUDIO:
        if not audio_path:
            raise ValueError("El preset estudio necesita el audio de un beat")
        cmd += ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", source,
                "-ss", f"{audio_start:.3f}", "-t", f"{duration:.3f}", "-i", audio_path,
                "-map", "0:v:0", "-map", "1:a:0", "-vf", vf]
        cmd += _encode_args(video_codec) + ["-c:a", "aac", "-b:a", "192k", "-t", f"{duration:.3f}"]

    elif preset == PRESET_LOOP:
        cmd += ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", source,
                "-map", "0:v:0", "-map", "0:a:0?", "-vf", vf]
        cmd += _encode_args(video_codec) + ["-c:a", "aac", "-b:a", "192k"]

    else:  # hook
        if not (hook_text or '').strip():
            raise ValueError("Escribí el texto del hook")
        if is_image(source):
            cmd += ["-loop", "1", "-framerate", "30", "-t", f"{duration:.3f}", "-i", source]
        else:
            cmd += ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", source]
        draw = (f"drawtext=text='{escape_drawtext(hook_text.strip())}':fontsize=84:fontcolor=white"
                ":borderw=4:bordercolor=black:line_spacing=12:x=(w-text_w)/2:y=(h-text_h)/2")
        if fontfile:
            draw += f":fontfile='{escape_drawtext(fontfile)}'"
        cmd += ["-map", "0:v:0", "-vf", f"{vf},{draw}", "-an"]
        cmd += _encode_args(video_codec) + ["-t", f"{duration:.3f}"]

    cmd += ["-movflags", "+faststart", output]
    return cmd


def unique_path(path):
    """Devuelve path, o path con sufijo _2, _3... si ya existe."""
    base, ext = os.path.splitext(path)
    candidate, n = path, 2
    while os.path.exists(candidate):
        candidate = f"{base}_{n}{ext}"
        n += 1
    return candidate
