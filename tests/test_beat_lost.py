"""Subidas perdidas: se libera el día y el beat solo si YouTube confirma que no llegó."""
import sys
import unittest
from datetime import timedelta
from pathlib import Path

from core.beat_daily import run_daily
from core.beat_assets import DropboxAssets
from core.beat_lost import lost_jobs
from core.beat_notify import message
from core.beat_schema import instant, migrate

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_beat_daily as base  # módulo: así pytest no vuelve a correr DailyTests

NOW = base.NOW


class LostUploadTests(unittest.TestCase):
    renderer = base.DailyTests.renderer
    upload = base.DailyTests.upload

    def setUp(self):
        base.DailyTests.setUp(self)
        self.cloud.update('config', lambda config: config['channels'][0].update(
            slots=[{'weekday': 0, 'hour': 18, 'minute': 0}, {'weekday': 3, 'hour': 18, 'minute': 0}]))

    def run_at(self, when, rows, uploader=None):
        return run_daily(self.cloud, 'channel', DropboxAssets(self.assets_client),
                         uploader or self.upload, self.receipts, source=self.source,
                         renderer=self.renderer, clock=lambda: when,
                         notify=self.notifications.append, calendar=lambda _: list(rows))

    def fail_first_run(self):
        def broken(**kwargs):
            self.upload(**kwargs)
            raise RuntimeError('timeout')
        summary = self.run_at(NOW, [], broken)
        self.assertGreater(summary['unknown'], 0)
        self.calls.clear()
        return summary['unknown']

    def jobs(self):
        return self.cloud.read('state')[0]['jobs']

    def test_lost_upload_frees_day_and_beat_next_day(self):
        lost = self.fail_first_run()
        before = {j['id']: j for j in self.jobs().values()}
        summary = self.run_at(NOW + timedelta(days=1), [])
        self.assertEqual(summary['released'], lost)
        self.assertEqual(summary['reasons'], {'upload_lost_released': lost})
        self.assertIn('se liberó su día', message(summary))
        jobs = self.jobs()
        released = [j for j in jobs.values() if j.get('lost')]
        self.assertEqual(len(released), lost)
        self.assertTrue(all(j['status'] == 'cancelled' for j in released))
        # Los horarios liberados que siguen en el futuro se vuelven a planificar y subir.
        future = {j['slot'] for j in released if instant(j['slot']) > NOW + timedelta(days=1)}
        replanned = {j['slot'] for j in jobs.values() if j['id'] not in before}
        self.assertTrue(future)
        self.assertTrue(future <= replanned)
        self.assertGreater(summary['uploaded'], 0)
        # Una tercera corrida no vuelve a liberar ni a subir lo mismo.
        again = self.run_at(NOW + timedelta(days=1, hours=1), [])
        self.assertEqual(again['released'], 0)

    def test_not_released_inside_grace_period(self):
        self.fail_first_run()
        summary = self.run_at(NOW + timedelta(hours=6), [])
        self.assertEqual(summary['released'], 0)
        self.assertFalse(any(j.get('lost') for j in self.jobs().values()))

    def test_not_released_when_title_is_on_youtube(self):
        self.fail_first_run()
        rows = [{'youtube_id': f'vid{n:08d}', 'title': j['seo_snapshot']['selected']['title'],
                 'privacy': 'private', 'published_at': NOW.isoformat(), 'publish_at': ''}
                for n, j in enumerate(self.jobs().values()) if j.get('seo_snapshot')]
        summary = self.run_at(NOW + timedelta(days=1), rows)
        self.assertEqual(summary['released'], 0)

    def test_not_released_when_day_is_taken(self):
        self.fail_first_run()
        rows = [{'youtube_id': f'vid{n:08d}', 'title': 'otro', 'privacy': 'private',
                 'published_at': NOW.isoformat(), 'publish_at': j['slot']}
                for n, j in enumerate(self.jobs().values())]
        summary = self.run_at(NOW + timedelta(days=1), rows)
        self.assertEqual(summary['released'], 0)


def _state(job_extra=None, reserved=None):
    job = {'track_id': 'TK1', 'channel': 'ch', 'cycle': 1,
           'slot': (NOW + timedelta(days=3)).isoformat(), 'status': 'planned',
           'seo_snapshot': {'selected': {'title': 'Beat <Uno>'}}}
    job.update(job_extra or {})
    job['id'] = 'job1'
    when = reserved or NOW
    return {'jobs': {'job1': job},
            'attempts': {when.date().isoformat(): {'a': {'job_id': 'job1',
                                                         'reserved_at': when.isoformat()}}}}


class LostJobsUnitTests(unittest.TestCase):
    later = NOW + timedelta(days=1)

    def test_basic_release(self):
        self.assertEqual(lost_jobs(_state(), 'ch', [], self.later, set()), ['job1'])

    def test_title_match_uses_upload_sanitizing(self):
        rows = [{'title': 'beat  uno', 'published_at': NOW.isoformat()}]
        self.assertEqual(lost_jobs(_state(), 'ch', rows, self.later, set()), [])

    def test_other_channel_status_or_missing_title(self):
        self.assertEqual(lost_jobs(_state(), 'otro', [], self.later, set()), [])
        self.assertEqual(lost_jobs(_state({'status': 'uploaded'}), 'ch', [], self.later, set()), [])
        self.assertEqual(lost_jobs(_state({'seo_snapshot': None}), 'ch', [], self.later, set()), [])

    def test_truncated_listing_must_cover_the_attempt(self):
        rows = [{'title': f't{n}', 'published_at': (NOW + timedelta(minutes=n + 1)).isoformat()}
                for n in range(200)]
        self.assertEqual(lost_jobs(_state(), 'ch', rows, self.later, set()), [])
        rows[0]['published_at'] = (NOW - timedelta(days=1)).isoformat()
        self.assertEqual(lost_jobs(_state(), 'ch', rows, self.later, set()), ['job1'])
        rows[0]['published_at'] = ''
        self.assertEqual(lost_jobs(_state(), 'ch', rows, self.later, set()), [])


class SchemaTests(unittest.TestCase):
    def test_lost_only_on_cancelled(self):
        from core.beat_schema import identity
        slot = (NOW + timedelta(days=3)).isoformat()
        def job(track, **extra):
            row = dict(track_id=track, channel='ch', cycle=1, slot=slot, status='planned', **extra)
            row['id'] = identity(track, 'ch', 1, slot)
            return row
        lost = job('TK1', lost=True)
        lost['status'] = 'cancelled'
        fresh = job('TK2')
        migrate({'jobs': {lost['id']: lost, fresh['id']: fresh}, 'attempts': {}}, 'state')
        with self.assertRaises(ValueError):
            migrate({'jobs': {fresh['id']: dict(fresh, lost=True)}, 'attempts': {}}, 'state')
        other = job('TK3')
        with self.assertRaises(ValueError):
            migrate({'jobs': {fresh['id']: fresh, other['id']: other}, 'attempts': {}}, 'state')


if __name__ == '__main__':
    unittest.main()
