"""Preserve meaningful FREE in catalog names; v1 snapshots remain replayable."""
import re
from core import beat_emotional_house_seo as previous
from core.beat_emotional_house_seo import TOKENS, description
from core.beat_names import clean_name

MODE = 'emotional_house_v2'


def catalog_name(title):
    # Remove structured file metadata, without the file parser's global FREE
    # removal (which also changes "I'm free" and "Carefree").
    name = re.sub(r'^\s*\(BEAT(?:\s+[^)]*)?\)\s*', '', title, flags=re.I)
    name = re.sub(r'\[[^\]]*\]', ' ', name)
    name = re.sub(r'\s+[-–—|]\s+(?:\d{2,3}(?:\.\d+)?\s*bpm\b|key\b).*$', '', name, flags=re.I)
    return clean_name(name)


def variants(track, profile):
    return previous.variants(track, profile, name=catalog_name(track['title']))
