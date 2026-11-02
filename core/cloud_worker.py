# -*- coding: utf-8 -*-
"""Hilo Qt para las acciones de Conexiones (OAuth, gh, llavero) sin congelar la UI.

Solo se muestran mensajes de excepciones propias, que nunca incluyen valores; cualquier
otro error (SDK de Google, Dropbox, red) se reemplaza por ``fallback``.
"""
from PyQt5.QtCore import QThread, pyqtSignal

from core.automation_status import AutomationError
from core.cloud_login import LoginError
from core.gh_status import GhError
from core.youtube import YouTubeError

_ORPHANS = set()  # hilos soltados al cerrar un panel: viven hasta terminar solos


def _safe_errors():
    from scripts.kit_secrets_sync import SyncError
    from core.kit_notify import KitNotifyError
    return (AutomationError, LoginError, GhError, YouTubeError, SyncError, KitNotifyError)


class CallWorker(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, fallback, parent=None):
        super().__init__(parent)
        self._fn, self._fallback = fn, fallback

    def run(self):
        try:
            self.done.emit(self._fn())
        except _safe_errors() as exc:
            self.failed.emit(str(exc) or self._fallback)
        except Exception:  # noqa: BLE001 - el texto del SDK puede traer datos sensibles
            self.failed.emit(self._fallback)


def detach(worker):
    """Suelta un hilo en curso sin esperarlo (p. ej. OAuth esperando al navegador).

    Corta sus señales hacia el panel que se cierra y lo saca de su padre, así destruir
    el panel no destruye un QThread vivo. El hilo se libera solo al terminar.
    """
    for old in [w for w in _ORPHANS if w.isFinished()]:
        _ORPHANS.discard(old)  # ya terminó: se puede soltar la referencia sin riesgo
    if worker is None:
        return
    for signal in (worker.done, worker.failed, worker.finished):
        try:
            signal.disconnect()
        except TypeError:
            pass  # sin conexiones
    if not worker.isRunning():
        worker.deleteLater()
        return
    worker.setParent(None)
    _ORPHANS.add(worker)  # se purga en el próximo detach, cuando isFinished()
