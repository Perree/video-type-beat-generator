"""Short-link lookup (bsta.rs) and its use in the uploaded description."""
import copy
import unittest
from core.beat_http import BeatError
from core.beat_queries import SHARE_QUERY, PROFILE_QUERY
from core.beat_share import ShareLinks
from core.beat_schema import migrate
import test_beat_daily as daily
CONFIG = daily.CONFIG


class FakeShare:
    def __init__(self, rows, fail=False):
        self.rows, self.fail, self.calls = rows, fail, 0

    def query(self, query, variables, deadline):
        self.calls += 1
        if self.fail:
            raise BeatError('http_error')
        if query == PROFILE_QUERY:
            return {'profileByUsername': {'memberId': 'MR1', 'username': 'Producer'}}
        assert query == SHARE_QUERY
        return {'profileTracks': {'number': variables['page'], 'last': True, 'content': [
            {'id': tid, 'shareUrl': link, 'profile': {'memberId': 'MR1'}} for tid, link in self.rows.items()]}}


class ShareLinksTests(unittest.TestCase):
    PROFILE = 'https://www.beatstars.com/producer/tracks'

    def test_returns_valid_short_links_only(self):
        fake = FakeShare({'TK1': 'https://bsta.rs/TFVk6H', 'TK2': 'https://evil.example/x',
                          'TK3': 'https://bsta.rs/a b'})
        links = ShareLinks(fake)
        self.assertEqual(links.get('TK1', self.PROFILE), 'https://bsta.rs/TFVk6H')
        self.assertIsNone(links.get('TK2', self.PROFILE))
        self.assertIsNone(links.get('TK3', self.PROFILE))
        self.assertIsNone(links.get('TK9', self.PROFILE))
        self.assertEqual(fake.calls, 2)  # profile + one page, then cached

    def test_failure_never_raises_and_is_not_retried(self):
        fake = FakeShare({}, fail=True)
        links = ShareLinks(fake)
        self.assertIsNone(links.get('TK1', self.PROFILE))
        self.assertIsNone(links.get('TK1', self.PROFILE))
        self.assertEqual(fake.calls, 1)


class ShareInDescription(daily.DailyTests):
    """Reuses the daily fixtures: the uploaded description carries the short link, or the page URL."""

    def setUp(self):
        super().setUp()
        config = copy.deepcopy(CONFIG)
        config['channels'][0]['seo'] = {'tags': ['trap'], 'title_template': 'Free "{name}"',
                                        'description': 'Get it: {url} / {url}'}
        _, rev = self.cloud.read('config')
        self.cloud.write('config', migrate(config, 'config'), rev)

    def test_short_link_replaces_placeholder_at_upload(self):
        class Stub:
            def get(self, track_id, profile_url):
                return 'https://bsta.rs/' + track_id[2:]
        summary = self.run_worker(share_links=Stub())
        self.assertEqual(summary['uploaded'], 6)
        for call in self.calls:
            self.assertNotIn('{url}', call['description'])
            self.assertRegex(call['description'], r'^Get it: https://bsta\.rs/\d+ / https://bsta\.rs/\d+$')
            self.assertTrue(call['title'].startswith('Free "'))

    def test_falls_back_to_page_url_without_short_link(self):
        summary = self.run_worker(share_links=ShareLinks(FakeShare({}, fail=True)))
        self.assertEqual(summary['uploaded'], 6)
        for call in self.calls:
            self.assertIn('https://www.beatstars.com/beat/', call['description'])
            self.assertNotIn('{url}', call['description'])


# Re-running the inherited daily tests here would only repeat them.
for _name in [n for n in dir(ShareInDescription) if n.startswith('test_')
              and n not in ('test_short_link_replaces_placeholder_at_upload',
                            'test_falls_back_to_page_url_without_short_link')]:
    setattr(ShareInDescription, _name, None)


if __name__ == '__main__':
    unittest.main()
