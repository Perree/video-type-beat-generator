"""Klein-shaped genre packaging, with the producer's own names and metadata."""
import re
from core.beat_latin_seo import normalized
from core.beat_names import clean_name
from core.beat_title import parse, parse_track

MODE = 'emotional_house_v1'
TOKENS = ('{style}', '{detail}', '{title}', '{music_info}', '{credits}', '{house_hashtags}')
STYLES = (
    ('Deep House', {'deep house', 'deep house type beat', 'deephouse', 'melodic deep house', 'sad deep house'}),
    ('Afro House', {'afro house', 'afrohouse', 'afro house type beat'}),
    ('Tech House', {'tech house', 'tech house type beat'}),
    ('House', {'house', 'house type beat', 'melodic house', 'emotional house', 'sad house', 'club house', 'latin house', 'reggaeton house'}),
    ('Jersey Club', {'jersey', 'jersey club', 'jersey club type beat', 'jersey type beat'}),
)
PARTNERS = (
    ('Jersey Club', {'jersey', 'jersey club', 'jersey club type beat', 'jersey type beat'}),
    ('Reggaeton', {'reggaeton', 'reggaeton type beat', 'reggaeton house'}),
    ('Brazilian Funk', {'brazilian funk', 'brazilian funk type beat'}),
    ('Techno', {'techno', 'techno type beat'}),
    ('Club', {'club', 'club type beat', 'club house', 'club banger', 'club banger type beat'}),
)


def labels(track):
    tags = {normalized(t) for t in track['tags']}
    base = next((name for name, aliases in STYLES if tags & aliases), None)
    if base is None:
        raise ValueError('emotional_house_style_missing')
    partner = next((name for name, aliases in PARTNERS if name != base and tags & aliases), None)
    style = base + (' x ' + partner if partner else '')
    detail = ('Sad Deep House Instrumental' if base == 'Deep House' and tags & {'sad', 'sad deep house'} else
              'Melodic Club Instrumental' if tags & {'emotional', 'melodic', 'melodic deep house', 'melodic house', 'emotional house'} else
              'EDM Club Banger Instrumental' if tags & {'club banger', 'club banger type beat'} else
              'EDM Deep House Instrumental' if base == 'Deep House' else base + ' Instrumental')
    return base, partner, style, detail


def variants(track, profile, *, name=None):
    base, partner, style, detail = labels(track)
    template = profile['title_template'].replace('{style}', style).replace('{detail}', detail)
    budget = 100 - len(template.replace('{name}', ''))
    if budget < 12:
        template = profile['title_template'].replace('{style}', style).replace('{detail}', base + ' Instrumental')
        budget = 100 - len(template.replace('{name}', ''))
    if budget < 1:
        raise ValueError('seo_title_too_long')
    name = clean_name(parse(track['title'])['name']) if name is None else name
    title = template.replace('{name}', name[:budget].rstrip())
    words = [f'{style.lower()} type beat', f'{base.lower()} type beat', f'{base.lower()} instrumental']
    if partner:
        words.append(f'{partner.lower()} type beat')
    words += profile['tags']
    tags, seen = [], set()
    for tag in words:
        candidate = tags + [tag]
        if (tag.casefold() not in seen and len(candidate) <= 40
                and len(','.join(candidate)) + 2 * sum(' ' in t for t in candidate) <= 450):
            tags.append(tag)
            seen.add(tag.casefold())
    return [{'title': title, 'tags': tags[i:] + tags[:i]} for i in range(len(tags))]


def description(profile, track, option):
    base, partner, style, detail = labels(track)
    music = parse_track(track)
    technical = '\n'.join(label + music[key] for label, key in [('BPM: ', 'bpm'), ('Key: ', 'key')] if music[key])
    authors = re.search(r'\((?:prod\.?\s+([^)]{1,250})|((?:@?matwyre)\s+x\s+[^)]{1,230}))\)', track['title'], re.I)
    credits = ('Prod. ' + (authors.group(1) or authors.group(2)).strip() if authors else
               'Prod. MatWyre. Full producer credits on the original beat page.')
    hashtags = ' '.join('#' + name.replace(' ', '') + 'Beat' for name in (base, partner) if name) + ' #TypeBeat'
    result = profile['description']
    for token, value in (('{title}', option['title']), ('{style}', style), ('{detail}', detail),
                         ('{music_info}', technical), ('{credits}', credits), ('{house_hashtags}', hashtags)):
        result = result.replace(token, value)
    return result
