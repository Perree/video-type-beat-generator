"""Exact channel eligibility, planner isolation and legacy compatibility."""
from copy import deepcopy
import unittest

from core.beat_schedule import plan
from core.beat_schema import migrate
from core.beat_selection import eligible_tracks, ensure_selection, SelectionChanged
from core.beat_cloud import BeatCloud, Transient
from core.beat_fakes import MemoryDropbox
from core.beat_state import BeatState
from core.beat_schema import instant

NOW = '2026-10-12T12:00:00-03:00'
CHANNEL = {'id': 'a', 'slots': [{'weekday': 0, 'hour': 18, 'minute': 0}]}
TRACKS = [{'id': 'exact', 'tags': [' Ambient ', 'other']},
          {'id': 'partial', 'tags': ['ambient type beat']},
          {'id': 'unrelated', 'tags': ['trap']},
          {'id': 'inactive', 'tags': ['ambient'], 'active': False},
          {'id': 'tagless'}]


class SelectionTests(unittest.TestCase):
    def test_exact_case_insensitive_outer_whitespace_and_any_tag(self):
        channel = dict(CHANNEL, selection_tags=['missing', '  aMBIENT  '])
        self.assertEqual(eligible_tracks(channel, TRACKS), [TRACKS[0]])

    def test_partial_matches_in_either_direction_are_rejected(self):
        for tag in ('amb', 'ambient type beat remix', 'Ambient  Music'):
            with self.subTest(tag=tag):
                self.assertEqual(eligible_tracks(dict(CHANNEL, selection_tags=[tag]), TRACKS), [])
        self.assertEqual(eligible_tracks(dict(CHANNEL, selection_tags=['ambient']),
                                        [TRACKS[1]]), [])

    def test_inactive_and_tagless_tracks_do_not_match(self):
        self.assertEqual(eligible_tracks(dict(CHANNEL, selection_tags=['ambient']), TRACKS[3:]), [])

    def test_absent_or_empty_selection_tags_preserve_old_plan(self):
        # SEO tags and genre folders have never restricted eligibility.
        legacy = dict(CHANNEL, tags=['seo-only'], genres=['genre-only'],
                      slots=[{'weekday': day, 'hour': 18, 'minute': 0} for day in range(7)])
        expected = plan({'channels': [legacy]}, {}, TRACKS, NOW)
        self.assertTrue(expected)
        self.assertEqual({job['track_id'] for job in expected},
                         {'exact', 'partial', 'unrelated', 'tagless'})
        for channel in (legacy, dict(legacy, selection_tags=[])):
            self.assertEqual(plan({'channels': [channel]}, {}, TRACKS, NOW), expected)

    def test_no_matches_create_no_jobs_and_do_not_mutate_state(self):
        state = migrate({}, 'state')
        before = deepcopy(state)
        for tracks in (TRACKS, [], [TRACKS[3]]):
            self.assertEqual(plan({'channels': [dict(CHANNEL, selection_tags=['missing'])]},
                                  state, tracks, NOW), [])
        self.assertEqual(state, before)

    def test_channel_pools_and_blocked_channels_are_isolated(self):
        channels = [dict(CHANNEL, selection_tags=['ambient']),
                    dict(CHANNEL, id='b', selection_tags=['trap']),
                    dict(CHANNEL, id='blocked', priority=100, selection_tags=['missing'])]
        jobs = plan({'channels': channels}, {}, TRACKS, NOW)
        self.assertEqual({job['channel'] for job in jobs}, {'a', 'b'})
        for job in jobs:
            self.assertEqual(job['track_id'], {'a': 'exact', 'b': 'unrelated'}[job['channel']])
        for channel in channels[:2]:
            self.assertEqual([job for job in jobs if job['channel'] == channel['id']],
                             plan({'channels': [channel]}, {}, TRACKS, NOW))

    def test_filtered_cycle_never_falls_back_to_full_catalog(self):
        jobs = plan({'channels': [dict(CHANNEL, selection_tags=['ambient'])]}, {}, TRACKS, NOW)
        self.assertEqual(len(jobs), 1)  # repeat cooldown still applies
        self.assertEqual(jobs[0]['track_id'], 'exact')

    def test_selection_tags_validate_in_local_and_remote_schema(self):
        from core.beat_settings import settings
        for value in (None, 'ambient', [''], ['   '], [1], ['x' * 101], ['x'] * 41):
            config = {'channels': [dict(CHANNEL, selection_tags=value)]}
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, '^invalid_selection_tags$'):
                    migrate(config, 'config')
                with self.assertRaisesRegex(ValueError, '^invalid_selection_tags$'):
                    settings(config, {'canales': []})

    def test_semantically_same_filter_and_unrelated_metadata_do_not_abort(self):
        memory = MemoryDropbox()
        cloud = BeatCloud(memory, sleep=lambda _: None)
        channel = dict(CHANNEL, selection_tags=[' Ambient ', 'Jazz'])
        cloud.write('config', {'channels': [dict(channel, selection_tags=['JAZZ', 'ambient'],
                                                tags=['seo'], genres=['visual'])]}, None)
        ensure_selection(cloud, channel)
        cloud.update('config', lambda cfg: cfg['channels'][0].update(selection_tags=[]))
        with self.assertRaises(SelectionChanged):
            ensure_selection(cloud, channel)
        ensure_selection(cloud, CHANNEL)  # [] and absent retain the same legacy rules

    def test_filter_change_during_cas_retry_does_not_commit_jobs_or_attempts(self):
        for phase in ('planning', 'attempt'):
            with self.subTest(phase=phase):
                memory = MemoryDropbox()
                cloud = BeatCloud(memory, sleep=lambda _: None)
                channel = dict(CHANNEL, selection_tags=['ambient'])
                config = {'channels': [channel]}
                cloud.write('config', config, None)
                cloud.write('state', migrate({}, 'state'), None)
                store = BeatState(cloud, lambda: instant(NOW))
                owner = store.acquire()
                if phase == 'attempt':
                    jobs = store.fill_buffer(config, TRACKS, owner)
                before = cloud.read('state')
                # The first write fails before commit, then config changes in backoff.
                def change(_):
                    cloud.update('config', lambda cfg: cfg['channels'][0].update(selection_tags=['missing']))
                cloud.sleep = change
                memory.faults.append(('write', Transient()))
                guard = lambda: ensure_selection(cloud, channel)
                with self.assertRaises(SelectionChanged):
                    if phase == 'planning':
                        store.fill_buffer(config, TRACKS, owner, before_commit=guard)
                    else:
                        store.reserve_attempt(jobs[0]['id'], 'intent', exclusive=True, before_commit=guard)
                self.assertEqual(cloud.read('state'), before)


if __name__ == '__main__':
    unittest.main()
