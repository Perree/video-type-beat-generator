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


WINNER_LABEL = 'Indie Rock x Bedroom Pop'
WINNER_STYLES = {'Bedroom Pop', 'Indie Pop x Bedroom Pop', 'Indie Pop x Indie Rock',
                 'Indie Rock', 'Indie Pop'}
# Best performer so far, then extensions that keep its structure and try to beat it.
WINNER = '[FREE] {label} Type Beat - "{name}" (prod. matwyre)'
EXTENSIONS = ('[FREE] {label} Type Beat 2026 - "{name}" (prod. matwyre)',
              '[FREE] {label} Type Beat - "{name}" | {style} (prod. matwyre)',
              '[FREE] {label} Type Beat - "{name}" (prod. matwyre) | Instrumental')
WINNER_SHARE = 3  # of every 4 beats start with the winner; the rest start with an extension


MIN_NAME = 20  # keep at least this many characters of the beat name when adding collaborators


def _with_collaborators(template, collaborators, name_len=MIN_NAME):
    """«(prod. matwyre)» → «(prod. matwyre x colab 1 x colab 2)»; sin lugar para el nombre, se quitan del final."""
    people = [p.lower() for p in collaborators]
    while people:
        credit = '(prod. matwyre' + ''.join(' x ' + p for p in people) + ')'
        candidate = template.replace('(prod. matwyre)', credit)
        if 100 - len(candidate.replace('{name}', '')) >= min(name_len, MIN_NAME):
            return candidate
        people.pop()
    return template


def variants(track, profile, *, legacy=False):
    current = style(track)
    seed = int(hashlib.sha256(track['id'].encode()).hexdigest()[:8], 16)
    label = WINNER_LABEL if current in WINNER_STYLES else current
    if legacy:
        templates = [profile['title_template'], '[FREE] "{name}" | {style} Type Beat',
                     '[FREE] {style} Instrumental - "{name}"']
        shift = seed % len(templates)
        templates = templates[shift:] + templates[:shift]
    else:
        extensions = [t for t in EXTENSIONS if current != label or '{style}' not in t]
        shift = (seed // 4) % len(extensions)
        extensions = extensions[shift:] + extensions[:shift]
        templates = [WINNER] + extensions if seed % 4 < WINNER_SHARE else extensions + [WINNER]
    tags = list(dict.fromkeys([f'{current.lower()} type beat'] + profile['tags']))
    bounded = []
    for tag in tags:
        if len(','.join(bounded + [tag])) <= 450:
            bounded.append(tag)
    result = []
    for template in templates:
        template = template.replace('{label}', label).replace('{style}', current)
        if not legacy:
            template = _with_collaborators(template, track.get('collaborators') or (), len(clean_name(track['title'])))
        budget = 100 - len(template.replace('{name}', ''))
        if budget < 1:
            raise ValueError('seo_title_too_long')
        title = template.replace('{name}', clean_name(track['title'])[:budget].rstrip())
        if not any(option['title'] == title for option in result):
            result.append({'title': title, 'tags': bounded})
    return result


def description(profile, track, option):
    return profile['description'].replace('{style}', style(track))
