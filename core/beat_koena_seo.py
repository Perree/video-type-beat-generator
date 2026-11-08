"""User-selected Koena title families, independent of catalog selection tags."""
import hashlib
from core import beat_guitar_seo
from core.beat_names import clean_name
from core.beat_title import parse

MODE = 'koena_v1'
TOKENS = beat_guitar_seo.TOKENS
STYLES = ('Guitar x Hurricane Wisdom x Nino Paid', 'Guitar x Nino Paid x FattMack')


def variants(track, profile):
    # Stable allocation: the main reference family appears on three of four hashes.
    bucket = int(hashlib.sha256(track['id'].encode()).hexdigest()[:8], 16) % 4
    style = STYLES[1 if bucket == 0 else 0]
    template = profile['title_template'].replace('{style}', style)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    title = template.replace('{name}', clean_name(parse(track['title'])['name'])[:budget].rstrip())
    return [dict(option, title=title) for option in beat_guitar_seo.variants(track, profile)]


description = beat_guitar_seo.description
