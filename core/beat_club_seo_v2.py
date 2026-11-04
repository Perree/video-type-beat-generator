"""Kiezah's established title frame, with genres and tags from each track."""
from core.beat_club_seo import STYLES
from core.beat_latin_seo import normalized
from core.beat_names import clean_name

MODE = 'club_v2'
TOKENS = ('{style}', '{detail}')


def genres(track):
    tags = {normalized(t) for t in track['tags']}
    found = [name for name, allowed in STYLES if tags & allowed]
    if any(name.endswith('House') and name != 'House' for name in found):
        found = [name for name in found if name != 'House']
    if 'Club Banger' in found:
        found = ['Club Banger'] + [name for name in found if name not in ('Club', 'Club Banger')]
    elif 'Club' in found:
        found = ['Club'] + [name for name in found if name != 'Club']
    if not found:
        raise ValueError('club_style_missing')
    return found


def labels(track):
    found = genres(track)
    return (' x '.join(found[:2]),
            found[2] + ' Type Beat' if len(found) > 2 else found[-1] + ' Instrumental')


def variants(track, profile):
    primary, detail = labels(track)
    template = profile['title_template'].replace('{style}', primary).replace('{detail}', detail)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 12:
        template = profile['title_template'].replace('{style}', genres(track)[0]).replace('{detail}', detail)
        budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    title = template.replace('{name}', clean_name(track['title']).upper()[:budget].rstrip())
    allowed = set().union(*(allowed for _, allowed in STYLES))
    raw = [normalized(t) for t in track['tags'] if normalized(t) in allowed]
    generated = [tag for genre in genres(track)
                 for tag in (f'{genre.lower()} type beat', f'{genre.lower()} instrumental')]
    bounded, seen = [], set()
    for tag in generated + raw + profile['tags']:
        if tag.casefold() in seen:
            continue
        if len(','.join(bounded + [tag])) + 2 * sum(' ' in t for t in bounded + [tag]) <= 500:
            bounded.append(tag)
            seen.add(tag.casefold())
    # Keep the same frame for every upload; repeat handling can rotate tags.
    return [{'title': title, 'tags': bounded[i:] + bounded[:i]}
            for i in range(max(1, len(bounded)))]


def description(profile, track, option):
    primary, detail = labels(track)
    return profile['description'].replace('{style}', primary).replace('{detail}', detail)
