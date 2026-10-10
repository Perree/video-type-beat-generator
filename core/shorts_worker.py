# -*- coding: utf-8 -*-
"""Hilo de Shorts: transcribir, elegir clips y renderizar, sin congelar la UI."""
import threading

from PyQt5.QtCore import QThread, pyqtSignal

from core.clip_render import RenderCancelled, render_one_clip, render_stored_clips
from core.clip_select import ClipSelectCancelled, ClipSelectError, select_clips
from core import shorts_store
from core.transcribe import TranscribeCancelled, transcribe_file


class ShortsWorker(QThread):
    """Una etapa pesada por vez (transcribir, elegir o renderizar).

    Señales:
        progress(etapa, pct, texto) — etapa transcribir | elegir | renderizar.
        finished_ok(video_id) — la etapa terminó y la base quedó actualizada.
        failed(mensaje) — error de ffmpeg, del modelo, del LLM o de la base.
        cancelled() — stop() cortó FFmpeg o el bucle de segmentos.

    stop() es seguro desde el hilo de la UI: marca la bandera y mata el
    Popen de FFmpeg si está extrayendo audio o renderizando.
    """

    progress = pyqtSignal(str, int, str)
    finished_ok = pyqtSignal(int)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, video_path, shorts_cfg, db_path=None, cache_dir=None, parent=None,
                 job="transcribir", video_id=None, output_dir=None, canal=None,
                 layout_profile="obs_unico", clip_id=None):
        super().__init__(parent)
        self.video_path = video_path
        self.shorts_cfg = shorts_cfg or {}
        self.db_path = db_path
        self.cache_dir = cache_dir
        self.job = job
        self.video_id = video_id
        self.clip_id = clip_id
        self.output_dir = output_dir
        self.canal = canal
        self.layout_profile = layout_profile or "obs_unico"
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._proc = None

    def stop(self):
        """Pide corte y termina el ffmpeg en curso."""
        self._cancel.set()
        with self._lock:
            proc = self._proc
        if proc is not None and proc.poll() is None:
            proc.terminate()

    def _register_proc(self, proc):
        """Lo llama el render o extract_wav al abrir y al cerrar el proceso."""
        with self._lock:
            self._proc = proc
            if proc is not None and self._cancel.is_set() and proc.poll() is None:
                proc.terminate()

    def run(self):
        try:
            if self.job == "elegir":
                self._run_select()
            elif self.job == "renderizar":
                self._run_render()
            elif self.job == "renderizar_uno":
                self._run_render_one()
            else:
                self._run_transcribe()
        except (TranscribeCancelled, RenderCancelled, ClipSelectCancelled):
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))

    def _run_transcribe(self):
        self.progress.emit("transcribir", 0, "Preparando…")
        video_id, _words = transcribe_file(
            self.video_path,
            self.shorts_cfg,
            db_path=self.db_path,
            cache_dir=self.cache_dir,
            should_stop=self._cancel.is_set,
            register_proc=self._register_proc,
            on_progress=lambda pct, texto: self.progress.emit("transcribir", pct, texto),
        )
        if self._cancel.is_set():
            self.cancelled.emit()
            return
        shorts_store.update_video(
            video_id, db_path=self.db_path,
            canal=self.canal or None,
            layout_profile=self.layout_profile,
        )
        self.finished_ok.emit(video_id)

    def _run_select(self):
        if not self.video_id:
            raise ClipSelectError("Primero transcribí el video.")
        self.progress.emit("elegir", 10, "Armando el pedido…")
        model = self.shorts_cfg.get("whisper_model") or "small"
        words = shorts_store.get_transcript(self.video_id, model, db_path=self.db_path)
        if not words:
            raise ClipSelectError("No hay transcripción para este video.")
        video = shorts_store.get_video(self.video_id, db_path=self.db_path) or {}
        previous = video.get("estado") or "transcrito"
        shorts_store.update_video(self.video_id, db_path=self.db_path, estado="eligiendo", error=None)
        self.progress.emit("elegir", 40, "Consultando el modelo…")
        try:
            select_clips(
                words, self.video_id, self.shorts_cfg,
                duration=video.get("duration_s"), db_path=self.db_path,
                should_stop=self._cancel.is_set,
            )
        except ClipSelectCancelled:
            restore = previous if previous not in ("eligiendo", "error") else "transcrito"
            shorts_store.update_video(
                self.video_id, db_path=self.db_path, estado=restore, error=None)
            raise
        except Exception as exc:
            # select_clips no escribe filas si el JSON no sirve; no dejar el video en "eligiendo".
            restore = previous if previous not in ("eligiendo", "error") else "transcrito"
            shorts_store.update_video(
                self.video_id, db_path=self.db_path, estado=restore, error=str(exc)[:500])
            raise
        if self._cancel.is_set():
            self.cancelled.emit()
            return
        self.progress.emit("elegir", 100, "Clips propuestos")
        self.finished_ok.emit(self.video_id)

    def _run_render(self):
        if not self.video_id:
            raise RuntimeError("Primero transcribí el video y elegí clips.")
        if not self.output_dir:
            raise RuntimeError("No hay carpeta de salida.")
        self.progress.emit("renderizar", 0, "Preparando el render…")
        render_stored_clips(
            self.video_id, self.shorts_cfg, self.output_dir,
            db_path=self.db_path, cache_dir=self.cache_dir,
            should_stop=self._cancel.is_set, register_proc=self._register_proc,
            on_progress=lambda pct, texto: self.progress.emit("renderizar", pct, texto),
        )
        if self._cancel.is_set():
            self.cancelled.emit()
            return
        self.finished_ok.emit(self.video_id)

    def _run_render_one(self):
        """Re-render de un clip. El caller ya guardó título e inicio/fin."""
        if not self.clip_id:
            raise RuntimeError("Elegí un clip para re-renderizar.")
        if not self.output_dir:
            raise RuntimeError("No hay carpeta de salida.")
        self.progress.emit("renderizar", 0, "Re-renderizando el clip…")
        video_id = render_one_clip(
            self.clip_id, self.shorts_cfg, self.output_dir,
            db_path=self.db_path, cache_dir=self.cache_dir,
            should_stop=self._cancel.is_set, register_proc=self._register_proc,
            on_progress=lambda pct, texto: self.progress.emit("renderizar", pct, texto),
        )
        if self._cancel.is_set():
            self.cancelled.emit()
            return
        self.finished_ok.emit(video_id)
