"""R&B titles weighted toward the channel's best performers (uppercase TYPE BEAT)."""
import hashlib
from core import beat_rnb_seo as v1
from core.beat_names import clean_name

MODE = 'rnb_test_v2'
TOKENS = v1.TOKENS
description = v1.description
# Share of beats per family; simple/melodic mirror the channel's top videos.
WEIGHTS = (('simple', 60), ('melodic', 30), ('detail', 4), ('crossover', 3), ('artists', 3))


def _titles(track):
    style, detail, artists, cross = v1.context(track)
    up = style.upper()
    titles = {'simple': f'(FREE) {up} TYPE BEAT - "{{name}}"',
              'melodic': f'(FREE) MELODIC {up} TYPE BEAT - "{{name}}"'}
    if detail:
        titles['detail'] = f'(FREE) {detail.upper()} {up} TYPE BEAT - "{{name}}"'
    if cross:
        titles['crossover'] = f'(FREE) {cross.upper()} TYPE BEAT - "{{name}}"'
    if artists:
        titles['artists'] = f'(FREE) {" x ".join(artists).upper()} {up} TYPE BEAT - "{{name}}"'
    return style, detail, artists, titles


def _options(track, profile):
    style, detail, artists, titles = _titles(track)
    keywords = [f'{style.lower()} type beat', f'{style.lower()} instrumental',
                f'melodic {style.lower()} type beat']
    if detail:
        keywords.append(f'{detail.lower()} {style.lower()} type beat')
    keywords.extend(f'{a.lower()} type beat' for a in artists)
    tags = []
    for tag in dict.fromkeys(keywords + profile['tags']):
        if sum(len(t) + (2 if ' ' in t else 0) + 1 for t in tags + [tag]) <= 450:
            tags.append(tag)
    present = [(f, w) for f, w in WEIGHTS if f in titles]
    bucket = int(hashlib.sha256((MODE + ':' + track['id']).encode()).hexdigest()[:8], 16) % sum(w for _, w in present)
    first = present[-1][0]
    for family, weight in present:
        if bucket < weight:
            first = family
            break
        bucket -= weight
    order = [first] + [f for f, _ in present if f != first]
    options = []
    for family in order:
        template = titles[family]
        budget = 100 - len(template.replace('{name}', ''))
        if budget < 1:
            raise ValueError('seo_title_too_long')
        option = {'title': template.replace('{name}', clean_name(track['title'])[:budget].rstrip()),
                  'tags': tags}
        if not any(row[1]['title'] == option['title'] for row in options):
            options.append((family, option))
    return options


def variants(track, profile):
    return [option for _, option in _options(track, profile)]


def experiment(track, profile, selected):
    family = next(family for family, option in _options(track, profile)
                  if option['title'] == selected['title'] and option['tags'] == selected['tags'])
    return {'version': MODE, 'family': family, 'allocation': 'track_sha256_weighted',
            'source_tags': list(track['tags'])}
