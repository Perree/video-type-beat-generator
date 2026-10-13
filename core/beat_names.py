"""Extract the bare beat name from a BeatStars title, e.g. 'juice wrld type beat - mellow' -> 'Mellow'."""
import re

ARTISTS = ('juice wrld', 'juice wrld', 'iann dior', 'kid laroi', 'xxxtentacion', 'dro kenji', 'polo g',
           'rusherking', 'zzz', 'eymat', 'taigen')
QUOTED = re.compile(r'[\"“”„«»]([^\"“”„«»]{1,80})[\"“”„«»]')
PROMO = re.compile(r'[\(\[][^\)\]]*\b(free|buy|\d+\s*get|exclusive|prod)\b[^\)\]]*[\)\]]', re.I)
SEPARATOR = re.compile(r'\s+[-–—|]\s+')
JUNK = re.compile(r'[<>{}\"“”]')


def _is_noise(segment):
    low = segment.lower()
    return ('type beat' in low or 'typebeat' in low
            or any(artist in low for artist in ARTISTS))


def _pretty(name):
    name = JUNK.sub('', name)
    name = re.sub(r'\s+', ' ', name).strip(' .,-|:;')
    if name and name == name.lower():
        # All-lowercase catalog names: capitalize each word without breaking "i'm".
        name = ' '.join(word[:1].upper() + word[1:] for word in name.split(' '))
    return name


def clean_name(title):
    return _clean(title) or 'Beat'


def _clean(title):
    """Best-effort bare name; falls back to the title minus markup characters."""
    text = PROMO.sub(' ', title)
    quoted = [q.strip() for q in QUOTED.findall(text) if q.strip() and not _is_noise(q)]
    if quoted:
        return _pretty(quoted[0])
    segments = [s for s in SEPARATOR.split(text) if s.strip()]
    kept = [s for s in segments if not _is_noise(s)]
    if kept:
        return _pretty(kept[-1] if len(segments) > 1 and len(kept) == 1 else kept[0])
    # Everything looks like promo text: strip the known noise words and keep what is left.
    stripped = re.sub(r'type\s*beat', ' ', text, flags=re.I)
    for artist in ARTISTS:
        stripped = re.sub(re.escape(artist), ' ', stripped, flags=re.I)
    stripped = re.sub(r'[\s,x&]+$|^[\s,x&]+', '', stripped)
    return _pretty(stripped) or _pretty(title) or 'Beat'
