#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aplica migración kind en library.db del repo (cerrar la app antes)."""

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import library


def main() -> int:
    db = os.path.join(ROOT, library.DB_PATH)
    conn = library._connect(db)
    conn.close()
    c = sqlite3.connect(db)
    cols = [r[1] for r in c.execute("PRAGMA table_info(beats)")]
    empty = c.execute(
        "SELECT COUNT(*) FROM beats WHERE kind IS NULL OR kind = ''").fetchone()[0]
    c.close()
    print("kind column present:", "kind" in cols)
    print("empty kind rows:", empty)
    if "kind" not in cols or empty:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
