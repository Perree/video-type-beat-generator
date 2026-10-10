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

    Cada trabajo: {channel, group, path, title, description, tags, thumbnail, privacy,
                   publish_at, beat_id, clip_id, category_id}.
    beat_id registra un beat; clip_id registra un Short (category_id default 10).
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
            # Un Short que ya tiene youtube_id no se vuelve a insertar: solo se registra.
            prior_id = ""
            if job.get('clip_id'):
                try:
                    from core import shorts_store
                    clip_row = shorts_store.get_clip(job['clip_id']) or {}
                    prior_id = (clip_row.get('youtube_id') or '').strip()
                except Exception:
                    prior_id = ""
            try:
                if prior_id:
                    res = {
                        'youtube_id': prior_id,
                        'url': f"https://youtu.be/{prior_id}",
                        'privacy': job.get('privacy', 'private'),
                        'thumbnail_error': '',
                    }
                else:
                    res = youtube.upload(
                        job['channel'], job['path'], job['title'], job.get('description', ''),
                        job.get('tags'), job.get('thumbnail'), job.get('privacy', 'private'),
                        publish_at=job.get('publish_at'),
                        category_id=job.get('category_id'),
                        progress=lambda p, label=label: self.progress.emit(f"{label} — {p}%"))
            except Exception as e:
                errors.append(f"{job['title']}: {e}")
                continue
            # Primero la fila de uploads. El clip queda «subido» solo si eso entra.
            # Si el registro falla, se guarda youtube_id sin ese estado para no
            # volver a llamar a videos.insert en el reintento.
            registered = not (job.get('beat_id') or job.get('clip_id'))
            if job.get('beat_id') or job.get('clip_id'):
                try:
                    library.record_upload(
                        job.get('beat_id'), job['channel'], job.get('group', ''),
                        youtube_id=res['youtube_id'], url=res['url'],
                        titulo=job['title'], estado=res['privacy'],
                        clip_id=job.get('clip_id'))
                    registered = True
                except Exception as e:
                    errors.append(f"{job['title']}: subido pero no registrado ({e})")
            if job.get('clip_id'):
                try:
                    from core import shorts_store
                    if registered:
                        shorts_store.update_clip(
                            job['clip_id'], youtube_id=res['youtube_id'], estado='subido')
                    else:
                        # El video ya está en YouTube. Guardar el id sin marcar subido
                        # permite reintentar solo el registro, sin otro videos.insert.
                        shorts_store.update_clip(
                            job['clip_id'], youtube_id=res['youtube_id'])
                except Exception as e:
                    errors.append(f"{job['title']}: subido pero el clip no quedó marcado ({e})")
            if res.get('thumbnail_error'):
                errors.append(f"{job['title']}: subido sin miniatura ({res['thumbnail_error'][:200]})")
            done.append({**job, **res})
        self.finished_all.emit(done, errors)


class ImportHistoryWorker(QThread):
    """Descarga el historial publicado de un canal y lo empareja con la biblioteca."""
    finished_ok = pyqtSignal(str, dict)   # canal, resultado de import_history
    failed = pyqtSignal(str, str)         # canal, error

    def __init__(self, channel, parent=None, kind=None):
        super().__init__(parent)
        self.channel = channel
        self.kind = kind if kind is not None else library.KIND_BEAT

    def run(self):
        from core import history_import
        try:
            self.finished_ok.emit(
                self.channel, history_import.import_channel_history(self.channel, kind=self.kind))
        except Exception as e:
            self.failed.emit(self.channel, str(e))
