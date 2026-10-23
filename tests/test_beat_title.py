import os
import unittest

from core import beat_title as bt

REAL = ("(BEAT PRO-527) [juice wrld, elec gtr, sad] This is for me - 160bpm - key A Sharp Minor "
        "(prod. @matwyre x @prodrenowrrst)")
SIMPLE = ["dolor", "Legends Fall", "lucid vibes", "money and lonely", "noche fria", "OLVIDARTE",
          "see through", "sicodelic", "tarde vacia", "young love"]
TITLE = '[FREE] {artist} Type Beat - "{name}"'


class ParseTests(unittest.TestCase):
    def test_real_beatstars_name(self):
        self.assertEqual(bt.parse(REAL), {"name": "This is for me", "artist": "juice wrld", "bpm": "160",
                                          "key": "A Sharp Minor", "mood": "sad"})

    def test_profile_artist_spelling_wins(self):
        self.assertEqual(bt.parse(REAL, ["Lil Peep", "Juice WRLD"])["artist"], "Juice WRLD")

    def test_simple_real_names_are_only_name(self):
        for name in SIMPLE:
            self.assertEqual(bt.parse(name), {"name": name, "artist": "", "bpm": "", "key": "", "mood": ""})

    def test_every_real_file_in_beats_folder_gets_a_name(self):
        folder = "beats"
        if not os.path.isdir(folder):
            self.skipTest("sin carpeta beats/")
        for entry in os.listdir(folder):
            stem, ext = os.path.splitext(entry)
            if ext.lower() in (".mp3", ".wav"):
                info = bt.parse(stem)
                self.assertTrue(info["name"], entry)
                self.assertNotIn("bpm", info["name"].lower(), entry)
                self.assertNotIn("prod", info["name"].lower(), entry)

    def test_common_producer_formats(self):
        self.assertEqual(bt.parse("Juice WRLD Type Beat - Lucid 140bpm")["artist"], "Juice WRLD")
        self.assertEqual(bt.parse("Juice WRLD Type Beat - Lucid 140bpm")["name"], "Lucid")
        info = bt.parse('[FREE] Lil Peep Type Beat "Pain" (prod. x)')
        self.assertEqual((info["artist"], info["name"]), ("Lil Peep", "Pain"))
        self.assertEqual(bt.parse("dark_trap_140bpm_key_Cm")["key"], "Cm")
        self.assertEqual(bt.parse("[piano, dark] Night")["artist"], "")
        self.assertEqual(bt.parse("[piano, dark] Night")["mood"], "dark")


class FillTests(unittest.TestCase):
    def test_title_with_all_data(self):
        self.assertEqual(bt.fill(TITLE + " [[({mood})]]", bt.parse(REAL, ["Juice WRLD"])),
                         '[FREE] Juice WRLD Type Beat - "This is for me" (sad)')

    def test_title_without_artist_has_no_dangling_parts(self):
        info = bt.parse("Legends Fall")
        self.assertEqual(bt.fill(TITLE + " [[({mood})]]", info), '[FREE] "Legends Fall"')
        self.assertEqual(bt.fill("{name} | {bpm} BPM | {key}", info), "Legends Fall")
        self.assertEqual(bt.fill("{artist} Type Beat | {name}", info), "Legends Fall")

    def test_optional_blocks_and_explicit_blocks(self):
        info = bt.parse("x 150bpm")
        self.assertEqual(bt.fill("[[{key} · ]]{name} [[{bpm} BPM]]", info), "x 150 BPM")

    def test_gaps_mode_keeps_static_lines(self):
        text = bt.fill("{name} | {bpm} BPM | {key}\nInstagram:\n[[Mood: {mood}]]", bt.parse("Solo"), tidy="gaps")
        self.assertEqual(text.split("\n")[:2], ["Solo", "Instagram:"])

    def test_variables_in(self):
        self.assertEqual(bt.variables_in("{artist} type beat {x}"), ["artist"])


if __name__ == "__main__":
    unittest.main()
