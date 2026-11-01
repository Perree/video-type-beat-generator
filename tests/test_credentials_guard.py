"""Los tests nunca tocan el llavero real ni ``gh`` real, y Conexiones dice el motivo verdadero."""
import json
import os
import tempfile
import unittest
from unittest import mock

from dropbox.exceptions import AuthError, BadInputError

from core import beat_cloud, cloud_login, gh_status, sandbox_guard
from core import connection_steps as cs
from core.beat_cloud import CloudError, DropboxTransport, Transient


class RunningTestsTests(unittest.TestCase):
    def test_detects_test_runners(self):
        env = {}
        self.assertTrue(sandbox_guard.running_tests({'pytest': 1}, 'x.py', env))
        self.assertTrue(sandbox_guard.running_tests({'unittest': 1}, 'unittest/__main__.py', env))
        self.assertTrue(sandbox_guard.running_tests({'unittest': 1}, 'runner.py', env))

    def test_app_and_plain_scripts_use_the_real_keyring(self):
        env = {}
        self.assertFalse(sandbox_guard.running_tests({'unittest': 1}, r'E:\app\main.py', env))
        self.assertFalse(sandbox_guard.running_tests({}, 'smoke.py', env))

    def test_override_for_deliberate_smokes(self):
        env = {sandbox_guard.OVERRIDE: '1'}
        self.assertFalse(sandbox_guard.running_tests({'pytest': 1}, 'x.py', env))


class KeyringSandboxTests(unittest.TestCase):
    def setUp(self):
        # Sin doble puesto por el test (como un test viejo que se olvidó): la guarda decide.
        self.addCleanup(cloud_login.set_backend, cloud_login.set_backend(None))
        self.addCleanup(setattr, cloud_login, '_test_backend', cloud_login._test_backend)
        cloud_login._test_backend = None

    def test_writes_go_to_memory_not_windows(self):
        import keyring
        with mock.patch.object(keyring, 'set_password') as real_set:
            cloud_login._set(cloud_login.DROPBOX_APP_KEY, 'abc123appkey')
        real_set.assert_not_called()
        self.assertEqual(cloud_login._get(cloud_login.DROPBOX_APP_KEY), 'abc123appkey')

    def test_gh_is_never_run(self):
        with mock.patch('subprocess.run') as run:
            self.assertEqual(gh_status._run(['secret', 'set', 'X'], 'value'), (127, ''))
        run.assert_not_called()


class DropboxErrorTests(unittest.TestCase):
    def call(self, exc):
        def boom():
            raise exc
        with self.assertRaises(CloudError) as ctx:
            DropboxTransport(None)._call(boom)
        return ctx.exception.args[0]

    def test_rejected_key_has_its_own_code(self):
        self.assertEqual(self.call(BadInputError('r', '{"error": "invalid_client"}')), 'dropbox_auth_error')
        self.assertEqual(self.call(AuthError('r', 'expired')), 'dropbox_auth_error')
        self.assertEqual(self.call(RuntimeError('x')), 'dropbox_error')


class CloudPrepReasonTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(cloud_login.set_backend, cloud_login.set_backend(None))
        cloud_login._set(cloud_login.DROPBOX_APP_KEY, 'realkey12345')
        cloud_login._set(cloud_login.DROPBOX_REFRESH_TOKEN, 'token')
        self.addCleanup(cloud_login.dropbox_forget)
        self.addCleanup(cs.CloudPrep._cache.update, dict(cs.CloudPrep._cache))

    def check(self, exc):
        cs.CloudPrep._cache.update(at=0.0, code=cs.UNKNOWN, reason='')
        with mock.patch('core.cloud_registry.CloudRegistry.read', side_effect=exc):
            cs.CloudPrep.check()
        return cs.CloudPrep._cache['reason']

    def test_reasons(self):
        self.assertEqual(self.check(CloudError('dropbox_auth_error')), 'auth')
        self.assertEqual(self.check(CloudError('No se pudo conectar Dropbox. Conectalo.')), 'auth')
        self.assertEqual(self.check(Transient()), 'offline')
        self.assertEqual(self.check(CloudError('document_too_large')), 'error')

    def test_rejected_key_turns_the_dropbox_card_red(self):
        self.check(CloudError('dropbox_auth_error'))
        self.assertEqual(cs.DropboxPC().status(), cs.INVALID)
        self.assertIn('Cambiar', cs.DropboxPC().status_text())
        self.assertIn('rechazó', cs.CloudPrep().status_text())
        self.check(Transient())
        self.assertEqual(cs.DropboxPC().status(), cs.OK)  # sin internet no es culpa de la clave
        self.assertIn('no respondió', cs.CloudPrep().status_text())


class GoogleClientTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(cloud_login.set_backend, cloud_login.set_backend(None))

    def write(self, client_id):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'client_secret.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'installed': {'client_id': client_id, 'client_secret': 'sec'}}, f)
        return path

    def test_test_value_is_invalid(self):
        cloud_login._set(cloud_login.YOUTUBE_CLIENT_SECRET,
                         json.dumps({'installed': {'client_id': 'id.apps', 'client_secret': 'sec'}}))
        self.addCleanup(cloud_login.forget_client_secret)
        missing = os.path.join(tempfile.mkdtemp(), 'none.json')
        self.assertEqual(cloud_login.client_secret_status(missing), cloud_login.INVALID)
        with self.assertRaises(cloud_login.LoginError):
            cloud_login.import_client_secret(self.write('id.apps'))

    def test_real_shape_is_accepted(self):
        cloud_login.import_client_secret(self.write('123-abc.apps.googleusercontent.com'))
        self.addCleanup(cloud_login.forget_client_secret)
        self.assertEqual(cloud_login.client_secret_status(), cloud_login.OK)


if __name__ == '__main__':
    unittest.main()
