"""Thread-safe in-memory Dropbox double with revisions and fault injection."""
from threading import RLock
from core.beat_cloud import Conflict, Missing


class MemoryDropbox:
    def __init__(self):
        self.files, self.calls, self.faults = {}, [], []
        self.counter = 0
        self.lock = RLock()

    def _fault(self, operation):
        if self.faults and self.faults[0][0] == operation:
            _, exception = self.faults.pop(0)
            raise exception

    def read(self, path):
        with self.lock:
            self.calls.append(("read", path))
            self._fault("read")
            if path not in self.files:
                raise Missing("document_missing")
            return self.files[path]

    def write(self, path, payload, rev):
        with self.lock:
            self.calls.append(("write", path, rev))
            self._fault("write")
            current = self.files.get(path)
            if (current is None and rev is not None) or (current is not None and current[1] != rev):
                raise Conflict("revision_conflict")
            self.counter += 1
            new_rev = format(self.counter, "016x")
            self.files[path] = (bytes(payload), new_rev)
            self._fault("after_write")
            return new_rev
