"""All Type Beats tests and optional offline Loopkits/manual Beats regressions."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import unittest

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--worker-only', action='store_true', help='No PyQt tests or desktop regressions')
    args = parser.parse_args()
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    suite = unittest.TestSuite()
    for path in sorted((root / 'tests').glob('test_beat_*.py')):
        if args.worker_only and path.name in ('test_beat_panel.py', 'test_beat_panel_cloud.py'):
            continue
        suite.addTests(unittest.defaultTestLoader.discover(str(root / 'tests'), pattern=path.name))
    success = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    if not args.worker_only:
        scripts = sorted((root / 'scripts').glob('smoke_kit_*.py'))
        scripts += [root / 'scripts' / ('smoke_' + name + '.py') for name in
                    ('library_kind', 'uploads_migration', 'publish_at', 'sections')]
        for path in scripts:
            try:
                result = subprocess.run([sys.executable, str(path)], cwd=root, timeout=180)
                success = result.returncode == 0 and success
            except subprocess.TimeoutExpired:
                print(path.name + ': timeout', flush=True)
                success = False
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
