#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: filtrado de canales por section (sin Qt)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.sections import (
    DEFAULT_SECTION,
    SECTION_BEATS,
    SECTION_LOOP_KITS,
    SECTION_PERSONAL,
    channel_section,
    filter_channels_by_section,
)


def main() -> int:
    sample = {
        "canal_beats": {"groups": ["Principal"], "section": SECTION_BEATS},
        "canal_kits": {"groups": ["Principal"], "section": SECTION_LOOP_KITS},
        "canal_personal": {"groups": ["Principal"], "section": SECTION_PERSONAL},
        "legacy": {"groups": ["Principal"]},
    }

    beats_only = filter_channels_by_section(sample, SECTION_BEATS)
    if set(beats_only.keys()) != {"canal_beats", "legacy"}:
        print("FAIL: beats filter", beats_only.keys())
        return 1

    kits_only = filter_channels_by_section(sample, SECTION_LOOP_KITS)
    if set(kits_only.keys()) != {"canal_kits"}:
        print("FAIL: loop_kits filter", kits_only.keys())
        return 1

    if channel_section(sample["legacy"]) != DEFAULT_SECTION:
        print("FAIL: legacy channel should default to beats")
        return 1

    print("OK smoke_sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
