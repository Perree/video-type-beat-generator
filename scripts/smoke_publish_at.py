#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: conversión local -> publishAt UTC (sin red ni Qt)."""

import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.publish_at import local_to_youtube_publish_at


def main() -> int:
    off = local_to_youtube_publish_at(False, datetime(2026, 10, 5, 15, 0))
    if off is not None:
        print("FAIL: programar apagado debe ser None, got", off)
        return 1

    buenos_aires = ZoneInfo('America/Argentina/Buenos_Aires')
    on = local_to_youtube_publish_at(
        True, datetime(2026, 10, 5, 15, 0, 0), tz=buenos_aires)
    expected = '2026-10-05T18:00:00Z'
    if on != expected:
        print("FAIL: UTC esperado", expected, "got", on)
        return 1
    if not on.endswith('Z'):
        print("FAIL: debe terminar en Z:", on)
        return 1

    print("OK smoke_publish_at")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
