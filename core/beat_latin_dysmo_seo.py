"""Dysmo reference structure, with keywords grounded in the selected beat's tags."""
from core import beat_latin_seo_v2 as latin
from core.beat_names import clean_name
from core.beat_title import parse

MODE = 'latin_dysmo_v1'
TOKENS = latin.TOKENS


def _keywords(track, profile):
    style, mood, artists = latin.context(track)
    genre = style.lower()
    musical = ((mood + ' ') if mood else '') + style
    labels = list(artists)
    if len(artists) == 2:
        labels = [' x '.join(artists), ' x '.join(reversed(artists))] + labels
    # Put the most specific searches first, before broad and branded terms.
    words = [musical.lower() + ' type beat']
    for label in labels:
        label = label.lower()
        words += [label + ' type beat', 'type beat ' + label, 'beat ' + label]
    words += [genre + ' type beat', 'type beat ' + genre, 'beat ' + genre,
              genre + ' instrumental', 'pistas de ' + genre]
    if mood == 'Sad':
        words += [genre + ' sad type beat', 'sad ' + genre + ' type beat',
                  'type beat ' + genre + ' sad', 'beat ' + genre + ' triste']
    elif mood == 'Emotional':
        words += ['emotional ' + genre + ' type beat']
    elif mood == 'Romantic':
        words += [genre + ' romantico type beat']
    for label in labels:
        words.append(label.lower() + ' ' + genre + ' type beat')
        if mood:
            words.append(label.lower() + ' ' + mood.lower() + ' type beat')
    tags, seen = [], set()
    for word in words + profile['tags']:
        if word.casefold() in seen:
            continue
        candidate = tags + [word]
        if (len(candidate) <= 40
                and len(','.join(candidate)) + 2 * sum(' ' in t for t in candidate) <= 450):
            tags.append(word)
            seen.add(word.casefold())
    return tags


def variants(track, profile):
    style, mood, artists = latin.context(track)
    musical = ((mood + ' ') if mood else '') + style
    label = ' x '.join(artists) if artists else musical
    detail = ' | ' + musical + ' Type Beat' if artists else ''
    template = profile['title_template'].replace('{style}', label).replace('{detail}', detail)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    name = clean_name(parse(track['title'])['name'])[:budget].rstrip()
    title = template.replace('{name}', name)
    tags = _keywords(track, profile)
    return [dict(title=title, tags=tags[i:] + tags[:i]) for i in range(len(tags))]


def description(profile, track, option):
    return latin.description(profile, track, option)
