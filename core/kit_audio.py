# -*- coding: utf-8 -*-
"""Planifica el audio de un video de loop kit por duración.

Suma previews de loops (cada uno cortado en su primer silencio) hasta entrar en la
ventana de duración. ``plan_audio`` solo decide los tramos ``{path, start, end}``;
``cut_segments`` escribe los wav. Los avisos no llevan nombres de archivo ni de kit.

Un loop nunca se repite: ni dentro del video ni contra los videos anteriores del ciclo.
Con menos de ``min_loops`` loops sin usar no se arma nada (``ok`` False). Con esa
cantidad o más, si el material no llega al mínimo de duración sale un video más corto
(``short``).
"""
import os
import subprocess

from core import kit_source
from core.kit_trim import KitTrimError, _ffmpeg, preview_end_sec

DEFAULTS = {'target_min_s': 135.0, 'target_max_s': 195.0, 'short_min_s': 0.0}
DEFAULT_MIN_LOOPS = 4
# Margen hacia adentro de la ventana: el corte real se cuantiza a muestras.
EDGE_SEC = 0.05
_TRIM_DEFAULTS = {'noise_db': -40, 'min_silence': 0.35, 'min_preview': 1.5, 'max_preview': 40}


def settings(kit_cfg=None):
    """target_min_s, target_max_s, short_min_s y min_loops desde ``kit_preview`` (con defaults).

    ``short_min_s`` es un piso opcional de duración para el video corto (0 = sin piso);
    ``min_loops`` sale de ``min_loops_per_video``.
    """
    kit_cfg = kit_cfg or {}
    cfg = {key: float(kit_cfg.get(key, default)) for key, default in DEFAULTS.items()}
    cfg['min_loops'] = max(1, int(kit_cfg.get('min_loops_per_video', DEFAULT_MIN_LOOPS)))
    return cfg


def downloader(dest_dir, dbx=None):
    """``local_fn`` que baja de Dropbox a dest_dir solo lo que se pide, una vez por archivo."""
    cache = {}

    def local(rec):
        if rec['path'] not in cache:
            cache[rec['path']] = kit_source.download_pack_files(
                [rec['path']], dest_dir, dbx=dbx)[0]
        return cache[rec['path']]
    return local


def _local_path(rec):
    return rec.get('local') or rec['path']


def _used_paths(used_before):
    """Paths de los loops ya usados. Acepta tramos sueltos o planes con ``segments``."""
    used = set()
    for item in used_before or []:
        segments = item['segments'] if 'segments' in item else [item]
        used.update(seg['path'] for seg in segments or [] if seg.get('path'))
    return used


def _segment(rec, start, end):
    return {'name': rec['name'], 'path': rec['path'],
            'start': round(start, 3), 'end': round(end, 3)}


def plan_audio(pack, used_before, rng, target_min=135, target_max=195, *, short_min=0,
               min_loops=DEFAULT_MIN_LOOPS, trim=None, local_fn=None, end_fn=None):
    """Decide los tramos de audio de un video para que dure entre target_min y target_max.

    Args:
        pack: dict de ``kit_source.list_packs``.
        used_before: tramos (o planes) de los videos anteriores del ciclo de este kit.
        rng: ``random.Random`` para el orden de los loops.
        short_min: piso opcional del video corto cuando el kit no llega a target_min.
        min_loops: loops sin usar que hacen falta para armar un video.
        trim: noise_db, min_silence, min_preview, max_preview (como en ``kit_trim``).
        local_fn: ``rec -> ruta local``; por defecto ``rec['local']`` o ``rec['path']``.
            Para Dropbox usar ``downloader(tmp)``.
        end_fn: reemplazo de ``kit_trim.preview_end_sec`` para pruebas sin ffmpeg.

    Returns:
        dict ``{ok, mode, segments, duration, short, exhausted, warnings}``. ``mode`` es
        siempre 'assembled'; cada segmento es ``{name, path, start, end}``. ``short`` True
        avisa que no se llegó a target_min; ``exhausted`` que al kit no le quedan loops sin
        usar para otro video (en los dos casos el kit cierra el ciclo). ``ok`` False: no hay
        nada para armar.
    """
    target_min, target_max, short_min = float(target_min), float(target_max), float(short_min)
    if target_min <= 0 or target_max - target_min <= 4 * EDGE_SEC:
        raise ValueError("Ventana de duración inválida")
    short_min = min(short_min, target_min)
    min_loops = max(1, int(min_loops))
    trim = {**_TRIM_DEFAULTS, **(trim or {})}
    local_fn = local_fn or _local_path
    end_fn = end_fn or preview_end_sec
    used = _used_paths(used_before)
    warnings = []

    def nothing(text):
        return {'ok': False, 'mode': None, 'segments': [], 'duration': 0.0, 'short': True,
                'exhausted': True, 'warnings': warnings + [text]}

    fresh = [loop for loop in pack.get('loops') or [] if loop['path'] not in used]
    if len(fresh) < min_loops:
        return nothing(f"El kit tiene menos de {min_loops} loops sin usar: no se arma video.")
    rng.shuffle(fresh)
    lo = target_min + EDGE_SEC
    hi = target_max - EDGE_SEC
    segments = []
    total = 0.0
    tried = unusable = 0
    for loop in fresh:
        if total >= lo and len(segments) >= min_loops:
            break
        tried += 1
        try:
            end = round(float(end_fn(local_fn(loop), **trim)), 3)
        except KitTrimError:
            unusable += 1
            continue
        if end <= 0 or total + end > hi:
            unusable += 1
            continue
        segments.append(_segment(loop, 0.0, end))
        total = round(total + end, 3)
    if unusable:
        warnings.append(f"{unusable} loop(s) no se pudieron usar (sin corte claro o demasiado largos).")
    if len(segments) < min_loops:
        return nothing(f"El kit no junta {min_loops} loops utilizables: no se arma video.")
    if total < short_min:
        return nothing(f"El kit no junta {short_min:.0f}s de audio sin repetir: no se arma video.")
    short = total < target_min
    if short:
        warnings.append(
            f"Audio de {total:.0f}s, por debajo del mínimo de {target_min:.0f}s: "
            "sale un video más corto y el kit cierra el ciclo.")
    return {'ok': True, 'mode': 'assembled', 'segments': segments, 'duration': total,
            'short': short, 'exhausted': len(fresh) - tried < min_loops, 'warnings': warnings}


def cut_segments(plan, dest_dir, local_fn=None):
    """Escribe un wav PCM por tramo del plan, en orden. Devuelve las rutas.

    El corte es exacto a la muestra y no incluye audio fuera de [start, end].

    Raises:
        KitTrimError: ffmpeg ausente o que no escribe el wav.
    """
    local_fn = local_fn or _local_path
    ffmpeg = _ffmpeg()
    os.makedirs(dest_dir, exist_ok=True)
    outputs = []
    for index, seg in enumerate(plan['segments']):
        filters = [f"atrim=start={seg['start']:.3f}:end={seg['end']:.3f}", "asetpts=PTS-STARTPTS"]
        dest = os.path.join(dest_dir, f"seg_{index:02d}.wav")
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", local_fn(seg),
               "-af", ",".join(filters), "-vn", "-c:a", "pcm_s16le",
               # Mismo formato en todos los tramos: el render los une con concat.
               "-ar", "44100", "-ac", "2", dest]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=300,
            )
        except subprocess.TimeoutExpired as exc:
            raise KitTrimError(f"ffmpeg tardó demasiado al cortar el tramo {index}") from exc
        except OSError as exc:
            raise KitTrimError(f"No se pudo ejecutar ffmpeg: {exc}") from exc
        if result.returncode != 0 or not os.path.isfile(dest):
            raise KitTrimError(f"No se pudo escribir el tramo {index} (código {result.returncode})")
        outputs.append(dest)
    return outputs
