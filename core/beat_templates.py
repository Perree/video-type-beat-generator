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
            if token in value:
                if not isinstance(replacement, str):
                    raise ValueError('channel_template_value_invalid')
                value = value.replace(token, replacement)
        if set(re.findall(r'\{([^{}]+)\}', value)) - {'name', 'url'}:
            raise ValueError('channel_template_placeholder_unsupported')
        return value
    profile.update(title_template=compile_template(title), description=compile_template(description))
    candidate = dict(channel, seo=profile)
    manual_profile(candidate)
    channel['seo'] = profile
    return channel
