#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del merge de 3 vías (core/cloud_merge) y su uso en los documentos de Dropbox.

Uso: ``py -3 scripts/smoke_cloud_merge.py``. Sin red: canales.json y /type-beats/config.json
van a core/beat_fakes.MemoryDropbox; kits.json al doble de smoke_kit_state.
"""
import json
import os
import sys
from copy import deepcopy
from threading import Event

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, 'scripts')):
    if path not in sys.path:
        sys.path.insert(0, path)

from core import cloud_merge, cloud_registry, kit_settings  # noqa: E402
from core.beat_cloud import BeatCloud  # noqa: E402
from core.beat_fakes import MemoryDropbox  # noqa: E402
from core.beat_panel_cloud import PanelCloud  # noqa: E402
from core.cloud_merge import MergeConflict, merge3  # noqa: E402

_failed = []


def check(cond, msg):
    if not cond:
        _failed.append(msg)
        print('FAIL:', msg)


def ficha(slug, tipo='beats', **extra):
    return dict({'slug': slug, 'tipo': tipo, 'clave': slug, 'nombre': slug, 'activo': True,
                 'legacy_default': False}, **extra)


def registry(*rows):
    return cloud_registry.normalize('canales', dict(cloud_registry.empty('canales'),
                                                    canales=list(rows)))


def check_pure():
    base = {'a': 1, 'b': 1, 'n': {'x': 1, 'y': 1}}
    merged, choques = merge3(base, dict(base, a=2, n={'x': 2, 'y': 1}),
                             dict(base, b=3, n={'x': 1, 'y': 3}))
    check(not choques and merged == {'a': 2, 'b': 3, 'n': {'x': 2, 'y': 3}},
          f'campos distintos se fusionan: {merged} {choques}')
    merged, choques = merge3(base, dict(base, a=2), dict(base, a=3))
    check([c['ruta'] for c in choques] == ['a'] and choques[0]['mio'] == 2 and choques[0]['nube'] == 3,
          f'mismo campo da choque: {choques}')
    check(base == {'a': 1, 'b': 1, 'n': {'x': 1, 'y': 1}}, 'merge3 no modifica la base')

    base = registry(ficha('x'))
    mine = deepcopy(base)
    mine['canales'].append(ficha('y'))
    theirs = deepcopy(base)
    theirs['canales'].append(ficha('z', 'loops'))
    merged, choques = merge3(base, mine, theirs)
    check(not choques and [r['slug'] for r in merged['canales']] == ['x', 'z', 'y'],
          f'altas concurrentes se conservan: {merged["canales"]} {choques}')

    mine = deepcopy(base)
    mine['canales'] = []
    theirs = deepcopy(base)
    theirs['canales'][0]['nombre'] = 'Editado en otra PC'
    merged, choques = merge3(base, mine, theirs)
    check(len(choques) == 1 and choques[0]['ruta'] == 'canales[slug=x]',
          f'borrado contra edición da choque: {choques}')
    merged, choques = merge3(base, mine, deepcopy(base))
    check(not choques and merged['canales'] == [], 'borrado sin edición ajena se aplica')

    merged, choques = merge3(base, theirs, deepcopy(theirs))
    check(not choques and merged == theirs, 'el mismo cambio en los dos lados no choca')
    merged, choques = merge3({'tags': ['a']}, {'tags': ['a', 'b']}, {'tags': ['c']})
    check(len(choques) == 1 and choques[0]['ruta'] == 'tags', 'listas sin identidad = un valor')


def check_registry_cas():
    memory = MemoryDropbox()
    service = cloud_registry.CloudRegistry(memory)
    base = registry(ficha('x'))
    rev = service.write('canales', base, None)
    other = deepcopy(base)
    other['canales'].append(ficha('z', 'loops'))
    service.write('canales', other, rev, base)
    mine = deepcopy(base)
    mine['canales'].append(ficha('y'))
    saved, new_rev = service.save('canales', mine, base, rev)
    stored, stored_rev = service.read('canales')
    check([r['slug'] for r in stored['canales']] == ['x', 'z', 'y'] and stored == saved
          and stored_rev == new_rev, 'canales.json: alta concurrente fusionada tras Conflict')

    before = memory.files[cloud_registry.PATHS['canales']]
    a, b = deepcopy(stored), deepcopy(stored)
    a['canales'][0]['nombre'] = 'Nombre A'
    b['canales'][0]['nombre'] = 'Nombre B'
    service.write('canales', a, stored_rev, stored)
    after_other = memory.files[cloud_registry.PATHS['canales']]
    try:
        service.save('canales', b, stored, stored_rev)
        check(False, 'canales.json: mismo campo debe dar MergeConflict')
    except MergeConflict as exc:
        check([c['ruta'] for c in exc.choques] == ['canales[slug=x].nombre'],
              f'ruta del choque: {exc.choques}')
    check(memory.files[cloud_registry.PATHS['canales']] == after_other != before,
          'con choque no se escribe nada')


def _beat_config():
    slot = [{'weekday': 0, 'hour': 18, 'minute': 0}]
    return {'beatstars_profile_url': 'https://www.beatstars.com/fixtureproducer',
            'channels': [{'id': 'uno', 'active': True, 'priority': 0, 'slots': slot,
                          'tags': ['a']},
                         {'id': 'dos', 'active': False, 'priority': 0, 'slots': slot}]}


def check_beats_config():
    memory = MemoryDropbox()
    reg = registry(ficha('uno'), ficha('dos'), ficha('tres'))
    cloud, service = BeatCloud(memory), PanelCloud(memory)
    from core import beat_settings
    base = beat_settings.validate(_beat_config(), reg)
    rev = cloud.write('config', base, None)
    base, rev = cloud.read('config')
    other = deepcopy(base)
    other['channels'][0]['priority'] = 5
    other['channels'].append({'id': 'tres', 'active': False, 'priority': 0,
                              'slots': [{'weekday': 2, 'hour': 9, 'minute': 0}]})
    cloud.write('config', other, rev)
    state_before = dict(memory.files)
    mine = deepcopy(base)
    mine['channels'][0]['tags'] = ['mio']
    saved, _ = service.save_config_merged(mine, base, rev, reg, Event())
    stored, _ = cloud.read('config')
    first = stored['channels'][0]
    check(first['priority'] == 5 and first['tags'] == ['mio']
          and [c['id'] for c in stored['channels']] == ['uno', 'dos', 'tres'] and stored == saved,
          f'/type-beats/config.json: campos distintos y altas fusionados: {stored["channels"]}')
    check('/type-beats/state.json' not in memory.files and set(memory.files) == set(state_before),
          'el merge de config no crea estado')
    base, rev = cloud.read('config')
    a, b = deepcopy(base), deepcopy(base)
    a['channels'][1]['active'] = True
    b['channels'][1]['active'] = False
    b['channels'][1]['priority'] = 1
    a['channels'][1]['priority'] = 2
    cloud.write('config', a, rev)
    try:
        service.save_config_merged(b, base, rev, reg, Event())
        check(False, 'config: mismo campo debe dar MergeConflict')
    except MergeConflict as exc:
        check('channels[id=dos].priority' in [c['ruta'] for c in exc.choques],
              f'choque en config: {exc.choques}')


def check_kits():
    from smoke_kit_state import FakeDropbox
    dbx = FakeDropbox()
    kits = [{'folder': 'f1', 'name': 'Uno', 'payhip_url': '', 'genre': 'g', 'description': '',
             'active': True},
            {'folder': 'f2', 'name': 'Dos', 'payhip_url': '', 'genre': 'g', 'description': '',
             'active': True}]
    _, rev = kit_settings.save_kits_merged(kits, None, None, dbx)
    other = deepcopy(kits)
    other[1]['name'] = 'Dos (otra PC)'
    other.append(dict(kits[0], folder='f3', name='Tres'))
    kit_settings.save_kits(other, rev, dbx)
    mine = deepcopy(kits)
    mine[0]['active'] = False
    saved, _ = kit_settings.save_kits_merged(mine, kits, rev, dbx)
    stored = json.loads(dbx.files[kit_settings.KITS_PATH][1])
    check(stored == saved and [k['folder'] for k in stored] == ['f1', 'f2', 'f3']
          and stored[0]['active'] is False and stored[1]['name'] == 'Dos (otra PC)',
          f'kits.json fusionado por folder: {stored}')

    config = {'channels': {'c': {'section': 'loop_kits'}},
              'kit_preview': {'channel': 'c', 'genres': ['g'], 'slots': [], 'trim': {'a': 1}}}
    from core import kit_cloud
    rev = kit_cloud.write_json(kit_settings.CONFIG_PATH, config, rev=kit_cloud.NEW, dbx=dbx)
    other = deepcopy(config)
    other['kit_preview']['trim'] = {'a': 2}
    kit_cloud.write_json(kit_settings.CONFIG_PATH, other, rev=rev, dbx=dbx)
    form = kit_settings.form_from_config(config)
    settings = kit_settings.validate_settings(dict(form, genres=['g', 'h'], channel='c',
                                                   refs_root='', cover_mode='manual'))
    kit_settings.save_config_merged(settings, config, rev, dbx)
    stored, _ = kit_cloud.read_json_rev(kit_settings.CONFIG_PATH, dbx=dbx)
    check(stored['kit_preview']['trim'] == {'a': 2} and stored['kit_preview']['genres'] == ['g', 'h'],
          f'config de kits: cambio ajeno y propio fusionados: {stored["kit_preview"]}')


def main():
    check_pure()
    check_registry_cas()
    check_beats_config()
    check_kits()
    if _failed:
        print(f'smoke_cloud_merge: {len(_failed)} fallas')
        return 1
    print('smoke_cloud_merge: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
