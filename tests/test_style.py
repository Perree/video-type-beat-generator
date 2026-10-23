import os
import subprocess
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt5.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])

from PIL import Image

from core import channel_profile as cp
from core import manual_render as mr
from core import style as st
from core.ffmpeg_util import get_media_duration, resolve_tool
from core.stock_cache import StockCache

TITLE = '[FREE] Juice WRLD Type Beat - "This is for me"'


class StyleLogicTests(unittest.TestCase):
    def test_defaults_presets_and_validation(self):
        for name in st.PRESETS:
            self.assertEqual(st.validate(st.preset(name)), st.preset(name))
        with self.assertRaises(st.StyleError):
            st.validate({"video": {"oscurecer": 200}})
        with self.assertRaises(st.StyleError):
            st.validate({"miniatura": {"desconocido": 1}})
        with self.assertRaises(st.StyleError):
            st.validate({"miniatura": {"color": "rojo"}})

    def test_profile_without_style_keeps_old_look(self):
        self.assertEqual(st.from_profile({"miniatura_con_titulo": True})["miniatura"]["plantilla"], "franja")
        self.assertEqual(st.from_profile({})["miniatura"]["plantilla"], "solo")
        self.assertEqual(st.from_profile({})["video"], st.DEFAULT["video"])

    def test_overlays_flag(self):
        self.assertFalse(st.video_overlays(st.preset("Limpio")))
        self.assertTrue(st.video_overlays(st.preset("Neón")))
        self.assertFalse(st.video_overlays(st.validate({"video": {"encuadre": "difuminado", "zoom": True}})))

    def test_render_sizes_and_layer(self):
        source = Image.new("RGB", (800, 1200), (200, 30, 30))  # vertical: el difuminado se nota
        source.paste((20, 200, 40), (0, 0, 800, 600))  # dos colores: recorte y difuminado difieren
        for name in st.PRESETS:
            style = st.preset(name)
            self.assertEqual(st.render_frame(source, style, TITLE).size, st.FRAME)
            self.assertEqual(st.render_thumbnail(source, style, TITLE).size, st.THUMB)
        blur = st.render_frame(source, st.validate({"video": {"encuadre": "difuminado"}}), TITLE)
        crop = st.render_frame(source, st.preset("Limpio"), TITLE)
        self.assertNotEqual(blur.getpixel((20, 540)), crop.getpixel((20, 540)))
        layer = st.overlay_layer(st.validate({"video": {"oscurecer": 50, "titulo": True}}), TITLE)
        self.assertEqual(layer.mode, "RGBA")
        self.assertGreater(layer.getpixel((5, 5))[3], 100)  # el oscurecido cubre todo

    def test_thumbnail_templates_draw_text(self):
        plain = st.render_thumbnail(Image.new("RGB", st.THUMB, (90, 90, 90)), st.preset("Limpio"), TITLE)
        band = st.render_thumbnail(Image.new("RGB", st.THUMB, (90, 90, 90)), st.preset("Franja oscura"), TITLE)
        self.assertNotEqual(plain.tobytes(), band.tobytes())
        self.assertEqual(band.getpixel((5, st.THUMB[1] - 90)), (15, 15, 20))  # la franja oscura

    def test_profile_validates_style(self):
        with tempfile.TemporaryDirectory() as root:
            cp.create(root, "C")
            saved = cp.save(root, "C", dict(cp.load(root, "C"), estilo={"video": {"zoom": True}}))
            self.assertTrue(saved["estilo"]["video"]["zoom"])
            self.assertEqual(saved["estilo"]["miniatura"]["plantilla"], "solo")
            with self.assertRaises(cp.ProfileError):
                cp.save(root, "C", dict(saved, estilo={"video": {"encuadre": "raro"}}))

    def test_cache_key_keeps_crop_and_separates_blur(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.join(tmp, "v.mp4")
            with open(src, "wb") as f:
                f.write(b"x")
            cache = StockCache(tmp)
            self.assertEqual(cache.key(src), cache.key(src, "recortar"))
            self.assertNotEqual(cache.key(src), cache.key(src, "difuminado"))


@unittest.skipUnless(resolve_tool("ffmpeg") and resolve_tool("ffprobe"), "requiere FFmpeg")
class StyledRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = cls.root = cls.tmp.name
        ff = resolve_tool("ffmpeg")
        cls.beat = os.path.join(root, "beat.mp3")
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=3", cls.beat], check=True)
        cls.image = os.path.join(root, "bg.png")
        Image.new("RGB", (640, 900), (20, 120, 200)).save(cls.image)
        cls.video = os.path.join(root, "stock.mp4")
        subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc=size=480x640:rate=25:duration=1",
                        cls.video], check=True)
        cls.logo = os.path.join(root, "logo.png")
        Image.new("RGBA", (200, 200), (255, 255, 0, 200)).save(cls.logo)
        cls.tools = mr.Tools(cache=StockCache(os.path.join(root, "cache")))

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def render(self, mode, content, style, name):
        result = mr.render_beat(self.beat, mode, content, name, os.path.join(self.root, "out"), self.tools,
                                style=st.validate(style), logo_path=self.logo)
        self.assertAlmostEqual(get_media_duration(result["video"]), 3.0, delta=0.15)
        with Image.open(result["thumbnail"]) as img:
            self.assertEqual(img.size, st.THUMB)
        return result

    def test_image_with_zoom_fade_and_logo(self):
        self.render("image", self.image, {"video": {"zoom": True, "fundido": True, "logo": True},
                                          "miniatura": {"plantilla": "logo"}}, "zoom")

    def test_video_with_overlay_and_blur(self):
        self.render("video", self.video, {"video": {"encuadre": "difuminado", "titulo": True, "oscurecer": 30,
                                                    "fundido": True},
                                          "miniatura": {"plantilla": "grande", "origen": "video"}}, "overlay")

    def test_video_without_overlays_uses_fast_copy(self):
        with mock.patch.object(self.tools, "run", wraps=self.tools.run) as run:
            self.render("video", self.video, {}, "rapido")
        final = run.call_args_list[-1][0][0]
        self.assertIn("copy", final)  # «-c:v copy»: sin recodificar


class StyleEditorTests(unittest.TestCase):
    def test_presets_custom_and_save(self):
        with tempfile.TemporaryDirectory() as root:
            cp.create(root, "C")
            Image.new("RGB", (640, 360), (10, 10, 10)).save(os.path.join(root, "canales", "C", "fondos", "a.png"))
            from core.style_editor import CUSTOM, StyleEditor
            editor = StyleEditor(root, "C")
            self.assertEqual(editor.preset.currentText(), "Limpio")
            editor.preset.setCurrentText("Neón")
            editor._apply_preset(0)
            self.assertTrue(editor.grain.isChecked())
            self.assertIsNotNone(editor.thumb_preview.pixmap())
            editor.darken.setValue(10)  # tocar un control → «Personalizado»
            self.assertEqual(editor.preset.currentText(), CUSTOM)
            editor.template.setCurrentIndex(editor.template.findData("franja"))
            editor.save()
            saved = cp.load(root, "C")
            self.assertEqual(saved["estilo"]["video"]["oscurecer"], 10)
            self.assertTrue(saved["miniatura_con_titulo"])
            editor.deleteLater()


if __name__ == "__main__":
    unittest.main()
