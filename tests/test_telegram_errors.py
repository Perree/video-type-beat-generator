import io
import json
import ssl
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from core import kit_notify


class TelegramErrorsTests(unittest.TestCase):
    def failure(self, code, description):
        return HTTPError('https://example.invalid/private-token', code, 'private-token', {},
            io.BytesIO(json.dumps({'ok': False, 'description': description}).encode()))

    def test_actionable_errors_and_no_credentials(self):
        for code, description, expected in [
            (401, 'Unauthorized private-token', 'token'),
            (400, 'Bad Request: chat not found private-token', '/start'),
            (403, 'Forbidden: bot was blocked by the user private-token', 'Desbloquealo'),
            (403, 'Forbidden private-token', 'permiso'),
            (429, 'Too many requests private-token', 'Esperá'),
            (503, 'private-token', 'temporal'),
            (400, 'private-token', 'solicitud'),
        ]:
            with self.subTest(code=code, description=description):
                with patch('core.kit_http.open_request', side_effect=self.failure(code, description)):
                    with self.assertRaises(kit_notify.KitNotifyError) as ctx:
                        kit_notify.send('test', env={'KIT_TELEGRAM_TOKEN': 'private-token',
                                                    'KIT_TELEGRAM_CHAT_ID': 'private-chat'})
                self.assertIn(expected, str(ctx.exception))
                self.assertNotIn('private-token', str(ctx.exception))
                self.assertIsNone(ctx.exception.__cause__)

    def test_connection_and_certificate_failures(self):
        from core.telegram_errors import message
        self.assertIn('certificado', message(URLError(ssl.SSLCertVerificationError('private-token'))))
        self.assertIn('conectar', message(URLError(TimeoutError('private-token'))))

    def test_untrusted_sdk_error_remains_hidden_by_worker(self):
        from core.cloud_worker import CallWorker
        def fail():
            raise ValueError('private-token')
        worker = CallWorker(fail, 'Error genérico')
        seen = []
        worker.failed.connect(seen.append)
        worker.run()
        self.assertEqual(seen, ['Error genérico'])
