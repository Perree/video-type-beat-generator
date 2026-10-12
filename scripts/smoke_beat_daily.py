"""Offline full daily pipeline: public catalog, Dropbox, HLS, FFmpeg, YouTube."""
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_beat_daily.py')
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
