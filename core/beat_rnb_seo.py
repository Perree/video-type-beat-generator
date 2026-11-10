"""Versioned R&B title experiments grounded in exact BeatStars tags."""
import hashlib
from core.beat_latin_seo import normalized
from core.beat_names import clean_name
from core.beat_title import parse, parse_track

MODE = 'rnb_test_v1'
TOKENS = ('{style}', '{context}', '{music_info}')
ARTISTS = (
    ('PARTYNEXTDOOR', ('partynextdoor', 'party next door', 'pnd')),
    ('Che Ecru', ('che ecru',)), ('Drake', ('drake',)),
    ('Brent Faiyaz', ('brent faiyaz',)), ('Bryson Tiller', ('bryson tiller',)),
    ('Kehlani', ('kehlani',)), ('Aaliyah', ('aaliyah',)), ('Karri', ('karri',)),
    ('SZA', ('sza',)), ('Summer Walker', ('summer walker',)),
    ('Aftertheparty', ('aftertheparty',)),
)
RNB = {'rnb', 'r b', 'rnb type beat', 'r b type beat', 'acoustic rnb',
       'sad rnb', 'guitar rnb', 'piano rnb', 'latin rnb', 'rnb trap', 'trapnb'}
SOUL = {'soul', 'soul beat', 'soul type beat', 'sad soul', 'soul guitar'}
DETAILS = (
    ('Acoustic', {'acoustic rnb', 'acoustic guitar', 'acoustic'}),
    ('Guitar', {'guitar rnb', 'guitar beat', 'guitar', 'soul guitar', 'elec gtr'}),
    ('Piano', {'piano rnb', 'piano'}),
    ('Sad', {'sad rnb', 'sad soul', 'sad'}),
    ('Emotional', {'emotional', 'emotional beat'}),
    ('Smooth', {'smooth', 'smooth rnb'}), ('Dark', {'dark', 'dark rnb'}),
)


def context(track):
    tags = {normalized(t) for t in track['tags']}
    # Explicit compounds also establish the R&B context.
    rnb = bool(tags & (RNB | {'smooth rnb', 'dark rnb', 'rnb drill', 'r b drill',
                              'rnb trap', 'trap rnb', 'rnb soul', 'trap soul'}))
    if not rnb and not tags & SOUL:
        raise ValueError('rnb_style_missing')
    style = 'R&B' if rnb else 'Soul'
    detail = next((label for label, aliases in DETAILS if tags & aliases), '')
    artists = [name for name, aliases in ARTISTS if any(
        tag in {alias, alias + ' type beat', alias + ' beat'}
        for alias in aliases for tag in tags)]
    cross = ''
    if rnb:
        if tags & {'trap soul', 'trapsoul'}:
            cross = 'Trap Soul + R&B'
        elif tags & {'drill', 'rnb drill', 'r b drill'}:
            cross = 'Drill + R&B'
        elif tags & SOUL:
            cross = 'Soul + R&B'
        elif tags & {'trap', 'trapnb', 'rnb trap', 'trap rnb'}:
            cross = 'Trap + R&B'
    return style, detail, artists[:2], cross


def _options(track, profile):
    style, detail, artists, cross = context(track)
    templates = [('simple', profile['title_template'].replace('{style}', style))]
    if detail:
        templates.append(('detail', f'(FREE) {style} Type Beat - "{{name}}" | {detail} {style} Instrumental'))
    if cross:
        templates.append(('crossover', f'(FREE) {cross} Type Beat - "{{name}}"'))
    if artists:
        templates.append(('artists', f'(FREE) {" x ".join(artists)} {style} Type Beat - "{{name}}"'))
    keywords = [f'{style.lower()} type beat', f'{style.lower()} instrumental']
    if detail:
        keywords.append(f'{detail.lower()} {style.lower()} type beat')
    keywords.extend(f'{a.lower()} type beat' for a in artists)
    tags = []
    for tag in dict.fromkeys(keywords + profile['tags']):
        if sum(len(t) + (2 if ' ' in t else 0) + 1 for t in tags + [tag]) <= 450:
            tags.append(tag)
    options = []
    for family, template in templates:
        budget = 100 - len(template.replace('{name}', ''))
        if budget < 1:
            raise ValueError('seo_title_too_long')
        option = {'title': template.replace('{name}', clean_name(track['title'])[:budget].rstrip()),
                  'tags': tags}
        if not any(row[1]['title'] == option['title'] for row in options):
            options.append((family, option))
    # Per-track deterministic allocation, never rerolled on network retries.
    offset = int(hashlib.sha256((MODE + ':' + track['id']).encode()).hexdigest()[:8], 16) % len(options)
    return options[offset:] + options[:offset]


def variants(track, profile):
    return [option for _, option in _options(track, profile)]


def experiment(track, profile, selected):
    family = next(family for family, option in _options(track, profile)
                  if option['title'] == selected['title'] and option['tags'] == selected['tags'])
    return {'version': MODE, 'family': family, 'allocation': 'track_sha256',
            'source_tags': list(track['tags'])}


def description(profile, track, option):
    style, detail, artists, _ = context(track)
    sentence = f'{detail + " " if detail else ""}{style} instrumental for vocal recording and songwriting.'
    if artists:
        sentence += ' Artist references: ' + ' x '.join(artists) + '.'
    info = parse_track(track)
    music = '\n'.join(label + info[key] for label, key in [('BPM: ', 'bpm'), ('Key: ', 'key')] if info[key])
    return (profile['description'].replace('{style}', style).replace('{context}', sentence)
            .replace('{music_info}', music))
