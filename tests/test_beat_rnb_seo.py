"""R&B allocation, immutable retries and measurement boundaries."""
from copy import deepcopy
import unittest
from unittest.mock import Mock
from core import beat_rnb_seo as rnb
from core.beat_seo import build_snapshot, validate_snapshot, digest
from core.beat_seo_store import prepare_seo
from core.beat_schema import identity
from core.beat_cloud import BeatCloud, Conflict, Transient
from core.beat_fakes import MemoryDropbox
from core.beat_title_metrics import collect
from core.beat_templates import apply_channel_templates

NOW = '2026-11-06T18:00:00+00:00'


def channel():
    return dict(id='lovesickk', active=True, priority=1, slots=[dict(weekday=1, hour=18, minute=0)],
                youtube_channel_id='UC' + 'x' * 22,
                seo=dict(title_mode=rnb.MODE, title_template='(FREE) {style} Type Beat - "{name}"',
                         tags=['type beat', 'matwyre'],
                         description='Buy: {url}\n{music_info}\n{context}\nNon-profit only.'))


def track(tags=None, tid='TK1'):
    return dict(id=tid, title='Nevermind <3', tags=tags or ['rnb', 'sad rnb', 'soul'])


def job(t=None, cycle=1):
    t = t or track()
    result = dict(channel='lovesickk', track_id=t['id'], cycle=cycle, slot=NOW, status='planned')
    result['id'] = identity(t['id'], 'lovesickk', cycle, NOW)
    return result


class RnbTests(unittest.TestCase):
    def test_compatible_families_only_and_no_invented_artists(self):
        cases = [(['rnb'], {'simple'}),
                 (['rnb', 'acoustic guitar'], {'simple', 'detail'}),
                 (['rnb', 'soul'], {'simple', 'crossover'}),
                 (['rnb', 'sad rnb', 'trap soul', 'che ecru', 'partynextdoor'],
                  {'simple', 'detail', 'crossover', 'artists'}),
                 (['soul'], {'simple'})]
        for tags, families in cases:
            t = track(tags)
            options = rnb.variants(t, channel()['seo'])
            self.assertEqual({rnb.experiment(t, channel()['seo'], o)['family'] for o in options}, families)
            self.assertLessEqual(len(options), 4)
            for option in options:
                self.assertNotIn('SZA', option['title'])
                self.assertNotIn('free for profit', option['title'].lower())
        for tags in [['not partynextdoor', 'rnb'], ['rnb', 'soul']]:
            titles = str(rnb.variants(track(tags), channel()['seo']))
            self.assertNotIn('PARTYNEXTDOOR', titles)
            self.assertNotIn('Trap Soul', titles)
        with self.assertRaises(ValueError):
            rnb.variants(track(['house']), channel()['seo'])

    def test_allocation_replay_repeat_and_metadata_tamper(self):
        families = set()
        for i in range(40):
            t = track(['rnb', 'sad rnb', 'soul', 'che ecru'], f'TK{i}')
            j = job(t)
            snap, _ = build_snapshot(j, t, channel(), NOW)
            self.assertEqual(validate_snapshot(snap, j), snap)
            families.add(snap['experiment']['family'])
            self.assertEqual(set(snap['selected']), {'title', 'tags', 'description'})
            self.assertEqual(snap['experiment']['source_tags'], t['tags'])
            again, _ = build_snapshot(j, t, channel(), NOW)
            self.assertEqual(snap, again)
            repeat = dict(j, cycle=2)
            changed, _ = build_snapshot(repeat, t, channel(), NOW, previous_selected=snap['selected'])
            validate_snapshot(changed, repeat)
            self.assertNotEqual(snap['selected']['title'], changed['selected']['title'])
        self.assertEqual(families, {'simple', 'detail', 'crossover', 'artists'})
        snap['experiment']['family'] = 'invented'
        snap['sha256'] = digest({k: v for k, v in snap.items() if k != 'sha256'})
        with self.assertRaisesRegex(ValueError, 'seo_experiment_invalid'):
            validate_snapshot(snap, j)

    def test_limits_and_description_source(self):
        t = track(['rnb', 'acoustic guitar', 'che ecru'])
        t['title'] = 'Night ' * 80
        for option in rnb.variants(t, channel()['seo']):
            self.assertLessEqual(len(option['title']), 100)
            self.assertLessEqual(sum(len(v) + (2 if ' ' in v else 0) + 1 for v in option['tags']), 450)
        t['title'] = 'Night - 92bpm - key D# minor'
        snap, _ = build_snapshot(job(t), t, channel(), NOW)
        self.assertIn('BPM: 92', snap['selected']['description'])
        self.assertIn('Key: D# minor', snap['selected']['description'])
        self.assertIn('Che Ecru', snap['selected']['description'])
        self.assertNotIn('Drake', snap['selected']['description'])
        saved = dict(title_template=channel()['seo']['title_template'],
                     description_template='{context}\n{music_info}\n{beatstars_url}')
        apply_channel_templates(dict(channel(), use_channel_templates=True), saved)

    def test_persisted_selection_survives_cas_retry_and_new_config(self):
        for fault in [Conflict('conflict'), Transient()]:
            fake = MemoryDropbox()
            cloud = BeatCloud(fake, sleep=lambda _: None)
            j = job()
            cloud.update('state', lambda d: d['jobs'].update({j['id']: j}))
            fake.faults.append(('after_write' if isinstance(fault, Transient) else 'write', fault))
            snap = prepare_seo(cloud, j['id'], track(), channel(), NOW)
            changed = channel()
            changed['seo']['description'] = 'new profile'
            replay = prepare_seo(cloud, j['id'], track(['rnb', 'partynextdoor']), changed, NOW)
            self.assertEqual(snap, replay)


class MetricsTests(unittest.TestCase):
    def fixture(self):
        cloud = BeatCloud(MemoryDropbox(), sleep=lambda _: None)
        cloud.update('config', lambda d: d['channels'].append(channel()))
        j = job()
        snap, _ = build_snapshot(j, track(), channel(), NOW)
        j.update(status='uploaded', youtube_id='123456789ab', uploaded_at=NOW, seo_snapshot=snap)
        cloud.update('state', lambda d: d['jobs'].update({j['id']: j}))
        row = dict(title=snap['selected']['title'], channel_id=channel()['youtube_channel_id'],
                   privacy='public', published_at=NOW, views=100, likes=5, comments=None)
        return cloud, j, row

    def test_due_windows_are_idempotent_and_missing_is_unknown(self):
        cloud, j, row = self.fixture()
        reader = Mock(return_value={j['youtube_id']: row})
        self.assertEqual(collect(cloud, 'lovesickk', reader, '2026-11-12T18:00:00Z'), 0)
        reader.assert_not_called()
        self.assertEqual(collect(cloud, 'lovesickk', reader, '2026-11-13T19:00:00Z'), 1)
        self.assertEqual(collect(cloud, 'lovesickk', reader, '2026-11-13T20:00:00Z'), 0)
        self.assertEqual(collect(cloud, 'lovesickk', reader, '2026-12-04T19:00:00Z'), 1)
        samples = cloud.read('state')[0]['jobs'][j['id']]['title_metrics']
        self.assertEqual(set(samples), {'7', '28'})
        self.assertFalse(samples['7']['late'])
        self.assertIsNone(samples['7']['comments'])
        self.assertIsNone(samples['7']['ctr'])
        self.assertEqual(samples['28']['views'], 100)

    def test_wrong_owner_title_private_or_actual_publish_date_not_measured(self):
        for changes in [dict(channel_id='other'), dict(title='edited'), dict(privacy='private'),
                        dict(published_at='2026-11-12T18:00:00Z')]:
            cloud, j, row = self.fixture()
            row.update(changes)
            self.assertEqual(collect(cloud, 'lovesickk', lambda *a: {j['youtube_id']: row},
                                     '2026-11-13T19:00:00Z'), 0)

    def test_late_samples_are_labelled_and_invalid_counts_rejected(self):
        cloud, j, row = self.fixture()
        self.assertEqual(collect(cloud, 'lovesickk', lambda *a: {j['youtube_id']: row},
                                 '2026-12-10T19:00:00Z'), 2)
        self.assertTrue(cloud.read('state')[0]['jobs'][j['id']]['title_metrics']['7']['late'])
        cloud, j, row = self.fixture()
        row['views'] = True
        with self.assertRaises(ValueError):
            collect(cloud, 'lovesickk', lambda *a: {j['youtube_id']: row}, '2026-11-13T19:00:00Z')


class RnbV2Tests(unittest.TestCase):
    def test_weighted_uppercase_titles_and_valid_snapshots(self):
        from core import beat_rnb_seo_v2 as v2
        seo = dict(channel()['seo'], title_mode=v2.MODE)
        ch = dict(channel(), seo=seo)
        counts = {}
        for i in range(400):
            t = track(['rnb', 'sad rnb'], f'TK{i}')
            j = job(t)
            snap, _ = build_snapshot(j, t, ch, NOW)
            self.assertEqual(validate_snapshot(snap, j), snap)
            family = snap['experiment']['family']
            counts[family] = counts.get(family, 0) + 1
            title = snap['selected']['title']
            self.assertIn(title.split(' - ')[0], ('(FREE) R&B TYPE BEAT', '(FREE) MELODIC R&B TYPE BEAT',
                                                   '(FREE) SAD R&B TYPE BEAT'))
            self.assertLessEqual(len(title), 100)
        self.assertGreater(counts['simple'], counts['melodic'] > 0 and counts['melodic'])
        self.assertGreater(counts['simple'] + counts['melodic'], 340)
