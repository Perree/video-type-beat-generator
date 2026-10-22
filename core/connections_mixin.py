# -*- coding: utf-8 -*-
"""Base común de las pestañas Conexiones (Beats y Loop kits): hilo, log y semáforos.

El panel define ``_conn_say(texto, error)`` y ``refresh_connections()``. Las lecturas de
``gh`` del hilo principal se cargan en segundo plano (``gh_status.enable_background``); al
terminar, ``gh_updates().updated`` vuelve a llamar a ``refresh_connections``.
"""
import re

from PyQt5.QtCore import QObject, pyqtSignal

from core import automation_status as status, gh_status
from core.cloud_worker import CallWorker, detach

LIGHTS = {status.OK: ('●', '#2e9e4f', 'Listo'), status.MISSING: ('●', '#c0392b', 'Falta'),
          status.INVALID: ('●', '#d98e04', 'Inválido'),
          status.UNKNOWN: ('●', '#888888', 'Desconocido')}
_MAX_LOG = 4000


def sanitize_log(text):
    """Deja solo texto imprimible, sin secuencias largas parecidas a tokens, y con tope de tamaño."""
    text = ''.join(c for c in text if c == '\n' or 32 <= ord(c) < 127 or ord(c) > 159)
    text = re.sub(r'[A-Za-z0-9_\-./+=]{40,}', '[oculto]', text)
    return text[:_MAX_LOG]


class _GhUpdates(QObject):
    updated = pyqtSignal()  # se emite desde el hilo de gh; llega encolado al hilo principal


_updates = None


def gh_updates():
    """Puente Qt (único) entre las cargas de ``gh`` en segundo plano y los paneles."""
    global _updates
    if _updates is None:
        _updates = _GhUpdates()
    gh_status.default().enable_background(_updates.updated.emit)
    return _updates


class ConnectionsMixin:
    def _init_connections(self):
        self.conn_worker = None
        self._conn_after = None  # paso siguiente (en el hilo de la UI) al terminar el hilo
        gh_updates().updated.connect(self.refresh_connections)

    def _set_light(self, key, code, text=None):
        symbol, color, default = LIGHTS.get(code, LIGHTS[status.UNKNOWN])
        self.light_labels[key].setText(f'<span style="color:{color}">{symbol}</span> '
                                       f'{text or default}')

    def _set_gh_light(self, code):
        texts = {status.OK: 'Conectado', status.UNKNOWN: 'Consultando GitHub…'}
        self._set_light('gh', code, texts.get(code, 'Sin sesión (gh auth login)'))

    def _conn_start(self, fn, fallback, done_text, wait_text, on_ok=None):
        """Corre ``fn`` en un hilo; solo muestra mensajes propios (sin valores)."""
        if self.conn_worker is not None:
            return
        worker = CallWorker(fn, fallback, self)

        def ok(result):
            self._conn_say(done_text, False)
            if on_ok:
                on_ok(result)
        worker.done.connect(ok)
        worker.failed.connect(lambda text: self._conn_say(text, True))
        worker.finished.connect(self._conn_finished)
        self.conn_worker = worker
        self.refresh_connections()
        self._conn_say(wait_text, False)
        worker.start()

    def _conn_finished(self):
        worker, self.conn_worker = self.conn_worker, None
        if worker is not None:
            worker.deleteLater()
        self.refresh_connections()
        after, self._conn_after = self._conn_after, None
        if after is not None:
            after()

    def _confirm_youtube(self, channel, title):
        """Pregunta antes de pisar el token del canal en GitHub (los smokes lo reemplazan)."""
        from PyQt5.QtWidgets import QMessageBox
        answer = QMessageBox.question(
            self, 'Confirmar cuenta de YouTube',
            f'Google autorizó el canal «{title or "(sin título)"}».\n'
            f'¿Subir su token a GitHub como el canal «{channel}»?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        return answer == QMessageBox.Yes

    def _youtube_two_steps(self, channel, expected_id, push, on_pushed):
        """OAuth en un hilo → confirmar la cuenta en la UI → subir en otro hilo.

        Nada se escribe en GitHub si la cuenta no es la esperada (``expected_id``) o si el
        usuario no confirma. El token queda solo en memoria entre los dos pasos.
        """
        from core import youtube

        def authorized(result):
            token_json, title, got_id = result

            def next_step():
                error = status.youtube_identity_error(expected_id, got_id)
                if error:
                    self._conn_say(error, True)
                    return
                if not self._confirm_youtube(channel, title):
                    self._conn_say('No se subió nada a GitHub.', False)
                    return
                self._conn_start(lambda: push(token_json), 'No se pudo subir el token a GitHub.',
                                 'YouTube cargado en GitHub.', 'Subiendo el token a GitHub…',
                                 lambda _r: on_pushed(title))
            self._conn_after = next_step
        self._conn_start(youtube.authorize, 'No se pudo conectar YouTube.', 'Cuenta autorizada.',
                         'Esperando la autorización en el navegador…', authorized)

    def _conn_log_lines(self, lines):
        self.conn_log.appendPlainText(sanitize_log('\n'.join(lines)).rstrip())

    def stop_connections(self):
        """Al cerrar: suelta (sin esperar) el OAuth o gh en curso y el del recuadro «Esta PC».

        Esperar acá congelaría la app si el usuario cerró el navegador sin autorizar.
        """
        worker, self.conn_worker = self.conn_worker, None
        self._conn_after = None  # no confirmar ni subir nada de un panel que se cierra
        detach(worker)
        self.login_box.stop()
