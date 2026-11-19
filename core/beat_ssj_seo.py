"""prodbySSJBeatzz titles: monthly main artist, alternating solo/duo titles, year by slot.

The second artist never comes from the beat's tags: it follows the channel's fixed
rotation so solo vs. duo titles (and each partner) can be compared over time.
"""
import calendar
from datetime import date
from math import lcm
import re

from core.beat_names import clean_name
from core.beat_schema import instant
from core.beat_seo_report import text

MODE = 'ssj_v1'
TOKENS = ('{main}', '{second}', '{year}', '{artist_tags}', '{hashtags}')
REQUIRED = ('{main}', '{second}', '{year}')
DUO = ' x {second}'
EXTRA_FIELDS = ('main_rotation', 'test_start', 'second_rotation', 'second_every')
YEARS = (' 2026', '', ' 2027', '')
TAG_BUDGET = 450
MAX_EVERY = 6


def _names(value, error, *, allow_empty=False):
    if type(value) is not list or (not value and not allow_empty) or len(value) > 12:
        raise ValueError(error)
    try:
        names = [text(name, 40) for name in value]
    except ValueError:
        raise ValueError(error) from None
    if any('"' in name for name in names) or len({n.casefold() for n in names}) != len(names):
        raise ValueError(error)
    return names


def validate(profile):
    main = _names(profile.get('main_rotation'), 'ssj_main_rotation_invalid')
    second = _names(profile.get('second_rotation'), 'ssj_second_rotation_invalid')
    every = profile.get('second_every')
    if (type(every) is not dict or any(name not in second for name in every)
            or any(type(v) is not int or not 1 <= v <= MAX_EVERY for v in every.values())):
        raise ValueError('ssj_second_every_invalid')
    if DUO not in profile.get('title_template', ''):
        raise ValueError('seo_title_mode_invalid')
    # Every month needs at least one partner that is not its own main artist.
    if any(not _partners(profile, name) for name in main):
        raise ValueError('ssj_second_rotation_invalid')
    _start(profile)


def _start(profile):
    value = profile.get('test_start')
    if type(value) is not str or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        raise ValueError('ssj_test_start_invalid')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValueError('ssj_test_start_invalid') from None


def test_month(start, day):
    """1-based test month: month N runs from the (N-1)th monthly anniversary of start."""
    months = (day.year - start.year) * 12 + day.month - start.month
    anniversary = min(start.day, calendar.monthrange(day.year, day.month)[1])
    if day.day < anniversary:
        months -= 1
    return max(0, months) + 1


def year_for(start, day):
    offset = (day - start).days
    year = YEARS[offset % len(YEARS)] if offset >= 0 else ''
    # Never advertise a year that is already over on the publication date.
    return '' if year and int(year) < day.year else year


def is_duo(index):
    """S D S D / D S D S: alternates daily and gives both variants every year value."""
    return (index + index // len(YEARS)) % 2 == 1


def duo_count(index):
    """Number of duo slots before slot `index`."""
    period = 2 * len(YEARS)
    return index // period * len(YEARS) + sum(is_duo(i) for i in range(index - index % period, index))


def _partners(profile, main):
    """Second-artist rotation for a month: the main artist's place goes to the other mains."""
    stand_ins = [n for n in profile['main_rotation']
                 if n != main and n not in profile['second_rotation']]
    result = []
    for name in profile['second_rotation']:
        if name == main:
            if stand_ins:
                result.append(stand_ins.pop(0))
        else:
            result.append(name)
    return result


def partner_cycle(profile, main):
    """One full cycle: an artist with second_every N appears in 1 of every N rounds."""
    every = profile['second_every']
    partners = _partners(profile, main)
    rounds = lcm(*(every.get(n, 1) for n in partners))
    return [n for r in range(rounds) for n in partners if r % every.get(n, 1) == 0]


def plan(track, profile, slot):
    day = instant(slot).date()
    start = _start(profile)
    month = test_month(start, day)
    main = profile['main_rotation'][(month - 1) % len(profile['main_rotation'])]
    index = max(0, (day - start).days)
    second = None
    if is_duo(index):
        cycle = partner_cycle(profile, main)
        second = cycle[duo_count(index) % len(cycle)]
    return {'variant': 'duo' if second else 'solo', 'main': main, 'second': second,
            'year': year_for(start, day), 'test_month': month, 'slot_index': index,
            'publication_day': day.isoformat()}


def _template(profile, main, second, year):
    template = profile['title_template']
    template = template.replace('{second}', second) if second else template.replace(DUO, '', 1)
    return template.replace('{main}', main).replace('{year}', year)


def _title(track, profile, chosen):
    template = _template(profile, chosen['main'], chosen['second'], chosen['year'])
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    return template.replace('{name}', clean_name(track['title'])[:budget].rstrip())


def _artists(main, second):
    return [main] + ([second] if second else [])


def _tags(profile, main, second):
    names = [n.lower() for n in _artists(main, second)]
    wanted = [f'{n} type beat' for n in names]
    if second:
        wanted.append(f'{names[0]} x {names[1]} type beat')
    wanted += [f'free {n} type beat' for n in names] + list(profile['tags'])
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
    chosen = plan(track, profile, slot)
    title = _title(track, profile, chosen)
    tags = _tags(profile, chosen['main'], chosen['second'])
    return [{'title': title, 'tags': tags[i:] + tags[:i]} for i in range(max(1, len(tags)))]


def experiment(track, profile, slot):
    return dict(plan(track, profile, slot), version=MODE)


def _parse_title(profile, title):
    names = '|'.join(re.escape(n) for n in sorted(
        set(profile['main_rotation']) | set(profile['second_rotation']), key=len, reverse=True))
    pattern = re.escape(profile['title_template'])
    for token, group in ((re.escape(DUO), f'(?: x (?P<second>{names}))?'),
                         (re.escape('{main}'), f'(?P<main>{names})'),
                         (re.escape('{year}'), r'(?P<year>(?: \d{4})?)'), (re.escape('{name}'), '.*')):
        pattern = pattern.replace(token, group, 1)
    match = re.fullmatch(pattern, title, re.S)
    if not match:
        raise ValueError('ssj_title_unparsed')
    return match.group('main'), match.group('second'), match.group('year')


def artist_tags(main, second=None):
    names = [n.lower() for n in _artists(main, second)]
    rows = []
    for x in names:
        rows += [f'{x} type beat', f'free {x} type beat', f'{x} type beat free', f'{x} instrumental',
                 f'melodic {x} type beat', f'sad {x} type beat', f'{x} style beat', f'{x} beat',
                 f'{x} type instrumental']
    if second:
        rows += [f'{names[0]} x {names[1]} type beat', f'{names[1]} x {names[0]} type beat']
    rows += ['melodic type beat', 'sad melodic type beat', 'emotional type beat', 'free type beat',
             'melodic rap instrumental', 'guitar type beat']
    return ', '.join(dict.fromkeys(rows))


def hashtags(main, second=None):
    tag = lambda name: '#' + re.sub(r'[^A-Za-z0-9]', '', name) + 'TypeBeat'
    return ' '.join([tag(n) for n in _artists(main, second)]
                    + ['#TypeBeat', '#FreeTypeBeat', '#MelodicTypeBeat', '#prodbySSJBeatzz'])


def description(profile, track, option):
    main, second, year = _parse_title(profile, option['title'])
    value = profile['description']
    # The description's first line mirrors the title's artist variant.
    if not second:
        value = value.replace(DUO, '', 1)
    return (value.replace('{main}', main).replace('{second}', second or '')
            .replace('{year}', year).replace('{artist_tags}', artist_tags(main, second))
            .replace('{hashtags}', hashtags(main, second)))
