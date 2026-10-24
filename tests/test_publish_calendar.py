# -*- coding: utf-8 -*-
import unittest
from datetime import date, datetime, timedelta, timezone
from unittest import mock

import httplib2
from googleapiclient.errors import HttpError

from core import publish_calendar, youtube
from core.beat_schema import BA

NOW = datetime(2026, 10, 24, 12, 0, tzinfo=BA)


def vid(privacy, publish_at='', published_at=''):
    return {'privacy': privacy, 'publish_at': publish_at, 'published_at': published_at}


class OccupiedDaysTest(unittest.TestCase):
    def test_buenos_aires_boundary(self):
        # lunes 22:00 BA = martes 01:00 UTC
        days = publish_calendar.occupied_days(
            [vid('private', publish_at='2026-10-27T01:00:00Z')], NOW)
        self.assertEqual(days, {date(2026, 10, 26)})

    def test_same_day_is_one_date(self):
        days = publish_calendar.occupied_days([
            vid('public', published_at='2026-10-30T15:00:00Z'),
            vid('private', publish_at='2026-10-30T21:00:00Z')], NOW)
        self.assertEqual(days, {date(2026, 10, 30)})

    def test_future_and_past(self):
        future = (NOW + timedelta(days=13)).astimezone(timezone.utc).isoformat()
        past = (NOW - timedelta(days=40)).astimezone(timezone.utc).isoformat()
        days = publish_calendar.occupied_days(
            [vid('private', publish_at=future), vid('public', published_at=past)], NOW)
        self.assertEqual(days, {(NOW + timedelta(days=13)).date(),
                                (NOW - timedelta(days=40)).date()})

    def test_private_without_publish_at_and_unlisted(self):
        self.assertEqual(publish_calendar.occupied_days(
            [vid('private', published_at='2026-10-01T10:00:00Z')], NOW), set())
        self.assertEqual(publish_calendar.occupied_days(
            [vid('unlisted', publish_at='2026-11-02T18:00:00Z',
                 published_at='2026-10-01T10:00:00Z')], NOW), {date(2026, 11, 2)})

    def test_bad_timestamps_raise(self):
        with self.assertRaisesRegex(ValueError, 'calendar_published_at_invalid'):
            publish_calendar.occupied_days([vid('public')], NOW)
        with self.assertRaisesRegex(ValueError, 'calendar_publish_at_invalid'):
            publish_calendar.occupied_days([vid('private', publish_at='basura')], NOW)
        with self.assertRaisesRegex(ValueError, 'calendar_publish_at_invalid'):
            publish_calendar.occupied_days([vid('private', publish_at='2026-10-30T10:00:00')], NOW)
        with self.assertRaisesRegex(ValueError, 'calendar_privacy_invalid'):
            publish_calendar.occupied_days([vid('')], NOW)
        with self.assertRaisesRegex(ValueError, 'aware_datetime_required'):
            publish_calendar.occupied_days([], datetime(2026, 10, 24))


MON_WED_FRI = [{'weekday': d, 'hour': 18, 'minute': 0} for d in (0, 2, 4)]
SUNDAY = datetime(2026, 10, 11, 10, 0)  # naive, hora de Buenos Aires


class NextFreeSlotsTest(unittest.TestCase):
    def free(self, occupied, count=3, horizon=28, now=SUNDAY, **kw):
        return publish_calendar.next_free_slots(MON_WED_FRI, now, occupied, count, horizon, **kw)

    def test_no_occupied_matches_cron(self):
        self.assertEqual([s.day for s in self.free(set())], [12, 14, 16])

    def test_taken_day_is_skipped_and_later_free_day_used(self):
        self.assertEqual([s.day for s in self.free({date(2026, 10, 12)})], [14, 16, 19])

    def test_free_day_between_taken_days_stays_usable(self):
        taken = {date(2026, 10, 12), date(2026, 10, 16)}
        self.assertEqual([s.day for s in self.free(taken)], [14, 19, 21])

    def test_horizon_bounds_the_walk(self):
        every_day = {date(2026, 10, 11) + timedelta(days=n) for n in range(60)}
        self.assertEqual(self.free(every_day), [])
        self.assertEqual([s.day for s in self.free(set(), count=10, horizon=7)], [12, 14, 16])

    def test_strictly_future_and_horizon_inclusive(self):
        at_slot = datetime(2026, 10, 12, 18, 0)
        self.assertEqual(self.free(set(), count=1, now=at_slot)[0], datetime(2026, 10, 14, 18, 0))
        self.assertEqual(len(self.free(set(), count=5, horizon=7, now=at_slot)), 3)

    def test_aware_now_uses_buenos_aires_date(self):
        # Lunes 22:00 en Buenos Aires es martes 01:00 UTC: el lunes sigue ocupado.
        now = datetime(2026, 10, 11, 13, 0, tzinfo=timezone.utc)
        slots = [{'weekday': 0, 'hour': 22, 'minute': 0}]
        with_ba = publish_calendar.next_free_slots(
            slots, now.astimezone(BA), {date(2026, 10, 12)}, 1, 28)
        self.assertEqual(with_ba[0].date(), date(2026, 10, 19))

    def test_naive_slots_use_given_zone(self):
        utc_naive = datetime(2026, 10, 11, 10, 0)
        slots = [{'weekday': 0, 'hour': 23, 'minute': 30}]
        # Lunes 23:30 UTC es lunes 20:30 en Buenos Aires.
        found = publish_calendar.next_free_slots(slots, utc_naive, {date(2026, 10, 12)}, 1, 28,
                                                 tz=timezone.utc)
        self.assertEqual(found[0].date(), date(2026, 10, 19))

    def test_invalid_arguments(self):
        with self.assertRaisesRegex(ValueError, 'invalid_slot_count'):
            self.free(set(), count=-1)
        with self.assertRaisesRegex(ValueError, 'invalid_horizon_days'):
            self.free(set(), horizon=0)


class _Call:
    def __init__(self, fn):
        self.fn = fn

    def execute(self):
        return self.fn()


class FakeYT:
    """Servicio falso: 2 páginas de playlist; la segunda puede fallar."""

    def __init__(self, fail_page=None, video_error=None):
        self.fail_page, self.video_error = fail_page, video_error
        self.pages = 0

    def channels(self):
        return self

    def playlistItems(self):
        return self

    def videos(self):
        return self

    def list(self, **kw):
        if kw.get('part') == 'contentDetails' and 'playlistId' not in kw:
            return _Call(lambda: {'items': [
                {'contentDetails': {'relatedPlaylists': {'uploads': 'UU1'}}}]})
        if 'playlistId' in kw:
            self.pages += 1
            page = self.pages

            def run():
                if page == self.fail_page:
                    raise HttpError(httplib2.Response({'status': 500}), b'boom')
                n = 3 if page == 1 else 2
                out = {'items': [{'contentDetails': {'videoId': f'v{page}{k}'}}
                                 for k in range(n)]}
                if page == 1:
                    out['nextPageToken'] = 't2'
                return out
            return _Call(run)

        def vids():
            if self.video_error:
                raise self.video_error
            return {'items': [{'id': i, 'snippet': {'title': i, 'publishedAt': '2026-01-01T00:00:00Z'},
                               'status': {'privacyStatus': 'private',
                                          'publishAt': '2026-11-01T18:00:00Z'}}
                              for i in kw['id'].split(',')]}
        return _Call(vids)


def _patched(fake):
    return mock.patch.multiple(youtube, _service=lambda c: fake,
                               _load_credentials=lambda ch, td=None: object())


class ListCalendarTest(unittest.TestCase):
    def test_rows_and_all_pages(self):
        with _patched(FakeYT()):
            rows = youtube.list_channel_calendar('c', max_videos=500)
        self.assertEqual(len(rows), 5)
        self.assertEqual(set(rows[0]), {'youtube_id', 'title', 'privacy',
                                        'published_at', 'publish_at'})
        self.assertEqual(rows[0]['publish_at'], '2026-11-01T18:00:00Z')

    def test_failed_second_page_raises(self):
        with _patched(FakeYT(fail_page=2)):
            with self.assertRaises(youtube.YouTubeError):
                youtube.list_channel_calendar('c')

    def test_timeout_raises(self):
        with _patched(FakeYT(video_error=TimeoutError('t'))):
            with self.assertRaises(youtube.YouTubeError):
                youtube.list_channel_calendar('c')

    def test_empty_channel_raises(self):
        fake = FakeYT()
        fake.channels = lambda: mock.Mock(list=lambda **kw: _Call(lambda: {'items': []}))
        with _patched(fake):
            with self.assertRaises(youtube.YouTubeError):
                youtube.list_channel_calendar('c')

    def test_list_channel_videos_contract_unchanged(self):
        with _patched(FakeYT()):
            rows = youtube.list_channel_videos('c')
        self.assertEqual(set(rows[0]), {'youtube_id', 'title', 'published_at', 'privacy'})


if __name__ == '__main__':
    unittest.main()
