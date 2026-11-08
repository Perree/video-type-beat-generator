"""Read-only verification accepts tag ordering and catches genuine metadata drift."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from core.beat_metadata_verify import compare


class MetadataVerifyTests(unittest.TestCase):
    def run_compare(self, title='Beat', tags=None, channel_id='UCowner'):
        job = dict(id='j', channel='isla', track_id='TK1', youtube_id='video', cycle=1,
                   slot='2099-11-08T15:00:00-03:00', publication_mode='scheduled',
                   seo_snapshot={'track': dict(id='TK1', title='Beat', tags=[])})
        channel = dict(id='isla', youtube_channel_id='UCowner',
                       seo=dict(title_template='{name}', tags=['b', 'a'], description=''))
        row = dict(id='video', snippet=dict(channelId=channel_id, title=title,
                                           tags=['a', 'b'] if tags is None else tags),
                   status=dict(privacyStatus='private', publishAt='2099-11-08T18:00:00Z'))
        # Neither fake exposes a mutation method.
        cloud = SimpleNamespace(read=lambda _: (dict(jobs={'j': deepcopy(job)}), 'revision'))
        service = SimpleNamespace(videos=lambda: SimpleNamespace(
            list=lambda **kwargs: SimpleNamespace(execute=lambda: dict(items=[row]))))
        return compare(cloud, channel, service)

    def test_order_and_timezone_are_equivalent(self):
        self.assertEqual(self.run_compare()[0]['differences'], [])

    def test_missing_tag_and_different_title_are_reported(self):
        self.assertEqual(self.run_compare(title='Other', tags=['a'])[0]['differences'],
                         ['title', 'tags'])

    def test_wrong_owner_blocks_verification(self):
        with self.assertRaisesRegex(ValueError, 'owner_mismatch'):
            self.run_compare(channel_id='UCother')
