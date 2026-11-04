"""Calendar-day cadence anchored to a fixed Buenos Aires publication time."""
from datetime import timedelta


def settings(channel):
    from core.beat_schema import instant
    value = channel.get('interval_schedule')
    if 'interval_schedule' not in channel:
        return None
    if (type(value) is not dict or set(value) != {'days', 'anchor'}
            or type(value['days']) is not int or not 1 <= value['days'] <= 30
            or type(value['anchor']) is not str):
        raise ValueError('invalid_interval_schedule')
    anchor = instant(value['anchor'])
    if anchor.second or anchor.microsecond or channel.get('slots') != []:
        raise ValueError('invalid_interval_schedule')
    from core.human_schedule import settings as variation
    if any(variation(channel.get('human_schedule')).values()):
        raise ValueError('interval_schedule_variation_unsupported')
    return value['days'], anchor


def slots(channel, now):
    from core.beat_schema import instant
    days, anchor = settings(channel)
    start = instant(now)
    step = timedelta(days=days)
    index = max(0, (start - anchor) // step + 1)
    value = anchor + index * step
    end = start + timedelta(days=14)
    result = []
    while value <= end:
        result.append(value)
        value += step
    return result
