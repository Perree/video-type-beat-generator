#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: filtrado de canales por section (sin Qt). Sin section es un error, nunca Beats."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import sections
from core.channel_kind import ChannelKindError
from core.sections import (
    SECTION_BEATS,
    SECTION_LOOP_KITS,
    channel_section,
    filter_channels_by_section,
)


def main() -> int:
    sample = {
        "canal_beats": {"groups": ["Principal"], "section": SECTION_BEATS},
        "canal_kits": {"groups": ["Principal"], "section": SECTION_LOOP_KITS},
        "canal_personal": {"groups": ["Principal"], "section": "personal"},  # legacy: se ignora
    }

    beats_only = filter_channels_by_section(sample, SECTION_BEATS)
    if set(beats_only.keys()) != {"canal_beats"}:
        print("FAIL: beats filter", beats_only.keys())
        return 1

    kits_only = filter_channels_by_section(sample, SECTION_LOOP_KITS)
    if set(kits_only.keys()) != {"canal_kits"}:
        print("FAIL: loop_kits filter", kits_only.keys())
        return 1

    if "canal_personal" in beats_only or "canal_personal" in kits_only:
        print("FAIL: canal legacy personal debe ignorarse")
        return 1

    if hasattr(sections, "DEFAULT_SECTION") or hasattr(sections, "ensure_channel_sections"):
        print("FAIL: no debe quedar un default a beats")
        return 1

    for broken in ({"groups": ["Principal"]}, {"section": "otra"}, {"section": None}, None):
        try:
            channel_section(broken)
        except ChannelKindError:
            pass
        else:
            print("FAIL: un canal sin tipo debe ser un error explícito", broken)
            return 1
    try:
        filter_channels_by_section(dict(sample, legacy={"groups": []}), SECTION_BEATS)
    except ChannelKindError:
        pass
    else:
        print("FAIL: filtrar con un canal sin section debe fallar")
        return 1

    print("OK smoke_sections")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
