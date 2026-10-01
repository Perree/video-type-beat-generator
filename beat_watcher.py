"""Vigilancia de la carpeta beats/ con watchdog: avisa cuando aparece un audio nuevo."""
import os
import time

from PyQt5.QtCore import QObject, pyqtSignal
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

AUDIO_EXTENSIONS = ('.mp3', '.wav', '.m4a', '.aac', '.flac')


def _wait_until_stable(path, timeout=30.0, interval=0.5):
    """Espera a que el archivo deje de crecer (copia terminada). Devuelve False si desaparece o expira."""
    deadline = time.time() + timeout
    last_size = -1
    while time.time() < deadline:
        try:
            size = os.path.getsize(path)
        except OSError:
            return False
        if size == last_size and size > 0:
            return True
        last_size = size
        time.sleep(interval)
    return os.path.exists(path)


class _AudioHandler(FileSystemEventHandler):
    def __init__(self, callback):
        super().__init__()
        self._callback = callback

    def _handle(self, path):
        if path.lower().endswith(AUDIO_EXTENSIONS):
            self._callback(path)

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path)


class BeatFolderWatcher(QObject):
    """Emite beat_detected(nombre_archivo) cuando un audio nuevo está listo en la carpeta."""
    beat_detected = pyqtSignal(str)

    def __init__(self, folder, parent=None):
        super().__init__(parent)
        self._folder = folder
        self._observer = None
        self._pending = set()

    def start(self):
        os.makedirs(self._folder, exist_ok=True)
        self._observer = Observer()
        self._observer.schedule(_AudioHandler(self._on_file), self._folder, recursive=False)
        self._observer.start()

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None

    def _on_file(self, path):
        # Se ejecuta en el hilo de watchdog; esperar aquí no bloquea la UI.
        if path in self._pending:
            return
        self._pending.add(path)
        try:
            if _wait_until_stable(path):
                self.beat_detected.emit(os.path.basename(path))
        finally:
            self._pending.discard(path)
