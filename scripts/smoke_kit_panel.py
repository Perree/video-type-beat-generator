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
from smoke_kit_scan import STORE, FakeStore, _tree

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QLineEdit

from core import kit_cloud, kit_settings, kit_source, kit_state
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
            'kit_preview': {'dropbox_root': STORE, 'art': {'model': 'm', 'refs_root': '/old'},
                            'genres': ['genre-a'], 'trim': {'a': 1}}}


class StoreDropbox(FakeDropbox):
    """JSON en memoria más el listado de carpetas de la tienda falsa."""

    def __init__(self):
        super().__init__()
        self.store = FakeStore(_tree())

    def files_list_folder(self, path):
        return self.store.files_list_folder(path)


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
    check(kp['dropbox_root'] == STORE and 'scan_folders' not in kp,
          'sin campos de carpeta en el formulario la config no cambia')

    # Carpeta raíz, categorías, carpetas de loops y nombres a ignorar.
    scan = {'dropbox_root': '/tienda con espacios/', 'scan_folders': ['B', 'A', 'b'],
            'loops_dirs': 'loops, WAV', 'ignore_names': 'tag, preview', 'scan_max_depth': 2}
    out = kit_settings.validate_settings({**good, **scan})
    check(out['dropbox_root'] == '/tienda con espacios' and out['scan_folders'] == ['B', 'A']
          and out['loops_dirs'] == ['loops', 'WAV'] and out['ignore_names'] == ['tag', 'preview']
          and out['scan_max_depth'] == 2, f'campos de carpeta normalizados: {out}')
    for bad in ({'dropbox_root': 'sin-barra'}, {'loops_dirs': ' , '}, {'scan_max_depth': 0},
                {'scan_max_depth': 'x'}):
        check(_rejects(kit_settings.validate_settings, {**good, **scan, **bad}),
              f'carpeta inválida: {bad}')
    kp = kit_settings.apply_to_config(cfg, out)['kit_preview']
    check(kp['dropbox_root'] == '/tienda con espacios' and kp['scan_folders'] == ['B', 'A']
          and kp['loops_dirs'] == ['loops', 'WAV'] and kp['scan_max_depth'] == 2
          and kp['trim'] == {'a': 1}, 'los campos de carpeta se guardan en kit_preview')
    empty_root = kit_settings.validate_settings({**good, **scan, 'dropbox_root': ''})
    check(kit_settings.apply_to_config(cfg, empty_root)['kit_preview']['dropbox_root'] == STORE,
          'una raíz vacía no borra la guardada')
    form = kit_settings.form_from_config(cfg)
    check(form['dropbox_root'] == STORE and form['loops_dirs'] == ['loops']
          and form['scan_folders'] == list(kit_source.DEFAULT_SCAN_FOLDERS)
          and form['ignore_names'] == ['tag', 'preview'] and form['scan_max_depth'] == 3,
          'el formulario arranca con los defaults del recorrido')
    check(kit_settings.form_from_config({'kit_preview': {'scan_folders': []}})['scan_folders'] == [],
          'una lista de categorías vacía se respeta')


def _check_panel(app):
    os.environ['KIT_TELEGRAM_TOKEN'] = TG_TOKEN
    os.environ['KIT_TELEGRAM_CHAT_ID'] = TG_CHAT
    dbx = StoreDropbox()
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

    # Carpeta de kits: casillas armadas leyendo Dropbox, con las de la config marcadas.
    cats = [panel.categories.item(i).text() for i in range(panel.categories.count())]
    check(panel.kits_root.text() == STORE and cats == list(kit_source.DEFAULT_SCAN_FOLDERS)
          + ['STASH KITS'], f'casillas de categorías: {cats}')
    check(panel.checked_categories() == list(kit_source.DEFAULT_SCAN_FOLDERS),
          'STASH KITS queda sin marcar')
    check(panel.loops_dirs.text() == 'loops' and panel.ignore_names.text() == 'tag, preview',
          'carpetas de loops y nombres a ignorar por defecto')

    # Detectar kits: suma las carpetas con loops, sin link, y no toca lo ya cargado.
    panel.detect_kits()
    check(_wait(app, panel), 'la detección termina')
    rows = {r['folder']: r for r in panel.kit_rows()}
    check(panel.table.rowCount() == 8 and rows['f1']['payhip_url'], 'la tabla suma los 7 kits')
    check(all(not r['payhip_url'] and not r['genre'] for f, r in rows.items() if f != 'f1'),
          'los kits detectados llegan sin link ni género')
    check(rows['Smoke Alpha (1)']['active'] is False and rows['Smoke Alpha']['active'] is True,
          'la carpeta duplicada llega inactiva')
    check('Smoke Drum Kit' not in rows and 'Kicks' not in rows, 'el drum kit no se detecta')
    panel.detect_kits()
    _wait(app, panel)
    check(panel.table.rowCount() == 8, 'detectar dos veces no duplica filas')
    panel.categories.item(0).setCheckState(Qt.Unchecked)
    panel.set_kits([_kit('f1')])
    panel.detect_kits()
    _wait(app, panel)
    check(panel.table.rowCount() == 4, 'una categoría sin marcar no se recorre')
    panel.kits_root.setText('')
    panel.detect_kits()
    check(panel._task is None and 'raíz' in panel.status.text(), 'sin carpeta raíz no se busca')
    panel.kits_root.setText(STORE)
    panel.read_categories()
    _wait(app, panel)
    check(panel.categories.count() == 5 and len(panel.checked_categories()) == 3,
          'leer categorías conserva las marcadas')

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
    check(kp['dropbox_root'] == STORE and kp['loops_dirs'] == ['loops']
          and kp['scan_folders'] == list(kit_source.DEFAULT_SCAN_FOLDERS)[1:]
          and kp['ignore_names'] == ['tag', 'preview'] and kp['scan_max_depth'] == 3,
          f"carpeta y categorías guardadas en la config del canal: {kp.get('scan_folders')}")
    check(panel.status.text().startswith('Guardado'), 'estado: guardado')
    blob = (dbx.files[kit_settings.KITS_PATH][1] + dbx.files[kit_settings.CONFIG_PATH][1]).decode()
    check(TG_TOKEN not in blob and TG_CHAT not in blob, 'ningún secreto en los JSON guardados')

    # Portada por plantilla: modo, prompt editable, topes y descripción por kit.
    default = kit_settings.default_prompt()
    headers = [panel.table.horizontalHeaderItem(c).text() for c in range(panel.table.columnCount())]
    check(headers[4:] == ['Descripción', 'Activo'], f'columna Descripción en la tabla: {headers}')
    check(panel.cover_mode.findData('template') == 2 and panel.cover_mode.findData('manual') == 0,
          'el modo "Plantilla + fondo" se suma sin quitar el manual')
    check(panel.art_prompt.toPlainText() == default and '{titulo}' in default,
          'el editor arranca con el prompt por defecto')
    check(panel.monthly_cap.value() == 10.0 and panel.max_images.value() == 6,
          'topes por defecto: USD 10 por mes y 6 imágenes por corrida')
    panel.cover_mode.setCurrentIndex(2)
    panel.art_prompt.setPlainText('Prompt propio sin marcador')
    panel.save()
    check(_wait(app, panel) and panel.status.text().startswith('Guardado'),
          'un prompt sin {titulo} se guarda (el worker agrega el título al final)')
    panel.art_prompt.setPlainText('Prompt propio con {titulo}')
    panel.monthly_cap.setValue(7.5)
    panel.max_images.setValue(4)
    panel.set_kits([dict(_kit('f1'), description='  guitarras  tristes '), _kit('f2')])
    check(panel.kit_rows()[1]['active'] is True and panel.kit_rows()[0]['description'],
          'la tabla lee la descripción y el activo de sus columnas')
    panel.save()
    check(_wait(app, panel) and panel.status.text().startswith('Guardado'), 'guarda el modo plantilla')
    kp = json.loads(dbx.files[kit_settings.CONFIG_PATH][1])['kit_preview']
    check(kp['cover_mode'] == 'template' and kp['art']['prompt'] == 'Prompt propio con {titulo}'
          and kp['spend'] == {'monthly_cap_usd': 7.5, 'max_images_per_run': 4}
          and kp['art']['model'] == 'm', f"modo plantilla guardado en la config: {kp.get('spend')}")
    saved_kits = json.loads(dbx.files[kit_settings.KITS_PATH][1])
    check(saved_kits[0].get('description') == 'guitarras tristes'
          and 'description' not in saved_kits[1], 'la descripción se guarda solo si existe')
    panel.reload()
    _wait(app, panel)
    check(panel.cover_mode.currentData() == 'template' and panel.monthly_cap.value() == 7.5
          and panel.max_images.value() == 4
          and panel.art_prompt.toPlainText() == 'Prompt propio con {titulo}'
          and panel._cell(0, 4) == 'guitarras tristes', 'el modo plantilla se vuelve a cargar')
    panel.restore_prompt()
    check(panel.art_prompt.toPlainText() == default, 'el botón restaura el prompt por defecto')
    panel.save()
    _wait(app, panel)
    kp = json.loads(dbx.files[kit_settings.CONFIG_PATH][1])['kit_preview']
    check('prompt' not in kp['art'], 'el prompt por defecto no se guarda en la config')
    panel.set_kits([dict(_kit('f1'), description='x' * 201)])
    panel.save()
    check(panel._task is None and 'Kit 1' in panel.status.text(),
          'una descripción de más de 200 caracteres no se guarda')
    panel.cover_mode.setCurrentIndex(1)

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
    check('Gasto estimado' in out and 'USD 0.00' in out, 'el estado muestra el gasto estimado del mes')
    from datetime import datetime
    from core import kit_spend
    kit_spend.record(state, kit_spend.month_key(datetime.now()), 1.26, images=5, verifications=1)
    dbx.files[kit_state.STATE_PATH] = ('0000000000b2', json.dumps(state).encode())
    panel.monthly_cap.setValue(7.5)
    panel.show_last_state()
    _wait(app, panel)
    check('USD 1.26 de 7.50' in panel.output.toPlainText(), 'gasto del mes contra el tope del panel')

    # SEO por género: una ficha por género, y horarios repetidos = menos videos.
    panel.genres.setPlainText('genre-a\ngenre-b')
    check([panel.seo_genre.itemText(i) for i in range(panel.seo_genre.count())] == GENRES,
          'el selector de SEO sigue a la lista de géneros')
    panel.seo_phrase.setText('Smoke Loop Kit')
    panel.seo_artists.setPlainText('Artist Uno\n\nSecond Act')
    panel.seo_tags.setPlainText('Dark\nSad')
    panel.seo_genre.setCurrentIndex(1)
    check(panel.seo_phrase.text() == '' and panel.seo_artists.toPlainText() == '',
          'cada género tiene su ficha')
    panel.seo_genre.setCurrentIndex(0)
    check(panel.seo_phrase.text() == 'Smoke Loop Kit' and not panel.vary_name.isChecked(),
          'la ficha se conserva al cambiar de género y "variar el nombre" arranca apagado')
    _catalog, settings = panel.serialize()
    check(settings['seo'] == {'genre-a': {'phrase': 'Smoke Loop Kit', 'tags': ['Dark', 'Sad'],
                                          'artists': ['Artist Uno', 'Second Act']}}
          and settings['vary_name'] is False, f"serializa la ficha de SEO: {settings.get('seo')}")
    panel.seo_template.setText('{phrase} sin nombre')
    panel.save()
    check(panel._task is None and 'SEO de "genre-a"' in panel.status.text(),
          'una plantilla de título inválida no se guarda')
    panel.seo_template.setText('')
    for i in (1, 2):
        panel.slot_day[i].setCurrentIndex(panel.slot_day[0].currentIndex())
        panel.slot_time[i].setTime(panel.slot_time[0].time())
    check(len(panel.serialize()[1]['slots']) == 1, 'tres filas con el mismo horario son un solo horario')
    panel.set_form({**kit_settings.form_from_config({'kit_preview': {
        'genres': ['genre-b'], 'names': {'vary_name': True},
        'slots': [{'weekday': 3, 'hour': 9, 'minute': 15}],
        'seo': {'Genre-B': {'phrase': 'Otra frase', 'artists': ['Uno']}}}}), 'categories': []})
    check(panel.seo_phrase.text() == 'Otra frase' and panel.vary_name.isChecked()
          and len(panel.form_values()['slots']) == 1
          and list(panel.seo_values()) == ['genre-b'],
          'la config guardada (un horario, ficha y variar nombre) se vuelve a cargar')

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
