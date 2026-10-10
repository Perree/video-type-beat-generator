# -*- coding: utf-8 -*-
"""Render 9:16 de un clip (layout obs_unico) con subtítulos ASS quemados.

Un FFmpeg por clip, en streaming. No usa loudnorm ni el recorte vertical de
los beats (`_build_vertical_cmd`): ese comando siempre fuerza libx264.
"""
import os
import re
import subprocess
import threading

from core.ass_subs import write_ass
from core.ffmpeg_util import (
    escape_filter_path,
    ffmpeg_has_ass_filter,
    get_available_video_codec,
    resolve_tool,
)
from core import shorts_store

CACHE_DIR = "shorts_cache"
FRAME_W = 1080
FRAME_H = 1920
FADE_S = 0.08
ASS_MISSING = (
    "FFmpeg no tiene el filtro ass (libass). "
    "Reemplazá bin/ffmpeg.exe por un build que incluya libass y volvé a probar."
)


class RenderCancelled(Exception):
    """El usuario cortó el FFmpeg de un clip."""


def obs_unico_filter(ass_path):
    """Filtergraph: fondo 1080x1920 desenfocado, imagen nítida centrada, ASS.

    El fondo cubre el cuadro (increase + crop) y se difumina. La copia nítida
    entra entera (decrease) y se centra. El recorte de beats hace solo crop
    y pierde el encuadre completo de la pantalla.

    Args:
        ass_path: archivo .ass ya escrito.

    Returns:
        Cadena para -filter_complex, salida etiquetada [vout].
    """
    escaped = escape_filter_path(ass_path)
    return (
        "[0:v]split=2[bg][fg];"
        "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,setsar=1,boxblur=20:2[bgb];"
        "[fg]scale=1080:1920:force_original_aspect_ratio=decrease,setsar=1[fgs];"
        f"[bgb][fgs]overlay=(W-w)/2:(H-h)/2,format=yuv420p,ass='{escaped}'[vout]"
    )


def render_clip(src, dst, start_s, end_s, words, cfg=None, *, ass_path=None,
                ffmpeg=None, codec=None, should_stop=None, register_proc=None):
    """Corta [start_s, end_s] a un mp4 1080x1920 con el ASS quemado.

    `-ss` va antes de `-i` para no decodificar el video entero. El codec sale
    de la prueba NVENC de un frame; si no pasa, libx264 -preset veryfast.
    Fade de audio de 80 ms solo para evitar clicks. Sin loudnorm.

    Args:
        src: video largo.
        dst: mp4 de salida (puede tener acentos).
        start_s, end_s: ventana en segundos.
        words: {t0, t1, w} del video largo.
        cfg: bloque shorts (estilo de subtítulos).
        ass_path: destino del .ass; default shorts_cache/clip_render.ass.
        ffmpeg: ejecutable; default resolve_tool.
        codec: h264_nvenc o libx264; si falta, se prueba NVENC.
        should_stop: callable; True pide corte.
        register_proc: callable(Popen|None) para terminate desde la UI.

    Returns:
        dst.

    Raises:
        RenderCancelled: si should_stop corta el proceso.
        RuntimeError: sin ffmpeg, sin libass, o FFmpeg con error.
    """
    ffmpeg = ffmpeg or resolve_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("No se encontró FFmpeg (ni en bin/ ni en el PATH).")
    if not ffmpeg_has_ass_filter(ffmpeg):
        raise RuntimeError(ASS_MISSING)

    start_s = float(start_s)
    end_s = float(end_s)
    duration = end_s - start_s
    if duration <= 0:
        raise RuntimeError("El clip no tiene duración (fin <= inicio).")

    if ass_path is None:
        os.makedirs(CACHE_DIR, exist_ok=True)
        ass_path = os.path.join(CACHE_DIR, "clip_render.ass")
    write_ass(ass_path, words, start_s, end_s, cfg)

    parent = os.path.dirname(os.path.abspath(dst))
    if parent:
        os.makedirs(parent, exist_ok=True)

    if codec is None:
        codec = get_available_video_codec(ffmpeg)

    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start_s:.3f}",
        "-i", src,
        "-t", f"{duration:.3f}",
        "-filter_complex", obs_unico_filter(ass_path),
        "-map", "[vout]",
        "-map", "0:a:0",
        "-c:v", codec,
    ]
    # veryfast es de libx264. NVENC no lo acepta; usa su preset fast.
    if codec == "libx264":
        cmd.extend(["-preset", "veryfast"])
    else:
        cmd.extend(["-preset", "fast"])
    cmd.extend(["-pix_fmt", "yuv420p"])
    if duration > FADE_S * 2:
        fade_out = duration - FADE_S
        cmd.extend([
            "-af", f"afade=t=in:d={FADE_S:.3f},afade=t=out:st={fade_out:.3f}:d={FADE_S:.3f}",
        ])
    cmd.extend(["-c:a", "aac", "-b:a", "192k", dst])
    _run_ffmpeg(cmd, should_stop=should_stop, register_proc=register_proc)
    return dst


def render_stored_clips(video_id, cfg, output_dir, *, db_path=None, cache_dir=None,
                        should_stop=None, register_proc=None, on_progress=None):
    """Renderiza los clips propuesto/aprobado/error de un video y guarda la ruta.

    Rechazados y subidos no entran. El codec se prueba una sola vez para
    todos los clips del lote.

    Args:
        video_id: fila de long_videos.
        cfg: bloque shorts.
        output_dir: carpeta de los mp4.
        db_path: library.db.
        cache_dir: carpeta ASCII de los .ass.
        should_stop, register_proc: cancelación del Popen.
        on_progress: callable(pct, texto).

    Returns:
        Cantidad de clips renderizados.

    Raises:
        RenderCancelled, RuntimeError.
    """
    video = shorts_store.get_video(video_id, db_path=db_path)
    if not video:
        raise RuntimeError("No está el video en la base.")
    layout = video.get("layout_profile") or "obs_unico"
    if layout != "obs_unico":
        raise RuntimeError(
            f"El perfil '{layout}' todavía no se renderiza. Usá obs_unico.")

    model = (cfg or {}).get("whisper_model") or "small"
    words = shorts_store.get_transcript(video_id, model, db_path=db_path) or []
    clips = [
        clip for clip in shorts_store.list_clips(video_id, db_path=db_path)
        if clip.get("estado") in ("propuesto", "aprobado", "error")
    ]
    if not clips:
        raise RuntimeError("No hay clips para renderizar (propuesto, aprobado o con error).")

    ffmpeg = resolve_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("No se encontró FFmpeg (ni en bin/ ni en el PATH).")
    if not ffmpeg_has_ass_filter(ffmpeg):
        raise RuntimeError(ASS_MISSING)
    codec = get_available_video_codec(ffmpeg)
    cache_dir = cache_dir or CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    shorts_store.update_video(video_id, db_path=db_path, estado="renderizando", error=None)
    done = 0
    try:
        for index, clip in enumerate(clips):
            if should_stop and should_stop():
                raise RenderCancelled("Render cancelado")
            if on_progress:
                pct = int(100 * index / len(clips))
                on_progress(pct, f"Renderizando {index + 1}/{len(clips)}")
            dst = os.path.join(output_dir, _output_name(clip))
            ass_path = os.path.join(cache_dir, f"c{int(clip['id'])}.ass")
            render_clip(
                video["path"], dst, clip["start_s"], clip["end_s"], words, cfg,
                ass_path=ass_path, ffmpeg=ffmpeg, codec=codec,
                should_stop=should_stop, register_proc=register_proc,
            )
            shorts_store.update_clip(
                clip["id"], db_path=db_path, estado="renderizado", render_path=os.path.abspath(dst))
            done += 1
        shorts_store.update_video(video_id, db_path=db_path, estado="listo", error=None)
        if on_progress:
            on_progress(100, "Clips listos")
        return done
    except RenderCancelled:
        shorts_store.update_video(video_id, db_path=db_path, estado="clips_listos", error=None)
        raise
    except Exception as exc:
        shorts_store.update_video(
            video_id, db_path=db_path, estado="error", error=str(exc)[:500])
        raise


def render_one_clip(clip_id, cfg, output_dir, *, db_path=None, cache_dir=None,
                    should_stop=None, register_proc=None, on_progress=None):
    """Re-renderiza un solo clip aprobado (o ya renderizado / con error).

    Lee ``start_s`` y ``end_s`` actuales. No escribe ``start_modelo`` ni
    ``end_modelo``. Un clip rechazado no se renderiza.

    Args:
        clip_id: fila de clips.
        cfg: bloque shorts.
        output_dir: carpeta del mp4.
        db_path: library.db.
        cache_dir: carpeta ASCII del .ass.
        should_stop, register_proc: cancelación del Popen.
        on_progress: callable(pct, texto).

    Returns:
        video_id del clip.

    Raises:
        RenderCancelled, RuntimeError.
    """
    clip = shorts_store.get_clip(clip_id, db_path=db_path)
    if not clip:
        raise RuntimeError("No está el clip en la base.")
    if clip.get("estado") == "rechazado":
        raise RuntimeError("Un clip rechazado no se renderiza.")
    if clip.get("estado") not in ("aprobado", "renderizado", "error"):
        raise RuntimeError("Aprobá el clip antes de re-renderizarlo.")

    video = shorts_store.get_video(clip["video_id"], db_path=db_path)
    if not video:
        raise RuntimeError("No está el video en la base.")
    layout = video.get("layout_profile") or "obs_unico"
    if layout != "obs_unico":
        raise RuntimeError(
            f"El perfil '{layout}' todavía no se renderiza. Usá obs_unico.")

    model = (cfg or {}).get("whisper_model") or "small"
    words = shorts_store.get_transcript(clip["video_id"], model, db_path=db_path) or []
    ffmpeg = resolve_tool("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("No se encontró FFmpeg (ni en bin/ ni en el PATH).")
    if not ffmpeg_has_ass_filter(ffmpeg):
        raise RuntimeError(ASS_MISSING)
    codec = get_available_video_codec(ffmpeg)
    cache_dir = cache_dir or CACHE_DIR
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    if should_stop and should_stop():
        raise RenderCancelled("Render cancelado")
    if on_progress:
        on_progress(10, "Re-renderizando el clip")
    dst = os.path.join(output_dir, _output_name(clip))
    ass_path = os.path.join(cache_dir, f"c{int(clip['id'])}.ass")
    try:
        render_clip(
            video["path"], dst, clip["start_s"], clip["end_s"], words, cfg,
            ass_path=ass_path, ffmpeg=ffmpeg, codec=codec,
            should_stop=should_stop, register_proc=register_proc,
        )
    except RenderCancelled:
        raise
    except Exception:
        shorts_store.update_clip(clip["id"], db_path=db_path, estado="error")
        raise
    shorts_store.update_clip(
        clip["id"], db_path=db_path, estado="renderizado", render_path=os.path.abspath(dst))
    if on_progress:
        on_progress(100, "Clip listo")
    return clip["video_id"]


def _output_name(clip):
    """Nombre de archivo a partir del título. Los caracteres de Windows se sacan."""
    title = re.sub(r'[<>:"/\\|?*]', "", (clip.get("titulo") or "clip")).strip()
    title = re.sub(r"\s+", " ", title)[:60] or "clip"
    return f"{title}_{int(clip['id'])}.mp4"


def _run_ffmpeg(cmd, *, should_stop=None, register_proc=None):
    """Corre FFmpeg con Popen. should_stop llama terminate y luego kill.

    stderr se lee en otro hilo para que el pipe no llene y congele el proceso.
    """
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if register_proc:
        register_proc(proc)
    stderr_box = []

    def _drain():
        try:
            stderr_box.append(proc.stderr.read() if proc.stderr else b"")
        except Exception:
            stderr_box.append(b"")

    reader = threading.Thread(target=_drain, daemon=True)
    reader.start()
    cancelled = False
    try:
        while proc.poll() is None:
            if should_stop and should_stop():
                cancelled = True
                _kill_proc(proc)
                break
            try:
                proc.wait(timeout=0.25)
            except subprocess.TimeoutExpired:
                continue
        if not cancelled and should_stop and should_stop():
            cancelled = True
            _kill_proc(proc)
    finally:
        if proc.poll() is None:
            _kill_proc(proc)
        reader.join(timeout=2)
        if proc.stderr:
            try:
                proc.stderr.close()
            except Exception:
                pass
        if register_proc:
            register_proc(None)
    if cancelled:
        raise RenderCancelled("Render cancelado")
    err = (stderr_box[0] if stderr_box else b"").decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(err or f"ffmpeg terminó con código {proc.returncode}")


def _kill_proc(proc):
    """terminate y, si sigue vivo, kill."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
