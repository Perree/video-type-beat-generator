"""Melodic channel metadata based on actual BeatStars tags."""
from core.beat_latin_seo import normalized
from core.beat_names import clean_name

MODE = 'melodic_v1'
TOKENS = ('{style}',)
ARTISTS = (
    ('Fattmack', ('fattmack', 'fatt mack')),
    ('Topoppgen', ('topoppgen', 'topopp gen')),
    ('Juice WRLD', ('juice wrld', 'juicewrld')),
    ('Duki', ('duki',)),
    ('Khea', ('khea',)),
)
MELODIC = {'melodic', 'melodic type beat', 'melodic trap', 'melodic trap type beat',
           'melodic hard', 'melodic hard type beat', 'melodic dark type beat', 'hard melodic'}


def style(track):
    tags = {normalized(tag) for tag in track['tags']}
    artists = [name for name, aliases in ARTISTS if any(
        tag in {alias, alias + ' type beat', alias + ' beat', 'type beat ' + alias}
        for alias in aliases for tag in tags)]
    if artists:
        return ' x '.join(artists[:2])
    if tags & MELODIC:
        return 'Melodic'
    raise ValueError('melodic_style_missing')


def variants(track, profile):
    current = style(track)
    tags = [f'{artist.lower()} type beat' for artist in current.split(' x ')]
    if {normalized(tag) for tag in track['tags']} & MELODIC:
        tags.append('melodic type beat')
    bounded = []
    for tag in dict.fromkeys(tags + profile['tags']):
        # Includes YouTube's implicit quotes for tags containing spaces.
        if sum(len(t) + (2 if ' ' in t else 0) + 1 for t in bounded + [tag]) <= 450:
            bounded.append(tag)
    result = []
    for template in (profile['title_template'], '[FREE] {style} Type Beat - "{name}"'):
        template = template.replace('{style}', current)
        budget = 100 - len(template.replace('{name}', ''))
        if budget < 1:
            raise ValueError('seo_title_too_long')
        title = template.replace('{name}', clean_name(track['title'])[:budget].rstrip())
        if not any(option['title'] == title for option in result):
            result.append({'title': title, 'tags': bounded})
    return result


def description(profile, track, option):
    return profile['description'].replace('{style}', style(track))
