"""House style per beat ({style}) chosen from the track's own BeatStars tags.

Tags are the producer's classification, not audio analysis: Afro House needs an
explicit afro house tag, Deep House an explicit deep house tag; anything else
eligible for the channel is plain House.
"""
from core.beat_latin_seo import normalized
from core.beat_names import clean_name

MODE = 'house_v1'
TOKENS = ('{style}',)
AFRO = {'afro house', 'afro house type beat'}
DEEP = {'deep house', 'deep house type beat', 'melodic deep house'}
EXTRA_TAGS = {'Afro House': ['afro house type beat', 'afro house instrumental'],
              'Deep House': ['deep house type beat', 'deep house instrumental'],
              'House': []}


def style(track):
    tags = {normalized(t) for t in track['tags']}
    if tags & AFRO:
        return 'Afro House'
    if tags & DEEP:
        return 'Deep House'
    return 'House'


def variants(track, profile):
    current = style(track)
    template = profile['title_template'].replace('{style}', current)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    title = template.replace('{name}', clean_name(track['title'])[:budget].rstrip())
    tags = list(dict.fromkeys(EXTRA_TAGS[current] + list(profile['tags'])))
    bounded = []
    for tag in tags:
        if len(','.join(bounded + [tag])) <= 450:
            bounded.append(tag)
    # Same title; repeats rotate the tag order, like the generic fixed-template mode.
    return [{'title': title, 'tags': bounded[i:] + bounded[:i]} for i in range(max(1, len(bounded)))]


def description(profile, track, option):
    return profile['description'].replace('{style}', style(track))
