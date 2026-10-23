import json
import os
import tempfile
import time
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication, QLineEdit, QPushButton

app = QApplication.instance() or QApplication([])

from core import cloud_login, connection_steps as cs, gh_status
from core.cloud_fakes import FakeGhRun


def wait_until(predicate, seconds=10):
    deadline = time.monotonic() + seconds
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.02)
    app.processEvents()
    return predicate()


def fields(wizard):
    return wizard.stack.currentWidget().findChildren(QLineEdit)


def button(wizard, text):
    return next(b for b in wizard.stack.currentWidget().findChildren(QPushButton) if text in b.text())


class ConnectionsViewTests(unittest.TestCase):
    def setUp(self):
        self.gh = FakeGhRun(logged_in=False)
        self.prev = gh_status.set_default(gh_status.GhStatus(run=self.gh))
        p = mock.patch.object(cs, "ensure_gh_on_path", lambda: True)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(cs, "open_url")
        self.opened = q.start()
        self.addCleanup(q.stop)
        cs.CloudPrep._cache.update(at=0.0, code=cs.MISSING)
        from core.connections_view import ConnectionsView
        self.view = ConnectionsView()
        self.view.show()
        app.processEvents()

    def tearDown(self):
        gh_status.set_default(self.prev)
        self.view.close_wizard()
        self.view.deleteLater()
        app.processEvents()

    def test_cards_split_required_and_optional(self):
        self.assertEqual(len(self.view.cards), 8)
        self.assertEqual(sum(c.required for c in self.view.connections), 5)
        self.assertIn("0 de 5", self.view.summary.text())
        title, intro, steps = self.view.guide()
        self.assertEqual(len(steps), 6)

    def test_dropbox_pc_flow(self):
        wizard = self.view.open("dropbox_pc")
        self.assertFalse(wizard.btn_next.isEnabled())
        fields(wizard)[0].setText("abc123appkey")
        wizard.update_state()
        wizard.btn_next.click()
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("Abrir Dropbox", wizard.hint.text())
        flow = mock.Mock()
        flow.finish.return_value = mock.Mock(refresh_token="refresh-token-xyz")
        with mock.patch.object(cloud_login, "dropbox_start", return_value=(flow, "https://dropbox/auth")):
            button(wizard, "Abrir Dropbox").click()
        self.opened.assert_called_with("https://dropbox/auth")
        fields(wizard)[0].setText("the-code")
        with mock.patch("dropbox.DropboxOAuth2FlowNoRedirect", create=True):
            wizard.update_state()
            wizard.btn_next.click()  # Guardar en esta PC (en segundo plano)
            self.assertTrue(wait_until(lambda: wizard.index == 2))
        self.assertEqual(cloud_login.dropbox_status(), cloud_login.OK)
        self.view.close_wizard()
        self.view.refresh()
        self.assertIn("1 de 5", self.view.summary.text())

    def test_github_login_flow(self):
        wizard = self.view.open("github")
        self.assertTrue(wizard.btn_next.isEnabled())  # instalado (simulado)
        wizard.btn_next.click()
        self.assertFalse(wizard.btn_next.isEnabled())
        with mock.patch.object(cs, "open_console") as console:
            button(wizard, "Iniciar sesión").click()
        self.assertIn("auth login", console.call_args[0][0])
        self.gh.logged_in = True
        button(wizard, "Revisar ahora").click()
        wizard.update_state()
        self.assertTrue(wizard.btn_next.isEnabled())

    def test_google_import_from_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "client_secret.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"installed": {"client_id": "id.apps", "client_secret": "sec"}}, f)
            wizard = self.view.open("google")
            self.assertFalse(wizard.btn_next.isEnabled())
            with mock.patch("core.connection_steps.QFileDialog.getOpenFileName", return_value=(path, "")):
                button(wizard, "Elegir el archivo").click()
            self.assertTrue(wait_until(lambda: cloud_login.client_secret_status() == cloud_login.OK))
            wizard.update_state()
            self.assertTrue(wizard.btn_next.isEnabled())

    def test_telegram_needs_github_then_saves_to_secrets(self):
        wizard = self.view.open("telegram")
        for field, value in zip(fields(wizard), ("123:ABC", "999")):
            field.setText(value)
        wizard.update_state()
        self.assertIn("GitHub", wizard.hint.text())
        self.gh.logged_in = True
        gh_status.default().invalidate()
        wizard.update_state()
        self.assertTrue(wizard.btn_next.isEnabled())
        wizard.btn_next.click()
        self.assertTrue(wait_until(lambda: wizard.index == 1))
        self.assertEqual(self.gh.value("kit-weekly", "KIT_TELEGRAM_CHAT_ID"), "999")
        for args, _stdin in self.gh.calls:
            self.assertNotIn("123:ABC", args)  # los valores viajan por stdin, nunca como argumento

    def test_cloud_prep_needs_dropbox(self):
        prep = self.view.connection("cloud_prep")
        self.assertEqual(prep.status(), cs.UNKNOWN)  # sin Dropbox no se sabe (no «Falta»)
        self.assertEqual(prep.status_text(), "Conectá Dropbox para revisar")
        wizard = self.view.open("cloud_prep")
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("conectá Dropbox", wizard.hint.text())

    def _prep_with_dropbox(self, migrados, omitidos=(), exists=False):
        cs.CloudPrep._cache.update(at=time.monotonic(), code=cs.OK if exists else cs.MISSING, reason="")
        report = {"migrados": list(migrados), "omitidos": list(omitidos), "avisos": []}
        patches = [mock.patch("core.connection_steps.cloud_login.dropbox_status", return_value=cs.OK),
                   mock.patch("scripts.migrate_to_cloud.read_app", return_value={}),
                   mock.patch("scripts.migrate_to_cloud.build", return_value=({}, {}, report))]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        return self.view.open("cloud_prep")

    def test_cloud_prep_blocks_empty_list_and_points_to_other_pc(self):
        wizard = self._prep_with_dropbox([], [{"canal": "x", "motivo": "tipo sin definir"}])
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("otra PC", wizard.hint.text())
        page_text = " ".join(label.text() for label in wizard.stack.currentWidget().findChildren(type(wizard.hint)))
        self.assertIn("no hay canales automatizados", page_text)

    def test_cloud_prep_ready_with_channels_and_says_when_already_done(self):
        channel = {"canal": "beat-a", "tipo": "beats", "slug": "beat-a", "legacy_default": False}
        wizard = self._prep_with_dropbox([channel])
        self.assertTrue(wizard.btn_next.isEnabled())
        self.assertEqual(wizard.btn_next.text(), "Crear en Dropbox")
        self.view.close_wizard()
        wizard = self._prep_with_dropbox([channel], exists=True)
        self.assertFalse(wizard.btn_next.isEnabled())
        self.assertIn("ya existe", wizard.hint.text())


class HomeConnectionsTests(unittest.TestCase):
    def test_home_has_connections_button(self):
        from core.home_screen import HomeScreen
        home = HomeScreen()
        hits = []
        home.connections_requested.connect(lambda: hits.append(1))
        home.btn_connections.click()
        self.assertEqual(hits, [1])
        home.deleteLater()


if __name__ == "__main__":
    unittest.main()
