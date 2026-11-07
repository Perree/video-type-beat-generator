"""Afro tag family shared by catalog selection and title generation."""
import re
from core.beat_latin_seo import normalized


AFRO = re.compile(r'\bafro(?:beats?|swing|house|pop|drill|fusion|trap|rnb)?\b')


def is_afro(tag):
    return isinstance(tag, str) and bool(AFRO.search(normalized(tag)))


def style(track):
    tags = [normalized(t) for t in track['tags']]
    if not any(is_afro(t) for t in tags):
        raise ValueError('afro_style_missing')
    joined = ' '.join(tags)
    # Generic R&B/guitar tags can refine a track only after Afro eligibility.
    if re.search(r'\b(?:rnb|r b|rb|afrornb)\b', joined):
        return 'Afro R&B'
    for pattern, label in (
        (r'\b(?:guitar|gtr)\b', 'Afro Guitar'),
        (r'\b(?:afroswing|swing)\b', 'Afroswing'),
        (r'\b(?:afrohouse|house)\b', 'Afro House'),
        (r'\b(?:afropop|pop)\b', 'Afropop'),
        (r'\b(?:afrodrill|drill)\b', 'Afro Drill'),
        (r'\b(?:afrofusion|fusion)\b', 'Afro Fusion'),
        (r'\b(?:afrotrap|trap)\b', 'Afro Trap'),
    ):
        if re.search(pattern, joined):
            return label
    return 'Afrobeat'
