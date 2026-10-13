"""Fresh remote pause and publication deadline checks immediately before insert."""
from core.beat_schema import instant


class ChannelPaused(ValueError):
    pass


class PublicationExpired(ValueError):
    pass


def active_channel(cloud, channel_id, expected_owner=None):
    config, rev = cloud.read('config')
    if rev is None:
        raise ValueError('beat_config_missing')
    channel = next((ch for ch in config['channels'] if ch['id'] == channel_id), None)
    if channel is None or not channel['active']:
        raise ChannelPaused('channel_paused')
    if expected_owner is not None and channel.get('youtube_channel_id') != expected_owner:
        raise ValueError('youtube_destination_changed')
    return channel


def future_slot(job, clock):
    if instant(job['slot']) <= instant(clock()):
        raise PublicationExpired('publication_slot_expired')
