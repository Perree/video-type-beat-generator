#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke de core/channel_kind: nombres actuales (Beats, Loops, legacy) y reglas del registro.

Uso: ``py -3 scripts/smoke_channel_kind.py``. Sin Qt, sin red: el registro se escribe en un
doble en memoria (core/beat_fakes.MemoryDropbox). Los workflows solo se leen para comparar.
"""
import os
import sys
from copy import deepcopy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import channel_kind as ck, cloud_registry  # noqa: E402
from core.beat_fakes import MemoryDropbox  # noqa: E402

_failed = []

KIT_SECRETS = ('KIT_YT_CHANNEL', 'KIT_YT_TOKEN_JSON', 'KIT_DROPBOX_REFRESH_TOKEN',
               'KIT_DROPBOX_APP_KEY', 'KIT_LLM_API_KEY', 'KIT_IMAGE_API_KEY',
               'KIT_TELEGRAM_TOKEN', 'KIT_TELEGRAM_CHAT_ID', 'KIT_NOTION_TOKEN',
               'KIT_NOTION_PAGE_ID')


def check(cond, msg):
    if not cond:
        _failed.append(msg)
        print('FAIL:', msg)


def rejects(new, previous=None, label=''):
    try:
        ck.validate_registry(new, previous)
    except ck.ChannelKindError:
        return
    check(False, f'validate_registry debe rechazar: {label}')


def row(slug, tipo, clave=None, **extra):
    return dict({'slug': slug, 'tipo': tipo, 'clave': clave or slug, 'nombre': clave or slug,
                 'activo': True}, **extra)


def reg(*rows):
    return {'schema_version': 1, 'namespace': 'automatizacion', 'canales': list(rows)}


def _workflow(name):
    with open(os.path.join(ROOT, '.github', 'workflows', name), encoding='utf-8') as f:
        return f.read()


def check_spec():
    check(ck.TYPES == ('beats', 'loops'), 'TYPES')
    beats = ck.spec('beats', 'ey-mat')
    check(beats == {'tipo': 'beats', 'slug': 'ey-mat',
                    'documents': {'config': '/Soft Projects/Type Beat Generator/datos/beats/config.json'},
                    'environment': 'kit-weekly',
                    'secrets': ('BEAT_CHANNEL_ID_EY_MAT', 'BEAT_YT_TOKEN_JSON_EY_MAT'),
                    'list_variable': 'BEAT_CHANNELS', 'list_entry': 'ey-mat',
                    'workflow': 'type-beats-daily.yml'}, f'spec Beats exacto: {beats}')
    loops = ck.spec('loops', 'canal-b')
    check(loops == {'tipo': 'loops', 'slug': 'canal-b',
                    'documents': {'config': '/Soft Projects/Type Beat Generator/datos/loop_kits/canal-b/config.json',
                                  'kits': '/Soft Projects/Type Beat Generator/datos/loop_kits/canal-b/kits.json',
                                  'state': '/Soft Projects/Type Beat Generator/datos/loop_kits/estado/canal-b/state.json'},
                    'environment': 'kit-weekly-canal-b', 'secrets': KIT_SECRETS,
                    'list_variable': 'KIT_CHANNELS', 'list_entry': 'canal-b',
                    'workflow': 'kit-weekly.yml'}, f'spec Loops exacto: {loops}')
    legacy = ck.spec('loops', 'wyresounds', legacy_default=True)
    check(legacy == {'tipo': 'loops', 'slug': 'wyresounds',
                     'documents': {'config': '/Soft Projects/Type Beat Generator/datos/loop_kits/config.json',
                                   'kits': '/Soft Projects/Type Beat Generator/datos/loop_kits/kits.json',
                                   'state': '/Soft Projects/Type Beat Generator/datos/loop_kits/estado/state.json'},
                     'environment': 'kit-weekly', 'secrets': KIT_SECRETS,
                     'list_variable': 'KIT_CHANNELS', 'list_entry': 'default',
                     'workflow': 'kit-weekly.yml'}, f'spec legacy exacto: {legacy}')
    # Los nombres coinciden con los workflows reales (solo lectura).
    daily, weekly = _workflow('type-beats-daily.yml'), _workflow('kit-weekly.yml')
    check('vars.BEAT_CHANNELS' in daily and 'environment: kit-weekly' in daily,
          'type-beats-daily.yml usa BEAT_CHANNELS y el Environment kit-weekly')
    check('vars.KIT_CHANNELS' in weekly and 'environment: kit-weekly${{ matrix.suffix }}' in weekly,
          'kit-weekly.yml usa KIT_CHANNELS y kit-weekly<suffix>')
    for name in KIT_SECRETS:
        check(f'secrets.{name}' in weekly, f'kit-weekly.yml pasa {name}')
    try:
        ck.spec('beats', 'ey-mat', legacy_default=True)
        check(False, 'legacy_default en Beats debe fallar en spec')
    except ck.ChannelKindError:
        pass
    for bad in ('video', None):
        try:
            ck.spec(bad, 'ey-mat')
            check(False, f'spec con tipo {bad!r} debe fallar')
        except ck.ChannelKindError:
            pass


def check_sections():
    check(ck.from_section('beats') == 'beats' and ck.from_section('loop_kits') == 'loops',
          'section → tipo')
    check(ck.from_section('personal') is None, 'personal se ignora')
    for bad in (None, '', 'otra', 'loops'):
        try:
            ck.from_section(bad)
            check(False, f'section {bad!r} debe ser error explícito')
        except ck.ChannelKindError:
            pass


def check_registry():
    ok = reg(row('ey-mat', 'beats', 'ey mat'), row('wyresounds', 'loops', 'WyreSounds',
                                                    legacy_default=True),
             row('kits-b', 'loops', 'Kits B'))
    try:
        ck.validate_registry(ok, deepcopy(ok))
    except ck.ChannelKindError as exc:
        check(False, f'registro válido rechazado: {exc}')
    rejects(reg(row('ey-mat', 'video')), label='tipo inválido')
    for slug in ('Mal_Slug', '1abc', 'default', 'a--b', 'fin-', 'x' * 41, ''):
        rejects(reg(row(slug, 'beats', 'c')), label=f'slug {slug!r} fuera del patrón')
    rejects(reg(row('dup', 'beats', 'uno'), row('dup', 'loops', 'dup')),
            label='slug repetido entre tipos')
    rejects(reg(row('dup', 'beats', 'uno'), row('dup', 'beats', 'dos')), label='slug repetido')
    base = reg(row('canal', 'beats', 'canal'))
    rejects(reg(row('canal', 'loops', 'canal')), base, label='cambió el tipo')
    rejects(reg(row('canal-2', 'beats', 'canal')), base, label='cambió el slug')
    rejects(reg(row('canal', 'beats', 'otra clave')), base, label='cambió la clave')
    rejects(reg(row('a', 'loops', 'a', legacy_default=True), row('b', 'loops', 'b',
                                                                 legacy_default=True)),
            label='más de un legacy_default')
    rejects(reg(row('a', 'beats', 'a', legacy_default=True)), label='legacy_default en Beats')
    rejects(reg(row('otro-slug', 'loops', 'Kits B')), label='Loops: slug distinto del de la clave')

    # cloud_registry valida antes de cada escritura: nada inválido llega a Dropbox.
    memory = MemoryDropbox()
    registry = cloud_registry.CloudRegistry(memory)
    doc, rev = registry.read('canales')
    check(rev is None and doc['canales'] == [], 'registro ausente = vacío, sin escribir')
    rev = registry.write('canales', base, None)
    for label, bad in (('tipo cambiado', reg(row('canal', 'loops', 'canal'))),
                       ('slug repetido', reg(row('canal', 'beats', 'canal'),
                                             row('canal', 'loops', 'x'))),
                       ('legacy en Beats', reg(row('canal', 'beats', 'canal',
                                                   legacy_default=True)))):
        before = dict(memory.files)
        try:
            registry.write('canales', bad, rev, base)
            check(False, f'cloud_registry escribió un registro inválido ({label})')
        except ValueError:
            pass
        check(memory.files == before, f'nada escrito con {label}')
    saved, _ = registry.read('canales')
    check(saved == cloud_registry.normalize('canales', base) and memory.calls.count(('write', '/Soft Projects/Type Beat Generator/datos/automatizacion/canales.json', None)) == 1,
          'el registro válido quedó tal cual')


def main():
    check_spec()
    check_sections()
    check_registry()
    if _failed:
        print(f'smoke_channel_kind: {len(_failed)} fallas')
        return 1
    print('smoke_channel_kind: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
