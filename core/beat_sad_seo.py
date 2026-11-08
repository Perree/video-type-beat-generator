"""Sad melodic metadata using only the artists present in each beat's tags."""
import re
from core.beat_names import clean_name
from core.beat_title import parse

MODE = 'sad_melodic_v1'
TOKENS = ('{style}', '{title}', '{music_info}', '{sad_hashtags}')
ARTISTS = (('Juice WRLD', 'juice wrld'), ('iann dior', 'iann dior'),
           ('The Kid LAROI', 'the kid laroi'))


def context(track):
    tags = {tag.strip().casefold() for tag in track['tags']}
    artists = [name for name, tag in ARTISTS if tag in tags]
    sad = 'sad beat' in tags
    if not artists and not sad:
        raise ValueError('sad_style_missing')
    style = ' x '.join(artists[:2])
    if sad:
        style = ('Sad ' + style).strip()
    return style, artists, sad


def variants(track, profile):
    style, artists, sad = context(track)
    template = profile['title_template'].replace('{style}', style)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    name = clean_name(parse(track['title'])['name'])
    title = template.replace('{name}', name[:budget].rstrip())
    keywords = [a.lower() + ' type beat' for a in artists]
    if sad:
        keywords += ['sad type beat', 'sad beat']
    tags = []
    for tag in dict.fromkeys(keywords + profile['tags']):
        candidate = tags + [tag]
        if len(candidate) <= 40 and len(','.join(candidate)) + 2 * sum(' ' in t for t in candidate) <= 450:
            tags.append(tag)
    return [dict(title=title, tags=tags[i:] + tags[:i]) for i in range(max(1, len(tags)))]


def description(profile, track, option):
    style, artists, sad = context(track)
    music = parse(track['title'])
    technical = '\n'.join(label + music[key] for label, key in
                          [('BPM: ', 'bpm'), ('Key: ', 'key')] if music[key])
    hashtags = ['#' + re.sub(r'[^A-Za-z0-9]', '', a) + 'TypeBeat' for a in artists]
    if sad:
        hashtags.append('#SadTypeBeat')
    hashtags.append('#TypeBeat')
    result = profile['description']
    for token, value in (('{style}', style), ('{title}', option['title']),
                         ('{music_info}', technical), ('{sad_hashtags}', ' '.join(hashtags[:3]))):
        result = result.replace(token, value)
    return result
