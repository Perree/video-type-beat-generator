#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del panel de configuración de loop kits (offscreen). Sin red. Datos ficticios."""

import json
import os
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, 'scripts')):
    if p not in sys.path:
        sys.path.insert(0, p)

from smoke_kit_state import FakeDropbox  # también instala el doble de dropbox.files si falta

from PyQt5.QtWidgets import QApplication, QLineEdit

from core import kit_cloud, kit_settings, kit_state
from loop_kit_panel import LoopKitPanel

TG_TOKEN = 'SMOKE-TG-TOKEN-1a2b'
TG_CHAT = 'SMOKE-TG-CHAT-3c4d'
GENRES = ['genre-a', 'genre-b']

_failed = []


def check(cond, msg):
    if not cond:
        _failed.append(msg)
        print('FAIL:', msg)


def _kit(folder, url='https://example.com/p', genre='genre-a', active=True, name=None):
    return {'folder': folder, 'name': name or f'Name {folder}', 'payhip_url': url,
            'genre': genre, 'active': active}


def _config():
    return {'channels': {'chan': {'section': 'loop_kits', 'title': 'T'},
                         'other': {'section': 'beats'}},
            'kit_preview': {'dropbox_root': '/x', 'art': {'model': 'm', 'refs_root': '/old'},
                            'genres': ['genre-a'], 'trim': {'a': 1}}}


def _rejects(fn, *args):
    try:
        fn(*args)
    except kit_settings.SettingsError:
        return True
    return False


def _wait(app, panel, timeout=10):
    end = time.time() + timeout
    while panel._task is not None and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return panel._task is None


def _widget_texts(panel):
    texts = [panel.status.text(), panel.output.toPlainText(), panel.telegram.text(),
             panel.ref_folders.text(), panel.genres.toPlainText(), panel.refs_root.text()]
    for r in range(panel.table.rowCount()):
        texts += [panel._cell(r, c) for c in range(4)]
    return '\n'.join(texts)


def _check_validation():
    rows = [_kit('f1'), _kit('f2', url=''), {'folder': '', 'name': '', 'payhip_url': '',
                                              'genre': '', 'active': True}]
    pruned = kit_settings.prune_blank(rows)
    check(len(pruned) == 2, 'las filas vacías se descartan')
    out = kit_settings.validate_kits(pruned, GENRES)
    check([k['folder'] for k in out] == ['f1', 'f2'] and out[1]['payhip_url'] == '',
          'un kit sin link se admite')
    check(_rejects(kit_settings.validate_kits, [_kit('f', url='http://example.com')], GENRES),
          'link http rechazado')
    check(_rejects(kit_settings.validate_kits, [_kit('f', url='javascript:alert(1)')], GENRES),
          'link javascript rechazado')
    check(_rejects(kit_settings.validate_kits, [_kit('f', url='https://u:p@example.com/x')], GENRES),
          'link con usuario y clave rechazado')
    check(_rejects(kit_settings.validate_kits, [_kit('')], GENRES), 'carpeta vacía rechazada')
    check(_rejects(kit_settings.validate_kits, [_kit('f', name=' ')], GENRES), 'nombre vacío rechazado')
    check(_rejects(kit_settings.validate_kits, [_kit('f', genre='')], GENRES), 'género vacío rechazado')
    check(_rejects(kit_settings.validate_kits, [_kit('f', genre='zzz')], GENRES),
          'género no configurado rechazado')
    check(_rejects(kit_settings.validate_kits, [_kit('f'), _kit('F')], GENRES),
          'carpeta repetida rechazada')
    try:
        kit_settings.validate_kits([_kit('f1'), _kit('f2', url='http://x.y')], GENRES)
    except kit_settings.SettingsError as exc:
        check('Kit 2' in str(exc) and 'f2' not in str(exc) and 'x.y' not in str(exc),
              'el error nombra la fila, no el kit ni el link')

    good = {'channel': 'chan', 'genres': GENRES, 'refs_root': '/refs', 'cover_mode': 'auto',
            'slots': [{'weekday': 0, 'hour': 18, 'minute': 0}, {'weekday': 2, 'hour': 18, 'minute': 30}]}
    check(kit_settings.validate_settings(good)['cover_mode'] == 'auto', 'ajustes válidos')
    for bad in ({'slots': []}, {'slots': [{'weekday': 7, 'hour': 1, 'minute': 0}]},
                {'slots': good['slots'] + good['slots'][:1]}, {'genres': []},
                {'refs_root': 'sin-barra'}, {'refs_root': '/con espacio'},
                {'refs_root': '', 'cover_mode': 'auto'}, {'cover_mode': 'otro'}):
        check(_rejects(kit_settings.validate_settings, {**good, **bad}), f'ajustes inválidos: {bad}')

    cfg = _config()
    new = kit_settings.apply_to_config(cfg, kit_settings.validate_settings(good))
    check(cfg['kit_preview']['genres'] == ['genre-a'], 'apply_to_config no muta el original')
    kp = new['kit_preview']
    check(kp['trim'] == {'a': 1} and kp['art']['model'] == 'm' and new['channels'] == cfg['channels'],
          'las claves ajenas se conservan')
    check(kp['channel'] == 'chan' and kp['cover_mode'] == 'auto' and kp['art']['refs_root'] == '/refs'
          and kp['genres'] == GENRES and len(kp['slots']) == 2, 'las claves propias se actualizan')
    check(not kit_settings.reference_folders('', GENRES), 'sin raíz no hay carpetas de referencia')


def _check_panel(app):
    os.environ['KIT_TELEGRAM_TOKEN'] = TG_TOKEN
    os.environ['KIT_TELEGRAM_CHAT_ID'] = TG_CHAT
    dbx = FakeDropbox()
    dbx.files[kit_settings.CONFIG_PATH] = ('0000000000a1', json.dumps(_config()).encode())
    dbx.files[kit_settings.KITS_PATH] = ('0000000000a2', json.dumps([_kit('f1')]).encode())
    panel = LoopKitPanel(dbx_provider=lambda: dbx)

    check('Configurado' in panel.telegram.text(), 'Telegram muestra solo "configurado"')

    panel.reload()
    check(_wait(app, panel), 'la lectura termina')
    check(panel.table.rowCount() == 1 and panel.channel.currentText() == '',
          'carga inicial con el canal sin elegir')
    check([panel.channel.itemText(i) for i in range(panel.channel.count())] == ['', 'chan'],
          'solo se ofrecen canales de loop kits')
    check(panel.genres.toPlainText() == 'genre-a', 'carga los géneros')

    # Ejemplo del enunciado: lista de kits de ejemplo, con una fila en blanco.
    panel.genres.setPlainText('genre-a\ngenre-b')
    panel.channel.setCurrentText('chan')
    panel.refs_root.setText('/refs')
    panel.cover_mode.setCurrentIndex(1)
    panel.set_kits([_kit('f1'), _kit('f2', url='', genre='genre-b', active=False),
                    _kit('f3', genre='genre-b')])
    panel.add_kit_row()
    catalog, settings = panel.serialize()
    check([k['folder'] for k in catalog] == ['f1', 'f2', 'f3'], 'serializa los kits sin la fila vacía')
    check(json.loads(json.dumps(catalog)) == catalog, 'el catálogo es JSON válido')
    check(settings['cover_mode'] == 'auto' and len(settings['slots']) == 3, 'serializa los ajustes')
    check('/refs/genre-b' in panel.ref_folders.text(), 'muestra la carpeta de referencias del género')

    panel.save()
    check(_wait(app, panel), 'el guardado termina')
    saved_kits = json.loads(dbx.files[kit_settings.KITS_PATH][1])
    saved_cfg = json.loads(dbx.files[kit_settings.CONFIG_PATH][1])
    check([k['folder'] for k in saved_kits] == ['f1', 'f2', 'f3'], 'kits.json guardado')
    kp = saved_cfg['kit_preview']
    check(kp['cover_mode'] == 'auto' and kp['channel'] == 'chan' and kp['art']['refs_root'] == '/refs'
          and kp['art']['model'] == 'm' and kp['trim'] == {'a': 1}, 'config guardada sin perder claves')
    check(panel.status.text().startswith('Guardado'), 'estado: guardado')
    blob = (dbx.files[kit_settings.KITS_PATH][1] + dbx.files[kit_settings.CONFIG_PATH][1]).decode()
    check(TG_TOKEN not in blob and TG_CHAT not in blob, 'ningún secreto en los JSON guardados')

    # Validación en la UI: no sube nada si algo está mal.
    uploads = dbx.uploads
    panel.set_kits([_kit('f1', url='http://example.com')])
    panel.save()
    check(dbx.uploads == uploads and panel._task is None, 'un link http no se guarda')
    check('Kit 1' in panel.status.text(), 'el error de validación se muestra')
    panel.set_kits([_kit('f1')])

    # Otro proceso cambió kits.json: no se pisa.
    panel.reload()
    _wait(app, panel)
    dbx.files[kit_settings.KITS_PATH] = ('0000000000ff', b'[]')
    panel.save()
    _wait(app, panel)
    check('recargá' in panel.status.text(), 'conflicto de edición detectado')
    check(dbx.files[kit_settings.KITS_PATH][1] == b'[]', 'el cambio ajeno queda intacto')

    # Sin config en Dropbox los kits igual se guardan y se avisa de los ajustes.
    del dbx.files[kit_settings.CONFIG_PATH]
    panel.reload()
    _wait(app, panel)
    panel.set_kits([_kit('f9')])
    panel.genres.setPlainText('genre-a')
    panel.save()
    _wait(app, panel)
    check('ajustes' in panel.status.text() and kit_settings.CONFIG_PATH not in dbx.files,
          'sin config no se crea una a medias')
    check(json.loads(dbx.files[kit_settings.KITS_PATH][1])[0]['folder'] == 'f9', 'los kits sí se guardan')

    # Último estado: sin nombres de kit ni secretos.
    state = kit_state._empty()
    state['runs'].append({'id': 1, 'estado': 'scheduled', 'publish_at': '2030-01-01T21:00:00Z',
                          'youtube_id': 'abc123', 'video_name': 'Secret Name'})
    dbx.files[kit_state.STATE_PATH] = ('0000000000b1', json.dumps(state).encode())
    panel.show_last_state()
    _wait(app, panel)
    out = panel.output.toPlainText()
    check('abc123' in out and 'Secret Name' not in out, 'el estado muestra la corrida sin nombres')

    check(TG_TOKEN not in _widget_texts(panel) and TG_CHAT not in _widget_texts(panel),
          'ningún secreto en la interfaz')
    check(all(w.echoMode() == QLineEdit.Normal for w in panel.findChildren(QLineEdit)),
          'el panel no tiene campos de contraseña')
    panel.shutdown()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    _check_validation()
    _check_panel(app)
    for name in ('KIT_TELEGRAM_TOKEN', 'KIT_TELEGRAM_CHAT_ID'):
        os.environ.pop(name, None)
    check(not kit_settings.telegram_configured(), 'sin variables Telegram figura no configurado')
    if _failed:
        print(f'{len(_failed)} chequeo(s) fallaron.')
        return 1
    print('smoke_kit_panel: OK')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
