# -*- coding: utf-8 -*-
"""WyreScapes: render de la mixtape con una imagen fija a 1080p.

Une los tracks en orden (filtro ``concat``, cada uno normalizado a 44.1 kHz estéreo) y
los pone sobre la imagen. La imagen entra a 1 fps con ``-tune stillimage``: un video de
horas se codifica en poco tiempo.
"""
import os
import subprocess

from core.ffmpeg_util import get_media_duration, resolve_tool

WIDTH, HEIGHT = 1920, 1080


class MixtapeRenderError(RuntimeError):
    pass


def track_durations(paths, probe=get_media_duration):
    """``{nombre de archivo: segundos}``; los que ffprobe no lee quedan afuera."""
    out = {}
    for path in paths:
        seconds = probe(path)
        if seconds:
            out[os.path.basename(path)] = float(seconds)
    return out


def build_command(ffmpeg, track_paths, image, out_path, total_seconds):
    """Comando ffmpeg (lista) para el render. Sin efectos: fácil de testear."""
    cmd = [ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
           '-loop', '1', '-framerate', '1', '-i', image]
    for path in track_paths:
        cmd += ['-i', path]
    parts = [f'[{i + 1}:a]aresample=44100,aformat=sample_fmts=fltp:channel_layouts=stereo[a{i}]'
             for i in range(len(track_paths))]
    joined = ''.join(f'[a{i}]' for i in range(len(track_paths)))
    parts.append(f'{joined}concat=n={len(track_paths)}:v=0:a=1[aout]')
    parts.append(f'[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,'
                 f'crop={WIDTH}:{HEIGHT},setsar=1,format=yuv420p[vout]')
    cmd += ['-filter_complex', ';'.join(parts), '-map', '[vout]', '-map', '[aout]',
            '-c:v', 'libx264', '-preset', 'veryfast', '-tune', 'stillimage', '-r', '1',
            '-c:a', 'aac', '-b:a', '320k', '-t', f'{total_seconds:.3f}',
            '-movflags', '+faststart', out_path]
    return cmd


def render(track_paths, image, out_path, total_seconds, ffmpeg=None, timeout=4 * 60 * 60):
    """Escribe el mp4. Raises MixtapeRenderError si falta algo o ffmpeg falla."""
    if not track_paths:
        raise MixtapeRenderError('No hay tracks para el video')
    if not os.path.isfile(image):
        raise MixtapeRenderError(f'No existe la imagen: {image}')
    ffmpeg = ffmpeg or resolve_tool('ffmpeg')
    if not ffmpeg:
        raise MixtapeRenderError('No está ffmpeg en bin/ ni en PATH')
    folder = os.path.dirname(out_path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    cmd = build_command(ffmpeg, track_paths, image, out_path, total_seconds)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', timeout=timeout, stdin=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as exc:
        raise MixtapeRenderError('ffmpeg tardó demasiado') from exc
    except OSError as exc:
        raise MixtapeRenderError(f'No se pudo ejecutar ffmpeg: {exc}') from exc
    if result.returncode != 0 or not os.path.isfile(out_path):
        tail = (result.stderr or '').strip()[-400:]
        raise MixtapeRenderError(f'ffmpeg falló (código {result.returncode}): {tail}')
    return out_path
