"""Stable per-slot visual alternation for Type Beats only."""
from core.beat_schema import instant
from core.beat_visual import options
from datetime import date


def job_options(channel, job):
    spec = options(channel)
    if spec['mode'] != 'alternate':
        return spec
    stored = job.get('visual_mode_snapshot')
    if stored is not None:
        if stored not in ('image', 'video'):
            raise ValueError('invalid_visual_mode_snapshot')
        spec['mode'] = stored
        return spec
    slot = instant(job['slot'])
    slots = sorted((s['weekday'], s['hour'], s['minute']) for s in channel['slots'])
    position = slots.index((slot.weekday(), slot.hour, slot.minute))
    week = (slot.date().toordinal() - slot.weekday() - date(1970, 1, 5).toordinal()) // 7
    spec['mode'] = 'image' if (week * len(slots) + position) % 2 == 0 else 'video'
    return spec
