"""Seen 3AM (plugg / pluggnb / new jazz / west coast) metadata.

One fixed title like the channel's competitors, `(FREE) plugg x suei type beat {year} - "{name}"`,
with the beat name in lower case and the newest year valid on the publication day (Buenos Aires).
The description credits seen3am plus the collaborators listed on the BeatStars page.
"""
import re

from core.beat_names import clean_name
from core.beat_schema import instant
from core.beat_title import parse_track
from core.beat_year import years_for

MODE = 'seen3am_v1'
TOKENS = ('{year}', '{title}', '{music}', '{producers}')
REQUIRED = ('{year}',)
EXTRA_FIELDS = ()
PRODUCER = 'seen3am'
YEAR_TAGS = ('plugg x suei type beat {year}', 'plugg type beat {year}', 'type beat {year}')
TAG_BUDGET = 450
TITLE_LIMIT = 100
_YEAR = re.compile(r'\b20\d{2}\b')


def validate(profile):
    """Nothing beyond the shared checks: a single title template that contains {year}."""


def plan(profile, slot):
    day = instant(slot).date()
    return {'year': str(max(years_for(day))), 'publication_day': day.isoformat()}


def _title(track, profile, year):
    template = profile['title_template'].replace('{year}', year)
    budget = TITLE_LIMIT - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    return template.replace('{name}', clean_name(track['title']).lower()[:budget].rstrip())


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
    year = plan(profile, slot)['year']
    title = _title(track, profile, year)
    tags = _tags(profile, year)
    return [{'title': title, 'tags': tags[i:] + tags[:i]} for i in range(max(1, len(tags)))]


def experiment(track, profile, slot):
    return dict(plan(profile, slot), version=MODE)


def music(track):
    """«BPM: 122» / «KEY: G♯m», only what BeatStars has."""
    info = parse_track(track)
    return '\n'.join(label + info[key] for label, key in (('BPM: ', 'bpm'), ('KEY: ', 'key')) if info[key])


def producers(track):
    """seen3am first; MatWyre (the same producer on BeatStars) is never listed as a collaborator."""
    own = {PRODUCER, 'matwyre'}
    people = [n for n in track.get('collaborators') or () if n.strip().casefold() not in own]
    return ' x '.join([PRODUCER] + people)


def description(profile, track, option):
    """{url} and {chapters} are left to the caller."""
    year = _YEAR.search(option['title'])
    value = profile['description']
    technical = music(track)
    if not technical:
        value = re.sub(r'\{music\}\n', '', value)
    for token, text in (('{year}', year.group() if year else ''), ('{title}', option['title']),
                        ('{music}', technical), ('{producers}', producers(track))):
        value = value.replace(token, text)
    return value
