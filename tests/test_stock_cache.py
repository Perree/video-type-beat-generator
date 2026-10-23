import json
import os
import subprocess
import tempfile
import time
import unittest

from core import manual_render as mr
from core.ffmpeg_util import get_media_duration, resolve_tool
from core.stock_cache import StockCache


def touch(path, size=10):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"x" * size)
    return path


class CacheLogicTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = os.path.join(self.tmp.name, "cache")

    def tearDown(self):
        self.tmp.cleanup()

    def test_key_changes_when_source_changes(self):
        src = touch(os.path.join(self.tmp.name, "v.mp4"), 10)
        cache = StockCache(self.dir)
        first = cache.key(src)
        self.assertEqual(first, cache.key(src))
        touch(src, 20)
        self.assertNotEqual(first, cache.key(src))

    def test_prune_removes_least_recently_used_first(self):
        cache = StockCache(self.dir, max_bytes=25)
        old = touch(os.path.join(self.dir, "a.mp4"), 10)
        mid = touch(os.path.join(self.dir, "b.mp4"), 10)
        new = touch(os.path.join(self.dir, "c.mp4"), 10)
        now = time.time()
        for i, path in enumerate((old, mid, new)):
            os.utime(path, (now - 100 + i, now - 100 + i))
        self.assertEqual(cache.prune(keep={old}), 1)  # «old» se protege: cae el siguiente
        self.assertTrue(os.path.exists(old))
        self.assertFalse(os.path.exists(mid))
        self.assertTrue(os.path.exists(new))

    def test_settings_cache_size(self):
        path = os.path.join(self.tmp.name, "mm.json")
        self.assertEqual(mr.load_settings(path)["cache_max_gb"], 5)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"cache_max_gb": "basura"}, f)
        self.assertEqual(mr.load_settings(path)["cache_max_gb"], 5)


@unittest.skipUnless(resolve_tool("ffmpeg") and resolve_tool("ffprobe"), "requiere FFmpeg")
class CacheRenderTests(unittest.TestCase):
    def test_cache_built_once_and_reused_with_exact_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            ff = resolve_tool("ffmpeg")
            src = os.path.join(tmp, "stock.mp4")
            subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=960x540:rate=25:duration=1.3",
                            src], check=True)
            cache = StockCache(os.path.join(tmp, "cache"))
            tools = mr.Tools(cache=cache)
            first = tools.cached_stock(src)
            self.assertEqual(len(cache.entries()), 1)
            stamp = os.path.getmtime(first)
            self.assertEqual(tools.cached_stock(src), first)  # reusada, no se vuelve a crear
            self.assertEqual(len(cache.entries()), 1)
            self.assertGreaterEqual(os.path.getmtime(first), stamp)
            beat = os.path.join(tmp, "beat.mp3")
            subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=4", beat], check=True)
            result = mr.render_beat(beat, mr.MODE_VIDEO, src, "T", os.path.join(tmp, "out"), tools)
            self.assertAlmostEqual(get_media_duration(result["video"]), 4.0, delta=1 / 30 + 0.02)
            check = subprocess.run([ff, "-v", "error", "-i", result["video"], "-f", "null", "-"],
                                   capture_output=True, text=True)
            self.assertEqual(check.stderr.strip(), "")

    def test_without_cache_still_renders(self):
        with tempfile.TemporaryDirectory() as tmp:
            ff = resolve_tool("ffmpeg")
            src = os.path.join(tmp, "stock.mp4")
            subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25:duration=1",
                            src], check=True)
            beat = os.path.join(tmp, "beat.mp3")
            subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=2", beat], check=True)
            tools = mr.Tools(cache=False)
            self.assertIsNone(tools.cached_stock(src))
            result = mr.render_beat(beat, mr.MODE_VIDEO, src, "T", os.path.join(tmp, "out"), tools)
            self.assertAlmostEqual(get_media_duration(result["video"]), 2.0, delta=0.1)

    def test_broken_stock_falls_back_to_error_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = touch(os.path.join(tmp, "roto.mp4"), 100)
            tools = mr.Tools(cache=StockCache(os.path.join(tmp, "cache")))
            self.assertIsNone(tools.cached_stock(bad))  # la caché falla → se usa el método de siempre
            self.assertEqual(os.listdir(os.path.join(tmp, "cache")), [])  # sin .part olvidados


if __name__ == "__main__":
    unittest.main()
