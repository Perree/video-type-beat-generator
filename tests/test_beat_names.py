"""Beat name cleaning for the fixed title template (real BeatStars title shapes)."""
import unittest
from core.beat_names import clean_name
from core.beat_seo import beat_url


class NameTests(unittest.TestCase):
    def test_real_catalog_shapes(self):
        cases = {
            'juice wrld type beat - mellow': 'Mellow',
            'juice wrld type beat - my life is sad (buy 2 get 2)': 'My Life Is Sad',
            'juice wrld x iann dior - drama': 'Drama',
            '(FREE) Juice WRLD x Zzz. Type Beat "Let me go now"': 'Let me go now',
            '[FREE] "Bad Choice" (The Kid LAROI x Iann Dior)': 'Bad Choice',
            'Sicodelic | Juice Wrld Type Beat': 'Sicodelic',
            'Type Beat Juice WRLD "Resiliencia es poder" | Sad beat': 'Resiliencia es poder',
            'juice wrld, the kid laroi, iann dior type beat - "peace"': 'Peace',
            '[FREE] KHEA Melodic Type Beat – “CICATRICES”': 'CICATRICES',
            "juice wrld x the kid laroi type beat - don't let me go": "Don't Let Me Go",
            'Buenos Aires': 'Buenos Aires',
            'espero encontrarte': 'Espero Encontrarte',
        }
        for raw, expected in cases.items():
            self.assertEqual(clean_name(raw), expected, raw)

    def test_never_empty_and_no_markup(self):
        for raw in ('Juice WRLD Type Beat', '<b>x</b>', '""'):
            result = clean_name(raw)
            self.assertTrue(result, raw)
            self.assertFalse(set(result) & set('<>{}"'), raw)

    def test_link_keeps_the_original_title(self):
        url = beat_url({'id': 'TK12325335', 'title': 'juice wrld type beat - mellow'})
        self.assertEqual(url, 'https://www.beatstars.com/beat/juice-wrld-type-beat-mellow-12325335')


if __name__ == '__main__':
    unittest.main()
