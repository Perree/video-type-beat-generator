# -*- coding: utf-8 -*-
"""Hilo de Shorts. En esta fase solo corre la transcripción, sin congelar la UI."""
import threading

from PyQt5.QtCore import QThread, pyqtSignal

from core.transcribe import TranscribeCancelled, transcribe_file


class ShortsWorker(QThread):
    """Transcribe un video largo en segundo plano.

    Señales:
        progress(etapa, pct, texto) — etapa "transcribir", pct 0-100.
        finished_ok(video_id) — la transcripción quedó en shorts_store.
        failed(mensaje) — error de ffmpeg, del modelo o de la base.
        cancelled() — stop() cortó FFmpeg o el bucle de segmentos.

    stop() es seguro desde el hilo de la UI: marca la bandera y mata el
    Popen de FFmpeg si todavía está extrayendo el wav.
    """

    progress = pyqtSignal(str, int, str)
    finished_ok = pyqtSignal(int)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, video_path, shorts_cfg, db_path=None, cache_dir=None, parent=None):
        super().__init__(parent)
        self.video_path = video_path
        self.shorts_cfg = shorts_cfg or {}
        self.db_path = db_path
        self.cache_dir = cache_dir
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
        """Lo llama extract_wav al abrir y al cerrar el proceso."""
        with self._lock:
            self._proc = proc
            if proc is not None and self._cancel.is_set() and proc.poll() is None:
                proc.terminate()

    def run(self):
        try:
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
            self.finished_ok.emit(video_id)
        except TranscribeCancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(str(exc))
