# -*- coding: utf-8 -*-
"""Extrae WAV mono 16 kHz y lo transcribe con faster-whisper (CPU por defecto).

TODO: pip install -r requirements.txt antes de transcribir de verdad.
No instalar el wheel CUDA de ctranslate2: el fallback de este módulo ya pasa a CPU.
"""
import json
import os
import sys
import subprocess
import threading

from core import library, shorts_store
from core.ffmpeg_util import get_media_duration, resolve_tool

# WAV de trabajo. No se versiona (ver .gitignore).
CACHE_DIR = "shorts_cache"
_SAMPLE_RATE = 16000

# El modelo pesa ~1-2 GB en RAM; se reutiliza dentro del proceso.
_model_slot = {"key": None, "model": None}
# Si CUDA falla una vez, no reintentar en cada video de esta sesión.
_cuda_unavailable = {"reason": None}


class TranscribeCancelled(Exception):
    """El usuario cortó la extracción o el bucle de Whisper."""


def extract_wav(ffmpeg, src, dst, *, should_stop=None, register_proc=None):
    """Convierte `src` a WAV PCM mono 16 kHz en `dst`.

    Escribe primero un archivo `.part` y lo renombra al terminar, así una
    cancelación no deja un wav a medias en el lugar del cache.

    Args:
        ffmpeg: ruta al ejecutable.
        src: video o audio de origen.
        dst: wav de salida.
        should_stop: callable sin argumentos; True corta el proceso.
        register_proc: callable(Popen|None) para que el hilo de UI pueda matarlo.

    Returns:
        Ruta final (`dst`).

    Raises:
        TranscribeCancelled: si should_stop pasa a True.
        RuntimeError: si ffmpeg falta o sale con error.
    """
    if not ffmpeg:
        raise RuntimeError("No se encontró FFmpeg (ni en bin/ ni en el PATH).")
    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)
    partial = dst + ".part"
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", src,
        "-vn", "-ac", "1", "-ar", str(_SAMPLE_RATE),
        "-c:a", "pcm_s16le", "-f", "wav",
        partial,
    ]
    try:
        _run_ffmpeg(cmd, should_stop=should_stop, register_proc=register_proc)
        os.replace(partial, dst)
    except Exception:
        if os.path.isfile(partial):
            try:
                os.remove(partial)
            except OSError:
                pass
        raise
    return dst


def transcribe(wav_path, cfg, *, should_stop=None, on_progress=None):
    """Transcribe un WAV ya extraído.

    Args:
        wav_path: PCM mono 16 kHz.
        cfg: bloque `shorts` (whisper_model, whisper_device, compute_type,
            language, initial_prompt).
        should_stop: se consulta entre segmentos de Whisper.
        on_progress: callable(pct: int, texto: str), pct 0-100 sobre el audio.

    Returns:
        Lista de {t0, t1, w}.
    """
    model_name = (cfg or {}).get("whisper_model") or "small"
    device = ((cfg or {}).get("whisper_device") or "auto").lower()
    compute_type = (cfg or {}).get("compute_type") or "int8"
    language = (cfg or {}).get("language") or None
    prompt = ((cfg or {}).get("initial_prompt") or "").strip() or None

    model, used = _load_model(model_name, device, compute_type, on_progress)

    def _collect(active):
        if should_stop and should_stop():
            raise TranscribeCancelled("Transcripción cancelada")
        segments, info = active.transcribe(
            wav_path,
            language=language,
            initial_prompt=prompt,
            vad_filter=True,
            word_timestamps=True,
        )
        duration = float(getattr(info, "duration", 0) or 0) or (get_media_duration(wav_path) or 0)
        words = []
        for segment in segments:
            if should_stop and should_stop():
                raise TranscribeCancelled("Transcripción cancelada")
            words.extend(_segment_words(segment))
            if on_progress and duration > 0:
                pct = int(min(100, 100 * float(segment.end or 0) / duration))
                on_progress(pct, "Transcribiendo…")
        return words

    try:
        return _collect(model)
    except TranscribeCancelled:
        raise
    except Exception as exc:
        # El modelo puede cargar en CUDA y fallar al iterar segmentos.
        # Se reintenta el archivo entero en CPU; el error original queda en stderr.
        if used != "cuda":
            raise
        msg = f"{type(exc).__name__}: {exc}"
        print(f"faster-whisper CUDA falló durante la transcripción ({msg}). Sigo en CPU.",
              file=sys.stderr)
        _cuda_unavailable["reason"] = msg
        _model_slot["key"] = None
        _model_slot["model"] = None
        if on_progress:
            on_progress(0, "CUDA no disponible, usando CPU")
        model = _cached_model(_whisper_model_cls(), model_name, "cpu", compute_type)
        return _collect(model)


def transcribe_file(src, cfg, *, db_path=None, cache_dir=None, should_stop=None,
                    register_proc=None, on_progress=None):
    """Transcribe un video largo y guarda las palabras en shorts_store.

    La caché es el par (hash del archivo, modelo): si el archivo se mueve,
    upsert_video reutiliza la fila y no se vuelve a correr Whisper.

    Args:
        src: ruta del video.
        cfg: bloque shorts de la config.
        db_path: library.db (None = la de la app).
        cache_dir: carpeta del wav (default shorts_cache/).
        should_stop, register_proc, on_progress: ver extract_wav y transcribe.

    Returns:
        (video_id, words).
    """
    def _pct(pct, texto):
        if on_progress:
            on_progress(int(pct), texto)

    src = os.path.abspath(src)
    model_name = (cfg or {}).get("whisper_model") or "small"
    language = (cfg or {}).get("language") or "es"
    digest = library.file_hash(src)
    duration = get_media_duration(src)
    video_id = shorts_store.upsert_video(
        src, digest, db_path=db_path, duration_s=duration)

    cached = shorts_store.get_transcript(video_id, model_name, db_path=db_path)
    if cached is not None:
        shorts_store.update_video(video_id, db_path=db_path, estado="transcrito", error=None)
        _pct(100, "Transcripción en caché")
        return video_id, cached

    shorts_store.update_video(video_id, db_path=db_path, estado="transcribiendo", error=None)
    try:
        if should_stop and should_stop():
            raise TranscribeCancelled("Transcripción cancelada")
        cache_dir = cache_dir or CACHE_DIR
        wav_path = os.path.join(cache_dir, f"{digest}.wav")
        _pct(5, "Extrayendo audio…")
        if not _wav_is_ready(wav_path, duration):
            ffmpeg = resolve_tool("ffmpeg")
            extract_wav(ffmpeg, src, wav_path, should_stop=should_stop, register_proc=register_proc)
        _pct(15, "Cargando modelo…")

        def _whisper_progress(pct, texto):
            # 15-99 lo ocupa Whisper; el 100 queda para cuando ya está en la DB.
            _pct(15 + int(pct * 0.84), texto)

        words = transcribe(
            wav_path, cfg, should_stop=should_stop, on_progress=_whisper_progress)
        shorts_store.save_transcript(video_id, model_name, language, words, db_path=db_path)
        shorts_store.update_video(video_id, db_path=db_path, estado="transcrito", error=None)
        _pct(100, "Transcripción lista")
        return video_id, words
    except TranscribeCancelled:
        shorts_store.update_video(video_id, db_path=db_path, estado="importado", error=None)
        raise
    except Exception as exc:
        shorts_store.update_video(
            video_id, db_path=db_path, estado="error", error=str(exc)[:500])
        raise


def _load_model(model_name, device, compute_type, on_progress):
    """Carga WhisperModel. device auto/cuda prueba CUDA y, si falla, CPU.

    El error de CUDA se imprime: no se descarta en un except vacío.
    """
    WhisperModel = _whisper_model_cls()
    resolved = device
    if device in ("auto", "cuda"):
        if _cuda_unavailable["reason"] is not None and device == "auto":
            resolved = "cpu"
        else:
            try:
                model = _cached_model(WhisperModel, model_name, "cuda", compute_type)
                return model, "cuda"
            except Exception as exc:
                # Se deja visible: un driver viejo (GTX 1650) suele fallar acá.
                msg = f"{type(exc).__name__}: {exc}"
                print(f"faster-whisper CUDA falló ({msg}). Sigo en CPU.", file=sys.stderr)
                _cuda_unavailable["reason"] = msg
                if on_progress:
                    on_progress(0, "CUDA no disponible, usando CPU")
                resolved = "cpu"
    model = _cached_model(WhisperModel, model_name, resolved, compute_type)
    return model, resolved


def _cached_model(WhisperModel, model_name, device, compute_type):
    key = (model_name, device, compute_type)
    if _model_slot["key"] != key:
        _model_slot["model"] = WhisperModel(
            model_name, device=device, compute_type=compute_type)
        _model_slot["key"] = key
    return _model_slot["model"]


def _whisper_model_cls():
    # TODO: pip install -r requirements.txt (faster-whisper). No el wheel CUDA.
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "Falta faster-whisper. Instalá con: pip install -r requirements.txt "
            "(el paquete de PyPI trae ctranslate2 para CPU; no instales el wheel CUDA)."
        ) from exc
    return WhisperModel


def _segment_words(segment):
    """Una entrada por palabra. Si el segmento no trae timestamps, se guarda entero."""
    raw = getattr(segment, "words", None) or []
    words = []
    for w in raw:
        text = (getattr(w, "word", None) or "").strip()
        if not text:
            continue
        words.append({
            "t0": round(float(w.start), 3),
            "t1": round(float(w.end), 3),
            "w": text,
        })
    if words:
        return words
    text = (getattr(segment, "text", None) or "").strip()
    if not text:
        return []
    return [{
        "t0": round(float(segment.start), 3),
        "t1": round(float(segment.end), 3),
        "w": text,
    }]


def _wav_is_ready(path, expected_duration):
    """True si el wav del cache ya es mono 16 kHz y dura como el origen."""
    info = _probe_audio(path)
    if not info:
        return False
    if info["sample_rate"] != _SAMPLE_RATE or info["channels"] != 1:
        return False
    if expected_duration and info["duration"] is not None:
        if abs(info["duration"] - expected_duration) > 1.5:
            return False
    return True


def _probe_audio(path):
    """sample_rate, channels y duration, o None si ffprobe no puede leer el archivo."""
    if not path or not os.path.isfile(path) or os.path.getsize(path) < 44:
        return None
    ffprobe = resolve_tool("ffprobe")
    if not ffprobe:
        return None
    cmd = [
        ffprobe, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=sample_rate,channels:format=duration",
        "-of", "json", path,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    except Exception:
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    streams = payload.get("streams") or []
    if not streams:
        return None
    stream = streams[0]
    try:
        sample_rate = int(stream.get("sample_rate") or 0)
        channels = int(stream.get("channels") or 0)
    except (TypeError, ValueError):
        return None
    duration = None
    raw_dur = (payload.get("format") or {}).get("duration")
    if raw_dur not in (None, ""):
        try:
            duration = float(raw_dur)
        except (TypeError, ValueError):
            duration = None
    return {"sample_rate": sample_rate, "channels": channels, "duration": duration}


def _run_ffmpeg(cmd, *, should_stop=None, register_proc=None):
    """Corre ffmpeg con Popen. Si should_stop, terminate y luego kill.

    stderr se lee en otro hilo para que el pipe no bloquee el proceso.
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
        raise TranscribeCancelled("Transcripción cancelada")
    err = (stderr_box[0] if stderr_box else b"").decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        raise RuntimeError(err or f"ffmpeg terminó con código {proc.returncode}")


def _kill_proc(proc):
    """terminate y, si sigue vivo, kill. No falla si ya terminó."""
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
