"""Stable Koena-shaped titles with each beat's actual artists and instruments."""
import re
from core.beat_guitar import context, SAD, EMOTIONAL, EMO, PAIN, MELODIC
from core.beat_names import clean_name
from core.beat_title import parse, parse_track

MODE = 'guitar_v1'
TOKENS = ('{style}', '{title}', '{music_info}', '{credits}', '{guitar_hashtags}')


def variants(track, profile):
    info = context(track)
    template = profile['title_template'].replace('{style}', info['style'])
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    name = clean_name(parse(track['title'])['name'])
    title = template.replace('{name}', name[:budget].rstrip())
    keywords = [info['style'].lower() + ' type beat']
    keywords += [a.lower() + ' type beat' for a in info['artists']]
    if info['guitar']:
        keywords += ['guitar type beat', 'guitar beat']
        if any('trap' in t for t in info['tags']):
            keywords += ['guitar trap type beat', 'trap guitar type beat']
    for values, label in ((SAD, 'sad'), (EMOTIONAL, 'emotional'),
                          (EMO, 'emo'), (PAIN, 'pain'), (MELODIC, 'melodic trap')):
        if info['tags'] & values:
            keywords.append(label + (' guitar' if info['guitar'] and label in ('sad', 'emotional') else '') + ' type beat')
    for values, label in (({'acoustic guitar', 'acoustic gtr'}, 'acoustic guitar'),
                          ({'elec gtr', 'electric guitar'}, 'electric guitar')):
        if info['tags'] & values:
            keywords.append(label + ' type beat')
    tags = []
    for tag in dict.fromkeys(keywords + profile['tags']):
        candidate = tags + [tag]
        if len(candidate) <= 40 and len(','.join(candidate)) + 2 * sum(' ' in t for t in candidate) <= 450:
            tags.append(tag)
    return [{'title': title, 'tags': tags[i:] + tags[:i]} for i in range(len(tags))]


def description(profile, track, option):
    info = context(track)
    music = parse_track(track)
    technical = '\n'.join(label + music[key] for label, key in [('BPM: ', 'bpm'), ('Key: ', 'key')] if music[key])
    authors = re.search(r'\((?:prod\.?\s+([^)]{1,250})|((?:@?matwyre)\s+x\s+[^)]{1,230}))\)', track['title'], re.I)
    credits = ('Prod. ' + (authors.group(1) or authors.group(2)).strip() if authors else
               'Prod. MatWyre. Full producer credits on the original beat page.')
    hashtags = ['#' + re.sub(r'[^A-Za-z0-9]', '', a) + 'TypeBeat' for a in info['artists']]
    hashtags += ['#GuitarTypeBeat' if info['guitar'] else '#TypeBeat', '#MatWyre']
    result = profile['description']
    for token, value in (('{title}', option['title']), ('{style}', info['style']),
                         ('{music_info}', technical), ('{credits}', credits),
                         ('{guitar_hashtags}', ' '.join(hashtags[:3]))):
        result = result.replace(token, value)
    return result
