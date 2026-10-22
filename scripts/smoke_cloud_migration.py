#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke de scripts/migrate_to_cloud.py y del documento /type-beats/config.json resultante.

Uso: ``py -3 scripts/smoke_cloud_migration.py``. Fixture sin datos reales
(scripts/fixtures/app_config_sample.json): canal sin section, canal de kits por defecto,
sección personal y un slug repetido. Dropbox es core/beat_fakes.MemoryDropbox: sin red.

Además compara byte a byte el /type-beats/config.json que genera la app nueva (registro +
config remota, también publicando desde el panel) contra el que generaba el código anterior
con app_config.json (scripts/fixtures/type_beats_config_expected.json) e imprime el diff.
"""
import contextlib
import difflib
import io
import json
import os
import sys
import tempfile
import time
from copy import deepcopy

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, 'scripts')):
    if path not in sys.path:
        sys.path.insert(0, path)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import migrate_to_cloud as mig  # noqa: E402
from core import beat_settings, cloud_registry  # noqa: E402
from core.beat_cloud import BeatCloud  # noqa: E402
from core.beat_fakes import MemoryDropbox  # noqa: E402

FIXTURE = os.path.join(ROOT, 'scripts', 'fixtures', 'app_config_sample.json')
EXPECTED = os.path.join(ROOT, 'scripts', 'fixtures', 'type_beats_config_expected.json')
SECRET_WORDS = ('refresh_token', 'client_secret', 'app_key', 'access_token')
_failed = []


def check(cond, msg):
    if not cond:
        _failed.append(msg)
        print('FAIL:', msg)


def run(argv, transport=None):
    out = io.StringIO()
    def factory():
        if transport is None:
            raise AssertionError('el dry-run no debe abrir Dropbox')
        return transport
    try:
        with contextlib.redirect_stderr(out):
            code = mig.main(argv, transport_factory=factory, out=out)
    except SystemExit as exc:  # argparse rechaza la combinación de opciones
        code = exc.code
    return code, out.getvalue()


def fixture(drop_duplicate=True):
    with open(FIXTURE, encoding='utf-8') as f:
        app = json.load(f)
    if drop_duplicate:
        del app['channels']['kits extra']
    return app


def check_build(tmp):
    full = os.path.join(tmp, 'full.json')
    with open(full, 'w', encoding='utf-8') as f:
        json.dump(fixture(False), f)
    code, text = run(['--config', full])
    check(code == 2 and 'Slug repetido' in text and 'canales.json' not in text,
          f'slug repetido aborta la migración: {code} {text[:120]}')
    code, text = run(['--config', full, '--apply'], MemoryDropbox())
    check(code == 2, 'slug repetido aborta también con --apply')

    canales, ajustes, report = mig.build(fixture())
    rows = {r['clave']: r for r in canales['canales']}
    check(set(rows) == {'canal uno', 'Beat Dos', 'Kits Default', 'Kits Extra'},
          f'canales migrados: {sorted(rows)}')
    check(rows['canal uno']['slug'] == 'canal-uno' and rows['canal uno']['tipo'] == 'beats'
          and rows['canal uno']['activo'] is True, 'Beats usa su actions_slug')
    check(rows['Beat Dos']['slug'] == 'beat-dos' and rows['Beat Dos']['activo'] is False,
          'Beats pausado conserva activo=false')
    check(rows['Kits Default']['legacy_default'] is True and rows['Kits Default']['tipo'] == 'loops'
          and rows['Kits Default']['slug'] == 'kits-default', 'kits por defecto: legacy_default')
    check(rows['Kits Extra']['slug'] == 'kits-extra' and not rows['Kits Extra']['legacy_default'],
          'Loops: slug = kit_channel.slug(nombre)')
    check(rows['canal uno']['plantillas']['title_template'] == '[Fixture] {name} | Free Type Beat'
          and rows['canal uno']['plantillas']['hashtags'] == '#fixture #typebeat',
          'plantillas migradas')
    omitted = {o['canal']: o['motivo'] for o in report['omitidos']}
    check(omitted.get('Sin Seccion') == 'tipo sin definir', 'canal sin section: tipo sin definir')
    check('Marca Personal' in omitted and 'Sin Seccion' not in rows, 'personal y sin tipo omitidos')
    check(ajustes['beatstars']['profile_url'] == 'https://www.beatstars.com/fixtureproducer'
          and ajustes['gasto_kits_default'] == {'monthly_cap_usd': 10.0, 'max_images_per_run': 6}
          and ajustes['github']['repo'] == 'Perree/video-type-beat-generator',
          'ajustes con los defaults del spike')

    app = fixture()
    app['kit_preview'] = {}
    canales, _, report = mig.build(app, kits_default='Kits Extra')
    rows = {r['clave']: r for r in canales['canales']}
    check(rows['Kits Extra']['legacy_default'] and not rows['Kits Default']['legacy_default'],
          '--kits-default elige el canal legacy')
    app['channels']['Beat Dos']['section'] = 'beats'
    canales, _, report = mig.build(app, kits_default='Beat Dos')
    check(any('corregida a loops' in a for a in report['avisos']),
          'un canal marcado beats que es el de kits por defecto se informa al corregirlo')
    return canales


def check_cli(tmp):
    path = os.path.join(tmp, 'app.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(fixture(), f)
    code, text = run(['--config', path])
    check(code == 0 and 'Dry-run' in text and 'tipo sin definir' in text, 'dry-run por defecto')
    check(not any(word in text for word in SECRET_WORDS), 'el dry-run no imprime secretos')

    memory = MemoryDropbox()
    code, text = run(['--config', path, '--apply'], memory)
    check(code == 0 and text.count('verificado') == 2, f'--apply escribe y verifica: {text[-200:]}')
    check(set(memory.files) == set(cloud_registry.PATHS.values()),
          'solo se escriben canales.json y ajustes.json')
    first = dict(memory.files)
    code, text = run(['--config', path, '--apply'], memory)
    check(code == 3 and 'ya existe' in text and memory.files == first,
          '--apply no pisa un destino existente')
    code, text = run(['--config', path, '--apply', '--force'], memory)
    check(code == 0 and memory.files != first and 'verificado' in text,
          '--force usa el rev actual')
    code, _ = run(['--config', path, '--force'], memory)
    check(code == 2, '--force sin --apply se rechaza')
    return memory


def _diff(label, expected, actual):
    a = json.dumps(json.loads(expected), indent=1, sort_keys=True, ensure_ascii=False).splitlines()
    b = json.dumps(json.loads(actual), indent=1, sort_keys=True, ensure_ascii=False).splitlines()
    lines = list(difflib.unified_diff(a, b, 'formato actual (app_config)', label, lineterm=''))
    print(f'diff /type-beats/config.json — {label}: '
          + ('vacío (idéntico byte a byte)' if expected == actual and not lines else ''))
    for line in lines:
        print('   ', line)
    return expected == actual


def check_beats_document(canales):
    with open(EXPECTED, 'rb') as f:
        expected = f.read()
    # 1) Lógica pura: config remota + registro (sin app_config).
    remote = json.loads(expected)
    memory = MemoryDropbox()
    BeatCloud(memory).write('config', beat_settings.validate(fixture()['beat_automation'], canales), None)
    check(_diff('validate(config, registro)', expected, memory.files['/type-beats/config.json'][0]),
          'el documento de Beats es idéntico al formato actual')

    # 2) La app: el panel carga Dropbox y publica sin cambios.
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core.beat_panel import BeatPanel
    memory = MemoryDropbox()
    memory.files['/type-beats/config.json'] = (expected, 'rev-config-0001')
    memory.files['/type-beats/state.json'] = (b'opaque-state', 'rev-state-0001')
    memory.files[cloud_registry.PATHS['canales']] = (cloud_registry.payload(canales), 'rev-reg-0001')
    panel = BeatPanel(cloud_provider=lambda: memory)

    def settle():
        deadline = time.monotonic() + 5
        while panel.task is not None and time.monotonic() < deadline:
            app.processEvents()
        app.processEvents()
    settle()
    check(panel.config_readable and panel.channel.count() == 2,
          f'el panel carga desde Dropbox: {panel.status.text()}')
    panel.save_and_publish()
    settle()
    check(_diff('panel «Publicar al robot»', expected, memory.files['/type-beats/config.json'][0]),
          'publicar desde el panel deja el documento idéntico')
    check(memory.files['/type-beats/state.json'] == (b'opaque-state', 'rev-state-0001'),
          'el estado remoto no se toca')
    check(memory.files[cloud_registry.PATHS['canales']][1] == 'rev-reg-0001',
          'sin cambios de plantillas no se reescribe el registro')
    check(remote['channels'][0]['seo']['description'].count('{url}') == 1, 'fixture coherente')
    panel.deleteLater()


def main():
    # Sin gh real ni llavero de Windows (core/cloud_fakes).
    from core import cloud_login, gh_status
    from core.cloud_fakes import FakeGhRun, MemoryKeyring
    gh_status.set_default(gh_status.GhStatus(run=FakeGhRun()))
    cloud_login.set_backend(MemoryKeyring())
    with tempfile.TemporaryDirectory() as tmp:
        canales = check_build(tmp)
        check_cli(tmp)
    check_beats_document(mig.build(fixture())[0])
    if _failed:
        print(f'smoke_cloud_migration: {len(_failed)} fallas')
        return 1
    print('smoke_cloud_migration: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
