"""Motivos de fallo de Beats: códigos fijos, legibles y sin datos sensibles."""
import json
import unittest
from types import SimpleNamespace

from googleapiclient.errors import HttpError

from core import youtube
from core.beat_cloud import CloudError, Transient
from core.beat_http import BeatError
from core.beat_notify import message
from core.beat_reasons import classify, lines, note


class RefreshError(Exception):
    """Mismo nombre que google.auth.exceptions.RefreshError."""


def http_error(status, reason=None, secret='SECRET'):
    body = {'error': {'message': secret, 'errors': [{'reason': reason, 'message': secret}]}}
    return HttpError(SimpleNamespace(status=status, reason='x'), json.dumps(body).encode())


class ClassifyTests(unittest.TestCase):
    def test_youtube_errors(self):
        self.assertEqual(classify(RefreshError('invalid_grant SECRET')), 'youtube_token_expired')
        self.assertEqual(classify(http_error(403, 'quotaExceeded')), 'youtube_quota')
        self.assertEqual(classify(http_error(400, 'uploadLimitExceeded')), 'youtube_upload_limit')
        self.assertEqual(classify(http_error(401)), 'youtube_token_expired')
        self.assertEqual(classify(http_error(403, 'otherReason')), 'youtube_forbidden')
        self.assertEqual(classify(http_error(503)), 'youtube_unavailable')
        self.assertEqual(classify(http_error(418)), 'youtube_http_418')

    def test_wrapped_errors_use_the_cause(self):
        try:
            try:
                raise http_error(403, 'quotaExceeded')
            except HttpError as e:
                raise youtube.YouTubeError('Error de YouTube SECRET') from e
        except youtube.YouTubeError as wrapped:
            self.assertEqual(classify(wrapped), 'youtube_quota')

    def test_project_codes_and_others(self):
        self.assertEqual(classify(ValueError('beat_config_missing')), 'beat_config_missing')
        self.assertEqual(classify(BeatError('scan_timeout')), 'scan_timeout')
        self.assertEqual(classify(CloudError('dropbox_api_error')), 'dropbox_api_error')
        self.assertEqual(classify(Transient(3)), 'dropbox_busy')
        self.assertEqual(classify(KeyError('BEAT_CHANNEL_ID')), 'missing_secret')
        self.assertEqual(classify(StopIteration()), 'channel_missing_in_config')
        self.assertEqual(classify(ConnectionResetError()), 'network_error')

    def test_free_text_never_becomes_a_code(self):
        for exc in (RuntimeError('SECRET token https://x'), ValueError('secret'),
                    ValueError('has spaces here'), KeyError('secret')):
            code = classify(exc)
            self.assertTrue(code.startswith('error_'), code)
            self.assertNotIn('secret', code.replace('error_', ''))


class MessageTests(unittest.TestCase):
    def test_message_lists_readable_reasons(self):
        summary = {'failed': 2}
        note(summary, RefreshError('SECRET'))
        note(summary, http_error(403, 'quotaExceeded'))
        note(summary, http_error(403, 'quotaExceeded'))
        text = message(summary)
        self.assertIn('Motivos:', text)
        self.assertIn('Reconectá el canal', text)
        self.assertIn('cuota diaria', text)
        self.assertIn('(x2)', text)
        self.assertNotIn('SECRET', text)

    def test_poisoned_reasons_are_ignored(self):
        summary = {'failed': 1, 'reasons': {'SECRET https://x': 1, 'ok_code': 'SECRET',
                                            'youtube_quota': 1}}
        text = message(summary)
        self.assertNotIn('SECRET', text)
        self.assertEqual(len(lines(summary)), 1)
        self.assertEqual(lines({'reasons': 'SECRET'}), [])

    def test_no_reasons_keeps_old_message(self):
        self.assertNotIn('Motivos', message({'uploaded': 1}))

    def test_unknown_code_is_shown_as_code(self):
        summary = {}
        note(summary, ValueError('seo_duplicate'))
        self.assertIn('seo_duplicate', message(summary))


class ActionTests(unittest.TestCase):
    def test_token_expired_goes_first_with_steps(self):
        summary = {'failed': 1}
        note(summary, RefreshError('SECRET'))
        text = message(summary)
        self.assertTrue(text.startswith('ACCIÓN NECESARIA:'))
        self.assertIn('pestaña Beats', text)
        self.assertIn('Conectar YouTube y subir a GitHub', text)
        self.assertIn('En producción', text)
        self.assertNotIn('SECRET', text)

    def test_no_action_for_transient_errors(self):
        summary = {'failed': 1}
        note(summary, http_error(503))
        self.assertTrue(message(summary).startswith('Type Beats daily'))

    def test_owner_mismatch_has_no_seven_day_hint(self):
        text = message({'reasons': {'youtube_owner_mismatch': 1}})
        self.assertIn('cuenta correcta', text)
        self.assertNotIn('7 días', text)

    def test_slug_prefix_only_when_valid(self):
        self.assertTrue(message({'slug': 'ey-mat'}).startswith('[ey-mat] Type Beats daily'))
        for bad in ('SECRET', 'a b', 'https://x', 7):
            self.assertTrue(message({'slug': bad}).startswith('Type Beats daily'))


class KitAlertTests(unittest.TestCase):
    def test_kit_alert_adds_reconnect_steps(self):
        from core import kit_notify
        text = kit_notify.alert(RefreshError('SECRET'), step='calendario')
        self.assertTrue(text.startswith('ACCIÓN NECESARIA:'))
        self.assertIn('pestaña Loop kits', text)
        self.assertIn("paso 'calendario'", text)
        self.assertNotIn('SECRET', text)
        wrapped = youtube.YouTubeError("El token de 'canal' no es válido; volvé a conectar el canal.")
        self.assertIn('token guardado en GitHub', kit_notify.alert(wrapped))

    def test_kit_alert_unchanged_for_other_errors(self):
        from core import kit_notify
        self.assertEqual(kit_notify.alert(ValueError('SECRET'), step='lock'),
                         "Loop kits: fallo el worker semanal en el paso 'lock' (ValueError). "
                         "Revisar el log de Actions.")


if __name__ == '__main__':
    unittest.main()
