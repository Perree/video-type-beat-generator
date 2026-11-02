"""Deterministic Latin title variants driven by the downloaded track tags."""
import hashlib
import re
import unicodedata
from core.beat_title import parse
from core.beat_names import clean_name

MODE = 'latin_v1'
TOKENS = ('{artists}', '{style}', '{bpm}', '{key}')


def normalized(value):
    value = unicodedata.normalize('NFKD', value.casefold())
    return re.sub(r'[^a-z0-9]+', ' ', ''.join(c for c in value if not unicodedata.combining(c))).strip()


def contexts(track):
    tags = {normalized(t) for t in track['tags']}
    styles = []
    if tags & {'trapnb', 'trap rnb bet', 'trap r b', 'trap rnb', 'rnb trap', 'trap rb', 'trap soul', 'latin rnb', 'reggaeton rnb', 'reggaeton r b'}:
        styles.append('Reggaeton R&B' if tags & {'reggaeton rnb', 'reggaeton r b'} else 'Trap/R&B')
    if tags & {'reggaeton', 'regueton', 'reggeaton', 'sad reggaeton', 'reggaeton sad', 'reggaeton romantico', 'reggaeton beat', 'reggaeton 2024', 'reggaeton type beat', 'regueton type beat'}:
        styles.append('Reggaeton')
    if tags & {'latin trap', 'trap latino', 'latin trap type beat', 'trap latino type beat'}:
        styles.append('Latin Trap')
    if not styles:
        raise ValueError('latin_style_missing')
    seed = int(hashlib.sha256(track['id'].encode()).hexdigest()[:8], 16)
    styles = styles[seed % len(styles):] + styles[:seed % len(styles)]
    for style in styles:
        pool = ['Mora', 'Omar Courtz', 'Bad Bunny', 'Feid']
        tagged = [a for a in pool if normalized(a) in tags or normalized(a) + ' type beat' in tags]
        pairs = [f'{tagged[0]} x {a}' for a in pool if a != tagged[0]] if len(tagged) == 1 else (
            [' x '.join(tagged[:2])] if tagged else ['Mora x Omar Courtz', 'Bad Bunny x Mora', 'Feid x Omar Courtz', 'Mora x Feid'])
        pairs = pairs[seed % len(pairs):] + pairs[:seed % len(pairs)]
        for artists in pairs:
            yield artists, style


def variants(track, profile):
    result = []
    for artists, style in contexts(track):
        template = profile['title_template'].replace('{artists}', artists).replace('{style}', style)
        name = clean_name(track['title'])
        # Keep the identifying name inside YouTube's 100-character title limit.
        budget = 100 - len(template.replace('{name}', ''))
        if budget < 1:
            raise ValueError('seo_title_too_long')
        title = template.replace('{name}', name[:budget].rstrip())
        tags = list(dict.fromkeys([f'{style.lower()} type beat'] + [f'{a.lower()} type beat' for a in artists.split(' x ')] + profile['tags']))
        bounded = []
        for tag in tags:
            if len(','.join(bounded + [tag])) <= 450:
                bounded.append(tag)
        result.append({'title': title, 'tags': bounded})
    return result


def description(profile, track, option):
    # The same candidate order produces the exact artist/style pair chosen for the title.
    index = variants(track, profile).index(option)
    artists, style = list(contexts(track))[index]
    info = parse(track['title'])
    values = dict(artists=artists, style=style, bpm=info['bpm'], key=info['key'])
    lines = []
    for line in profile['description'].split('\n'):
        if any('{' + key + '}' in line and not values[key] for key in ('bpm', 'key')):
            continue
        for key, value in values.items():
            line = line.replace('{' + key + '}', value)
        lines.append(line)
    return '\n'.join(lines)
