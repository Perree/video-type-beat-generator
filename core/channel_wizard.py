# -*- coding: utf-8 -*-
"""Asistente de alta de canal en piloto (Beats primero, luego Loop kits) y chips de estado.

La lógica (pasos, gate de activación, chips) no usa Qt y no lee valores de secretos: solo
códigos ``ok/missing`` de ``core/automation_status``. El diálogo es no modal para poder
usar la pestaña Conexiones del panel mientras se avanza. No hace red por su cuenta: delega
en los handlers del panel (OAuth de YouTube, sync por ``QProcess``, guardar y publicar).
"""
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from core import automation_status as status
import ui_theme as theme

BEATS, KITS = 'beats', 'kits'
TITLES = ('Canal', 'YouTube', 'Dropbox y avisos', 'Secretos de GitHub', 'Publicar y activar')
# Flags de sesión por canal: lo que la app no puede deducir leyendo archivos locales.
SECRETS, CONFIG, DRYRUN = 'secrets', 'config', 'dryrun'
_GREEN, _AMBER, _GRAY = theme.color('success'), theme.color('warning'), theme.color('text_muted')


def _items(kind, channel, slug, deps):
    """Checklist ``{id: ok}`` del canal. ``deps`` inyecta rutas/``which`` (tests y smoke)."""
    deps = deps or {}
    if kind == BEATS:
        rows = status.readiness_beats(channel, slug, **deps)
    else:
        rows = status.readiness_kits(channel, slug, **deps)
    return {r['id']: r['ok'] for r in rows}


def steps(kind, channel, slug, flags=(), deps=None):
    """Los 5 pasos del alta: ``[{id, title, ok}]``. ``flags`` son los de ``SECRETS/CONFIG/DRYRUN``."""
    ok, flags = _items(kind, channel, slug, deps), set(flags)
    first = ok.get('slug' if kind == BEATS else 'env', False)
    third = ok.get('dropbox', False) and (kind == BEATS or ok.get('telegram', False))
    done = [first, ok.get('youtube', False), third,
            ok.get('gh', False) and SECRETS in flags,
            CONFIG in flags and DRYRUN in flags]
    return [{'id': i + 1, 'title': t, 'ok': bool(d)} for i, (t, d) in enumerate(zip(TITLES, done))]


def can_activate(rows):
    """Gate de activación: solo con los 5 pasos en verde (config en Dropbox, secretos, dry-run)."""
    return all(r['ok'] for r in rows)


def blockers(rows):
    """Títulos de los pasos que faltan, para explicar por qué no se puede activar."""
    return [r['title'] for r in rows if not r['ok']]


def chip(rows):
    """``(texto, color)`` del chip de estado de un canal a partir de ``steps``."""
    done = sum(1 for r in rows if r['ok'])
    if done == len(rows):
        return '✔ Listo', _GREEN
    return (f'◐ {done}/{len(rows)}', _AMBER) if done else (f'○ 0/{len(rows)}', _GRAY)


class ChannelWizardHost:
    """Mixin de los paneles: guarda flags de sesión y abre el asistente.

    El panel define ``wizard_kind`` y ``wizard_target()``; los handlers existentes llaman
    a ``pilot_flag_set`` cuando una acción termina bien (sync, publicar, dry-run).
    """
    wizard_kind = BEATS

    def pilot_flags_for(self, key):
        store = self.__dict__.setdefault('pilot_flags', {})
        return store.setdefault((self.wizard_kind, key), set())

    def pilot_flag_set(self, key, name):
        self.pilot_flags_for(key).add(name)
        if hasattr(self, 'refresh_channel_chips'):
            self.refresh_channel_chips()

    def channel_chip(self, channel, slug, key, deps=None):
        """Chip del canal ``channel`` (``key`` indexa sus flags de sesión)."""
        return chip(steps(self.wizard_kind, channel, slug, self.pilot_flags_for(key), deps))

    def wizard_busy(self):
        """True si el panel tiene una tarea en curso (el formulario puede estar a medias)."""
        return bool(getattr(self, '_task', None) or getattr(self, 'task', None))

    def wizard_bind(self, channel, slug, key):
        """True solo si el formulario del panel es el del asistente y no hay una carga en curso.

        Si el usuario cambió de canal, intenta volver al del asistente. En Loop kits eso
        dispara un reload asíncrono: esta llamada falla y hay que repetir cuando termine.
        """
        current = self.wizard_target()
        if current[0] == channel and current[2] == key and not self.wizard_busy():
            return True
        focus = getattr(self, 'wizard_focus', None)
        if focus:
            focus(channel, slug, key)
        current = self.wizard_target()
        return current[0] == channel and current[2] == key and not self.wizard_busy()

    def wizard_notify(self, ok, detail=''):
        """Avisa al asistente abierto el resultado de publicar (no asume éxito)."""
        wiz = self.__dict__.get('_wizard')
        if wiz is not None:
            wiz.notify_publish(ok, detail)

    def open_channel_wizard(self, deps=None):
        """Abre (o trae al frente) el asistente del canal elegido en el panel."""
        wiz = self.__dict__.get('_wizard')
        if wiz is not None and wiz.isVisible():
            wiz.raise_()
            return wiz
        self._wizard = ChannelWizard(self, deps, self)
        self._wizard.show()
        return self._wizard


class ChannelWizard(QDialog):
    """Asistente de 5 pasos. El panel host expone los handlers que se reutilizan."""

    def __init__(self, host, deps=None, parent=None):
        super().__init__(parent)
        self.host, self.deps = host, deps
        self.kind = host.wizard_kind
        self.channel, self.slug, self.key = host.wizard_target()
        self._hold = False  # no pisar «Publicando…» / resultado con el texto del checklist
        self._awaiting = False
        self.setWindowTitle('Alta de canal en piloto')
        self.setModal(False)
        self.resize(560, 360)
        self.stack = QStackedWidget()
        self.state_labels = {}
        for i in range(5):
            self.stack.addWidget(self._page(i))
        self.header = QLabel()
        self.message = QLabel()
        self.message.setWordWrap(True)
        self.back_button, self.next_button = QPushButton('Atrás'), theme.primary(QPushButton('Siguiente'))
        self.back_button.clicked.connect(lambda: self._go(-1))
        self.next_button.clicked.connect(lambda: self._go(1))
        nav = QHBoxLayout()
        nav.addWidget(self.back_button)
        nav.addStretch(1)
        nav.addWidget(self.next_button)
        lay = QVBoxLayout(self)
        for w in (self.header, self.stack, self.message):
            lay.addWidget(w)
        lay.addLayout(nav)
        # Las acciones corren en el panel y terminan solas: se relee el estado cada tanto.
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(800)
        self.refresh()

    # --- Construcción de páginas ---

    def _button(self, lay, text, slot):
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        lay.addWidget(btn)
        return btn

    def _page(self, index):
        page = QWidget()
        lay = QVBoxLayout(page)
        text = QLabel(self._help(index))
        text.setWordWrap(True)
        lay.addWidget(text)
        state = QLabel()
        state.setWordWrap(True)
        self.state_labels[index] = state
        lay.addWidget(state)
        if index == 0 and self.kind == BEATS:
            self.slug_edit = QLineEdit(self.slug or '')
            self.slug_edit.setPlaceholderText('slug de Actions (minúsculas, números y guiones)')
            lay.addWidget(self.slug_edit)
            self.apply_slug_button = self._button(lay, 'Aplicar slug', self.apply_slug)
        elif index == 1:
            self.youtube_button = self._button(lay, 'Conectar YouTube', self.connect_youtube)
        elif index == 2:
            self._button(lay, 'Ir a la pestaña Conexiones', self.go_connections)
        elif index == 3:
            self.sync_button = self._button(lay, 'Sincronizar secretos', self.sync)
        elif index == 4:
            self.publish_button = self._button(lay, 'Publicar al robot (canal pausado)',
                                               self.publish)
            if self.kind == KITS:
                self.dry_button = self._button(lay, 'Probar sin subir', self.dry_run)
            else:
                # Beats no tiene dry-run local: se corre en Actions y se confirma a mano.
                self.dry_check = QCheckBox('Corrí el dry-run en Actions (workflow_dispatch con '
                                           'este canal) y salió bien')
                self.dry_check.toggled.connect(self._dry_attest)
                lay.addWidget(self.dry_check)
            self.activate_button = self._button(lay, 'Activar canal', self.activate)
        lay.addStretch(1)
        return page

    def _help(self, index):
        beats = self.kind == BEATS
        return (
            ('Definí el slug de Actions del canal (cada canal tiene sus secretos por slug).' if beats
             else 'El canal necesita un Environment válido (canal por defecto o slug de la lista).',
             'Autorizá la cuenta de YouTube del canal (se abre el navegador).',
             'Dropbox del robot' + ('' if beats else ' y Telegram') + ' se cargan una sola vez en '
             'Conexiones y sirven para todos los canales. Este paso se completa solo al quedar en verde.',
             'Con GitHub CLI instalada y logueada (TODO: gh auth login), subí los secretos del canal.',
             'Publicá la config (pausada), corré el dry-run y recién entonces activá el canal.'))[index]

    # --- Estado ---

    def _flags(self):
        return self.host.pilot_flags_for(self.key)

    def rows(self):
        return steps(self.kind, self.channel, self.slug, self._flags(), self.deps)

    def refresh(self):
        """Recalcula pasos, habilita botones y muestra qué falta."""
        rows = self.rows()
        for r in rows:
            self.state_labels[r['id'] - 1].setText(
                f'<span style="color:{_GREEN if r["ok"] else theme.color("danger")}">'
                f'{"✔ Listo" if r["ok"] else "✘ Pendiente"}</span>')
        index = self.stack.currentIndex()
        self.header.setText(f'<b>Canal: {self.channel or "(sin elegir)"}</b> — paso '
                            f'{index + 1} de 5: {TITLES[index]}')
        self.back_button.setEnabled(index > 0)
        self.next_button.setEnabled(index < 4)
        self.youtube_button.setEnabled(bool(self.channel))
        self.activate_button.setEnabled(can_activate(rows))
        if not self._hold:
            if not can_activate(rows):
                self.message.setText('Para activar faltan: ' + ', '.join(blockers(rows)) + '.')
            else:
                self.message.setText('Checklist en verde: ya podés activar el canal.')
        return rows

    def _go(self, delta):
        self._hold = False
        self.stack.setCurrentIndex(max(0, min(4, self.stack.currentIndex() + delta)))
        self.refresh()

    def _bound(self):
        """False si el panel no está en el canal congelado al abrir el asistente."""
        if self.host.wizard_bind(self.channel, self.slug, self.key):
            return True
        self._hold = True
        self.message.setText(
            'El panel no está en el canal del asistente. Esperá a que cargue y repetí.')
        return False

    # --- Acciones (delegan en el panel; siempre sobre self.channel, no el elegido ahora) ---

    def apply_slug(self):
        slug = self.slug_edit.text().strip()
        if not status.valid_slug(slug):
            self.message.setText('Slug inválido: minúsculas, números y guiones; empieza con letra.')
            return
        if not self.host.wizard_set_slug(self.channel, slug):
            self._hold = True
            self.message.setText(
                'No se aplicó el slug: el panel no está en el canal del asistente.')
            return
        self.slug = slug
        self.refresh()

    def connect_youtube(self):
        if self._bound():
            self.host.connect_youtube()

    def go_connections(self):
        self.host.tabs.setCurrentIndex(0)
        self.host.window().raise_()

    def sync(self):
        if self._bound():
            (self.host.sync_secrets if self.kind == BEATS else self.host.sync_kit_secrets)()

    def publish(self):
        if self._bound():
            self.host.save_and_publish()

    def dry_run(self):
        if self._bound():
            self.host.run_dry_run()

    def _dry_attest(self, checked):
        flags = self._flags()
        (flags.add if checked else flags.discard)(DRYRUN)
        self.refresh()

    def activate(self):
        """Defensa en profundidad: el botón ya está deshabilitado, pero se revalida el gate."""
        rows = self.rows()
        if not can_activate(rows):
            self._hold = True
            self.message.setText('Para activar faltan: ' + ', '.join(blockers(rows)) + '.')
            return
        if not self._bound():
            return
        self._hold = True
        self._awaiting = True
        self.message.setText('Publicando…')
        if self.host.wizard_activate() is False:
            self.notify_publish(False, 'No se pudo iniciar la publicación.')

    def notify_publish(self, ok, detail=''):
        """Resultado real de guardar y publicar (el panel llama esto al terminar)."""
        if not self._awaiting:
            return
        self._awaiting = False
        self._hold = True
        if ok:
            self.message.setText('Canal activado y publicado.' if self.kind == BEATS else
                                 'Config publicada. TODO: sumá el slug a KIT_CHANNELS en GitHub.')
        else:
            self.message.setText(detail or 'No se publicó. El canal no se activó.')

    def done(self, result):
        self.timer.stop()  # el timer no debe tocar el panel una vez cerrado el asistente
        super().done(result)
