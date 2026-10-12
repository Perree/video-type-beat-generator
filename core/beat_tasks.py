"""Cancelable Qt tasks; public metadata and cloud reads stay off the UI thread."""
from threading import Event
from collections import Counter
from PyQt5.QtCore import QThread, pyqtSignal

from core.beat_http import BeatError, PublicTransport
from core.beat_source import BeatStarsSource
from core.beat_cloud import BeatCloud, CloudError, DropboxTransport


class Cancelled(Exception):
    pass


def checkpoint(event):
    if event.is_set():
        raise Cancelled()


class CancelCloudRead:
    def __init__(self, transport, event):
        self.transport, self.event = transport, event

    def read(self, path):
        checkpoint(self.event)
        value = self.transport.read(path)
        checkpoint(self.event)
        return value


def load_state(event, transport=None):
    def sleep(delay):
        if event.wait(delay):
            raise Cancelled()
    checkpoint(event)
    transport = transport if transport is not None else DropboxTransport.from_env()
    state, rev = BeatCloud(CancelCloudRead(transport, event), sleep=sleep).read("state")
    checkpoint(event)
    if rev is None:
        raise CloudError("beat_state_not_initialized")
    return state


class CancelTransport:
    def __init__(self, event, progress, transport=None):
        self.event, self.progress = event, progress
        self.transport = transport or PublicTransport()
        self.pages = 0

    def query(self, query, variables, deadline):
        checkpoint(self.event)
        result = self.transport.query(query, variables, deadline)
        checkpoint(self.event)
        if "page" in variables:
            self.pages += 1
            self.progress(f"Analizando catálogo: {self.pages} páginas recibidas…")
        return result


def analyze(url, event, progress, transport=None):
    source = BeatStarsSource(transport=CancelTransport(event, progress, transport))
    snapshot = source.scan(url)
    checkpoint(event)
    tracks = [t.payload() for t in snapshot.tracks]
    tags = Counter(tag for track in tracks for tag in track["tags"])
    durations = [t["duration"] for t in tracks if t["duration"] is not None]
    return {"url": url, "tracks": tracks, "tags": tags.most_common(10),
            "duration_count": len(durations), "duration_total": sum(durations)}


class BeatTask(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn, self.event = fn, Event()

    def cancel(self):
        self.event.set()
        self.requestInterruption()

    def run(self):
        try:
            checkpoint(self.event)
            value = self.fn(self.event, self.progress.emit)
            checkpoint(self.event)
            self.done.emit(value)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            if self.event.is_set():
                self.cancelled.emit()
            else:
                self.failed.emit(str(exc) if isinstance(exc, (BeatError, CloudError)) else
                                 f"La operación falló ({type(exc).__name__}).")
