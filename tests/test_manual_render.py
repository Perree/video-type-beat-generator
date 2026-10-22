import json
import os
import random
import subprocess
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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

    def test_channels_merge_config_and_folders(self):
        touch(os.path.join(self.root, "config", "app_config.json"),
              json.dumps({"channels": {"Uno": {"groups": ["Principal", "Dark"]}}}).encode())
        os.makedirs(os.path.join(self.root, "images", "Uno", "Extra"))
        os.makedirs(os.path.join(self.root, "videos", "Dos", "Principal"))
        self.assertEqual(mr.channels(self.root),
                         {"Dos": ["Principal"], "Uno": ["Principal", "Dark", "Extra"]})

    def test_counts_by_kind(self):
        touch(os.path.join(self.root, "images", "C", "G", "a.jfif"))
        touch(os.path.join(self.root, "images", "C", "G", "notes.txt"))
        touch(os.path.join(self.root, "videos", "C", "G", "v.mp4"))
        touch(os.path.join(self.root, "miniaturas", "C", "G", "t.png"))
        self.assertEqual(mr.counts("C", "G", self.root), {"image": 1, "video": 1, "thumbnail": 1})

    def test_rotation_uses_all_before_repeating(self):
        rot = mr.Rotation(["a", "b", "c"], random.Random(1))
        first = [rot.next() for _ in range(3)]
        self.assertEqual(sorted(first), ["a", "b", "c"])
        self.assertIn(rot.next(), ["a", "b", "c"])
        self.assertIsNone(mr.Rotation([]).next())

    def test_unique_base_does_not_overwrite(self):
        touch(os.path.join(self.root, "x.mp4"))
        touch(os.path.join(self.root, "x (2).jpg"))
        self.assertEqual(mr.unique_base(self.root, "x"), "x (3)")

    def test_title_template_from_config(self):
        touch(os.path.join(self.root, "config", "app_config.json"), json.dumps(
            {"name_template": "G {name}", "channels": {"A": {"title_template": "A {name}"}, "B": {}}}).encode())
        self.assertEqual(mr.title_template("A", self.root), "A {name}")
        self.assertEqual(mr.title_template("B", self.root), "G {name}")

    def test_batch_without_content_explains_folder(self):
        with self.assertRaises(mr.ManualError) as ctx:
            mr.run_batch(["b.mp3"], "C", "G", mr.MODE_VIDEO, "{name}", self.root, root=self.root,
                         tools=object())
        self.assertIn("videos", str(ctx.exception))

    def test_beat_info_from_filename(self):
        self.assertEqual(mr.beat_info("This is for me - 160bpm - key A Sharp Minor (prod. x)"),
                         (160.0, "A Sharp Minor"))
        self.assertEqual(mr.beat_info("dark 140 BPM key: F#m"), (140.0, "F#m"))
        self.assertEqual(mr.beat_info("sin datos"), (None, None))

    def test_settings_roundtrip(self):
        path = os.path.join(self.root, "config", "manual_mode.json")
        data = mr.load_settings(path)
        self.assertEqual(data["mode"], mr.MODE_IMAGE)
        data["templates"]["C"] = "{name} x"
        mr.save_settings(data, path)
        self.assertEqual(mr.load_settings(path)["templates"], {"C": "{name} x"})


@unittest.skipUnless(resolve_tool("ffmpeg") and resolve_tool("ffprobe"), "requiere FFmpeg")
class ManualRenderTests(unittest.TestCase):
    """Render real y corto con FFmpeg: imagen y video stock."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = cls.root = cls.tmp.name
        ff = resolve_tool("ffmpeg")
        run = lambda *a: subprocess.run([ff, "-v", "error", "-y", *a], check=True)
        cls.beat = os.path.join(root, "beats", "Dark Beat.mp3")
        os.makedirs(os.path.dirname(cls.beat))
        run("-f", "lavfi", "-i", "sine=frequency=440:duration=3", cls.beat)
        os.makedirs(os.path.join(root, "images", "C", "G"))
        from PIL import Image
        Image.new("RGB", (800, 800), (200, 30, 30)).save(os.path.join(root, "images", "C", "G", "bg.jfif"), "JPEG")
        os.makedirs(os.path.join(root, "videos", "C", "G"))
        run("-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=1",
            os.path.join(root, "videos", "C", "G", "stock.mp4"))
        cls.tools = mr.Tools()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def check_outputs(self, results, expected_title):
        self.assertEqual(len(results), 1)
        out = results[0]
        self.assertEqual(os.path.basename(out["video"]), expected_title + ".mp4")
        self.assertAlmostEqual(get_media_duration(out["video"]), 3.0, delta=0.3)
        from PIL import Image
        with Image.open(out["thumbnail"]) as img:
            self.assertEqual(img.size, (1280, 720))
        with open(out["text"], encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith(expected_title))
        self.assertEqual(text.count("Tags:"), 1)
        self.assertFalse(any(name.endswith(".part") for name in os.listdir(os.path.dirname(out["video"]))))

    def test_image_mode(self):
        out_root = os.path.join(self.root, "out-image")
        results, errors = mr.run_batch([self.beat], "C", "G", mr.MODE_IMAGE, "{name} Type Beat", out_root,
                                       title_on_thumbnail=True, root=self.root, tools=self.tools)
        self.assertEqual(errors, [])
        self.check_outputs(results, "Dark Beat Type Beat")
        self.assertEqual(os.path.dirname(results[0]["video"]), os.path.join(out_root, "C"))

    def test_video_mode_loops_short_stock(self):
        out_root = os.path.join(self.root, "out-video")
        results, errors = mr.run_batch([self.beat], "C", "G", mr.MODE_VIDEO, "[FREE] {name}", out_root,
                                       root=self.root, tools=self.tools)
        self.assertEqual(errors, [])
        self.check_outputs(results, "[FREE] Dark Beat")

    def test_cancel_stops_batch(self):
        with self.assertRaises(mr.Cancelled):
            mr.run_batch([self.beat], "C", "G", mr.MODE_IMAGE, "{name}", os.path.join(self.root, "out-c"),
                         root=self.root, tools=self.tools, cancelled=lambda: True)

    def test_bad_audio_is_reported_not_fatal(self):
        bad = touch(os.path.join(self.root, "beats", "roto.mp3"), b"not audio")
        results, errors = mr.run_batch([bad, self.beat], "C", "G", mr.MODE_IMAGE, "{name}",
                                       os.path.join(self.root, "out-bad"), root=self.root, tools=self.tools)
        self.assertEqual(len(results), 1)
        self.assertEqual(errors[0][0], "roto")


class ManualPanelTests(unittest.TestCase):
    def setUp(self):
        from PyQt5.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        root = self.root = self.tmp.name
        touch(os.path.join(root, "images", "Canal", "Principal", "a.jpg"))
        touch(os.path.join(root, "drop", "one.mp3"))
        touch(os.path.join(root, "drop", "more", "two.wav"))
        from core.manual_panel import ManualPanel
        self.panel = ManualPanel(root=root, settings_path=os.path.join(root, "config", "manual_mode.json"))

    def tearDown(self):
        self.panel.deleteLater()
        self.tmp.cleanup()

    def test_drop_folder_adds_audio_once_and_enables_generate(self):
        p = self.panel
        self.assertFalse(p.btn_generate.isEnabled())
        self.assertEqual(p.channel_combo.currentText(), "Canal")
        p.add_paths([os.path.join(self.root, "drop")])
        p.add_paths([os.path.join(self.root, "drop", "one.mp3")])
        self.assertEqual(p.beat_list.count(), 2)
        self.assertTrue(p.btn_generate.isEnabled())
        self.assertIn("1 imágenes", p.content_label.text())
        self.assertIn("one", p.preview_label.text())

    def test_job_uses_selected_options(self):
        p = self.panel
        p.add_paths([os.path.join(self.root, "drop")])
        p.radio_video.setChecked(True)
        p.template_edit.setText("{name} | Free")
        job = p.job()
        self.assertEqual((job["channel"], job["group"], job["mode"], job["template"]),
                         ("Canal", "Principal", mr.MODE_VIDEO, "{name} | Free"))
        self.assertEqual(len(job["beats"]), 2)

    def test_remove_and_clear(self):
        p = self.panel
        p.add_paths([os.path.join(self.root, "drop")])
        p.beat_list.item(0).setSelected(True)
        p._remove_selected()
        self.assertEqual(p.beats[0].endswith("two.wav"), True)
        p.clear_beats()
        self.assertFalse(p.btn_generate.isEnabled())


if __name__ == "__main__":
    unittest.main()
