"""Artist-first Latin titles following the user's Taimet reference format."""
from core import beat_latin_seo_v2 as latin
from core.beat_names import clean_name
from core.beat_title import parse

MODE = 'latin_taimet_v1'
TOKENS = latin.TOKENS


def variants(track, profile):
    style, _, artists = latin.context(track)
    label = ' x '.join(artist.upper() for artist in artists) if artists else style.upper()
    template = profile['title_template'].replace('{style}', label).replace('{detail}', '')
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    name = clean_name(parse(track['title'])['name']).upper()
    title = template.replace('{name}', name[:budget].rstrip())
    return [dict(option, title=title) for option in latin.variants(track, profile)]


def description(profile, track, option):
    return latin.description(profile, track, option)
