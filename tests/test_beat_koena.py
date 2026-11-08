"""Explicit reference-title overrides preserve legacy snapshot replay."""
import unittest
from copy import deepcopy
from core import beat_seo, beat_koena_seo
from core.beat_templates import apply_channel_templates


class KoenaTests(unittest.TestCase):
    def test_explicit_families_override_source_artists_and_remain_stable(self):
        profile = dict(title_mode='koena_v1', title_template='[FREE] {style} Type Beat - "{name}"',
                       description='{title}\n{url}\n{music_info}\n{credits}\n{guitar_hashtags}',
                       tags=['type beat', 'matwyre'])
        channel = dict(id='guitar-trap', use_channel_templates=True, seo=profile)
        apply_channel_templates(channel, dict(title_template=profile['title_template'],
                                            description_template=profile['description']))
        families = set()
        for number in range(1, 25):
            track = dict(id='TK'+str(number), title='My Song', tags=['juice wrld'])
            job = dict(id='job', channel='guitar-trap', track_id=track['id'], cycle=2)
            snap, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-07T18:00:00-03:00')
            beat_seo.validate_snapshot(snap, job)
            title = snap['selected']['title']
            style = next(s for s in beat_koena_seo.STYLES if title == f'[FREE] {s} Type Beat - "My Song"')
            families.add(style)
            self.assertTrue(snap['selected']['description'].startswith(title))
            self.assertNotIn('Juice WRLD', title)
            again, _ = beat_seo.build_snapshot(job, track, channel, '2026-11-07T18:00:00-03:00',
                                               previous_selected=snap['selected'])
            beat_seo.validate_snapshot(again, job)
            self.assertEqual(title, again['selected']['title'])
            legacy = deepcopy(channel)
            legacy['seo']['title_mode'] = 'guitar_v1'
            old, _ = beat_seo.build_snapshot(job, track, legacy, '2026-11-07T18:00:00-03:00')
            beat_seo.validate_snapshot(old, job)
            self.assertEqual(old['selected']['title'], '[FREE] Juice WRLD Type Beat - "My Song"')
        self.assertEqual(families, set(beat_koena_seo.STYLES))


if __name__ == '__main__':
    unittest.main()
