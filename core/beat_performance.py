"""Validated channel report -> bounded rank score and reproducible 70/20/10."""
import hashlib
import math
import random
from core.beat_seo_report import parse_report
from core.beat_seo import digest


def ranks(values):
    """Percentile ranks with average ties; equal values carry neutral evidence."""
    ordered = sorted(values)
    if len(set(ordered)) <= 1:
        return {value: 50.0 for value in ordered}
    return {value: 100 * (ordered.index(value) + len(ordered) - 1
                         - ordered[::-1].index(value)) / (2 * (len(ordered) - 1))
            for value in set(ordered)}


def performance(payload, channel, tracks, now):
    if payload is None:
        return {}, None
    try:
        report = parse_report(payload, channel, now.isoformat())
    except ValueError:
        return {}, None
    rows = report['keywords']
    normalized = {key: ranks([row[key] for row in rows])
                  for key in ('views', 'ctr', 'average_view_percentage')}
    scores = {row['tag'].casefold(): sum(weight * normalized[key][row[key]]
              for key, weight in (('views', .5), ('ctr', .3), ('average_view_percentage', .2)))
              for row in rows}
    result = {}
    for track in tracks:
        raw_tags = track.get('tags', [])
        if type(raw_tags) is not list or any(type(tag) is not str for tag in raw_tags):
            continue
        tags = {tag.casefold() for tag in raw_tags}
        matches = [scores[tag] for tag in sorted(tags) if tag in scores]
        if matches:
            result[track['id']] = sum(matches) / len(matches)
    return result, digest(report)


def bucket_sequence(seed, channel, block):
    # Seven/two/one in every block of ten, persisted via reservation count.
    value = hashlib.sha256(repr((seed, channel, block)).encode()).hexdigest()
    sequence = ['top'] * 7 + ['middle'] * 2 + ['remaining']
    random.Random(value).shuffle(sequence)
    return sequence


def choose(available, catalog_ids, scores, history, channel, seed, lru):
    if not set(catalog_ids) <= scores.keys():
        return min(available, key=lru), 'lru'
    ordered = sorted(catalog_ids, key=lambda tid: (-scores[tid], tid))
    width = math.ceil(len(ordered) / 3)
    groups = dict(top=ordered[:width], middle=ordered[width:2 * width],
                  remaining=ordered[2 * width:])
    ordinal = sum(row['cycle'] > 1 and row['status'] != 'cancelled' for row in history)
    bucket = bucket_sequence(seed, channel, ordinal // 10)[ordinal % 10]
    candidates = [tid for tid in available if tid in groups[bucket]]
    if not candidates:
        return min(available, key=lru), 'lru'
    return min(candidates, key=lambda tid: (-scores[tid], lru(tid))), bucket
