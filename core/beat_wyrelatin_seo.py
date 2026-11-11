"""WyreLatinBeatz's requested channel format, preserving historical modes."""
from core import beat_latin_seo_v2 as latin
from core.beat_names import clean_name
from core.beat_title import parse

MODE = 'wyrelatin_v1'
TOKENS = latin.TOKENS


def variants(track, profile):
    style, _, _ = latin.context(track)
    genre = style if style.startswith('Latin ') else 'Latin ' + style
    # Bad Bunny x Feid is the channel's editorial reference from the user's image.
    template = profile['title_template'].replace('{style}', 'Bad Bunny x Feid')
    template = template.replace('{detail}', ' | ' + genre + ' Type Beat')
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    name = clean_name(parse(track['title'])['name']).upper()
    title = template.replace('{name}', name[:budget].rstrip())
    return [dict(option, title=title) for option in latin.variants(track, profile)]


def description(profile, track, option):
    return latin.description(profile, track, option)
