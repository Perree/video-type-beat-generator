"""Channel eligibility only; selection tags are independent of SEO metadata."""
from core.beat_afro import is_afro
from core.beat_matwyre import SELECTION as MATWYRE, matches as matwyre_matches
from core.beat_guitar import SELECTION as GUITAR, matches as guitar_matches
import re


class SelectionChanged(ValueError):
    pass


class TrackNotMatching(ValueError):
    pass


def selection_tags(channel):
    excluded_track_ids(channel)
    values = channel.get('selection_tags', [])
    if (type(values) is not list or len(values) > 40
            or any(type(tag) is not str or not tag.strip() or len(tag) > 100
                   for tag in values)):
        raise ValueError('invalid_selection_tags')
    return {tag.strip().casefold() for tag in values}


def excluded_track_ids(channel):
    values = channel.get('excluded_track_ids', [])
    if (type(values) is not list or len(values) > 5000 or
            any(type(tid) is not str or not re.fullmatch(r'TK[0-9]{1,20}', tid) for tid in values)):
        raise ValueError('invalid_excluded_track_ids')
    return set(values)


def eligible_tracks(channel, tracks):
    wanted = selection_tags(channel)
    excluded = excluded_track_ids(channel)
    result = []
    for track in tracks:
        if not track.get('active', True) or track.get('id') in excluded:
            continue
        tags = track.get('tags', [])
        if GUITAR in wanted:
            if guitar_matches(track):
                result.append(track)
            continue
        if MATWYRE in wanted:
            if matwyre_matches(track):
                result.append(track)
            continue
        if not wanted or (type(tags) is list and any(
                type(tag) is str and (tag.strip().casefold() in wanted
                    or ('afro*' in wanted and is_afro(tag))) for tag in tags)):
            result.append(track)
    return result


def require_track(channel, track, track_id=None):
    # Legacy callers may not provide metadata: retain their old unfiltered contract.
    if (selection_tags(channel) or excluded_track_ids(channel)) and (type(track) is not dict
            or (track_id is not None and track.get('id') != track_id)
            or not eligible_tracks(channel, [track])):
        raise TrackNotMatching('track_not_matching')


def ensure_selection(cloud, channel):
    """Abort this run if its channel's eligibility rules changed remotely."""
    config, rev = cloud.read('config')
    if rev is None:
        raise ValueError('beat_config_missing')
    current = next((ch for ch in config['channels'] if ch['id'] == channel['id']), None)
    if (current is None or selection_tags(current) != selection_tags(channel)
            or excluded_track_ids(current) != excluded_track_ids(channel)):
        raise SelectionChanged('selection_changed')


def selection_fence(cloud, channel, fence=None):
    """Extend the renderer's existing lease checkpoints, preserving its fence."""
    def checkpoint():
        if fence is not None:
            fence()
        ensure_selection(cloud, channel)
    return checkpoint
