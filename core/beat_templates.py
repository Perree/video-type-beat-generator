"""Opt-in bridge from saved channel templates to the Beats worker SEO profile."""
from copy import deepcopy
import re
from core.beat_seo import manual_profile


def apply_channel_templates(channel, saved):
    enabled = channel.get('use_channel_templates', False)
    if type(enabled) is not bool:
        raise ValueError('invalid_channel_template_source')
    if not enabled:
        return channel
    if not isinstance(saved, dict):
        raise ValueError('channel_templates_missing')
    title, description = saved.get('title_template'), saved.get('description_template')
    if not isinstance(title, str) or not title.strip() or not isinstance(description, str):
        raise ValueError('channel_templates_missing')
    profile = deepcopy(channel.get('seo', {'tags': channel.get('tags', []), 'description': ''}))
    def compile_template(value):
        value = value.replace('{beatstars_url}', '{url}')
        for token, replacement in (
            ('{channel}', channel['id']), ('{socials}', saved.get('socials', '')),
            ('{hashtags}', saved.get('hashtags', '')), ('{tags}', ', '.join(profile['tags']))):
            if token == '{hashtags}' and profile.get('title_mode') == 'matwyre_v1':
                continue
            if token in value:
                if not isinstance(replacement, str):
                    raise ValueError('channel_template_value_invalid')
                value = value.replace(token, replacement)
        allowed = {'name', 'url', 'music_info'}
        if profile.get('title_mode') == 'latin_v1':
            allowed.update(('artists', 'style', 'bpm', 'key'))
        elif profile.get('title_mode') in ('latin_v2', 'latin_taimet_v1', 'latin_dysmo_v1', 'latin_dysmo_v2', 'latin_dysmo_v3'):
            allowed.update(('style', 'detail', 'context', 'music_info', 'latin_hashtags'))
        elif profile.get('title_mode') in ('house_v1', 'indie_v1', 'club_v1'):
            allowed.add('style')
        elif profile.get('title_mode') == 'club_v2':
            allowed.update(('style', 'detail'))
        elif profile.get('title_mode') in ('emotional_house_v1', 'emotional_house_v2'):
            allowed.update(('style', 'detail', 'title', 'music_info', 'credits', 'house_hashtags'))
        elif profile.get('title_mode') == 'afro_v1':
            allowed.update(('style', 'title', 'technical', 'afro_hashtags'))
        elif profile.get('title_mode') in ('guitar_v1', 'koena_v1'):
            allowed.update(('style', 'title', 'music_info', 'credits', 'guitar_hashtags'))
        elif profile.get('title_mode') == 'sad_melodic_v1':
            allowed.update(('style', 'title', 'music_info', 'sad_hashtags'))
        elif profile.get('title_mode') in ('rnb_test_v1', 'rnb_test_v2'):
            allowed.update(('style', 'context', 'music_info'))
        elif profile.get('title_mode') == 'matwyre_v1':
            allowed.update(('style', 'detail', 'context', 'music_info', 'credits', 'hashtags'))
        if set(re.findall(r'\{([^{}]+)\}', value)) - allowed:
            raise ValueError('channel_template_placeholder_unsupported')
        return value
    profile.update(title_template=compile_template(title), description=compile_template(description))
    candidate = dict(channel, seo=profile)
    manual_profile(candidate)
    channel['seo'] = profile
    return channel
