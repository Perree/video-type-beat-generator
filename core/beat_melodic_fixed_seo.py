"""Fixed channel title; retain the existing per-track tags and description."""
from core import beat_melodic_seo

MODE = 'melodic_fixed_v1'
TOKENS = beat_melodic_seo.TOKENS


def variants(track, profile):
    option = beat_melodic_seo.variants(track, profile)[0]
    tags = option['tags']
    return [dict(title=option['title'], tags=tags[i:] + tags[:i])
            for i in range(max(1, len(tags)))]


description = beat_melodic_seo.description
