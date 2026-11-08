"""Opt-in, separate clip pools rotated by publication slot, including retries."""
from datetime import timedelta
import math


def validate(groups):
    if type(groups) is not list or not 1 <= len(groups) <= 12:
        raise ValueError('invalid_video_groups')
    names = set()
    for group in groups:
        if type(group) is not dict or set(group) != {'name', 'folder', 'min_seconds', 'max_seconds'}:
            raise ValueError('invalid_video_groups')
        if (type(group['name']) is not str or not group['name'].strip()
                or len(group['name']) > 80 or group['name'] in names
                or type(group['folder']) is not str or not group['folder'].strip()
                or len(group['folder']) > 1000 or any(ord(c) < 32 for c in group['folder'])):
            raise ValueError('invalid_video_groups')
        names.add(group['name'])
        lo, hi = group['min_seconds'], group['max_seconds']
        if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (lo, hi))
                or not .5 <= lo <= hi <= 30 or math.ceil(lo * 30) > math.floor(hi * 30)):
            raise ValueError('invalid_video_groups')


def for_job(spec, channel, job):
    groups = spec.get('video_groups')
    if groups is None:
        return spec
    # An interval calendar gives true A/B/C rotation regardless of which beat is
    # selected, skipped upload runs, or the beat's repeat cycle.
    from core.beat_interval import settings
    from core.beat_schema import instant
    interval = settings(channel)
    if interval is None or spec['mode'] != 'video':
        raise ValueError('video_groups_require_interval_video')
    days, anchor = interval
    slot = instant(job['slot'])
    delta = slot - anchor
    step = timedelta(days=days)
    if delta < timedelta(0) or delta % step:
        raise ValueError('video_group_slot_off_schedule')
    group = groups[(delta // step) % len(groups)]
    return dict(spec, videos_folder=group['folder'], clip_min_seconds=group['min_seconds'],
                clip_max_seconds=group['max_seconds'], video_group=group['name'])
