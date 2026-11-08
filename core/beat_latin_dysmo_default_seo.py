"""User-chosen editorial default for Latin beats without tagged artists."""
from core import beat_latin_dysmo_seo as dysmo
from core import beat_latin_seo_v2 as latin

MODE = 'latin_dysmo_v2'
TOKENS = latin.TOKENS
DEFAULT_ARTISTS = ('bad bunny', 'mora')


def variants(track, profile):
    _, _, artists = latin.context(track)
    if not artists:
        # Editorial references explicitly requested by the user, not source tags.
        track = dict(track, tags=list(track['tags']) + list(DEFAULT_ARTISTS))
    return dysmo.variants(track, profile)


def description(profile, track, option):
    # Keep factual musical context and source tags unchanged in descriptions.
    return latin.description(profile, track, option)
