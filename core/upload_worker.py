# -*- coding: utf-8 -*-
"""Hilos Qt para conectar canales y subir videos a YouTube sin congelar la interfaz."""
from PyQt5.QtCore import QThread, pyqtSignal

from core import library, youtube


class ConnectChannelWorker(QThread):
    """Ejecuta el flujo OAuth (abre el navegador) para un canal."""
    finished_ok = pyqtSignal(str, str)   # canal, título del canal de YouTube
    failed = pyqtSignal(str, str)        # canal, error

    def __init__(self, channel, parent=None):
        super().__init__(parent)
        self.channel = channel

    def run(self):
        try:
            self.finished_ok.emit(self.channel, youtube.connect_channel(self.channel))
        except Exception as e:
            self.failed.emit(self.channel, str(e))


class YouTubeUploadWorker(QThread):
    """Sube una lista de trabajos y registra cada subida en la biblioteca.

    Cada trabajo: {channel, group, path, title, description, tags, thumbnail, privacy, beat_id}
    """
    progress = pyqtSignal(str)
    finished_all = pyqtSignal(list, list)   # resultados ok, errores (str)

    def __init__(self, jobs, parent=None):
        super().__init__(parent)
        self.jobs = jobs

    def run(self):
        done, errors = [], []
        total = len(self.jobs)
        for i, job in enumerate(self.jobs, 1):
            label = f"Subiendo a YouTube ({i}/{total}) {job['title']}"
            self.progress.emit(label)
            try:
                res = youtube.upload(
                    job['channel'], job['path'], job['title'], job.get('description', ''),
                    job.get('tags'), job.get('thumbnail'), job.get('privacy', 'private'),
                    progress=lambda p, label=label: self.progress.emit(f"{label} — {p}%"))
            except Exception as e:
                errors.append(f"{job['title']}: {e}")
                continue
            if job.get('beat_id'):
                try:
                    library.record_upload(job['beat_id'], job['channel'], job.get('group', ''),
                                          youtube_id=res['youtube_id'], url=res['url'],
                                          titulo=job['title'], estado=res['privacy'])
                except Exception as e:
                    errors.append(f"{job['title']}: subido pero no registrado ({e})")
            if res.get('thumbnail_error'):
                errors.append(f"{job['title']}: subido sin miniatura ({res['thumbnail_error'][:200]})")
            done.append({**job, **res})
        self.finished_all.emit(done, errors)
