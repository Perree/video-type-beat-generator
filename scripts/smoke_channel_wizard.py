#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke offscreen del asistente de alta de canal y de los chips. Sin red ni gh real.

Uso: ``py -3 scripts/smoke_channel_wizard.py``. ``gh`` y el llavero son dobles en memoria
(``core/cloud_fakes``); no toca ``tokens/`` ni ``config/``.
"""
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from PyQt5.QtWidgets import QApplication

from core import automation_status as st, channel_wizard as cw, cloud_login, gh_status
from core.channel_wizard import ChannelWizard
from core.cloud_fakes import FakeGhRun, MemoryKeyring

APP = QApplication.instance() or QApplication([])
_failed = []


def check(cond, msg):
    if not cond:
        _failed.append(msg)
        print('FAIL:', msg)


class FakeHost(cw.ChannelWizardHost):
    """Panel mínimo: registra qué acciones del asistente se invocaron."""

    def __init__(self, kind, target):
        self.wizard_kind, self._target, self.calls = kind, target, []

    def wizard_target(self):
        return self._target

    def wizard_set_slug(self, channel, slug):
        if not self.wizard_bind(channel, slug, self._target[2]):
            return False
        self.calls.append(('slug', slug))
        return True

    def wizard_activate(self):
        self.calls.append('activate')
        return True

    def window(self):
        raise AssertionError('no debería usarse en el smoke')


def check_kind(kind, channel, slug, key):
    fake = FakeGhRun()
    gh = gh_status.GhStatus(run=fake)
    deps = {'gh': gh}
    env = st.kit_env_name(slug) if kind == cw.KITS else 'kit-weekly'
    yt = (st.beat_secret_names(slug)[1:] if kind == cw.BEATS else st.KIT_YT_KEYS)
    host = FakeHost(kind, (channel, slug, key))

    rows = cw.steps(kind, channel, slug, host.pilot_flags_for(key), deps)
    check(len(rows) == 5, f'{kind}: debe haber 5 pasos')
    check(not cw.can_activate(rows), f'{kind}: sin nada no se puede activar')
    check(cw.chip(rows)[0].startswith('○') or cw.chip(rows)[0].startswith('◐'),
          f'{kind}: chip parcial')

    fake.put(env, *yt, *st.KIT_DROPBOX_KEYS)
    if kind == cw.KITS:
        fake.put(env, *st.KIT_TELEGRAM_KEYS)
    gh.invalidate()
    wiz = ChannelWizard(host, deps)
    wiz.timer.stop()
    rows = wiz.refresh()
    check([r['ok'] for r in rows] == [True, True, True, False, False],
          f'{kind}: conexiones en verde, secretos y publicación pendientes: {rows}')
    check(not wiz.activate_button.isEnabled(), f'{kind}: activar bloqueado')

    # Cada flag por separado no alcanza: el gate exige los tres.
    host.pilot_flag_set(key, cw.SECRETS)
    host.pilot_flag_set(key, cw.CONFIG)
    wiz.refresh()
    check(not cw.can_activate(wiz.rows()), f'{kind}: falta dry-run')
    check(not wiz.activate_button.isEnabled(), f'{kind}: activar sigue bloqueado sin dry-run')
    wiz.activate()
    check('activate' not in host.calls, f'{kind}: activate() revalida el gate')

    host.pilot_flag_set(key, cw.DRYRUN)
    rows = wiz.refresh()
    check(cw.can_activate(rows) and wiz.activate_button.isEnabled(),
          f'{kind}: checklist verde habilita activar')
    check(cw.chip(rows)[0] == '✔ Listo', f'{kind}: chip listo')

    # El panel cambió de canal: no se activa el que está elegido ahora.
    host._target = ('otro', 'otro', 'otro')
    wiz.activate()
    check('activate' not in host.calls, f'{kind}: no activa un canal distinto al del asistente')

    host._target = (channel, slug, key)
    wiz.activate()
    check('activate' in host.calls, f'{kind}: activar con gate en verde')
    check('Publicando' in wiz.message.text(), f'{kind}: no asume éxito al toque ({wiz.message.text()})')
    wiz.notify_publish(False, 'CAS falló')
    check('CAS falló' in wiz.message.text(), f'{kind}: error de publicación visible')
    wiz.activate()
    wiz.notify_publish(True)
    check('activado' in wiz.message.text().lower() or 'publicada' in wiz.message.text().lower(),
          f'{kind}: éxito solo al confirmar Dropbox')

    # Un canal sin token vuelve a bloquear: el gate se evalúa de nuevo.
    fake.drop(env, *yt)
    gh.invalidate()
    check(not cw.can_activate(wiz.rows()), f'{kind}: sin YouTube no se activa')
    wiz.done(0)
    return host


def main():
    # Los paneles reales y el asistente sin deps usan el cliente compartido: también falso.
    gh_status.set_default(gh_status.GhStatus(run=FakeGhRun()))
    cloud_login.set_backend(MemoryKeyring())
    host = check_kind(cw.BEATS, 'canal-beats', 'canal-beats', 'canal-beats')

    # Slug inválido: el paso 1 no pasa y apply_slug rechaza el valor.
    host = FakeHost(cw.BEATS, ('canal-beats', '', 'canal-beats'))
    wiz = ChannelWizard(host)
    wiz.timer.stop()
    wiz.slug_edit.setText('Slug Inválido!')
    wiz.apply_slug()
    check(('slug', 'Slug Inválido!') not in host.calls, 'slug inválido rechazado')
    wiz.slug_edit.setText('canal-beats')
    wiz.apply_slug()
    check(('slug', 'canal-beats') in host.calls, 'slug válido aplicado')
    wiz.dry_check.setChecked(True)
    check(cw.DRYRUN in host.pilot_flags_for('canal-beats'), 'el dry-run se confirma a mano en Beats')
    wiz.done(0)

    check_kind(cw.KITS, 'Canal Kits', '', '')

    # Paneles reales: chips en las listas, sin tocar red ni archivos privados.
    from core.beat_panel import BeatPanel
    from core.beat_fakes import MemoryDropbox
    panel = BeatPanel(cloud_provider=MemoryDropbox)  # sin Dropbox real
    _deadline = time.monotonic() + 5
    while panel.task is not None and time.monotonic() < _deadline:
        QApplication.processEvents()
    check(hasattr(panel, 'wizard_button'), 'Beats: botón del asistente')
    for row in range(panel.automations.count()):
        text = panel.automations.item(row).text()
        check('·' in text and ('/5' in text or 'Listo' in text), f'Beats: chip en la lista ({text})')
    from loop_kit_panel import LoopKitPanel
    kits = LoopKitPanel()
    check(hasattr(kits, 'btn_wizard') and kits.chip_label.text() != '', 'Kits: chip y asistente')

    if _failed:
        print(f'smoke_channel_wizard: {len(_failed)} fallas')
        return 1
    print('smoke_channel_wizard: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
