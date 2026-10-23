import csv
import os
import random
import subprocess
import tempfile
import unittest
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import channel_profile as cp
from core import manual_render as mr
from core.ffmpeg_util import get_media_duration, resolve_tool


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


class ManualLogicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_collect_audio_expands_folders_and_dedupes(self):
        a = touch(os.path.join(self.root, "in", "a.mp3"))
        touch(os.path.join(self.root, "in", "sub", "b.WAV"))
        touch(os.path.join(self.root, "in", "cover.jpg"))
        found = mr.collect_audio([os.path.join(self.root, "in"), a, os.path.join(self.root, "nope.mp3")])
        self.assertEqual([os.path.basename(p) for p in found], ["a.mp3", "b.WAV"])

    def test_rotation_uses_all_before_repeating(self):
        rot = mr.Rotation(["a", "b", "c"], random.Random(1))
        self.assertEqual(sorted(rot.next() for _ in range(3)), ["a", "b", "c"])
        self.assertIn(rot.next(), ["a", "b", "c"])
        self.assertIsNone(mr.Rotation([]).next())

    def test_unique_folder_does_not_overwrite(self):
        os.makedirs(os.path.join(self.root, "x"))
        os.makedirs(os.path.join(self.root, "x (2)"))
        self.assertEqual(mr.unique_folder(self.root, "x"), "x (3)")

    def test_safe_name_keeps_quotes_readable(self):
        self.assertEqual(mr.safe_name('[FREE] A Type Beat - "Pain"'), "[FREE] A Type Beat - 'Pain'")
        self.assertEqual(mr.safe_name("a: b?"), "a_ b_")

    def test_upload_text_blocks(self):
        text = mr.upload_text("T", "Desc\n", ["a", "b"])
        self.assertEqual(text, "TÍTULO\nT\n\nDESCRIPCIÓN\nDesc\n\nTAGS\na, b\n")

    def test_beat_info_from_filename(self):
        self.assertEqual(mr.beat_info("This is for me - 160bpm - key A Sharp Minor (prod. x)"),
                         (160.0, "A Sharp Minor"))
        self.assertEqual(mr.beat_info("dark 140 BPM key: F#m"), (140.0, "F#m"))
        self.assertEqual(mr.beat_info("sin datos"), (None, None))

    def test_title_uses_profile_and_respects_youtube_limit(self):
        profile = dict(cp.default_profile("C"), titulo="[FREE] {name} | {channel}")
        self.assertEqual(mr.beat_title(profile, "dark", "C"), "[FREE] dark | C")
        clean = dict(cp.default_profile("C"), artistas=["Juice WRLD"])
        real = "(BEAT PRO-527) [juice wrld, elec gtr, sad] This is for me - 160bpm - key A Sharp Minor (prod. @a x @b)"
        self.assertEqual(mr.beat_title(clean, real, "C"), '[FREE] Juice WRLD Type Beat - "This is for me"')
        self.assertEqual(mr.beat_title(clean, "Legends Fall", "C"), '[FREE] "Legends Fall"')
        long_name = "(BEAT PRO-527) [juice wrld, elec gtr, sad] This is for me - 160bpm - key A Sharp Minor (prod. @a x @b)"
        self.assertLessEqual(len(mr.beat_title(profile, long_name, "C")), 100)

    def test_text_uses_profile_description_and_tags_once(self):
        profile = dict(cp.default_profile("C"), descripcion="{name} | {bpm} BPM\n{socials}",
                       socials="IG: @yo", tags=["{name} type beat", "trap"])
        text = mr.beat_text(profile, "dark 140bpm", "C")
        self.assertIn("dark | 140 BPM", text)
        self.assertIn("IG: @yo", text)
        self.assertEqual(text.count("Tags:"), 0)  # los tags van en su propio bloque
        self.assertEqual(mr.beat_tags(profile, "dark 140bpm", "C"), ["dark type beat", "trap"])
        self.assertEqual(mr.beat_text(profile, "solo", "C").split("\n")[0], "solo")  # sin «| BPM» colgando
        with_tags = dict(profile, descripcion="Tags: {tags}")
        self.assertEqual(mr.beat_text(with_tags, "x", "C").count("Tags:"), 1)

    def test_batch_without_backgrounds_explains_folder(self):
        cp.create(self.root, "C")
        cp.save(self.root, "C", dict(cp.load(self.root, "C"), fondo="video"))
        with self.assertRaises(mr.ManualError) as ctx:
            mr.run_batch(["b.mp3"], "C", self.root, self.root, tools=object())
        self.assertIn("videos", str(ctx.exception))

    def test_settings_roundtrip(self):
        path = os.path.join(self.root, "config", "manual_mode.json")
        data = mr.load_settings(path)
        self.assertIn("local_root", data)
        data["local_root"] = "D:/x"
        mr.save_settings(data, path)
        self.assertEqual(mr.load_settings(path)["local_root"], "D:/x")


@unittest.skipUnless(resolve_tool("ffmpeg") and resolve_tool("ffprobe"), "requiere FFmpeg")
class ManualRenderTests(unittest.TestCase):
    """Render real y corto con FFmpeg: imagen y video stock, con el perfil del canal."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = cls.root = cls.tmp.name
        ff = resolve_tool("ffmpeg")
        run = lambda *a: subprocess.run([ff, "-v", "error", "-y", *a], check=True)
        cls.beat = os.path.join(root, "beats", "Dark Beat 150bpm.mp3")
        os.makedirs(os.path.dirname(cls.beat))
        run("-f", "lavfi", "-i", "sine=frequency=440:duration=3", cls.beat)
        cp.create(root, "Img")
        cp.save(root, "Img", dict(cp.load(root, "Img"), titulo="{name} Type Beat", miniatura_con_titulo=True,
                                  descripcion="{name} | {bpm} BPM\nTags: {tags}"))
        from PIL import Image
        Image.new("RGB", (800, 800), (200, 30, 30)).save(
            os.path.join(root, "canales", "Img", "fondos", "bg.jfif"), "JPEG")
        cp.create(root, "Vid")
        cp.save(root, "Vid", dict(cp.load(root, "Vid"), fondo="video", titulo="[FREE] {name}",
                                  descripcion="{name} | {bpm} BPM"))
        run("-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=1",
            os.path.join(root, "canales", "Vid", "fondos", "stock.mp4"))
        from core.stock_cache import StockCache
        cls.tools = mr.Tools(cache=StockCache(os.path.join(root, 'cache')))  # no tocar la caché real

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_outputs(self, results, expected_title):
        self.assertEqual(len(results), 1)
        out = results[0]
        self.assertEqual(os.path.basename(out["folder"]), expected_title)
        self.assertEqual(os.path.basename(out["video"]), expected_title + ".mp4")
        self.assertEqual(os.path.basename(out["thumbnail"]), expected_title + " - miniatura.jpg")
        self.assertAlmostEqual(get_media_duration(out["video"]), 3.0, delta=0.3)
        from PIL import Image
        with Image.open(out["thumbnail"]) as img:
            self.assertEqual(img.size, (1280, 720))
        with open(out["text"], encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("TÍTULO\n" + expected_title))
        self.assertEqual(text.count("TAGS\n"), 1)
        self.assertIn("150 BPM", text)
        self.assertEqual(sorted(os.listdir(out["folder"])),
                         sorted([expected_title + ext for ext in (".mp4", " - miniatura.jpg", ".txt")]))

    def test_image_profile(self):
        out_root = os.path.join(self.root, "out-image")
        results, errors = mr.run_batch([self.beat], "Img", self.root, out_root, tools=self.tools,
                                       today=datetime(2026, 1, 2))
        self.assertEqual(errors, [])
        self.check_outputs(results, "Dark Beat Type Beat")
        day = os.path.join(out_root, "2026-01-02")
        self.assertEqual(os.path.dirname(results[0]["folder"]), os.path.join(day, "Img"))
        with open(os.path.join(day, "pendientes.csv"), encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["canal", "título", "carpeta", "subido"])
        self.assertEqual(rows[1][:2], ["Img", "Dark Beat Type Beat"])

    def test_failed_beat_leaves_no_folder(self):
        bad = touch(os.path.join(self.root, "beats", "malo.mp3"), b"not audio")
        out_root = os.path.join(self.root, "out-fail")
        _, errors = mr.run_batch([bad], "Img", self.root, out_root, tools=self.tools, today=datetime(2026, 1, 2))
        self.assertEqual(len(errors), 1)
        channel_dir = os.path.join(out_root, "2026-01-02", "Img")
        self.assertEqual(os.listdir(channel_dir) if os.path.isdir(channel_dir) else [], [])

    def test_video_profile_loops_short_stock(self):
        results, errors = mr.run_batch([self.beat], "Vid", self.root, os.path.join(self.root, "out-video"),
                                       tools=self.tools)
        self.assertEqual(errors, [])
        self.check_outputs(results, "[FREE] Dark Beat")

    def test_manual_title_override_is_used_and_capped(self):
        results, errors = mr.run_batch([self.beat], "Img", self.root, os.path.join(self.root, "out-title"),
                                       tools=self.tools, titles={self.beat: "Mi título " + "x" * 120})
        self.assertEqual(errors, [])
        self.assertLessEqual(len(os.path.splitext(os.path.basename(results[0]["video"]))[0]), 100)
        self.assertTrue(os.path.basename(results[0]["video"]).startswith("Mi título"))

    def test_cancel_stops_batch(self):
        with self.assertRaises(mr.Cancelled):
            mr.run_batch([self.beat], "Img", self.root, os.path.join(self.root, "out-c"),
                         tools=self.tools, cancelled=lambda: True)

    def test_bad_audio_is_reported_not_fatal(self):
        bad = touch(os.path.join(self.root, "beats", "roto.mp3"), b"not audio")
        results, errors = mr.run_batch([bad, self.beat], "Img", self.root, os.path.join(self.root, "out-bad"),
                                       tools=self.tools)
        self.assertEqual(len(results), 1)
        self.assertEqual(errors[0][0], "roto")


if __name__ == "__main__":
    unittest.main()
