import json
from pathlib import Path
import unittest
from core import beat_seo
from core.beat_share import publication_link


class WyreLatinTests(unittest.TestCase):
    def channel(self):
        return json.loads(Path('docs/wyrelatinbeatz.channel.json').read_text(encoding='utf8'))

    def snapshot(self, tags, name='Rushed Love'):
        job = dict(id='j', channel='wyrelatinbeatz', track_id='TK1', cycle=1)
        s, _ = beat_seo.build_snapshot(job, dict(id='TK1', title=name, tags=tags),
                                      self.channel(), '2026-11-11T15:00:00-03:00')
        self.assertEqual(beat_seo.validate_snapshot(s, job), s)
        return s

    def test_reference_format_and_real_genres(self):
        for tags, genre in [(['latin trap', 'sad'], 'Latin Trap'),
                            (['reggaeton'], 'Latin Reggaeton'),
                            (['dancehall'], 'Latin Dancehall')]:
            s = self.snapshot(tags)
            self.assertEqual(s['selected']['title'],
                'Bad Bunny x Feid Type Beat - "RUSHED LOVE" | ' + genre + ' Type Beat')
            # Editorial pairing must not rewrite the source tags or factual context.
            self.assertEqual(s['track']['tags'], tags)
            self.assertNotIn('Referencias de estilo:', s['selected']['description'])

    def test_uppercase_expansion_length_and_retry(self):
        s = self.snapshot(['latin trap'], 'Straße ' * 50)
        self.assertLessEqual(len(s['selected']['title']), 100)
        self.assertTrue(s['selected']['title'].endswith('" | Latin Trap Type Beat'))
        self.assertEqual(s, self.snapshot(['latin trap'], 'Straße ' * 50))

    def test_individual_purchase_link_required(self):
        with self.assertRaisesRegex(ValueError, 'beat_individual_link_missing'):
            publication_link(self.channel(), dict(id='TK1', title='Beat'), None)

    def test_picture_rotation_configured(self):
        c = self.channel()
        self.assertEqual(c['visual']['mode'], 'image')
        self.assertEqual(c['visual']['image_fit'], 'contain')
        self.assertTrue(c['dropbox_images']['latin'].endswith('/imagenes'))
