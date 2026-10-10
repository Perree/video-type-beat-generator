#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: métricas opcionales en build_prompt. Sin red."""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import clip_select as cs

FIXTURE = os.path.join(ROOT, 'scripts', 'fixtures', 'transcript_sample.json')
CFG = {'clip_min_s': 20, 'clip_max_s': 60, 'clip_count': 6, 'language': 'es'}
FIXTURE_TITLE = 'Smoke fixture — 5 tips de mezcla que explotaron'


def fail(msg, *extra):
    print("FAIL:", msg, *extra)
    return 1


def main() -> int:
    with open(FIXTURE, encoding='utf-8') as f:
        fx = json.load(f)
    words, duration = fx['words'], fx['duration']

    _, user_plain = cs.build_prompt(words, CFG, duration)
    low = user_plain.lower()
    if 'visualizaciones' in low or 'views' in low:
        return fail("sin métricas no debe mencionar views", user_plain[:200])

    fake = [{'title': FIXTURE_TITLE, 'views': 98765, 'youtube_id': 'fake'}]
    _, user_metrics = cs.build_prompt(words, CFG, duration, channel_metrics=fake)
    if FIXTURE_TITLE not in user_metrics or '98765 visualizaciones' not in user_metrics:
        return fail("con métricas fixture", user_metrics[:400])

    block = cs._metrics_prompt_block([])
    if block:
        return fail("lista vacía no debe generar bloque")

    block = cs._metrics_prompt_block([{'title': '', 'views': 1}])
    if block:
        return fail("título vacío no debe generar bloque")

    print("OK smoke_clip_prompt_metrics")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
