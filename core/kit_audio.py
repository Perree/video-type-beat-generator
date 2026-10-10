# -*- coding: utf-8 -*-
"""Planifica el audio de un video de loop kit por duración.

Con archivo preview, lo parte en tramos que caen en la ventana y cortan en un
silencio; sin preview, suma previews de loops hasta entrar en la ventana.
``plan_audio`` solo decide los tramos ``{path, start, end}``; ``cut_segments``
escribe los wav. Los avisos no llevan nombres de archivo ni de kit.

Kit chico: un loop nunca se repite dentro del mismo video. Si el material no
llega al mínimo sale un video más corto (``short``) siempre que supere
``short_min``; por debajo de eso no se arma nada (``ok`` False).
"""
import os
import subprocess

from core import kit_source
from core.kit_select import _pick_named_preview
from core.kit_trim import KitTrimError, _ffmpeg, preview_end_sec, silence_points

DEFAULTS = {'target_min_s': 135.0, 'target_max_s': 195.0, 'short_min_s': 60.0}
# Margen hacia adentro de la ventana: el corte real se cuantiza a muestras.
EDGE_SEC = 0.05
FADE_SEC = 0.03
_TRIM_DEFAULTS = {'noise_db': -40, 'min_silence': 0.35, 'min_preview': 1.5, 'max_preview': 40}
_EPS = 1e-6
# Los tramos guardados van redondeados al milisegundo: tolerancia al compararlos.
_ROUND_TOL = 2e-3


def settings(kit_cfg=None):
    """target_min_s, target_max_s y short_min_s desde ``kit_preview`` (con defaults)."""
    kit_cfg = kit_cfg or {}
    return {key: float(kit_cfg.get(key, default)) for key, default in DEFAULTS.items()}


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


def _used_by_path(used_before):
    """``{path: [(start, end), ...]}`` y orden del último uso de cada path.

    Acepta tramos sueltos o planes con ``segments``. Un tramo sin start/end
    (corridas viejas) cuenta como el archivo entero.
    """
    ranges = {}
    last_use = {}
    order = 0
    for item in used_before or []:
        segments = item['segments'] if 'segments' in item else [item]
        for seg in segments or []:
            path = seg.get('path')
            if not path:
                continue
            start = float(seg.get('start') or 0.0)
            end = seg.get('end')
            end = float('inf') if end is None else float(end)
            if end > start:
                ranges.setdefault(path, []).append((start, end))
            last_use[path] = order
            order += 1
    return ranges, last_use


def _free_gaps(start, end, used):
    """Partes de [start, end] que no pisan ningún rango de ``used``."""
    gaps = []
    cursor = start
    for used_start, used_end in sorted(used):
        if used_end <= cursor:
            continue
        if used_start >= end:
            break
        if used_start > cursor:
            gaps.append((cursor, used_start))
        cursor = max(cursor, used_end)
    if cursor < end:
        gaps.append((cursor, end))
    return gaps


def _snap_gap(gap, silences):
    """Saca el silencio de las puntas de un hueco. Devuelve (start, end) o None."""
    start, end = gap
    for sil_start, sil_end in silences:
        if sil_start - _ROUND_TOL <= start < sil_end:
            start = sil_end
        if sil_start < end <= sil_end + _ROUND_TOL:
            end = sil_start
    return (start, end) if end - start > _EPS else None


def _segment(rec, start, end, fade_in=False, fade_out=False):
    seg = {'name': rec['name'], 'path': rec['path'],
           'start': round(start, 3), 'end': round(end, 3)}
    if fade_in:
        seg['fade_in'] = True
    if fade_out:
        seg['fade_out'] = True
    return seg


def _plan_preview(rec, used, target_min, target_max, short_min, local_fn, silences_fn, trim):
    """Un tramo libre del archivo preview. None si no queda nada que llegue a short_min."""
    duration, silences = silences_fn(
        local_fn(rec), noise_db=trim['noise_db'], min_silence=trim['min_silence'])
    if not duration or duration <= 0:
        raise KitTrimError("No se leyó la duración del archivo preview")
    silences = sorted((max(0.0, s), min(duration, e)) for s, e in silences if e > s)

    # El contenido va entre el silencio inicial y el final del archivo.
    content_start, content_end = 0.0, duration
    for sil_start, sil_end in silences:
        if sil_start <= EDGE_SEC:
            content_start = max(content_start, sil_end)
        if sil_end >= duration - EDGE_SEC:
            content_end = min(content_end, sil_start)
    clean_starts = [content_start] + [e for _, e in silences]
    clean_ends = [content_end] + [s for s, _ in silences]

    def is_clean(value, points):
        return any(abs(value - p) < _ROUND_TOL for p in points)

    gaps = [g for g in (_snap_gap(gap, silences)
                        for gap in _free_gaps(content_start, content_end, used)) if g]
    warnings = []
    hi = target_max - EDGE_SEC
    for start, end in gaps:
        length = end - start
        if length < target_min:
            continue
        # Cuántos tramos entran en el hueco: el ideal los reparte parejos.
        parts = max(1, int(length // target_min))
        ideal = start + min(max(length / parts, target_min + EDGE_SEC), hi)
        latest = min(end, start + hi)
        cuts = [(s, e) for s, e in silences if start + target_min + EDGE_SEC <= s <= latest]
        if length <= hi:
            cuts.append((end, end))
        # Se prefiere un corte que deje lugar a los tramos que faltan.
        roomy = [c for c in cuts if end - c[1] >= (parts - 1) * target_min]
        pool = roomy or cuts
        if pool:
            cut = min(pool, key=lambda c: (abs(c[0] - ideal), c[0]))[0]
        else:
            cut = ideal
            warnings.append("La preview no tiene un silencio dentro de la ventana: "
                            "corte directo con fundido.")
        return _candidate('named_preview', [_segment(
            rec, start, cut,
            fade_in=not is_clean(start, clean_starts),
            fade_out=not is_clean(cut, clean_ends))], warnings)

    if not gaps:
        return None
    start, end = max(gaps, key=lambda g: (g[1] - g[0], -g[0]))
    end = min(end, start + hi)
    if end - start < short_min:
        return None
    return _candidate('named_preview', [_segment(
        rec, start, end,
        fade_in=not is_clean(start, clean_starts),
        fade_out=not is_clean(end, clean_ends))], warnings)


def _plan_loops(loops, last_use, rng, target_min, target_max, local_fn, end_fn, trim):
    """Suma previews de loops: primero los no usados en el ciclo, después el resto."""
    fresh = [loop for loop in loops if loop['path'] not in last_use]
    rng.shuffle(fresh)
    # Si hay que repetir, primero el que hace más que no suena.
    old = sorted((loop for loop in loops if loop['path'] in last_use),
                 key=lambda loop: (last_use[loop['path']], loop['path']))
    lo = target_min + EDGE_SEC
    hi = target_max - EDGE_SEC
    segments = []
    total = 0.0
    unusable = 0
    repeated = 0
    for is_old, group in ((False, fresh), (True, old)):
        for loop in group:
            if total >= lo:
                break
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
            repeated += 1 if is_old else 0
    warnings = []
    if unusable:
        warnings.append(f"{unusable} loop(s) no se pudieron usar (sin corte claro o demasiado largos).")
    if repeated:
        warnings.append(f"No alcanzan los loops sin usar: se repiten {repeated} de videos "
                        "anteriores del ciclo.")
    if not segments:
        return None
    cand = _candidate('assembled', segments, warnings)
    cand['repeated'] = bool(repeated)
    return cand


def _candidate(mode, segments, warnings):
    duration = round(sum(seg['end'] - seg['start'] for seg in segments), 3)
    return {'mode': mode, 'segments': segments, 'duration': duration,
            'repeated': False, 'warnings': list(warnings)}


def plan_audio(pack, used_before, rng, target_min=135, target_max=195, *, short_min=60,
               prefer_named_preview=True, trim=None, local_fn=None, silences_fn=None,
               end_fn=None):
    """Decide los tramos de audio de un video para que dure entre target_min y target_max.

    Args:
        pack: dict de ``kit_source.list_packs``.
        used_before: tramos (o planes) de los videos anteriores del ciclo de este kit,
            del más viejo al más nuevo.
        rng: ``random.Random`` para el orden de los loops.
        short_min: piso del video corto cuando el kit no llega a target_min.
        trim: noise_db, min_silence, min_preview, max_preview (como en ``kit_trim``).
        local_fn: ``rec -> ruta local``; por defecto ``rec['local']`` o ``rec['path']``.
            Para Dropbox usar ``downloader(tmp)``.
        silences_fn / end_fn: reemplazos de ``kit_trim.silence_points`` y
            ``preview_end_sec`` para pruebas sin ffmpeg.

    Returns:
        dict ``{ok, mode, segments, duration, short, repeated, warnings}``. ``mode`` es
        'named_preview' o 'assembled'; cada segmento es ``{name, path, start, end}`` (más
        ``fade_in`` / ``fade_out`` si el corte no cae en un silencio). ``short`` True
        avisa que no se llegó a target_min; ``ok`` False que no hay nada para armar.
    """
    target_min, target_max, short_min = float(target_min), float(target_max), float(short_min)
    if target_min <= 0 or target_max - target_min <= 4 * EDGE_SEC:
        raise ValueError("Ventana de duración inválida")
    short_min = min(short_min, target_min)
    trim = {**_TRIM_DEFAULTS, **(trim or {})}
    local_fn = local_fn or _local_path
    ranges, last_use = _used_by_path(used_before)

    candidates = []
    warnings = []
    previews = pack.get('named_previews') or []
    if prefer_named_preview and previews:
        rec = _pick_named_preview(previews)
        try:
            cand = _plan_preview(rec, ranges.get(rec['path'], []), target_min, target_max,
                                 short_min, local_fn, silences_fn or silence_points, trim)
        except KitTrimError:
            cand = None
            warnings.append("No se pudo medir el archivo preview.")
        if cand:
            candidates.append(cand)
    if not any(c['duration'] >= target_min for c in candidates) and pack.get('loops'):
        if previews and prefer_named_preview:
            warnings.append("La preview no tiene un tramo libre que llegue al mínimo: "
                            "se prueba armar con loops.")
        cand = _plan_loops(pack['loops'], last_use, rng, target_min, target_max,
                           local_fn, end_fn or preview_end_sec, trim)
        if cand:
            candidates.append(cand)

    full = [c for c in candidates if c['duration'] >= target_min]
    usable = [c for c in candidates if c['duration'] >= short_min]
    if full:
        best = full[0]
    elif usable:
        best = max(usable, key=lambda c: c['duration'])
    else:
        return {'ok': False, 'mode': None, 'segments': [], 'duration': 0.0, 'short': True,
                'repeated': False,
                'warnings': warnings + [
                    f"El kit no junta {short_min:.0f}s de audio sin repetir: no se arma video."]}
    best = dict(best, ok=True, short=best['duration'] < target_min,
                warnings=warnings + best['warnings'])
    if best['short']:
        best['warnings'].append(
            f"Audio de {best['duration']:.0f}s, por debajo del mínimo de {target_min:.0f}s: "
            "sale un video más corto y el kit cierra el ciclo.")
    return best


def cut_segments(plan, dest_dir, local_fn=None):
    """Escribe un wav PCM por tramo del plan, en orden. Devuelve las rutas.

    El corte es exacto a la muestra y no incluye audio fuera de [start, end]. Los
    tramos marcados con fade llevan un fundido corto para no dejar un clic.

    Raises:
        KitTrimError: ffmpeg ausente o que no escribe el wav.
    """
    local_fn = local_fn or _local_path
    ffmpeg = _ffmpeg()
    os.makedirs(dest_dir, exist_ok=True)
    outputs = []
    for index, seg in enumerate(plan['segments']):
        length = seg['end'] - seg['start']
        filters = [f"atrim=start={seg['start']:.3f}:end={seg['end']:.3f}", "asetpts=PTS-STARTPTS"]
        fade = min(FADE_SEC, length / 4)
        if seg.get('fade_in'):
            filters.append(f"afade=t=in:st=0:d={fade:.3f}")
        if seg.get('fade_out'):
            filters.append(f"afade=t=out:st={length - fade:.3f}:d={fade:.3f}")
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
