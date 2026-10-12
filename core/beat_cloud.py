"""Dropbox CAS JSON storage. No Loopkits client, paths, or credentials."""
import json
import math
import os
import time
from copy import deepcopy
from core.beat_schema import migrate


def decode_document(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("nonfinite_json_number")

    def number(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("nonfinite_json_number")
        return result

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant, parse_float=number)


class CloudError(Exception):
    pass


class Conflict(CloudError):
    pass


class Missing(CloudError):
    pass


class Transient(CloudError):
    def __init__(self, delay=0):
        super().__init__("transient_dropbox_error")
        self.delay = delay


class DropboxTransport:
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_env(cls):
        import dropbox
        from core.beat_dropbox_http import DropboxSession
        key = os.environ.get("BEAT_DROPBOX_APP_KEY")
        token = os.environ.get("BEAT_DROPBOX_REFRESH_TOKEN")
        if not key or not token:
            raise CloudError("missing_beat_dropbox_credentials")
        return cls(dropbox.Dropbox(app_key=key, oauth2_refresh_token=token,
                                   session=DropboxSession(), timeout=30, max_retries_on_error=0,
                                   max_retries_on_rate_limit=0))

    def _call(self, operation):
        from dropbox.exceptions import ApiError, RateLimitError, InternalServerError
        from requests.exceptions import ConnectionError, Timeout
        try:
            return operation()
        except RateLimitError as exc:
            raise Transient(exc.backoff or 1) from None
        except (InternalServerError, ConnectionError, Timeout):
            raise Transient() from None
        except ApiError as exc:
            error = exc.error
            if hasattr(error, "is_path") and error.is_path():
                error = error.get_path()
                if hasattr(error, "reason"):
                    error = error.reason
                if hasattr(error, "is_not_found") and error.is_not_found():
                    raise Missing("document_missing") from None
                if hasattr(error, "is_conflict") and error.is_conflict():
                    raise Conflict("revision_conflict") from None
                if hasattr(error, "is_too_many_write_operations") and error.is_too_many_write_operations():
                    raise Transient(1) from None
            raise CloudError("dropbox_api_error") from None
        except Exception:
            raise CloudError("dropbox_error") from None

    def read(self, path):
        meta, response = self._call(lambda: self.client.files_download(path))
        try:
            limit = 8 * 1024 * 1024
            if type(meta.size) is not int or not 0 < meta.size <= limit:
                raise CloudError("document_too_large")
            data, deadline = bytearray(), time.monotonic() + 180
            for chunk in response.iter_content(65536):
                if time.monotonic() >= deadline:
                    raise CloudError('document_timeout')
                data.extend(chunk)
                if len(data) > limit:
                    raise CloudError('document_too_large')
            if len(data) != meta.size:
                raise CloudError('document_incomplete')
            return bytes(data), meta.rev
        except CloudError:
            raise
        except Exception:
            raise CloudError('document_read_failed') from None
        finally:
            response.close()

    def write(self, path, payload, rev):
        from dropbox.files import WriteMode
        mode = WriteMode.add if rev is None else WriteMode.update(rev)
        meta = self._call(lambda: self.client.files_upload(
            payload, path, mode=mode, autorename=False, strict_conflict=True))
        return meta.rev


class BeatCloud:
    def __init__(self, transport, retries=5, sleep=time.sleep):
        if type(retries) is not int or not 1 <= retries <= 10:
            raise ValueError("invalid_retries")
        self.transport, self.retries, self.sleep = transport, retries, sleep

    def _retry(self, call):
        for n in range(self.retries):
            try:
                return call()
            except Transient as exc:
                if n + 1 == self.retries:
                    raise CloudError("retry_exhausted") from None
                # Never retry earlier than Dropbox's Retry-After.
                self.sleep(max(0.1 * 2 ** n, exc.delay))

    def read(self, kind):
        path = self._path(kind)
        try:
            data, rev = self._retry(lambda: self.transport.read(path))
        except Missing:
            return migrate({}, kind), None
        try:
            return migrate(decode_document(data), kind), rev
        except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
            raise CloudError("invalid_cloud_document") from None

    @staticmethod
    def _path(kind):
        if kind not in ("config", "state"):
            raise ValueError("invalid_kind")
        return "/type-beats/" + kind + ".json"

    def write(self, kind, document, rev, before_write=None):
        validated = migrate(document, kind)
        payload = json.dumps(validated, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(payload) > 8 * 1024 * 1024:
            raise CloudError("document_too_large")
        def commit():
            if before_write is not None:
                before_write()
            return self.transport.write(self._path(kind), payload, rev)
        return self._retry(commit)

    def update(self, kind, mutate, guard=None, *, require_existing=False):
        """Reapply pure mutation after CAS conflict, including lost write responses."""
        for _ in range(self.retries):
            document, rev = self.read(kind)
            if require_existing and rev is None:
                raise Missing('document_missing')
            source = deepcopy(document) if guard is not None else None
            before = json.dumps(document, sort_keys=True)
            result = mutate(document)
            if guard is not None:
                guard(source)
            if rev is not None and before == json.dumps(document, sort_keys=True):
                return result
            try:
                self.write(kind, document, rev,
                           before_write=(lambda: guard(source)) if guard is not None else None)
                return result
            except Conflict:
                continue
        raise Conflict("revision_retry_exhausted")

    def initialize(self):
        for kind in ("config", "state"):
            # Persist migrations too, with the revision of the source document.
            for _ in range(self.retries):
                try:
                    payload, rev = self._retry(lambda: self.transport.read(self._path(kind)))
                    raw = decode_document(payload)
                    doc = migrate(raw, kind)
                    if doc == raw:
                        break
                except Missing:
                    doc, rev = migrate({}, kind), None
                except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
                    raise CloudError("invalid_cloud_document") from None
                try:
                    self.write(kind, doc, rev)
                    break
                except Conflict:
                    continue
            else:
                raise Conflict("revision_retry_exhausted")
