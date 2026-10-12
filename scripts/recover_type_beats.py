"""Read-only by default: reconcile a known, verified upload receipt."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.beat_recover_cli import main

if __name__ == '__main__':
    raise SystemExit(main())
