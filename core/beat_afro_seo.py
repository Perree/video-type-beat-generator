"""Opt-in Afro packaging, derived exclusively from the selected track's tags."""
from core.beat_afro import is_afro, style
from core.beat_latin_seo import normalized
from core.beat_names import clean_name
from core.beat_title import parse

MODE = 'afro_v1'
TOKENS = ('{style}', '{title}', '{technical}', '{afro_hashtags}')
ARTISTS = ('Burna Boy', 'Wizkid', 'Rema', 'Tems', 'Omah Lay', 'Tayc')


def label(track):
    tags = {normalized(t) for t in track['tags']}
    artists = [a for a in ARTISTS if tags & {normalized(a), normalized(a) + ' type beat'}]
    return ' x '.join([style(track)] + artists[:2])


def variants(track, profile):
    template = profile['title_template'].replace('{style}', label(track))
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 16:
        template = profile['title_template'].replace('{style}', style(track))
        budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    title = template.replace('{name}', clean_name(track['title'])[:budget].rstrip())
    tags, seen = [], set()
    actual = [normalized(t) for t in track['tags'] if is_afro(t)]
    artists = [a.lower() + ' type beat' for a in ARTISTS
               if {normalized(a), normalized(a) + ' type beat'} & {normalized(t) for t in track['tags']}]
    for tag in [style(track).lower() + ' type beat', 'afro type beat'] + actual + artists + profile['tags']:
        if tag.casefold() in seen:
            continue
        if len(','.join(tags + [tag])) + 2 * sum(' ' in t for t in tags + [tag]) <= 500:
            tags.append(tag)
            seen.add(tag.casefold())
    return [{'title': title, 'tags': tags[i:] + tags[:i]} for i in range(max(1, len(tags)))]


def description(profile, track, option):
    info = parse(track['title'])
    technical = []
    if info['bpm']:
        technical.append('BPM: ' + info['bpm'])
    if info['key']:
        technical.append('Key: ' + info['key'])
    value = profile['description']
    for token, replacement in (
        ('{title}', option['title']), ('{style}', label(track)),
        ('{technical}', ' | '.join(technical)),
        ('{afro_hashtags}', ' '.join(dict.fromkeys(('#afro', '#afrobeat',
             '#' + normalized(style(track)).replace(' ', ''))))),
    ):
        value = value.replace(token, replacement)
    return value
