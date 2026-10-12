"""Phase 7 repeat barriers, exhaustion and deterministic missing-data fallback."""
from copy import deepcopy
from datetime import timedelta
import unittest
import json
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from core.beat_schedule import plan, apply_plan
from core.beat_schema import migrate, identity, instant
from core.beat_rotation import repeat_ready, changed_image, check_repeat, image_digest
from core.beat_seo import build_snapshot, validate_snapshot
from core.beat_performance import performance, choose, bucket_sequence, ranks
from core.beat_cloud import BeatCloud, Transient
from core.beat_fakes import MemoryDropbox
from core.beat_state import BeatState

NOW = instant('2026-10-12T12:00:00-03:00')
CHANNEL = {'id': 'beats', 'tags': ['trap', 'drill'],
           'slots': [{'weekday': d, 'hour': 18, 'minute': 0} for d in range(7)]}
TRACK = {'id': 'TK1', 'title': 'Night', 'tags': ['trap', 'drill']}


def job(tid='TK1', at=NOW, cycle=1, status='uploaded', channel='beats'):
    row = dict(track_id=tid, channel=channel, cycle=cycle, slot=at.isoformat(), status=status)
    row['id'] = identity(tid, channel, cycle, at)
    return row


class RotationTests(unittest.TestCase):
    def report(self):
        return {'schema_version': 1, 'channel_id': 'beats', 'generated_at': NOW.isoformat(),
                'sources': ['claude_code', 'vidiq', 'youtube_analytics'], 'keywords': [
                {'tag': tag, 'score': 0, 'views': views, 'ctr': ctr,
                 'average_view_percentage': retention}
                for tag, views, ctr, retention in [('trap', 10, 1, 20),
                    ('drill', 100, 10, 80), ('ambient', 10**12, 5, 50)]]}

    def test_score_formula_outlier_and_ties(self):
        tracks = [dict(TRACK, id=f'TK{i}', tags=[tag])
                  for i, tag in enumerate(('trap', 'drill', 'ambient'))]
        scores, rh = performance(json.dumps(self.report()).encode(), 'beats', tracks, NOW)
        self.assertEqual(scores, {'TK0': 0, 'TK1': 75, 'TK2': 75})
        self.assertEqual(len(rh), 64)
        smaller_outlier = self.report()
        smaller_outlier['keywords'][2]['views'] = 1000
        self.assertEqual(performance(json.dumps(smaller_outlier).encode(), 'beats', tracks, NOW)[0], scores)
        self.assertEqual(ranks([5, 5, 5]), {5: 50})
        self.assertEqual(ranks([0, 1, 1, 2])[1], 50)

    def test_missing_invalid_metrics_fallback_lru(self):
        tracks = [dict(TRACK, id='TK1', tags=['unknown']), dict(TRACK, id='TK2', tags=['drill'])]
        scores, _ = performance(json.dumps(self.report()).encode(), 'beats', tracks, NOW)
        self.assertNotIn('TK1', scores)
        self.assertEqual(choose(['TK1', 'TK2'], ['TK1', 'TK2'], scores, [], 'beats', 1,
                               lambda tid: tid), ('TK1', 'lru'))
        variants = []
        for key, value in [('views', None), ('views', -1), ('views', 10**12 + 1),
                           ('ctr', float('nan')), ('ctr', True), ('average_view_percentage', 101)]:
            row = self.report()
            row['keywords'][0][key] = value
            variants.append(json.dumps(row).encode())
        missing = self.report()
        del missing['keywords'][0]['ctr']
        variants.append(json.dumps(missing).encode())
        wrong = self.report()
        wrong['channel_id'] = 'other'
        variants.append(json.dumps(wrong).encode())
        expired = self.report()
        expired['generated_at'] = (NOW - timedelta(days=15)).isoformat()
        variants.append(json.dumps(expired).encode())
        for payload in [None, b'bad'] + variants:
            with self.subTest(payload=str(payload)[:40]):
                self.assertEqual(performance(payload, 'beats', tracks, NOW), ({}, None))

    def test_distribution_seed_and_group_exhaustion(self):
        sequence = bucket_sequence(42, 'beats', 0)
        self.assertEqual(Counter(sequence), {'top': 7, 'middle': 2, 'remaining': 1})
        self.assertEqual(sequence, bucket_sequence(42, 'beats', 0))
        self.assertNotEqual(sequence, bucket_sequence(43, 'beats', 0))
        ids = [f'TK{i}' for i in range(9)]
        scores = {tid: 100 - i for i, tid in enumerate(ids)}
        history, selected = [], []
        for index in range(10):
            tid, bucket = choose(ids, ids, scores, history, 'beats', 42, lambda tid: tid)
            selected.append(bucket)
            history.append(job(tid, NOW + timedelta(days=index), cycle=2, status='planned'))
        self.assertEqual(Counter(selected), Counter(sequence))
        # Exhaustion is deterministic and does not invent an eligible candidate.
        available = ids[3:] if sequence[0] == 'top' else ids[:3]
        self.assertEqual(choose(available, ids, scores, [], 'beats', 42, lambda tid: tid),
                         (min(available), 'lru'))

    def test_cover_catalog_once_and_exhaust_without_repeating(self):
        tracks = [dict(TRACK, id=f'TK{i}') for i in range(8)]
        first = plan({'channels': [CHANNEL]}, {}, tracks, NOW, seed=42)
        self.assertEqual(len(first), 8)
        self.assertEqual(len({row['track_id'] for row in first}), 8)
        self.assertEqual(first, plan({'channels': [CHANNEL]}, {}, reversed(tracks), NOW, seed=42))
        state = migrate({}, 'state')
        apply_plan(state, first)
        self.assertEqual(plan({'channels': [CHANNEL]}, state, tracks, NOW), [])
        self.assertEqual(plan({'channels': [CHANNEL]}, {}, [], NOW), [])

    def test_exact_180_days_and_publication_time(self):
        old = job()
        self.assertFalse(repeat_ready([old], 'TK1', NOW + timedelta(days=180, microseconds=-1)))
        self.assertTrue(repeat_ready([old], 'TK1', NOW + timedelta(days=180)))
        old['uploaded_at'] = (NOW + timedelta(days=2)).isoformat()
        self.assertFalse(repeat_ready([old], 'TK1', NOW + timedelta(days=180)))
        for status in ('planned', 'failed'):
            old['status'] = status
            self.assertFalse(repeat_ready([old], 'TK1', NOW + timedelta(days=500)))
        old['status'] = 'cancelled'
        self.assertTrue(repeat_ready([old], 'TK1', NOW))

    def test_lru_missing_metrics_and_channel_isolation(self):
        old = job('TK1', NOW - timedelta(days=300))
        newer = job('TK2', NOW - timedelta(days=200))
        other = job('TK3', NOW, channel='other')
        state = {'jobs': {row['id']: row for row in (old, newer, other)}}
        tracks = [{'id': f'TK{i}'} for i in (1, 2, 3)]
        jobs = plan({'channels': [CHANNEL]}, state, tracks, NOW)
        self.assertEqual([row['track_id'] for row in jobs], ['TK3', 'TK1', 'TK2'])

    def test_repeat_changes_both_assets_and_blocks_exhaustion(self):
        old = job(at=NOW - timedelta(days=200))
        old['visual_snapshot'] = {'path': '/images/a.png', 'rev': 'r'}
        old['seo_snapshot'] = build_snapshot(old, TRACK, CHANNEL, NOW.isoformat())[0]
        new = job(at=NOW + timedelta(days=1), cycle=2, status='planned')
        new['visual_snapshot'] = {'path': '/images/b.png', 'rev': 'r'}
        new['seo_snapshot'] = build_snapshot(new, TRACK, CHANNEL, NOW.isoformat(),
            previous_selected=old['seo_snapshot']['selected'])[0]
        self.assertEqual(validate_snapshot(new['seo_snapshot'], new), new['seo_snapshot'])
        state = {'jobs': {row['id']: row for row in (old, new)}}
        rows = [{'path': '/images/a.png'}, {'path': '/images/b.png'}]
        self.assertEqual(changed_image(rows, state, new), rows[1:])
        check_repeat(state, new, NOW)
        with self.assertRaisesRegex(ValueError, 'repeat_image_exhausted'):
            changed_image(rows[:1], state, new)
        new['seo_snapshot'] = deepcopy(old['seo_snapshot'])
        with self.assertRaisesRegex(ValueError, 'repeat_seo_unchanged'):
            check_repeat(state, new, NOW)
        one_tag = dict(CHANNEL, tags=['trap'])
        prior = build_snapshot(old, TRACK, one_tag, NOW.isoformat())[0]
        with self.assertRaisesRegex(ValueError, 'repeat_seo_exhausted'):
            build_snapshot(new, TRACK, one_tag, NOW.isoformat(), previous_selected=prior['selected'])

    def test_unknown_previous_assets_fail_closed(self):
        old = job(at=NOW - timedelta(days=200))
        new = job(at=NOW, cycle=2, status='planned')
        state = {'jobs': {old['id']: old, new['id']: new}}
        with self.assertRaisesRegex(ValueError, 'previous_image_unknown'):
            changed_image([{'path': '/images/a.png'}], state, new)

    def test_pixels_detect_renamed_duplicate_image(self):
        with TemporaryDirectory() as folder:
            a, b, c = [Path(folder) / name for name in ('a.png', 'b.bmp', 'c.png')]
            Image.new('RGB', (320, 180), 'red').save(a)
            Image.new('RGB', (320, 180), 'red').save(b)
            Image.new('RGB', (320, 180), 'blue').save(c)
            self.assertEqual(image_digest(a), image_digest(b))
            self.assertNotEqual(image_digest(a), image_digest(c))

    def test_seed_report_cas_and_lost_response_integration(self):
        fake = MemoryDropbox()
        cloud = BeatCloud(fake, sleep=lambda _: None)
        store = BeatState(cloud, lambda: NOW)
        tracks = [dict(TRACK, id=f'TK{i}', tags=[tag])
                  for i, tag in enumerate(('trap', 'drill', 'ambient'))]
        old = [job(track['id'], NOW - timedelta(days=200 + i)) for i, track in enumerate(tracks)]
        cloud.update('state', lambda state: state['jobs'].update({row['id']: row for row in old}))
        reports = {'beats': json.dumps(self.report()).encode()}
        expected = store.dry_run({'channels': [CHANNEL]}, tracks, seed=42, reports=reports)['jobs']
        owner = store.acquire()
        fake.faults = [('after_write', Transient())]
        actual = store.fill_buffer({'channels': [CHANNEL]}, tracks, owner, seed=42, reports=reports)
        store.release(owner)
        self.assertEqual(actual, expected)
        self.assertTrue(all(row['cycle'] == 2 and row['selection']['report_hash'] for row in actual))
        self.assertEqual(len({row['track_id'] for row in actual}), len(actual))

    def test_early_upload_repeat_does_not_spend_budget(self):
        cloud = BeatCloud(MemoryDropbox(), sleep=lambda _: None)
        old = job(at=NOW - timedelta(days=179))
        old['visual_snapshot'] = {'path': '/images/a.png', 'rev': 'r'}
        old['seo_snapshot'] = build_snapshot(old, TRACK, CHANNEL, NOW.isoformat())[0]
        new = job(at=NOW + timedelta(days=2), cycle=2, status='planned')
        new['visual_snapshot'] = {'path': '/images/b.png', 'rev': 'r'}
        new['seo_snapshot'] = build_snapshot(new, TRACK, CHANNEL, NOW.isoformat(),
            previous_selected=old['seo_snapshot']['selected'])[0]
        cloud.update('state', lambda state: state['jobs'].update({old['id']: old, new['id']: new}))
        store = BeatState(cloud, lambda: NOW)
        with self.assertRaisesRegex(ValueError, 'repeat_not_ready'):
            store.reserve_attempt(new['id'], 'repeat', exclusive=True)
        self.assertEqual(cloud.read('state')[0]['attempts'], {})
        store.clock = lambda: NOW + timedelta(days=1)
        self.assertFalse(store.reserve_attempt(new['id'], 'repeat', exclusive=True)['replayed'])

    def test_cancelled_unknown_insert_remains_blocked(self):
        old = job(at=NOW - timedelta(days=200), status='cancelled')
        state = migrate({'jobs': {old['id']: old}, 'attempts': {
            instant(old['slot']).date().isoformat(): {'unknown': {
                'job_id': old['id'], 'reserved_at': old['slot']}}}}, 'state')
        self.assertEqual(plan({'channels': [CHANNEL]}, state, [TRACK], NOW), [])
        new = job(at=NOW + timedelta(days=1), cycle=2, status='planned')
        state['jobs'][new['id']] = new
        with self.assertRaisesRegex(ValueError, 'repeat_not_ready'):
            check_repeat(state, new, NOW)
        del state['attempts']
        self.assertTrue(repeat_ready([old], 'TK1', NOW))

    def test_malformed_track_tags_use_missing_data_fallback(self):
        for tags in (None, 'trap', [None]):
            track = dict(TRACK, tags=tags)
            scores, _ = performance(json.dumps(self.report()).encode(), 'beats', [track], NOW)
            self.assertEqual(scores, {})
