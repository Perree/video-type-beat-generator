import unittest
import io
import os
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import HTTPError
from datetime import datetime, timezone, date
from core.automation_maintenance import next_slots, telegram_probe


class MaintenanceTests(unittest.TestCase):
    def test_tuesday_thursday_argentina_and_occupied_days(self):
        now = datetime(2026, 11, 2, 12, tzinfo=timezone.utc)
        self.assertEqual(next_slots(now, 3), ['2026-11-03T13:00:00Z',
            '2026-11-05T13:00:00Z', '2026-11-10T13:00:00Z'])
        self.assertEqual(next_slots(now, 1, {date(2026, 11, 3)}), ['2026-11-05T13:00:00Z'])

    def test_passed_slot_is_skipped(self):
        self.assertEqual(next_slots(datetime(2026, 11, 3, 13, tzinfo=timezone.utc), 1),
                         ['2026-11-05T13:00:00Z'])

    def test_probe_checks_bot_chat_and_delivery_without_logging_credentials(self):
        output = io.StringIO()
        with patch.dict(os.environ, {'KIT_TELEGRAM_TOKEN': 'private-token',
                                     'KIT_TELEGRAM_CHAT_ID': 'private-chat'}), \
             patch('urllib.request.urlopen', side_effect=lambda *a, **kw: io.BytesIO(b'{"ok":true}')) as send, \
             redirect_stdout(output):
            self.assertEqual(telegram_probe(), 0)
        self.assertEqual(send.call_count, 3)
        self.assertNotIn('private-token', output.getvalue())
        self.assertNotIn('private-chat', output.getvalue())

    def test_probe_stops_when_bot_token_is_rejected(self):
        output = io.StringIO()
        error = HTTPError('https://example.invalid', 401, 'Unauthorized', {},
                          io.BytesIO(b'{"ok":false,"error_code":401}'))
        with patch.dict(os.environ, {'KIT_TELEGRAM_TOKEN': 'private-token',
                                     'KIT_TELEGRAM_CHAT_ID': 'private-chat'}), \
             patch('urllib.request.urlopen', side_effect=error) as send, redirect_stdout(output):
            self.assertEqual(telegram_probe(), 1)
        self.assertEqual(send.call_count, 1)
        self.assertNotIn('private-token', output.getvalue())
