"""Link del kit sin seguimiento si el canal lo pide, y carpeta de fondos fija por canal."""
import unittest
from unittest import mock

from core import dropbox_client, kit_art, kit_week

LINK = 'https://wyresounds.com/b/lqtC9'


class VideoLinkTests(unittest.TestCase):
    def test_tracks_by_default(self):
        tracking_id, templates = kit_week.video_link(LINK, {'link': 'https://wyresounds.com/'})
        self.assertTrue(tracking_id)
        self.assertIn('utm_source=youtube', templates['link'])
        self.assertIn(tracking_id, templates['link'])

    def test_plain_link_when_channel_turns_tracking_off(self):
        tracking_id, templates = kit_week.video_link(LINK, {'track_links': False})
        self.assertIsNone(tracking_id)
        self.assertEqual(templates['link'], LINK)

    def test_no_link(self):
        self.assertEqual(kit_week.video_link('', {'a': 1}), (None, {'a': 1}))


class BackgroundsFolderTests(unittest.TestCase):
    def test_channel_folder_overrides_genre(self):
        art = {'refs_root': '/refs', 'backgrounds_folder': '/refs/wyreguitars/'}
        seen = []

        def listing(path, dbx=None):
            seen.append(path)
            return [{'name': 'a.jfif', 'path': f'{path}/a.jfif', 'is_folder': False}]
        with mock.patch.object(dropbox_client, 'list_folder_entries', side_effect=listing):
            found = kit_art.dropbox_candidates(art, 'guitarras')
        self.assertEqual(seen, ['/refs/wyreguitars'])
        self.assertEqual([f['path'] for f in found], ['/refs/wyreguitars/a.jfif'])

    def test_without_folder_uses_genre(self):
        with mock.patch.object(dropbox_client, 'list_folder_entries', return_value=[]) as ls:
            kit_art.dropbox_candidates({'refs_root': '/refs'}, 'guitarras')
        ls.assert_called_once_with('/refs/guitarras', dbx=None)


if __name__ == '__main__':
    unittest.main()
