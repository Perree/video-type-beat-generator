"""Weighted MurrayBeats title rotation by Buenos Aires publication date."""
from datetime import date

from core.beat_names import clean_name
from core.beat_schema import instant


MODE = 'murray_reggaeton_v1'
EXPIRING_MODE = 'murray_reggaeton_v2'
TOKENS = ()
START = date(2026, 11, 14)
YEARS = (' 2026', '', '', ' 2027', '', '')


def title(track, profile, slot):
    publication_day = instant(slot).date()
    offset = (publication_day - START).days
    year = YEARS[offset % len(YEARS)] if offset >= 0 else ''
    if profile['title_mode'] == EXPIRING_MODE and publication_day.year > 2026 and year == ' 2026':
        year = ''
    template = profile['title_template'].replace(' TYPE BEAT - ', f' TYPE BEAT{year} - ', 1)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    return template.replace('{name}', clean_name(track['title'])[:budget].rstrip())


def description(profile, track, option):
    return profile['description']
