"""prodbySSJBeatzz titles: monthly main artist + tag-backed second artist, year by slot."""
import calendar
from datetime import date
import hashlib
import re

from core.beat_latin_seo import normalized
from core.beat_names import clean_name
from core.beat_schema import instant

MODE = 'ssj_v1'
TOKENS = ('{main}', '{second}', '{year}', '{artist_tags}', '{hashtags}')
REQUIRED = ('{main}', '{second}', '{year}')
EXTRA_FIELDS = ('main_rotation', 'test_start')
# Second-artist roster in the order the channel plan lists it, with BeatStars tag aliases.
ARTISTS = (
    ('Juice WRLD', ('juice wrld', 'juicewrld')),
    ('Polo G', ('polo g', 'polog')),
    ('Iann Dior', ('iann dior', 'ianndior')),
    ('The Kid Laroi', ('the kid laroi', 'thekidlaroi', 'kid laroi', 'laroi')),
    ('Scorey', ('scorey',)),
    ('Lil Tjay', ('lil tjay', 'liltjay')),
    ('Toosii', ('toosii',)),
)
NAMES = tuple(name for name, _ in ARTISTS)
YEARS = (' 2026', '', ' 2027', '')
TAG_BUDGET = 450


def validate(profile):
    rotation = profile.get('main_rotation')
    if (type(rotation) is not list or not rotation or len(rotation) > len(NAMES)
            or any(name not in NAMES for name in rotation) or len(set(rotation)) != len(rotation)):
        raise ValueError('ssj_main_rotation_invalid')
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


def _artist_in(tag):
    tag = normalized(tag)
    for name, aliases in ARTISTS:
        if any(tag in (a, a + ' type beat', 'type beat ' + a, a + ' beat', 'free ' + a + ' type beat')
               for a in aliases):
            return name
    return None


def second_artist(track, main):
    """(name, source): first title artist found in the beat's real tags, else stable rotation."""
    for tag in track['tags']:
        name = _artist_in(tag)
        if name and name != main:
            return name, 'tags'
    others = [name for name in NAMES if name != main]
    seed = int(hashlib.sha256(f'{MODE}:{track["id"]}'.encode()).hexdigest()[:8], 16)
    return others[seed % len(others)], 'rotation'


def plan(track, profile, slot):
    day = instant(slot).date()
    start = _start(profile)
    month = test_month(start, day)
    rotation = profile['main_rotation']
    main = rotation[(month - 1) % len(rotation)]
    second, source = second_artist(track, main)
    return {'main': main, 'second': second, 'second_source': source,
            'year': year_for(start, day), 'test_month': month, 'publication_day': day.isoformat()}


def _title(track, profile, chosen):
    template = (profile['title_template'].replace('{main}', chosen['main'])
                .replace('{second}', chosen['second']).replace('{year}', chosen['year']))
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    return template.replace('{name}', clean_name(track['title'])[:budget].rstrip())


def _tags(profile, main, second):
    a, b = main.lower(), second.lower()
    wanted = [f'{a} type beat', f'{b} type beat', f'{a} x {b} type beat', f'free {a} type beat',
              f'free {b} type beat'] + list(profile['tags'])
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
    names = '|'.join(re.escape(n) for n in NAMES)
    pattern = re.escape(profile['title_template'])
    for token, group in (('{main}', f'(?P<main>{names})'), ('{second}', f'(?P<second>{names})'),
                         ('{year}', r'(?P<year>(?: \d{4})?)'), ('{name}', '.*')):
        pattern = pattern.replace(re.escape(token), group, 1)
    match = re.fullmatch(pattern, title, re.S)
    if not match:
        raise ValueError('ssj_title_unparsed')
    return match.group('main'), match.group('second'), match.group('year')


def artist_tags(main, second):
    a, b = main.lower(), second.lower()
    rows = []
    for x, y in ((a, b), (b, a)):
        rows += [f'{x} type beat', f'free {x} type beat', f'{x} type beat free', f'{x} instrumental',
                 f'{x} x {y} type beat', f'melodic {x} type beat', f'sad {x} type beat',
                 f'{x} style beat', f'{x} beat', f'{x} type instrumental']
    rows += ['melodic type beat', 'sad melodic type beat', 'emotional type beat', 'free type beat',
             'melodic rap instrumental', 'guitar type beat']
    return ', '.join(dict.fromkeys(rows))


def hashtags(main, second):
    tag = lambda name: '#' + re.sub(r'[^A-Za-z0-9]', '', name) + 'TypeBeat'
    return ' '.join((tag(main), tag(second), '#TypeBeat', '#FreeTypeBeat', '#MelodicTypeBeat',
                     '#prodbySSJBeatzz'))


def description(profile, track, option):
    main, second, year = _parse_title(profile, option['title'])
    return (profile['description'].replace('{main}', main).replace('{second}', second)
            .replace('{year}', year).replace('{artist_tags}', artist_tags(main, second))
            .replace('{hashtags}', hashtags(main, second)))
