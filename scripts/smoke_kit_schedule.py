#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke de slots y del fallback privado. Sin red ni Google."""

import os
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_store, youtube
from core.kit_publish import DEFAULT_SLOTS, next_slot, publish_preview
from core.youtube import YouTubeError


def _fail(msg):
    print('FAIL:', msg)
    return 1


def _check_slots():
    slots = list(DEFAULT_SLOTS)
    wednesday = datetime(2026, 10, 7, 19, 0)
    monday = datetime(2026, 10, 5, 10, 0)
    if wednesday.weekday() != 2 or monday.weekday() != 0:
        return _fail(f'fechas de prueba inesperadas {wednesday} {monday}')

    friday = next_slot(wednesday, slots)
    if (friday.weekday(), friday.hour, friday.minute) != (4, 18, 0):
        return _fail(f'miércoles 19:00 debía caer el viernes 18:00, salió {friday}')
    if friday.date() != datetime(2026, 10, 9).date():
        return _fail(f'viernes esperado 2026-10-09, salió {friday.date()}')

    same_monday = next_slot(monday, slots)
    if same_monday != datetime(2026, 10, 5, 18, 0):
        return _fail(f'lunes 10:00 debía caer ese lunes 18:00, salió {same_monday}')
    return 0


class _Upload:
    """Reemplaza youtube.upload. El primer insert con publish_at falla."""

    def __init__(self, fail_second=False):
        self.calls = []
        self.fail_second = fail_second

    def __call__(self, channel, video_path, title, description='', tags=None,
                 thumbnail=None, privacy='private', publish_at=None, **kwargs):
        self.calls.append({
            'privacy': privacy,
            'publish_at': publish_at,
            'video_path': video_path,
        })
        if publish_at:
            raise YouTubeError(
                'Error de YouTube (400): publishAt not allowed for unaudited clients')
        if self.fail_second:
            raise YouTubeError('Error de YouTube (403): quotaExceeded')
        return {
            'youtube_id': 'yt-kit',
            'url': 'https://youtu.be/yt-kit',
            'privacy': privacy,
            'thumbnail_error': '',
        }


def _check_fallback(db):
    pack_id = kit_store.upsert_pack('/kits/Smoke', 'Smoke Pack', db_path=db)
    fake = _Upload()
    youtube.upload = fake
    out = publish_preview(
        'kits', 'exported/smoke.mp4', None, 'Smoke Pack', list(DEFAULT_SLOTS),
        {'title_template': '{name} Kit'},
        pack_id=pack_id, audio_mode='named_preview', db_path=db,
        now=datetime(2026, 10, 5, 10, 0),
    )
    if len(fake.calls) != 2:
        return _fail(f'se esperaban 2 uploads, hubo {len(fake.calls)}')
    second = fake.calls[1]
    if second['privacy'] != 'private' or second['publish_at'] is not None:
        return _fail(f'segundo intento debía ser privado sin publish_at: {second}')
    if fake.calls[0]['video_path'] != second['video_path']:
        return _fail('el reintento no usó el mismo archivo')
    if out['estado'] != 'private_pending':
        return _fail(f'estado {out["estado"]}')
    if kit_store.last_run_at(pack_id, db_path=db) is None:
        return _fail('private_pending no actualizó last_used_at')
    with kit_store.connect(db) as conn:
        row = conn.execute(
            "SELECT estado, publish_at FROM kit_runs WHERE id = ?",
            (out['run_id'],)).fetchone()
    if row['estado'] != 'private_pending':
        return _fail(f'fila estado {row["estado"]}')
    return 0


def _check_other_error(db):
    """Un error que no es de publishAt no se reintenta ni marca el pack."""
    pack_id = kit_store.upsert_pack('/kits/Quota', 'Quota', db_path=db)

    calls = {'n': 0}

    def quota(*_args, **_kwargs):
        calls['n'] += 1
        raise YouTubeError('Error de YouTube (403): quotaExceeded')

    youtube.upload = quota
    try:
        publish_preview(
            'kits', 'exported/quota.mp4', None, 'Quota', list(DEFAULT_SLOTS), {},
            pack_id=pack_id, audio_mode='named_preview', db_path=db,
            now=datetime(2026, 10, 5, 10, 0),
        )
    except YouTubeError as exc:
        if 'quotaExceeded' not in str(exc):
            return _fail(f'error inesperado: {exc}')
    else:
        return _fail('el error de cuota debía propagarse')
    with kit_store.connect(db) as conn:
        used = conn.execute(
            "SELECT last_used_at FROM kit_packs WHERE id = ?",
            (pack_id,)).fetchone()[0]
    if used is not None:
        return _fail('un error ajeno a publishAt marcó el pack')
    if calls['n'] != 1:
        return _fail(f'un error ajeno a publishAt no debe reintentar, llamadas={calls["n"]}')
    return 0


def _check_both_fail(db):
    """Si el reintento también falla, el pack no queda usado."""
    pack_id = kit_store.upsert_pack('/kits/Both', 'Both', db_path=db)
    youtube.upload = _Upload(fail_second=True)
    try:
        publish_preview(
            'kits', 'exported/both.mp4', None, 'Both', list(DEFAULT_SLOTS), {},
            pack_id=pack_id, audio_mode='assembled', db_path=db,
            now=datetime(2026, 10, 5, 10, 0),
        )
    except YouTubeError:
        pass
    else:
        return _fail('el segundo error debía propagarse')
    with kit_store.connect(db) as conn:
        used = conn.execute(
            "SELECT last_used_at FROM kit_packs WHERE id = ?",
            (pack_id,)).fetchone()[0]
        n = conn.execute(
            "SELECT COUNT(*) FROM kit_runs WHERE pack_id = ?",
            (pack_id,)).fetchone()[0]
    if used is not None or n != 0:
        return _fail(f'pack marcado pese a fallar ambos intentos used={used} runs={n}')
    return 0


def main() -> int:
    original = youtube.upload
    try:
        code = _check_slots()
        if code:
            return code
        db = os.path.join(tempfile.mkdtemp(), 'kit_schedule.db')
        code = _check_fallback(db)
        if code:
            return code
        code = _check_other_error(db)
        if code:
            return code
        code = _check_both_fail(db)
        if code:
            return code
    finally:
        youtube.upload = original
    print('OK smoke_kit_schedule')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
