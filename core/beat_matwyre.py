"""Versioned matwyrebeats repertory and balanced family selection."""
from collections import Counter
import re
from core.beat_latin_seo import normalized

SELECTION = 'matwyre:v1'
ARTISTS = (
    ('Milo J', ('milo j',)), ('Seven Kayne', ('seven kayne',)),
    ('3AM', ('3am',)), ('Khea', ('khea',)), ('Duki', ('duki',)),
    ('Lautaro López', ('lautaro lopez',)),
    ('Salastkbron', ('salastkbron',)), ('YSY A', ('ysy a',)),
)
MELODIC = {'melodic', 'melodic type beat', 'melodic trap', 'melodic hard',
           'hard melodic', 'melodic hard type beat', 'melodic dark type beat'}
EMO = {'emo', 'emo trap', 'emo rap', 'emo trap type beat', 'emo rap type beat'}
SAD = {'sad', 'sad beat', 'sad beats', 'sad type beat', 'sad vibes', 'sad trap',
       'trap sad', 'sad guitar', 'guitar sad', 'sad piano', 'sad rap', 'beat sad',
       'type beat sad', 'sad type beat chill', 'sad chill beat', 'sad rnb', 'sad soul'}
GUITAR = {'guitar', 'guitar beat', 'guitar type beat', 'elec gtr', 'electric guitar',
          'sad guitar', 'guitar sad', 'acoustic guitar', 'acoustic gtr', 'guitar rnb',
          'soul guitar', 'latin guitar', 'emotional beat guitar'}
ACOUSTIC = {'acoustic', 'acoustic guitar', 'acoustic gtr', 'acoustic rnb', 'acoustic type beat'}
RNB = {'rnb', 'r b', 'rnb type beat', 'sad rnb', 'acoustic rnb', 'guitar rnb',
       'piano rnb', 'rnb trap', 'trap rnb', 'trapnb', 'latin rnb', 'trap soul'}
HARD = {'hard', 'beat hard', 'hard trap', 'hard trap type beat', 'trap hard',
        'melodic hard', 'hard melodic', 'melodic hard type beat', 'aggressive'}
TRAP = {'trap', 'trap beat', 'trap type beat', 'latin trap', 'latin trap type beat',
        'trap latino', 'piano trap', 'melodic trap', 'sad trap', 'trap sad'}
CHILL = {'chill', 'chill beat', 'chill type beat', 'sad type beat chill', 'sad chill beat'}
MOOD = {'emotional', 'emotional beat', 'nostalgic', 'melancholic', 'romantic'}
WEIGHTS = {'melodic': 5, 'emotional': 3, 'trap': 2}
OTHER = re.compile(r'\b(?:house|reggaeton|regueton|reggeaton|afro\w*|dancehall|jersey|edm|techno|pop|indie|rock)\b')


def context(track):
    values = track.get('tags', [])
    if not isinstance(values, list) or any(not isinstance(t, str) for t in values):
        raise ValueError('matwyre_style_missing')
    tags = {normalized(t) for t in values}
    if any(OTHER.search(t) for t in tags):
        raise ValueError('matwyre_style_conflict')
    artists = []
    for name, aliases in ARTISTS:
        if any(re.fullmatch(r'(?:type beat )?' + re.escape(alias)
                           + r'(?: (?:type beat|beat))?(?: 20\d{2})?', t)
               for alias in aliases for t in tags):
            artists.append(name)
    if tags & HARD:
        family = 'trap'
    elif 'Milo J' in artists or tags & (RNB | ACOUSTIC) or tags & GUITAR and tags & CHILL:
        family = 'emotional'
    elif artists or tags & (MELODIC | EMO | SAD | GUITAR | MOOD | CHILL):
        family = 'melodic'
    elif tags & TRAP:
        family = 'trap'
    else:
        raise ValueError('matwyre_style_missing')
    if tags & EMO:
        genre = ('Emo Trap' if any('trap' in t for t in tags & EMO) else
                 'Emo Rap' if any('rap' in t for t in tags & EMO) else 'Emo')
    elif tags & RNB:
        genre = 'R&B'
    elif tags & HARD:
        genre = 'Hard Trap' if tags & TRAP or any('trap' in t for t in tags & HARD) else 'Hard'
    elif tags & MELODIC:
        genre = 'Melodic Trap' if 'melodic trap' in tags else 'Melodic'
    elif tags & TRAP:
        genre = 'Trap'
    elif tags & SAD:
        genre = 'Sad'
    elif tags & CHILL:
        genre = 'Chill'
    elif tags & GUITAR:
        genre = 'Guitar'
    elif tags & ACOUSTIC:
        genre = 'Acoustic'
    elif tags & MOOD:
        genre = 'Emotional'
    else:
        genre = ''
    detail = ('Acoustic Guitar' if tags & {'acoustic guitar', 'acoustic gtr'}
              else 'Guitar' if tags & GUITAR else 'Piano' if tags & {'piano', 'piano rnb', 'sad piano', 'piano trap'}
              else 'Sad' if tags & SAD else 'Chill' if tags & CHILL else '')
    return {'family': family, 'artists': artists[:2], 'genre': genre,
            'detail': detail, 'tags': tags}


def matches(track):
    try:
        context(track)
        return True
    except ValueError:
        return False


def balanced(available, tracks, history):
    """Deficit weighting over available families; never forces absent repertory."""
    kinds = {tid: context(track)['family'] for tid, track in tracks.items()}
    counts = Counter(kinds[row['track_id']] for row in history
                     if row['status'] != 'cancelled' and row['track_id'] in kinds)
    families = {kinds[tid] for tid in available}
    if not families:
        return available
    total = sum(counts.values()) + 1
    target = max(sorted(families), key=lambda f: WEIGHTS[f] * total / 10 - counts[f])
    return [tid for tid in available if kinds[tid] == target]
