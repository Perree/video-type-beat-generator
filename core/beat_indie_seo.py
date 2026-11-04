"""Indie/pop titles derived from the producer's actual BeatStars tags."""
import hashlib

from core.beat_latin_seo import normalized
from core.beat_names import clean_name

MODE = 'indie_v1'
TOKENS = ('{style}',)


def style(track):
    tags = {normalized(tag) for tag in track['tags']}
    if tags & {'bedroom', 'bedroom pop', 'indie bedroom', 'bedroom pop type beat'}:
        return 'Indie Pop x Bedroom Pop' if 'indie pop' in tags else 'Bedroom Pop'
    if 'indie pop' in tags:
        return 'Indie Pop x Indie Rock' if tags & {'indie rock', 'rock type beat'} else 'Indie Pop'
    if tags & {'indie rock', 'indie rock type beat'}:
        return 'Indie Rock'
    if tags & {'guitar pop', 'pop guitar', 'guitar pop beat', 'guitar pop type beat'}:
        return 'Guitar Pop'
    if tags & {'sad pop', 'sad pop beat'}:
        return 'Sad Pop'
    if 'indie' in tags:
        return 'Indie'
    if tags & {'pop', 'pop beat', 'pop type beat'}:
        return 'Pop'
    raise ValueError('indie_style_missing')


def variants(track, profile):
    current = style(track)
    templates = [profile['title_template'],
                 '[FREE] "{name}" | {style} Type Beat',
                 '[FREE] {style} Instrumental - "{name}"']
    seed = int(hashlib.sha256(track['id'].encode()).hexdigest()[:8], 16)
    templates = templates[seed % len(templates):] + templates[:seed % len(templates)]
    tags = list(dict.fromkeys([f'{current.lower()} type beat'] + profile['tags']))
    bounded = []
    for tag in tags:
        if len(','.join(bounded + [tag])) <= 450:
            bounded.append(tag)
    result = []
    for template in templates:
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
