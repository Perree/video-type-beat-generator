import os
import subprocess
import tempfile
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from core import bulk_queue as bq
from core import channel_profile as cp
from core import manual_render as mr
from core.ffmpeg_util import resolve_tool


def touch(path, data=b"x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)
    return path


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        cp.create(self.root, "A")
        cp.create(self.root, "B")

    def tearDown(self):
        self.tmp.cleanup()

    def entrada(self, channel, name, data=b"x"):
        return touch(os.path.join(self.root, "entrada", channel, name), data)

    def test_scan_takes_loose_audio_only(self):
        a1 = self.entrada("A", "uno.mp3")
        self.entrada("A", "notas.txt")
        self.entrada("A", "bajando.mp3.part")
        self.entrada("A", "hechos/viejo.mp3")
        b1 = self.entrada("B", "dos.wav")
        beats, notes = bq.scan(self.root)
        self.assertEqual([(b["channel"], b["path"]) for b in beats], [("A", a1), ("B", b1)])
        self.assertEqual(notes, [])

    def test_scan_warns_channel_without_profile_and_online_only(self):
        self.entrada("Fantasma", "x.mp3")
        remote = self.entrada("A", "remoto.mp3")
        with mock.patch.object(cp, "online_only", side_effect=lambda p: p == remote):
            beats, notes = bq.scan(self.root)
        self.assertEqual(beats, [])
        self.assertTrue(any("Fantasma" in n and "sin perfil" in n for n in notes))
        self.assertTrue(any("sin bajar de Dropbox" in n for n in notes))

    def test_settled_skips_files_that_change(self):
        stable = self.entrada("A", "listo.mp3", b"abc")
        growing = self.entrada("A", "copiando.mp3", b"a")
        beats = [{"channel": "A", "path": stable}, {"channel": "A", "path": growing}]
        calls = {"n": 0}

        def fake_stat(path):
            calls["n"] += 1
            size = os.path.getsize(path) + (calls["n"] if path == growing else 0)
            return SimpleNamespace(st_size=size, st_mtime=1.0)

        ready, busy = bq.settled(beats, wait=1, sleep=lambda s: None, stat=fake_stat)
        self.assertEqual([b["path"] for b in ready], [stable])
        self.assertEqual([b["path"] for b in busy], [growing])

    def test_mark_done_never_overwrites(self):
        self.entrada("A", "hechos/beat.mp3")
        moved = bq.mark_done(self.root, "A", self.entrada("A", "beat.mp3"))
        self.assertEqual(os.path.basename(moved), "beat (2).mp3")
        self.assertFalse(os.path.exists(os.path.join(self.root, "entrada", "A", "beat.mp3")))

    def test_channel_without_backgrounds_logs_errors_and_keeps_beats(self):
        beat = self.entrada("A", "uno.mp3")
        summary = bq.run_bulk(self.root, os.path.join(self.root, "out"), [{"channel": "A", "path": beat}],
                              tools=object())
        self.assertEqual(summary["A"]["ok"], 0)
        self.assertTrue(os.path.exists(beat))
        with open(os.path.join(self.root, "entrada", "A", "errores.txt"), encoding="utf-8") as f:
            self.assertIn("uno.mp3: No hay imágenes", f.read())


@unittest.skipUnless(resolve_tool("ffmpeg") and resolve_tool("ffprobe"), "requiere FFmpeg")
class BulkRenderTests(unittest.TestCase):
    def test_two_channels_each_with_its_style_and_beats_move_to_done(self):
        with tempfile.TemporaryDirectory() as root:
            ff = resolve_tool("ffmpeg")
            from PIL import Image
            for channel, color, template in (("Sad", (20, 20, 90), "{name} Sad Type Beat"),
                                             ("Rage", (200, 0, 0), "[RAGE] {name}")):
                cp.create(root, channel)
                cp.save(root, channel, dict(cp.load(root, channel), titulo=template))
                Image.new("RGB", (640, 360), color).save(os.path.join(root, "canales", channel, "fondos", "bg.png"))
                beat = os.path.join(root, "entrada", channel, "Night 140bpm.mp3")
                subprocess.run([ff, "-v", "error", "-y", "-f", "lavfi", "-i", "sine=duration=2", beat], check=True)
            beats, _ = bq.scan(root)
            out = os.path.join(root, "out")
            summary = bq.run_bulk(root, out, beats, titles={beats[1]["path"]: "A mano"},
                                  today=datetime(2026, 3, 4))
            self.assertEqual({c: e["ok"] for c, e in summary.items()}, {"Rage": 1, "Sad": 1})
            day = os.path.join(out, "2026-03-04")
            self.assertEqual(os.listdir(os.path.join(day, "Rage")), ["[RAGE] Night"])
            self.assertEqual(os.listdir(os.path.join(day, "Sad")), ["A mano"])
            self.assertEqual(bq.scan(root)[0], [])  # todo pasó a hechos/
            self.assertTrue(os.path.exists(os.path.join(root, "entrada", "Sad", "hechos", "Night 140bpm.mp3")))
            with open(os.path.join(day, mr.PENDING_CSV), encoding="utf-8-sig") as f:
                self.assertEqual(len(f.read().strip().splitlines()), 3)


class BulkPanelTests(unittest.TestCase):
    def test_scan_shows_rows_and_edits_titles(self):
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as base:
            local = os.path.join(base, "local")
            cp.create(local, "Canal")
            touch(os.path.join(local, "entrada", "Canal", "uno 150bpm.mp3"))
            touch(os.path.join(local, "entrada", "Fantasma", "x.mp3"))
            from core.manual_tab import ManualTab
            tab = ManualTab(settings_path=os.path.join(base, "mm.json"), local_root=local,
                            legacy_root=os.path.join(base, "legacy"))
            tab.setCurrentWidget(tab.bulk_panel)  # entrar a la subpestaña revisa las carpetas
            panel = tab.bulk_panel
            self.assertEqual(panel.table.rowCount(), 1)
            self.assertEqual(panel.table.item(0, 0).text(), "Canal")
            self.assertTrue(panel.btn_generate.isEnabled())
            self.assertIn("Fantasma", panel.notes.text())
            panel.table.item(0, 2).setText("Otro título")
            self.assertEqual(list(panel.title_overrides.values()), ["Otro título"])
            self.assertIn("1 títulos editados", panel.count_label.text())
            tab.deleteLater()
            app.processEvents()


if __name__ == "__main__":
    unittest.main()
