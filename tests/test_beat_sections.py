"""Phase 4 ey mat: beat parts from per-bar energy -> YouTube chapters."""
import json
from pathlib import Path
import tempfile
import unittest
import wave
from types import SimpleNamespace

import numpy as np

from core import beat_sections as s
from core.beat_render import MediaTools
from core.ffmpeg_util import resolve_tool

BPM = 150          # bar = 1.6 s, 4-bar phrase = 6.4 s
PHRASE = 240 / BPM * 4
LEVELS = {'quiet': .05, 'mid': .2, 'loud': .6, 'build': .1}


def song(parts, bpm=BPM, lead=0.0):
    """Noise whose loudness changes per 4-bar phrase: [('quiet', 2), ('loud', 4), ...]."""
    rng = np.random.default_rng(7)
    chunks = [np.zeros(int(lead * s.RATE), dtype='f4')]
    phrase = 240 / bpm * 4
    for level, count in parts:
        size = int(round(phrase * count * s.RATE))
        chunks.append((rng.standard_normal(size) * LEVELS[level]).astype('f4'))
    return np.concatenate(chunks)


def labels(rows):
    return [row['label'] for row in rows]


class DetectTests(unittest.TestCase):
    def test_typical_type_beat_structure(self):
        audio = song([('quiet', 2), ('loud', 4), ('mid', 4), ('loud', 4), ('mid', 4), ('loud', 4),
                      ('quiet', 2)])
        rows = s.detect(audio, BPM)
        self.assertEqual(labels(rows), ['Intro', 'Chorus', 'Verse', 'Chorus', 'Verse', 'Chorus', 'Outro'])
        self.assertEqual(rows[0]['start'], 0)
        self.assertEqual([row['start'] for row in rows[1:]],
                         [int(PHRASE * n) for n in (2, 6, 10, 14, 18, 22)])

    def test_pre_chorus_is_the_phrase_that_breaks_away_before_the_hook(self):
        audio = song([('quiet', 2), ('loud', 4), ('mid', 3), ('build', 2), ('loud', 4), ('quiet', 2)])
        self.assertEqual(labels(s.detect(audio, BPM)),
                         ['Intro', 'Chorus', 'Verse', 'Pre-Chorus', 'Chorus', 'Outro'])

    def test_song_ending_on_the_hook_has_no_outro(self):
        audio = song([('quiet', 2), ('loud', 4), ('mid', 4), ('loud', 4)])
        self.assertEqual(labels(s.detect(audio, BPM)), ['Intro', 'Chorus', 'Verse', 'Chorus'])

    def test_leading_silence_shifts_the_bar_grid(self):
        audio = song([('quiet', 2), ('loud', 4), ('mid', 4), ('loud', 4)], lead=.5)
        rows = s.detect(audio, BPM)
        self.assertEqual(labels(rows), ['Intro', 'Chorus', 'Verse', 'Chorus'])
        self.assertEqual(rows[1]['start'], int(.5 + PHRASE * 2))

    def test_without_bpm_uses_fixed_windows(self):
        # 2 s "bars": 8 s phrases; parts aligned to that grid still come out.
        audio = song([('quiet', 2), ('loud', 4), ('mid', 4), ('loud', 4)], bpm=120)
        self.assertEqual(labels(s.detect(audio, None)), ['Intro', 'Chorus', 'Verse', 'Chorus'])
        self.assertEqual(s.bar_seconds(None), s.FALLBACK_BAR)
        self.assertEqual(s.bar_seconds(0), s.FALLBACK_BAR)
        self.assertEqual(s.bar_seconds(True), s.FALLBACK_BAR)

    def test_flat_short_or_silent_audio_gives_no_chapters(self):
        self.assertEqual(s.detect(song([('loud', 20)]), BPM), [])
        self.assertEqual(s.detect(song([('quiet', 1), ('loud', 2)]), BPM), [])
        self.assertEqual(s.detect(np.zeros(s.RATE * 120, dtype='f4'), BPM), [])
        self.assertEqual(s.detect(np.zeros(0, dtype='f4'), BPM), [])

    def test_youtube_rules_merge_short_parts_and_need_three(self):
        rows = [{'start': 0, 'label': 'Intro'}, {'start': 4.7, 'label': 'Chorus'},
                {'start': 30, 'label': 'Pre-Chorus'}, {'start': 35, 'label': 'Chorus'},
                {'start': 60, 'label': 'Verse'}]
        # 0-4.7 Intro is too short (joins the chorus), 30-35 Pre-Chorus too (chorus continues):
        # only Chorus + Verse are left, fewer than YouTube's 3.
        self.assertEqual(s.youtube_rules(rows, 90), [])
        rows.append({'start': 75, 'label': 'Outro'})
        self.assertEqual(s.youtube_rules(rows, 90), [{'start': 0, 'label': 'Chorus'},
                         {'start': 60, 'label': 'Verse'}, {'start': 75, 'label': 'Outro'}])
        # Last part shorter than 10 s joins the previous one.
        self.assertEqual(s.youtube_rules([{'start': 0, 'label': 'Intro'}, {'start': 20, 'label': 'Chorus'},
                                          {'start': 40, 'label': 'Verse'}, {'start': 55, 'label': 'Outro'}], 60),
                         [{'start': 0, 'label': 'Intro'}, {'start': 20, 'label': 'Chorus'},
                          {'start': 40, 'label': 'Verse'}])

    def test_chapters_text(self):
        rows = [{'start': 0, 'label': 'Intro'}, {'start': 21, 'label': 'Chorus'},
                {'start': 3725, 'label': 'Outro'}]
        self.assertEqual(s.chapters_text(rows), '0:00 Intro\n0:21 Chorus\n1:02:05 Outro')
        self.assertEqual(s.chapters_text(rows[:2]), '')
        self.assertEqual(s.chapters_text(None), '')
        self.assertEqual(s.chapters_text([dict(rows[0], start=3)] + rows[1:]), '')

    def test_every_chapter_respects_youtube(self):
        audio = song([('quiet', 1), ('loud', 1), ('mid', 1), ('build', 1), ('loud', 5), ('mid', 4),
                      ('loud', 4), ('quiet', 1)])
        rows = s.detect(audio, BPM)
        total = len(audio) / s.RATE
        self.assertGreaterEqual(len(rows), 3)
        self.assertEqual(rows[0]['start'], 0)
        ends = [row['start'] for row in rows[1:]] + [int(total)]
        self.assertTrue(all(end - row['start'] >= 10 for row, end in zip(rows, ends)))
        self.assertTrue(all(a['label'] != b['label'] for a, b in zip(rows, rows[1:])))


class ChannelTests(unittest.TestCase):
    def test_only_channels_that_use_sections_decode(self):
        self.assertTrue(s.wants_sections({'seo': {'description': 'a\n\n{chapters}'}}, {}))
        self.assertTrue(s.wants_sections({}, {'section_cuts': True}))
        self.assertFalse(s.wants_sections({'seo': {'description': '{url}'}}, {}))
        self.assertFalse(s.wants_sections({'seo': 'x'}, {}))

    def test_decode_failure_means_no_chapters(self):
        def run(command, **kwargs):
            return SimpleNamespace(returncode=1, stdout=b'')
        self.assertEqual(s.sections(Path('x.wav'), MediaTools('fakeffmpeg', 'fakeprobe', run), BPM), [])

    def test_ffmpeg_command_is_mono_pcm_to_stdout(self):
        calls = []
        audio = song([('quiet', 2), ('loud', 4), ('mid', 4), ('loud', 4)])

        def run(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=0, stdout=audio.tobytes())
        rows = s.sections(Path('a.bin'), MediaTools('fakeffmpeg', 'fakeprobe', run), BPM, 90)
        self.assertEqual(labels(rows), ['Intro', 'Chorus', 'Verse', 'Chorus'])
        command = calls[0]
        for part in (['-ac', '1'], ['-ar', str(s.RATE)], ['-f', 'f32le'], ['-t', '90']):
            self.assertIn(part, [command[i:i + 2] for i in range(len(command))])
        self.assertEqual(command[-1], '-')

    @unittest.skipUnless(resolve_tool('ffmpeg'), 'ffmpeg not installed')
    def test_real_ffmpeg_decode(self):
        audio = song([('quiet', 2), ('loud', 4), ('mid', 4), ('loud', 4)])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'beat.wav'
            with wave.open(str(path), 'wb') as stream:
                stream.setparams((1, 2, s.RATE, 0, 'NONE', ''))
                stream.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())
            rows = s.sections(path, MediaTools(resolve_tool('ffmpeg'), 'unused'), BPM)
        self.assertEqual(labels(rows), ['Intro', 'Chorus', 'Verse', 'Chorus'])


if __name__ == '__main__':
    unittest.main()
