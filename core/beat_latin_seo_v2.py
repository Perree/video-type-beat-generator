"""Latin metadata grounded in each track; opt-in, preserving latin_v1 snapshots."""
from core.beat_latin_seo import normalized
from core.beat_names import clean_name
from core.beat_title import parse

MODE = 'latin_v2'
TOKENS = ('{style}', '{detail}', '{context}', '{music_info}', '{latin_hashtags}')
ARTISTS = (
    ('Bad Bunny', ('bad bunny',)), ('Feid', ('feid',)),
    ('Mora', ('mora',)), ('Omar Courtz', ('omar courtz',)),
    ('Tainy', ('tainy',)), ('Rauw Alejandro', ('rauw alejandro', 'rauw')),
    ('De La Rose', ('de la rose',)), ('Roa', ('roa',)),
    ('Saiko', ('saiko',)), ('Kidd Voodoo', ('kidd voodoo',)),
    ('Jhayco', ('jhayco', 'jhay cortez')), ('Alvaro Diaz', ('alvaro diaz',)),
    ('Quevedo', ('quevedo',)),
    ('Myke Towers', ('myke towers',)), ('Rels B', ('rels b',)),
)
# Generic trap, pop or R&B alone do not establish a Latin catalog entry.
STYLES = (
    ('Reggaeton R&B', ('reggaeton rnb', 'reggaeton r&b', 'reggaeton r b')),
    ('Latin R&B', ('latin rnb', 'latin r&b', 'latin r b')),
    ('Latin Pop', ('latin pop', 'pop latino')),
    ('Latin Trap', ('latin trap', 'trap latino', 'latin trap type beat', 'trap latino type beat')),
    ('Reggaeton', ('reggaeton', 'regueton', 'reggeaton', 'sad reggaeton',
                   'reggaeton sad', 'reggaeton romantico', 'reggaeton beat',
                   'reggaeton 2024', 'reggaeton type beat', 'regueton type beat')),
    ('Dancehall', ('dancehall', 'latin dancehall', 'dancehall type beat')),
    ('Trap/R&B', ('trapnb', 'trap rnb bet', 'trap r&b', 'trap rnb', 'rnb trap',
                  'trap rb', 'trap soul')),
)
SELECTION_TAGS = list(dict.fromkeys(tag for _, tags in STYLES for tag in tags))
DETAILS = (
    ('Sad', ('sad', 'sad reggaeton', 'reggaeton sad')),
    ('Romantic', ('romantic', 'romantico', 'reggaeton romantico')),
    ('Dark', ('dark',)), ('Emotional', ('emotional', 'emotional beat')),
    ('Melodic', ('melodic',)),
    ('Chill', ('chill',)), ('Perreo', ('perreo',)),
)


def context(track):
    tags = {normalized(tag) for tag in track['tags']}
    style = next((name for name, aliases in STYLES
                  if tags & {normalized(alias) for alias in aliases}), None)
    if style is None:
        raise ValueError('latin_style_missing')
    artists = [name for name, aliases in ARTISTS if any(
        normalized(alias) in tags or normalized(alias) + ' type beat' in tags
        for alias in aliases)][:2]
    detail = next((name for name, aliases in DETAILS if tags & set(aliases)), '')
    return style, detail, artists


def variants(track, profile):
    style, mood, artists = context(track)
    musical = (mood + ' ' if mood else '') + style
    label = ' x '.join(artists) if artists else musical
    suffix = ' | ' + musical if artists else ''
    template = profile['title_template'].replace('{style}', label).replace('{detail}', suffix)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    title = template.replace('{name}', clean_name(parse(track['title'])['name'])[:budget].rstrip())
    keywords = [style.lower() + ' type beat', style.lower() + ' instrumental']
    keywords += [artist.lower() + ' type beat' for artist in artists]
    if mood:
        keywords.append(musical.lower() + ' type beat')
    tags, seen = [], set()
    for tag in keywords + profile['tags']:
        if tag.casefold() in seen:
            continue
        candidate = tags + [tag]
        if len(candidate) <= 40 and len(','.join(candidate)) + 2 * sum(' ' in item for item in candidate) <= 450:
            tags.append(tag)
            seen.add(tag.casefold())
    # Repeat cycles change tag order, while retrying a reservation stays deterministic.
    return [{'title': title, 'tags': tags[i:] + tags[:i]} for i in range(len(tags))]


def description(profile, track, option, *, musical_context=None):
    style, mood, artists = musical_context if musical_context is not None else context(track)
    musical = (mood + ' ' if mood else '') + style
    sentence = musical + ' instrumental para grabar voces y componer canciones.'
    if artists:
        sentence += ' Referencias de estilo: ' + ' x '.join(artists) + '.'
    info = parse(track['title'])
    technical = '\n'.join(label + info[key] for label, key in [('BPM: ', 'bpm'), ('Key: ', 'key')]
                          if info[key])
    hashtags = ['#' + normalized(artist).replace(' ', '') + 'typebeat' for artist in artists]
    hashtags.append('#' + normalized(style).replace(' ', '') + 'typebeat')
    value = profile['description']
    for token, replacement in (('{context}', sentence), ('{music_info}', technical),
                               ('{style}', ' x '.join(artists) if artists else musical),
                               ('{detail}', ' | ' + musical if artists else ''),
                               ('{latin_hashtags}', ' '.join(hashtags))):
        value = value.replace(token, replacement)
    return value
