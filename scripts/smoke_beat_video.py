"""Offline Phase 4 HLS + Dropbox + FFmpeg smoke suite."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
suite = unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / 'tests'),
                                          pattern='test_beat_video.py')
suite.addTests(unittest.defaultTestLoader.discover(str(Path(__file__).resolve().parents[1] / 'tests'),
                                                 pattern='test_beat_montage.py'))
if __name__ == '__main__':
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
