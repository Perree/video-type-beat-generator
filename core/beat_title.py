# -*- coding: utf-8 -*-
"""Datos limpios desde el nombre del archivo de un beat, y plantillas con bloques opcionales.

``parse('(BEAT PRO-527) [juice wrld, elec gtr, sad] This is for me - 160bpm - key A Sharp Minor
(prod. @a x @b)')`` → ``name='This is for me'``, ``artist='juice wrld'``, ``mood='sad'``,
``bpm='160'``, ``key='A Sharp Minor'``. Un nombre simple (``Legends Fall``) queda solo como ``name``.

Plantillas: ``{name} {artist} {bpm} {key} {mood} {channel}``. Un bloque ``[[ ... ]]`` se muestra
solo si todas sus variables tienen valor: ``[FREE] [[{artist} Type Beat - ]]"{name}"``.
"""
import re

VARIABLES = ('name', 'artist', 'bpm', 'key', 'mood', 'channel')
INSTRUMENTS = {
    '808', 'bass', 'bells', 'brass', 'choir', 'drums', 'elec gtr', 'electric guitar', 'flute', 'gtr',
    'guitar', 'acoustic gtr', 'acoustic guitar', 'harp', 'keys', 'organ', 'pad', 'piano', 'rhodes', 'sax',
    'saxophone', 'strings', 'synth', 'trumpet', 'vocal', 'vocals', 'violin', 'cello', 'pluck', 'arp',
}
MOODS = {
    'aggressive', 'ambient', 'angry', 'bouncy', 'calm', 'chill', 'dark', 'dreamy', 'emotional', 'energetic',
    'epic', 'happy', 'hard', 'hype', 'lofi', 'lo-fi', 'love', 'mellow', 'melancholic', 'melodic',
    'nostalgic', 'romantic', 'sad', 'smooth', 'summer', 'upbeat', 'uplifting', 'vibey', 'wavy',
}
_BPM = re.compile(r'(\d{2,3}(?:\.\d)?)\s*bpm\b', re.I)
_KEY = re.compile(r'\bkey\s*[:\-]?\s*([A-G](?:\s*(?:#|b|sharp|flat))?(?:\s*(?:minor|major|min|maj|m))?)(?![A-Za-z])',
                  re.I)
_BRACKETS = re.compile(r'\[([^\]]*)\]')
_PARENS = re.compile(r'\(([^)]*)\)')
_TYPE_BEAT = re.compile(r'^\s*(.+?)\s+type\s+beat\b', re.I)
_FREE = re.compile(r'[\[(]?\s*free(?:\s+for\s+profit)?\s*[\])]?', re.I)
_OPTIONAL = re.compile(r'\[\[(.*?)\]\]', re.S)
_VAR = re.compile(r'\{(' + '|'.join(VARIABLES) + r')\}')
_SEP = r'[|\-–—~•,:/]'
_GAP = '\x00'
# Ya dentro de [[…]] se deja igual (la primera alternativa consume el bloque entero).
_AUTO_OPTIONAL = re.compile(r'\[\[.*?\]\]|\{bpm\}\s*BPM|\{artist\}\s*Type\s+Beat(?:\s*[-–—|~]\s*)?',
                            re.I | re.S)


def _clean(text):
    return ' '.join(text.split()).strip(' -–—|~•,:/_.')


def _find_artist(stem, artists):
    lower = stem.lower()
    for artist in artists or ():
        if artist and re.search(r'(?<![a-z0-9])' + re.escape(artist.lower()) + r'(?![a-z0-9])', lower):
            return artist
    return ''


def parse(stem, artists=()):
    """Partes del nombre del archivo (sin extensión). Las que no aparecen quedan vacías."""
    info = dict.fromkeys(('name', 'artist', 'bpm', 'key', 'mood'), '')
    text = stem.replace('_', ' ')
    bpm = _BPM.search(text)
    if bpm:
        info['bpm'] = bpm.group(1).rstrip('0').rstrip('.') if '.' in bpm.group(1) else bpm.group(1)
    key = _KEY.search(text)
    if key:
        info['key'] = ' '.join(key.group(1).split())
    text = _KEY.sub(' ', _BPM.sub(' ', text))

    found_artist = ''
    for group in _BRACKETS.findall(text):
        for item in (part.strip() for part in group.split(',')):
            low = item.lower()
            if not item or low in ('free', 'free for profit'):
                continue
            if low in MOODS:
                info['mood'] = info['mood'] or item
            elif low not in INSTRUMENTS and not found_artist:
                found_artist = item
    text = _BRACKETS.sub(' ', text)
    # Paréntesis: códigos tipo «BEAT PRO-527», «prod. …» y «FREE» no son parte del nombre.
    text = _PARENS.sub(lambda m: ' ' if re.search(r'\d|prod|free', m.group(1), re.I) else m.group(0), text)
    text = _FREE.sub(' ', text)
    match = _TYPE_BEAT.search(text)
    if match:
        found_artist = found_artist or _clean(match.group(1))
        text = text[match.end():]
    info['artist'] = _find_artist(stem, artists) or found_artist
    parts = [_clean(p).strip('"“”\'') for p in re.split(r'\s[-–—|~]\s', text)]
    info['name'] = ' - '.join(p for p in parts if p) or _clean(stem)
    return info


def variables_in(template):
    return _VAR.findall(template)


def _tidy(text):
    """Saca separadores colgados, paréntesis/comillas vacías y espacios dobles (una línea)."""
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r'\(\s*\)|\[\s*\]|"\s*"|“\s*”|\'\s*\'', '', text)
        text = re.sub(rf'\s*{_SEP}\s*(?={_SEP})', ' ', text)
        text = re.sub(rf'^\s*{_SEP}+\s*|\s*{_SEP}+\s*$', '', text)
        text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


def fill(template, values, tidy=True):
    """Reemplaza variables; quita bloques ``[[…]]`` con alguna variable vacía.

    ``tidy``: True limpia separadores en cada línea (títulos); ``"gaps"`` solo en las líneas donde
    quedó una variable vacía (descripciones: no toca líneas fijas como «Instagram:»); False, nunca.
    """
    def empty(name):
        return not str(values.get(name) or '').strip()

    def optional(match):
        block = match.group(1)
        return _GAP if any(empty(n) for n in _VAR.findall(block)) else block

    # Atajos comunes que se vuelven opcionales solos: «{bpm} BPM», «{artist} Type Beat».
    template = _AUTO_OPTIONAL.sub(lambda m: m.group(0) if m.group(0).startswith('[[') else f'[[{m.group(0)}]]',
                                  template)
    lines = []
    for line in _OPTIONAL.sub(optional, template).split('\n'):
        # Se limpia la línea si se pidió, o si quedó un hueco (variable vacía o bloque quitado).
        gap = _GAP in line or any(empty(n) for n in _VAR.findall(line))
        line = _VAR.sub(lambda m: str(values.get(m.group(1)) or ''), line).replace(_GAP, '')
        lines.append(_tidy(line) if tidy is True or (tidy == 'gaps' and gap) else line)
    return '\n'.join(lines)
