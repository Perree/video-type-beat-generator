"""Phase 1 entry point, independent from the existing UI and local audio library."""
from core.beat_http import BeatError
from core.beat_source import BeatStarsSource, profile_username


def sync_configured(app_config, catalog, source=None):
    """Read beat_automation.beatstars_profile_url; never rewrite app configuration."""
    try:
        url = app_config["beat_automation"]["beatstars_profile_url"]
    except (KeyError, TypeError):
        raise BeatError("profile_not_configured") from None
    profile_username(url)
    snapshot = (source or BeatStarsSource()).scan(url)
    return catalog.apply(snapshot)
