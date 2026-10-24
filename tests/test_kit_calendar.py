# -*- coding: utf-8 -*-
"""Calendario de YouTube en los workers de Loopkits (semanal y preview), sin red."""
import contextlib
import io
import os
import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, 'scripts')):
    if path not in sys.path:
        sys.path.insert(0, path)

from PIL import Image

import smoke_kit_weekly as weekly
from smoke_kit_weekly import Counters, FakeDropbox, FakeTelegram, scheduled_row
from core import kit_source, kit_state, youtube
from core.beat_schema import BA
from core.kit_publish import next_slot
from run_kit_preview import run_preview

# Domingo 11/10 10:00 en Buenos Aires: el cron lun/mié/vie arranca el lunes 12.
SUNDAY = datetime(2026, 10, 11, 10, 0)
MONDAY_TAKEN = [scheduled_row('2026-10-12T18:00:00Z')]  # lunes 12, 15:00 en Buenos Aires
MON, WED, FRI = '2026-10-12T21:00:00Z', '2026-10-14T21:00:00Z', '2026-10-16T21:00:00Z'
NEXT_MON = '2026-10-19T21:00:00Z'


class WeeklyCalendarTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.out.cleanup)
        for target, fake in ((kit_source, 'download_pack_files'), (youtube, 'upload')):
            patcher = mock.patch.object(target, fake, getattr(
                weekly, '_fake_download' if fake == 'download_pack_files' else '_fake_upload'))
            patcher.start()
            self.addCleanup(patcher.stop)
        weekly._reset()
        self.asked = []

    def calendar(self, rows_by_channel):
        def read(channel):
            self.asked.append(channel)
            rows = rows_by_channel[channel]
            if isinstance(rows, Exception):
                raise rows
            return rows
        return read

    def run_week(self, dbx=None, **kw):
        dbx = dbx or FakeDropbox()
        tg = kw.pop('tg', FakeTelegram())
        code, log = weekly._run(dbx, tg, self.out.name, now=SUNDAY, **kw)
        return code, log, dbx, tg

    def test_taken_monday_moves_to_wed_fri_and_next_monday(self):
        code, _, _, _ = self.run_week(calendar_fn=self.calendar({'canal-smoke': MONDAY_TAKEN}))
        self.assertEqual(code, 0)
        self.assertEqual(Counters.publish_ats, [WED, FRI, NEXT_MON])
        self.assertEqual(self.asked, ['canal-smoke'])

    def test_kit_state_dedupe_still_skips_stored_iso(self):
        dbx = FakeDropbox()
        pack = kit_state.upsert_pack('/smoke/Old', 'Old', dbx=dbx)
        kit_state.record_run(pack, dbx=dbx, canal='canal-smoke', estado='scheduled',
                             publish_at=WED, youtube_id='old', audio_mode='assembled')
        # YouTube también muestra ese video propio del miércoles.
        rows = MONDAY_TAKEN + [scheduled_row(WED)]
        code, _, _, _ = self.run_week(dbx, calendar_fn=self.calendar({'canal-smoke': rows}))
        self.assertEqual(code, 0)
        self.assertEqual(Counters.publish_ats, [FRI, NEXT_MON])

    def test_rerun_same_week_does_not_walk_past_own_videos(self):
        code, _, dbx, _ = self.run_week(calendar_fn=self.calendar({'canal-smoke': MONDAY_TAKEN}))
        self.assertEqual(code, 0)
        rows = MONDAY_TAKEN + [scheduled_row(iso) for iso in (WED, FRI, NEXT_MON)]
        code, _, _, _ = self.run_week(dbx, calendar_fn=self.calendar({'canal-smoke': rows}))
        self.assertEqual(code, 0)
        self.assertEqual(Counters.uploads, 3)

    def test_horizon_cuts_and_warns(self):
        # Todos los lun/mié/vie de los próximos 28 días ocupados salvo el viernes 16.
        rows = [scheduled_row(f'2026-{m:02d}-{d:02d}T15:00:00Z')
                for m, d in [(10, 12), (10, 14), (10, 19), (10, 21), (10, 23), (10, 26),
                             (10, 28), (10, 30), (11, 2), (11, 4), (11, 6)]]
        tg = FakeTelegram()
        code, _, _, _ = self.run_week(tg=tg, calendar_fn=self.calendar({'canal-smoke': rows}))
        self.assertEqual(code, 0)
        self.assertEqual(Counters.publish_ats, [FRI])
        self.assertTrue(any('Solo 1 de 3' in text for text in tg.sent))

    def test_loader_failure_publishes_nothing(self):
        tg = FakeTelegram()
        code, log, dbx, _ = self.run_week(
            tg=tg, calendar_fn=self.calendar({'canal-smoke': youtube.YouTubeError('SECRET')}))
        self.assertEqual(code, 1)
        self.assertEqual(Counters.uploads, 0)
        self.assertEqual(Counters.renders, 0)
        self.assertFalse(dbx.uploads)
        self.assertEqual(kit_state.load(dbx=dbx)['runs'], [])
        self.assertTrue(tg.sent and 'calendario' in tg.sent[0])
        self.assertNotIn('SECRET', log + ''.join(tg.sent))

    def test_dry_run_never_reads_calendar(self):
        code, _, _, _ = self.run_week(dry_run=True, calendar_fn=lambda ch: self.fail('YouTube'))
        self.assertEqual(code, 0)

    def test_one_channel_calendar_does_not_move_another(self):
        reader = self.calendar({'canal-a': MONDAY_TAKEN, 'canal-b': []})
        self.run_week(calendar_fn=reader, channel='canal-a')
        self.assertEqual(Counters.publish_ats, [WED, FRI, NEXT_MON])
        weekly._reset()
        self.run_week(calendar_fn=reader, channel='canal-b')
        self.assertEqual(Counters.publish_ats, [MON, WED, FRI])
        self.assertEqual(self.asked, ['canal-a', 'canal-b'])

    def test_long_gap_rechecks_before_insert(self):
        ticks = iter(range(0, 10 ** 6, 1500))
        answers = iter([[], [], [scheduled_row(WED)], [scheduled_row(WED)]])
        tg = FakeTelegram()
        code, _, _, _ = self.run_week(
            tg=tg, calendar_fn=lambda ch: next(answers),
            extra_hooks={'monotonic': lambda: next(ticks)})
        self.assertEqual(code, 0)
        # El miércoles se ocupó durante la corrida: no se sube y el kit queda para el viernes.
        self.assertEqual(Counters.publish_ats, [MON, FRI])
        self.assertTrue(any('se omitieron' in text for text in tg.sent))

    def test_recheck_failure_stops_uploads(self):
        ticks = iter(range(0, 10 ** 6, 1500))
        answers = iter([[], []])
        def read(ch):
            try:
                return next(answers)
            except StopIteration:
                raise youtube.YouTubeError('down') from None
        code, _, _, _ = self.run_week(calendar_fn=read,
                                      extra_hooks={'monotonic': lambda: next(ticks)})
        self.assertEqual(code, 1)
        self.assertEqual(Counters.publish_ats, [MON])


def _fake_trim(src, dest, **_k):
    open(dest, 'wb').close()
    return dest


class PreviewCalendarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        patcher = mock.patch.object(kit_source, 'download_pack_files', weekly._fake_download)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.db = os.path.join(self.tmp.name, 'k.db')
        self.published = []

    def run(self, result=None):
        with contextlib.redirect_stdout(io.StringIO()):
            return super().run(result)

    def preview(self, calendar_fn, dry_run=False):
        bg = os.path.join(self.tmp.name, 'bg.png')
        Image.new('RGB', (64, 64)).save(bg)
        pack = [{'name': 'PackPreview', 'dropbox_path': '/kits/PackPreview',
                 'loops': [{'name': f'L{i}.wav', 'path': f'/kits/l{i}.wav'} for i in range(6)],
                 'images': [{'name': 'bg.png', 'path': bg, 'source': 'local'}]}]

        def publish(channel, video, thumbnail, name, slots, templates, **kw):
            # Igual que publish_preview: el slot sale de next_slot(now).
            self.published.append(next_slot(kw['now'], slots))
            return {'youtube_id': 'x', 'title': 't'}
        return run_preview(
            app_config={'kit_preview': {'dropbox_root': '/k'}, 'channels': {}},
            channel='c', channel_templates={}, now=SUNDAY, seed=1, db_path=self.db, tz=BA,
            dry_run=dry_run, list_packs_fn=lambda *_a, **_k: pack, trim_fn=_fake_trim,
            render_fn=lambda *a: a[-1], publish_fn=publish, calendar_fn=calendar_fn,
            output_dir=os.path.join(self.tmp.name, 'out'))

    def test_advances_off_taken_day(self):
        out = self.preview(lambda ch: MONDAY_TAKEN)
        self.assertEqual(out['publish_at'], WED)
        self.assertEqual(self.published, [datetime(2026, 10, 14, 18, 0)])

    def test_free_day_keeps_next_slot(self):
        out = self.preview(lambda ch: [])
        self.assertEqual(out['publish_at'], MON)
        self.assertEqual(self.published, [datetime(2026, 10, 12, 18, 0)])

    def test_already_scheduled_kept_for_exact_publish_at(self):
        from core import kit_store
        pack = kit_store.upsert_pack('/kits/Old', 'Old', db_path=self.db)
        kit_store.record_run(pack, db_path=self.db, canal='c', audio_mode='assembled',
                             estado='scheduled', publish_at=MON)
        out = self.preview(lambda ch: MONDAY_TAKEN)
        self.assertEqual(out['reason'], 'already_scheduled')
        self.assertEqual(out['publish_at'], MON)
        self.assertEqual(self.published, [])

    def test_loader_failure_uploads_nothing(self):
        def down(ch):
            raise youtube.YouTubeError('SECRET')
        with self.assertRaises(SystemExit) as caught:
            self.preview(down)
        self.assertNotIn('SECRET', str(caught.exception))
        self.assertEqual(self.published, [])

    def test_dry_run_never_reads_calendar(self):
        out = self.preview(lambda ch: self.fail('YouTube'), dry_run=True)
        self.assertEqual(out['publish_at'], MON)

    def test_calendar_full_skips(self):
        rows = [scheduled_row(f'2026-{m:02d}-{d:02d}T15:00:00Z')
                for m, d in [(10, 12), (10, 14), (10, 16), (10, 19), (10, 21), (10, 23),
                             (10, 26), (10, 28), (10, 30), (11, 2), (11, 4), (11, 6)]]
        out = self.preview(lambda ch: rows)
        self.assertEqual(out['reason'], 'calendar_full')
        self.assertEqual(self.published, [])


if __name__ == '__main__':
    unittest.main()
