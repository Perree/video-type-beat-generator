"""ey mat (Juice WRLD) titles: own vs. competitor format A/B, year from the publication day.

Slot index = days since `test_start` (Buenos Aires publication day), so a snapshot
can always be replayed. Even slots use `title_template` (own format), odd slots
`alt_title_template` (competitor format). When two years are valid (Nov–Dec) the
pattern is own/Y, competitor/Y+1, own/Y+1, competitor/Y so both formats get both years.
"""
from datetime import date
import re

from core.beat_names import clean_name
from core.beat_schema import instant
from core.beat_seo_report import text
from core.beat_year import years_for

MODE = 'ey_mat_v1'
TOKENS = ('{year}', '{title}')
REQUIRED = ('{year}',)
EXTRA_FIELDS = ('alt_title_template', 'test_start')
FORMATS = ('own', 'competitor')
YEAR_TAGS = ('juice wrld type beat {year}', 'free juice wrld type beat {year}', 'type beat {year}')
TAG_BUDGET = 450
TEMPLATE_LIMIT = 90
TITLE_LIMIT = 100
_YEAR = re.compile(r'\b20\d{2}\b')


def _start(profile):
    value = profile.get('test_start')
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('ey_mat_test_start_invalid')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError('ey_mat_test_start_invalid') from None


def validate(profile):
    alt = profile.get('alt_title_template')
    if (type(alt) is not str or '{name}' not in alt or '{year}' not in alt
            or alt == profile.get('title_template')):
        raise ValueError('ey_mat_alt_template_invalid')
    try:
        text(alt.replace('{name}', 'x').replace('{year}', 'x'), TEMPLATE_LIMIT)
    except ValueError:
        raise ValueError('ey_mat_alt_template_invalid') from None
    _start(profile)


def _templates(profile):
    return {'own': profile['title_template'], 'competitor': profile['alt_title_template']}


def plan(profile, slot):
    day = instant(slot).date()
    index = max(0, (day - _start(profile)).days)
    years = years_for(day)
    year = years[(index + 1) // 2 % 2] if len(years) > 1 else years[0]
    return {'format': FORMATS[index % 2], 'year': str(year), 'years': [str(y) for y in years],
            'slot_index': index, 'publication_day': day.isoformat()}


def _title(track, profile, chosen):
    template = _templates(profile)[chosen['format']].replace('{year}', chosen['year'])
    budget = TITLE_LIMIT - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    return template.replace('{name}', clean_name(track['title'])[:budget].rstrip())


def _tags(profile, year):
    """Channel tags with every year rewritten to the title's year, plus the year tags."""
    wanted = [_YEAR.sub(year, t) for t in profile['tags']] + [t.format(year=year) for t in YEAR_TAGS]
    bounded, seen = [], set()
    for tag in wanted:
        if tag.casefold() in seen:
            continue
        # Includes YouTube's implicit quotes for tags containing spaces.
        if sum(len(t) + (2 if ' ' in t else 0) + 1 for t in bounded + [tag]) <= TAG_BUDGET:
            bounded.append(tag)
            seen.add(tag.casefold())
    return bounded


def variants(track, profile, slot):
    """Fixed title for the slot; repeats only rotate the tag order."""
    chosen = plan(profile, slot)
    title = _title(track, profile, chosen)
    tags = _tags(profile, chosen['year'])
    return [{'title': title, 'tags': tags[i:] + tags[:i]} for i in range(max(1, len(tags)))]


def experiment(track, profile, slot):
    return dict(plan(profile, slot), version=MODE)


def _parse_title(profile, title):
    for name, template in _templates(profile).items():
        pattern = re.escape(template)
        for token, group in ((re.escape('{year}'), r'(?P<year>\d{4})'), (re.escape('{name}'), '.*')):
            pattern = pattern.replace(token, group, 1)
        match = re.fullmatch(pattern, title, re.S)
        if match:
            return name, match.group('year')
    raise ValueError('ey_mat_title_unparsed')


def description(profile, track, option):
    """{year} and {title} follow the chosen title; {url}/{chapters}/{music_info} are left to the caller."""
    _, year = _parse_title(profile, option['title'])
    return profile['description'].replace('{year}', year).replace('{title}', option['title'])
