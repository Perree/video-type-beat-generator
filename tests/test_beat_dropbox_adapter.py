"""Official SDK error unions, with a fake client: no network or credentials."""
import io
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.beat_cloud import DropboxTransport, Conflict, Missing, Transient, CloudError

try:
    import dropbox
    from dropbox.exceptions import ApiError, RateLimitError, InternalServerError, AuthError
    from dropbox.files import UploadError, UploadWriteFailed, WriteError, DownloadError, LookupError
except ImportError:
    dropbox = None


@unittest.skipIf(dropbox is None, "optional Dropbox SDK not installed")
class AdapterTests(unittest.TestCase):
    def test_upload_modes_exclusive_and_revision(self):
        calls = []
        client = SimpleNamespace(files_upload=lambda data, path, **kw:
                                 (calls.append((data, path, kw)) or SimpleNamespace(rev="new")))
        transport = DropboxTransport(client)
        self.assertEqual(transport.write("/type-beats/state.json", b"{}", None), "new")
        transport.write("/type-beats/state.json", b"{}", "0000000000000001")
        self.assertTrue(calls[0][2]["mode"].is_add())
        self.assertEqual(calls[1][2]["mode"].get_update(), "0000000000000001")
        self.assertTrue(all(c[2]["strict_conflict"] and not c[2]["autorename"] for c in calls))

    def test_actual_sdk_error_mapping(self):
        errors = [
            (ApiError("r", DownloadError.path(LookupError.not_found), None, None), Missing),
            (ApiError("r", UploadError.path(UploadWriteFailed(reason=WriteError.conflict(
                dropbox.files.WriteConflictError.file))), None, None), Conflict),
            (ApiError("r", UploadError.path(UploadWriteFailed(reason=WriteError.too_many_write_operations)), None, None), Transient),
            (RateLimitError("r", backoff=2), Transient),
            (InternalServerError("r", 503, "secret response"), Transient),
            (AuthError("r", "secret response"), CloudError),
        ]
        transport = DropboxTransport(None)
        for exception, expected in errors:
            def operation():
                raise exception
            with self.subTest(expected=expected), self.assertRaises(expected) as caught:
                transport._call(operation)
            self.assertNotIn("secret response", str(caught.exception))

    def test_read_response_closed_and_size_limit(self):
        class Response(io.BytesIO):
            @property
            def content(self):
                return self.getvalue()
            def iter_content(self, size):
                while chunk := self.read(size):
                    yield chunk
        response = Response(b"{}")
        client = SimpleNamespace(files_download=lambda _: (SimpleNamespace(rev="rev", size=len(response.getvalue())), response))
        transport = DropboxTransport(client)
        self.assertEqual(transport.read("/type-beats/state.json"), (b"{}", "rev"))
        self.assertTrue(response.closed)
        response = Response(b"x" * (8 * 1024 * 1024 + 1))
        with self.assertRaises(CloudError):
            transport.read("/type-beats/state.json")
        self.assertTrue(response.closed)

    def test_credentials_isolated_no_kit_fallback(self):
        with patch.dict("os.environ", {"KIT_DROPBOX_APP_KEY": "kit", "KIT_DROPBOX_REFRESH_TOKEN": "kit"}, clear=True):
            with self.assertRaises(CloudError):
                DropboxTransport.from_env()
        with patch.dict("os.environ", {"BEAT_DROPBOX_APP_KEY": "beat-key", "BEAT_DROPBOX_REFRESH_TOKEN": "beat-token"}, clear=True):
            with patch.object(dropbox, "Dropbox") as constructor:
                DropboxTransport.from_env()
                self.assertEqual(constructor.call_args.kwargs["app_key"], "beat-key")
                self.assertEqual(constructor.call_args.kwargs["oauth2_refresh_token"], "beat-token")
                self.assertEqual(constructor.call_args.kwargs["max_retries_on_error"], 0)


if __name__ == "__main__":
    unittest.main()
