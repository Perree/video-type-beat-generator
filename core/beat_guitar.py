"""Opt-in guitar/emo repertory for Make You Beats; no global tag changes."""
import re
from core.beat_latin_seo import normalized

SELECTION = 'guitar-trap:v1'
ARTISTS = (
    ('Juice WRLD', ('juice wrld', 'juicewrld')),
    ('Hurricane Wisdom', ('hurricane wisdom',)),
    ('Nino Paid', ('nino paid', 'ninopaid')),
    ('FattMack', ('fattmack', 'fatt mack')),
    ('TopOppGen', ('topoppgen', 'topopp gen')),
)
GUITAR = {'guitar', 'guitar beat', 'beat guitar', 'guitar type beat', 'trap guitar',
          'guitar trap', 'trap guitar type beat', 'guitar trap type beat', 'gtr',
          'elec gtr', 'electric guitar', 'acoustic guitar', 'acoustic gtr',
          'sad guitar', 'guitar sad', 'sad guitar beat', 'guitar sad type beat',
          'guitar sad trap type beat', 'sad beat guitar', 'emotional guitar',
          'emotional guitar beat', 'emotional beat guitar', 'guitar juice wrld',
          'guitar rnb', 'soul guitar'}
EMO = {'emo', 'emo rap', 'emo trap', 'emo type beat', 'emo rap type beat', 'emo trap type beat'}
PAIN = {'pain', 'pain beat', 'pain type beat'}
MELODIC = {'melodic trap', 'melodic trap type beat', 'emotional trap beat'}
SAD = {'sad', 'sad beat', 'sad type beat', 'sad trap', 'sad guitar', 'guitar sad',
       'sad guitar beat', 'guitar sad type beat', 'guitar sad trap type beat', 'sad beat guitar'}
EMOTIONAL = {'emotional', 'emotional beat', 'emotional type beat',
             'emotional guitar', 'emotional guitar beat', 'emotional beat guitar'}
OTHER = re.compile(r'\b(?:afro\w*|house|reggaeton|regueton|reggeaton|dancehall|jersey|edm|techno|pop|indie|rock)\b')


def context(track):
    values = track.get('tags')
    if not isinstance(values, list) or any(not isinstance(t, str) for t in values):
        raise ValueError('guitar_style_missing')
    tags = {normalized(t) for t in values}
    if any(OTHER.search(t) for t in tags):
        raise ValueError('guitar_style_conflict')
    artists = [name for name, aliases in ARTISTS if any(
        re.fullmatch(r'(?:free |sad |type beat |beat type )?' + re.escape(alias)
                     + r'(?: (?:type beat|beat|beats))?(?: 20\d{2})?', tag)
        for alias in aliases for tag in tags)]
    if not artists and not tags & (GUITAR | EMO | PAIN | MELODIC):
        raise ValueError('guitar_style_missing')
    guitar = bool(tags & GUITAR)
    if artists:
        style = ' x '.join((['Guitar'] if guitar else []) + artists[:2])
    elif guitar:
        style = ('Sad Guitar' if tags & SAD else 'Emotional Guitar' if tags & EMOTIONAL
                 else 'Guitar Trap' if any('trap' in t for t in tags) else 'Guitar')
    elif tags & EMO:
        style = 'Emo Rap' if any('rap' in t for t in tags & EMO) else 'Emo Trap' if any('trap' in t for t in tags & EMO) else 'Emo'
    elif tags & PAIN:
        style = 'Pain'
    else:
        style = 'Emotional Trap' if tags & EMOTIONAL else 'Melodic Trap'
    return {'style': style, 'artists': artists[:2], 'guitar': guitar, 'tags': tags}


def matches(track):
    try:
        context(track)
        return True
    except ValueError:
        return False
