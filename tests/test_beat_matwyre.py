"""Repertory selection, truthful metadata, balanced scheduling and immutable replay."""
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import re
import unittest
from core import beat_matwyre as repertoire
from core import beat_matwyre_seo as seo
from core.beat_selection import eligible_tracks, ensure_selection, SelectionChanged
from core.beat_seo import build_snapshot, validate_snapshot, digest
from core.beat_schedule import plan
from core.beat_templates import apply_channel_templates
from core.beat_cloud import BeatCloud
from core.beat_fakes import MemoryDropbox
from core.beat_title_metrics import collect
from core.beat_share import publication_link
from core.beat_schema import identity

NOW = '2026-11-07T12:00:00+00:00'


def channel():
    return dict(id='matwyrebeats', active=True, priority=10, selection_tags=[repertoire.SELECTION],
                slots=[dict(weekday=d, hour=18, minute=0) for d in range(7)],
                youtube_channel_id='UC' + 'x' * 22,
                seo=dict(title_mode=seo.MODE, title_template='(FREE) {style} Type Beat - "{name}" | {detail} Type Beat 2026',
                         tags=['matwyre', 'matwyrebeats'],
                         description='Compra: {url}\n{context}\n{music_info}\n{credits}\n{hashtags}'))


def track(tags, tid='TK1', title='La Noche'):
    return dict(id=tid, title=title, tags=tags)


class MatwyreTests(unittest.TestCase):
    def test_sound_tags_expand_without_imaginary_artists(self):
        cases = [(['sad', 'guitar'], 'melodic'), (['rnb'], 'emotional'),
                 (['acoustic'], 'emotional'), (['hard'], 'trap'),
                 (['MILO J', 'sad trap'], 'emotional'),
                 (['type beat seven kayne'], 'melodic'),
                 (['duki type beat 2022'], 'melodic')]
        for tags, family in cases:
            t = track(tags)
            self.assertEqual(repertoire.context(t)['family'], family)
            self.assertEqual(eligible_tracks(channel(), [t]), [t])
            for option in seo.variants(t, channel()['seo']):
                self.assertNotIn('FREE FOR PROFIT', option['title'])
                for artist in repertoire.context(t)['artists']:
                    self.assertIn(artist, option['title'].split(' Type Beat')[0])
        for tags in [['melodic house'], ['sad', 'reggaeton'], ['guitar pop'], ['rnb', 'afrobeats'],
                     ['not duki'], ['hardstyle'], ['sadder'], ['hyperpop']]:
            self.assertEqual(eligible_tracks(channel(), [track(tags)]), [])
        old = dict(channel(), selection_tags=['sad'])
        self.assertEqual(eligible_tracks(old, [track(['sad', 'reggaeton'])]), [track(['sad', 'reggaeton'])])

    def test_title_format_always_two_artists(self):
        pattern = re.compile(r'^\(FREE\) (.+) x (.+) Type Beat - "La Noche" \| (.+) Type Beat 2026$')
        for tags, genre in [(['sad', 'guitar'], 'Sad'), (['duki', 'melodic'], 'Melodic'),
                            (['khea', 'duki', 'melodic'], 'Melodic'), (['rnb'], 'R&B'),
                            (['hard'], 'Hard'), (['milo j', 'sad trap'], 'Trap')]:
            t = track(tags)
            titles = [o['title'] for o in seo.variants(t, channel()['seo'])]
            self.assertGreater(len(titles), 1)
            for title in titles:
                m = pattern.match(title)
                self.assertTrue(m, title)
                self.assertNotEqual(m.group(1), m.group(2))
                self.assertEqual(m.group(3), genre)
        for o in seo.variants(track(['khea', 'duki', 'melodic']), channel()['seo']):
            self.assertEqual(set(o['title'].split(' Type Beat')[0][7:].split(' x ')), {'Khea', 'Duki'})

    def test_precise_labels(self):
        for tags, must, absent in [(['acoustic'], 'Acoustic', 'Guitar'),
                                   (['hard'], 'Hard', 'Hard Trap'),
                                   (['emo rap'], 'Emo Rap', 'Emo Trap'),
                                   (['guitar'], 'Guitar', 'Acoustic'),
                                   (['sad'], 'Sad', 'Hard')]:
            t = track(tags)
            text = str([o['title'].split('|')[1] for o in seo.variants(t, channel()['seo'])])
            self.assertIn(must, text)
            self.assertNotIn(absent, text)
        t = track(['Khea', 'Duki', 'melodic'])
        self.assertEqual(repertoire.context(t)['artists'], ['Khea', 'Duki'])

    def test_snapshot_replay_and_tampering(self):
        ch = channel()
        for i, tags in enumerate([['rnb', 'guitar'], ['duki', 'hard'], ['milo j', 'sad trap']]):
            t = track(tags, 'TK' + str(i))
            j = dict(id='job'+str(i), channel=ch['id'], track_id=t['id'], cycle=1)
            snap, _ = build_snapshot(j, t, ch, NOW)
            self.assertEqual(validate_snapshot(snap, j), snap)
            self.assertEqual(build_snapshot(j, t, ch, NOW)[0], snap)
            repeat = dict(j, cycle=2)
            changed, _ = build_snapshot(repeat, t, ch, NOW, previous_selected=snap['selected'])
            validate_snapshot(changed, repeat)
            self.assertNotEqual(changed['selected']['title'], snap['selected']['title'])
            snap['experiment']['repertory'] = 'invented'
            snap['sha256'] = digest({k:v for k,v in snap.items() if k != 'sha256'})
            with self.assertRaisesRegex(ValueError, 'seo_experiment_invalid'):
                validate_snapshot(snap, j)

    def test_name_limits_credits_and_missing_technical(self):
        ch = channel()
        t = track(['rnb', 'acoustic guitar'], title='Night ' * 80)
        for option in seo.variants(t, ch['seo']):
            self.assertLessEqual(len(option['title']), 100)
            self.assertLessEqual(sum(len(v)+(2 if ' ' in v else 0)+1 for v in option['tags']), 450)
        t['title'] = 'La Noche - 92bpm - key D# minor (prod. @matwyre x @collab)'
        text = seo.description(ch['seo'], t, seo.variants(t, ch['seo'])[0])
        self.assertIn('BPM: 92', text)
        self.assertIn('Tono: D# minor', text)
        self.assertIn('@matwyre x @collab', text)
        t['title'] = 'La Noche'
        text = seo.description(ch['seo'], t, seo.variants(t, ch['seo'])[0])
        self.assertNotIn('BPM:', text)
        self.assertNotIn('Tono:', text)
        self.assertNotIn('{', text.replace('{url}', ''))
        t['title'] = "I'm Fucked (matwyre x capsctrl x ibifibi)"
        for option in seo.variants(t, ch['seo']):
            self.assertNotIn('Acoustic Guitar Guitar', option['title'])
            self.assertNotIn('capsctrl', option['title'])
        self.assertIn('matwyre x capsctrl x ibifibi', seo.description(ch['seo'], t, {}))

    def test_balanced_planning_and_absent_family(self):
        ch = channel()
        tracks = [track(tags, 'TK'+str(i*20+j)) for i,tags in enumerate(
            [['melodic'], ['rnb'], ['hard trap']]) for j in range(20)]
        state = dict(jobs={}, attempts={}, lock=None)
        jobs = plan(dict(channels=[ch]), state, tracks, datetime.fromisoformat(NOW))
        lookup = {t['id']: repertoire.context(t)['family'] for t in tracks}
        first = Counter(lookup[j['track_id']] for j in jobs[:10])
        self.assertEqual(first, Counter(melodic=5, emotional=3, trap=2))
        self.assertEqual(len({j['track_id'] for j in jobs}), len(jobs))
        only = [t for t in tracks if lookup[t['id']] == 'emotional']
        jobs = plan(dict(channels=[ch]), state, only, datetime.fromisoformat(NOW))
        self.assertEqual(len(jobs), 14)
        self.assertTrue(all(lookup[j['track_id']] == 'emotional' for j in jobs))

    def test_templates_and_selection_fence(self):
        ch = channel()
        saved = dict(title_template=ch['seo']['title_template'],
                     description_template=ch['seo']['description'])
        compiled = apply_channel_templates(dict(ch, use_channel_templates=True), saved)
        self.assertEqual(compiled['seo'], ch['seo'])
        cloud = BeatCloud(MemoryDropbox(), sleep=lambda _:None)
        cloud.write('config', dict(channels=[ch]), None)
        ensure_selection(cloud, ch)
        cloud.update('config', lambda d:d['channels'][0].update(selection_tags=['sad']))
        with self.assertRaises(SelectionChanged):
            ensure_selection(cloud, ch)

    def test_old_catalog_exclusions_are_enforced_and_fenced(self):
        ch = dict(channel(), excluded_track_ids=['TK1'])
        self.assertEqual(eligible_tracks(ch, [track(['sad'])]), [])
        self.assertEqual(len(eligible_tracks(ch, [track(['sad'], 'TK2')])), 1)
        cloud = BeatCloud(MemoryDropbox(), sleep=lambda _:None)
        cloud.write('config', dict(channels=[ch]), None)
        cloud.update('config', lambda d:d['channels'][0].update(excluded_track_ids=[]))
        with self.assertRaises(SelectionChanged):
            ensure_selection(cloud, ch)
        with self.assertRaisesRegex(ValueError, 'invalid_excluded_track_ids'):
            eligible_tracks(dict(ch, excluded_track_ids=['not a track']), [])

    def test_individual_link_uses_source_slug(self):
        ch = channel()
        t = dict(track(['sad']), url='https://www.beatstars.com/beat/different-slug-1')
        self.assertEqual(publication_link(ch, t, None), t['url'])
        self.assertEqual(publication_link(ch, t, 'https://bsta.rs/abcd'), 'https://bsta.rs/abcd')
        for url in ['https://evil.test/beat/different-slug-1', 'https://www.beatstars.com/matwyre',
                    'https://www.beatstars.com/beat/different-slug-2']:
            with self.assertRaisesRegex(ValueError, 'beat_individual_link_missing'):
                publication_link(ch, dict(t, url=url), None)

    def test_public_counters_for_new_mode_without_fabricated_ctr(self):
        ch = channel()
        t = track(['sad'])
        j = dict(channel=ch['id'], track_id=t['id'], cycle=1, slot=NOW, status='uploaded',
                 youtube_id='abcdefghijk', uploaded_at=NOW)
        j['id'] = identity(t['id'], ch['id'], 1, NOW)
        j['seo_snapshot'] = build_snapshot(j, t, ch, NOW)[0]
        cloud = BeatCloud(MemoryDropbox(), sleep=lambda _:None)
        cloud.write('config', dict(channels=[ch]), None)
        cloud.write('state', dict(jobs={j['id']:j}, attempts={}, lock=None), None)
        def reader(channel_id, ids):
            return {j['youtube_id']:dict(privacy='public', channel_id=ch['youtube_channel_id'],
                    title=j['seo_snapshot']['selected']['title'], published_at=NOW,
                    views=100, likes=4, comments=1)}
        self.assertEqual(collect(cloud, ch['id'], reader, '2026-11-15T12:00:00+00:00'), 1)
        sample = cloud.read('state')[0]['jobs'][j['id']]['title_metrics']['7']
        self.assertEqual(sample['views'], 100)
        self.assertEqual(sample['experiment']['version'], seo.MODE)
        self.assertTrue(sample['late'])
        self.assertIsNone(sample['ctr'])
        self.assertEqual(collect(cloud, ch['id'], reader, '2026-11-15T12:00:00+00:00'), 0)


if __name__ == '__main__':
    unittest.main()
