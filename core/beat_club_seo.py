"""House/club packaging without artist targeting, based on exact catalog tags."""
import hashlib
from core.beat_latin_seo import normalized
from core.beat_names import clean_name

MODE = 'club_v1'
TOKENS = ('{style}',)
STYLES = (
    ('Afro House', {'afro house', 'afro house type beat', 'afrohouse'}),
    ('Melodic Deep House', {'melodic deep house'}),
    ('Melodic House', {'melodic house', 'melodic house type beat'}),
    ('Deep House', {'deep house', 'deep house type beat', 'sad deep house', 'deephouse'}),
    ('Latin House', {'latin house'}),
    ('Reggaeton House', {'reggaeton house'}),
    ('House', {'house', 'house type beat', 'club house', 'sad house', 'emotional house'}),
    ('Club Banger', {'club banger', 'club banger type beat'}),
    ('EDM', {'edm', 'edm type beat'}),
    ('Club', {'club', 'club type beat'}),
)


def style(track):
    tags = {normalized(t) for t in track['tags']}
    for name, allowed in STYLES:
        if tags & allowed:
            if name.endswith('House') and tags & {'club', 'club banger', 'club house', 'club type beat', 'club banger type beat'}:
                return name + ' x Club Banger' if 'club banger' in tags or 'club banger type beat' in tags else name + ' x Club'
            return name
    raise ValueError('club_style_missing')


def variants(track, profile):
    current = style(track)
    templates = [profile['title_template'],
                 '[FREE] {style} Instrumental - "{name}"',
                 '[FREE] "{name}" | {style} Type Beat']
    seed = int(hashlib.sha256(track['id'].encode()).hexdigest()[:8], 16) % len(templates)
    templates = templates[seed:] + templates[:seed]
    tags = list(dict.fromkeys([f'{current.lower()} type beat', f'{current.lower()} instrumental'] + profile['tags']))
    bounded = []
    for tag in tags:
        if len(','.join(bounded + [tag])) + 2 * sum(' ' in t for t in bounded + [tag]) <= 500:
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
