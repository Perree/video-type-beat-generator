"""Afro and Afro Reggaeton reference labels, retaining the user's default artists."""
import re
from core import beat_latin_seo_v2 as latin
from core import beat_latin_dysmo_seo as dysmo
from core.beat_afro import is_afro
from core.beat_latin_dysmo_default_seo import DEFAULT_ARTISTS

MODE = 'latin_dysmo_v3'
TOKENS = latin.TOKENS


def context(track, *, defaults=False):
    afro = any(is_afro(t) for t in track['tags'])
    try:
        style, mood, artists = latin.context(track)
    except ValueError:
        if not afro:
            raise
        tags = {latin.normalized(t) for t in track['tags']}
        artists = [name for name, aliases in latin.ARTISTS if any(
            latin.normalized(a) in tags or latin.normalized(a) + ' type beat' in tags
            for a in aliases)][:2]
        mood = next((name for name, aliases in latin.DETAILS if tags & set(aliases)), '')
        style = ''
    if afro:
        reggaeton = style.startswith('Reggaeton') or any(re.search(
            r'\b(?:reggaeton|regueton|reggeaton|afroreggaeton)\b', latin.normalized(t))
            for t in track['tags'])
        style = 'Afro Reggaeton' if reggaeton else 'Afro'
    if defaults and not artists:
        artists = [name.title() for name in DEFAULT_ARTISTS]
    return style, mood, artists


def variants(track, profile):
    return dysmo.variants(track, profile, musical_context=context(track, defaults=True))


def description(profile, track, option):
    return latin.description(profile, track, option, musical_context=context(track))
