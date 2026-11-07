"""Truthful artist/style titles with stable per-beat presentation experiments."""
import hashlib
import re
from core.beat_matwyre import context, MELODIC, SAD, CHILL, RNB, GUITAR, HARD, TRAP, EMO
from core.beat_names import clean_name
from core.beat_title import parse

MODE = 'matwyre_v1'
TOKENS = ('{style}', '{context}', '{music_info}', '{credits}', '{hashtags}')


def _source_credits(title):
    return re.search(r'\((?:prod\.?\s+([^)]{1,250})|'
                     r'((?:@?matwyre)\s+x\s+[^)]{1,230}))\)', title, re.I)


def _name(track):
    title = track['title']
    credits = _source_credits(title)
    if credits:
        title = title[:credits.start()] + title[credits.end():]
    return clean_name(title)


def _sound(info):
    detail, genre = info['detail'], info['genre']
    if genre and genre.casefold() in detail.casefold():
        return detail
    if detail and detail.casefold() in genre.casefold():
        return genre
    return ' '.join(v for v in (detail, genre) if v)


def _options(track, profile):
    info = context(track)
    style = ' x '.join(info['artists']) or _sound(info)
    if not style:
        raise ValueError('matwyre_style_missing')
    # Preserve the catalog's name rather than fabricating an emotional phrase.
    templates = [('search', profile['title_template'].replace('{style}', style)),
                 ('name_first', '{name} (' + style + ' Type Beat)')]
    if info['artists'] and info['genre']:
        templates.append(('detail', '(FREE) ' + style + ' Type Beat - "{name}" | '
                          + _sound(info)))
    keywords = [f'{a.lower()} type beat' for a in info['artists']]
    if info['genre']:
        keywords.append(info['genre'].lower() + ' type beat')
    if len(info['artists']) > 1:
        keywords.append(' x '.join(a.lower() for a in info['artists']) + ' type beat')
    tags = info['tags']
    for values, keyword in ((EMO, info['genre'].lower() + ' type beat'), (RNB, 'rnb type beat'),
                            (MELODIC, 'melodic type beat'), (GUITAR, 'guitar type beat'),
                            (SAD, 'sad type beat'), (HARD, 'hard type beat'),
                            (TRAP, 'trap type beat'), (CHILL, 'chill type beat')):
        if tags & values:
            keywords.append(keyword)
    if tags & {'acoustic guitar', 'acoustic gtr'}:
        keywords.append('acoustic guitar type beat')
    bounded = []
    for tag in dict.fromkeys(keywords + profile['tags']):
        if sum(len(t) + (2 if ' ' in t else 0) + 1 for t in bounded + [tag]) <= 450:
            bounded.append(tag)
    options = []
    for family, template in templates:
        budget = 100 - len(template.replace('{name}', ''))
        if budget < 1:
            raise ValueError('seo_title_too_long')
        option = {'title': template.replace('{name}', _name(track)[:budget].rstrip()),
                  'tags': bounded}
        if not any(row[1]['title'] == option['title'] for row in options):
            options.append((family, option))
    offset = int(hashlib.sha256((MODE + ':' + track['id']).encode()).hexdigest()[:8], 16) % len(options)
    return options[offset:] + options[:offset]


def variants(track, profile):
    return [option for _, option in _options(track, profile)]


def experiment(track, profile, selected):
    family = next(f for f, o in _options(track, profile) if
                  o['title'] == selected['title'] and o['tags'] == selected['tags'])
    return {'version': MODE, 'family': family, 'allocation': 'track_sha256',
            'source_tags': list(track['tags']), 'repertory': context(track)['family']}


def description(profile, track, option):
    info = context(track)
    style = ' x '.join(info['artists']) or info['genre'] or info['detail']
    details = [info['genre'], info['detail']]
    sentence = f'{style} type beat para escribir y grabar voces.'
    if any(details):
        sentence += ' Sonido: ' + ', '.join(dict.fromkeys(d for d in details if d)) + '.'
    parsed = parse(track['title'])
    music = '\n'.join(label + parsed[key] for label, key in [('BPM: ', 'bpm'), ('Tono: ', 'key')] if parsed[key])
    authors = _source_credits(track['title'])
    credits = ('Producción: ' + (authors.group(1) or authors.group(2)).strip() if authors else
               'Prod. MatWyre. Créditos completos y colaboradores en la ficha original del beat.')
    hashtags = ['#TypeBeat', '#MatWyre']
    if info['artists']:
        hashtags.insert(0, '#' + re.sub(r'[^A-Za-z0-9]', '', info['artists'][0]) + 'TypeBeat')
    result = profile['description']
    for token, value in (('{style}', style), ('{context}', sentence), ('{music_info}', music),
                         ('{credits}', credits), ('{hashtags}', ' '.join(hashtags))):
        result = result.replace(token, value)
    return result
