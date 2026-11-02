#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del orquestador en dry-run: mocks de Dropbox/YouTube, DB temporal."""

import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_store
from core.kit_publish import DEFAULT_SLOTS, next_slot
from core.publish_at import local_to_youtube_publish_at
SCRIPTS = os.path.join(ROOT, 'scripts')
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)
from run_kit_preview import run_preview

NOW = datetime(2026, 10, 5, 10, 0)


def _fail(msg):
    print('FAIL:', msg)
    return 1


def _img(name, path):
    return {'name': name, 'path': path, 'source': 'local'}


def _pack_many():
    loops = [{'name': f'Loop_{i}.wav', 'path': f'/kits/A/loop{i}.wav'} for i in range(1, 11)]
    return [{
        'name': 'PackMany',
        'dropbox_path': '/kits/PackMany',
        'loops': loops,
        'images': [_img('a.png', os.path.join('images', 'a.png'))],
    }]


def _pack_assembled():
    loops = [{'name': f'L{i}.wav', 'path': f'/kits/B/l{i}.wav'} for i in range(1, 6)]
    return [{
        'name': 'PackLoops',
        'dropbox_path': '/kits/PackLoops',
        'loops': loops,
        'images': [_img('b.png', os.path.join('images', 'b.png'))],
    }]


def _app_config():
    return {
        'kit_preview': {
            'dropbox_root': '/loop_kits',
            'loops_min': 6,
            'loops_max': 8,
        },
        'channels': {
            'kits_chan': {'section': 'loop_kits', 'title_template': '{name} Kit'},
        },
    }


def _trim_spy(calls):
    def _trim(src, dest, **kwargs):
        calls.append((src, dest))
        open(dest, 'wb').close()
        return dest

    return _trim


def _check_many(db):
    trim_calls = []
    out = run_preview(
        app_config=_app_config(),
        channel='kits_chan',
        channel_templates=_app_config()['channels']['kits_chan'],
        dry_run=True,
        now=NOW,
        seed=42,
        db_path=db,
        list_packs_fn=lambda *_a, **_k: _pack_many(),
        trim_fn=_trim_spy(trim_calls),
    )
    if out.get('audio_mode') != 'assembled':
        return _fail(f"esperaba assembled, salió {out.get('audio_mode')}")
    if not 6 <= len(out.get('audio_files') or []) <= 8:
        return _fail(f"debía elegir entre 6 y 8 loops: {out.get('audio_files')}")
    if trim_calls:
        return _fail('dry-run no debe trimar')
    if out.get('dry_run') is not True:
        return _fail('debía ser dry_run')
    return 0


def _check_assembled(db):
    trim_calls = []
    out = run_preview(
        app_config=_app_config(),
        channel='kits_chan',
        channel_templates=_app_config()['channels']['kits_chan'],
        dry_run=True,
        now=NOW,
        seed=7,
        db_path=db,
        list_packs_fn=lambda *_a, **_k: _pack_assembled(),
        trim_fn=_trim_spy(trim_calls),
    )
    if out.get('audio_mode') != 'assembled':
        return _fail(f"esperaba assembled, salió {out.get('audio_mode')}")
    n = len(out.get('audio_files') or [])
    if n < 1 or n > 8:
        return _fail(f'assembled debía tener 1-8 loops, salió {n}')
    if trim_calls:
        return _fail('dry-run no debe trimar')
    return 0


def _check_idempotent(db):
    slot = next_slot(NOW, list(DEFAULT_SLOTS))
    publish_iso = local_to_youtube_publish_at(True, slot)
    pack_id = kit_store.upsert_pack('/kits/Existing', 'Existing', db_path=db)
    kit_store.record_run(
        pack_id,
        db_path=db,
        canal='kits_chan',
        audio_mode='assembled',
        estado='scheduled',
        publish_at=publish_iso,
    )
    packs_seen = []

    def list_once(*_a, **_k):
        packs_seen.append(1)
        return _pack_many() + _pack_assembled()

    out = run_preview(
        app_config=_app_config(),
        channel='kits_chan',
        channel_templates=_app_config()['channels']['kits_chan'],
        dry_run=True,
        now=NOW,
        seed=99,
        db_path=db,
        list_packs_fn=list_once,
    )
    if not out.get('skipped'):
        return _fail(f'debía saltar por publish_at duplicado: {out}')
    if packs_seen:
        return _fail('no debía listar packs si ya hay corrida scheduled')
    return 0


def main() -> int:
    db = os.path.join(tempfile.mkdtemp(), 'kit_preview_dry.db')
    for fn in (_check_many, _check_assembled, _check_idempotent):
        code = fn(db)
        if code:
            return code
    print('OK smoke_kit_preview_dry')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
