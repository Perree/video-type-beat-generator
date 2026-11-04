import json
from pathlib import Path
import unittest
from core import beat_seo
from core.beat_templates import apply_channel_templates


class KiezahTitleTests(unittest.TestCase):
    def channel(self):
        return json.loads((Path(__file__).resolve().parents[1] / 'docs/kiezah.channel.json').read_text(encoding='utf-8'))

    def snapshot(self, tags, name='Freedom', previous=None):
        ch = self.channel()
        apply_channel_templates(ch, {'title_template': ch['seo']['title_template'], 'description_template': ch['seo']['description']})
        job = {'id': 'job', 'channel': ch['id'], 'track_id': 'TK1', 'cycle': 2}
        snapshot, _ = beat_seo.build_snapshot(job, {'id': 'TK1', 'title': name, 'tags': tags}, ch,
                                             '2026-11-03T23:00:00-03:00', previous_selected=previous)
        beat_seo.validate_snapshot(snapshot, job)
        return snapshot

    def test_established_frame_with_actual_three_genres(self):
        s = self.snapshot(['club banger', 'afro house', 'deep house'])
        self.assertEqual(s['selected']['title'], '[FREE] Club Banger x Afro House Type Beat - "FREEDOM" | Deep House Type Beat')
        self.assertEqual(len({v['title'] for v in s['candidates']}), 1)

    def test_tags_and_labels_follow_track_and_exclude_artist(self):
        for tags, primary in [(['deep house', 'makar'], 'Deep House'), (['melodic house'], 'Melodic House'),
                              (['edm'], 'EDM'), (['club', 'house'], 'Club x House')]:
            selected = self.snapshot(tags)['selected']
            self.assertTrue(selected['title'].startswith(f'[FREE] {primary} Type Beat - "FREEDOM" | '))
            self.assertNotIn('Afro House', selected['title'])
            self.assertNotIn('afro house type beat', selected['tags'])
            self.assertFalse(any('makar' in tag for tag in selected['tags']))
            if 'club' not in tags:
                self.assertNotIn('club instrumental', selected['tags'])

    def test_long_name_repeat_and_old_snapshot_compatibility(self):
        s = self.snapshot(['melodic deep house', 'reggaeton house', 'club banger'], 'Name ' * 80)
        self.assertLessEqual(len(s['selected']['title']), 100)
        again = self.snapshot(['melodic deep house', 'reggaeton house', 'club banger'], 'Name ' * 80, s['selected'])
        self.assertEqual(s['selected']['title'], again['selected']['title'])
        self.assertNotEqual(s['selected']['tags'], again['selected']['tags'])
        self.assertLessEqual(len(','.join(s['selected']['tags'])) + 2 * sum(' ' in t for t in s['selected']['tags']), 500)


if __name__ == '__main__': unittest.main()
