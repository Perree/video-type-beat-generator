"""Weighted MurrayBeats title rotation by Buenos Aires publication date."""
from datetime import date

from core.beat_names import clean_name
from core.beat_schema import instant


MODE = 'murray_reggaeton_v1'
TOKENS = ()
START = date(2026, 11, 14)
YEARS = (' 2026', '', '', ' 2027', '', '')


def title(track, profile, slot):
    offset = (instant(slot).date() - START).days
    year = YEARS[offset % len(YEARS)] if offset >= 0 else ''
    template = profile['title_template'].replace(' TYPE BEAT - ', f' TYPE BEAT{year} - ', 1)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    return template.replace('{name}', clean_name(track['title'])[:budget].rstrip())


def description(profile, track, option):
    return profile['description']
