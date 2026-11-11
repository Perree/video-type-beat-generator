"""Deterministic SEO options. Report text can only match existing tag options."""
from copy import deepcopy
import hashlib
import json
import re
import unicodedata
from core.beat_names import clean_name
from core.beat_title import parse_track
from core import beat_latin_seo, beat_house_seo, beat_indie_seo, beat_club_seo, beat_club_seo_v2, beat_melodic_seo
from core import beat_melodic_fixed_seo
from core import beat_rnb_seo
from core import beat_matwyre_seo
from core import beat_afro_seo
from core import beat_latin_seo_v2
from core import beat_guitar_seo
from core import beat_koena_seo
from core import beat_latin_taimet_seo
from core import beat_latin_dysmo_seo
from core import beat_latin_dysmo_default_seo
from core import beat_latin_dysmo_afro_seo
from core import beat_sad_seo
from core import beat_emotional_house_seo
from core import beat_emotional_house_seo_v2
from core import beat_murray_seo
from core.beat_seo_report import fields, text, texts, moment, parse_report, validate_report


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


PLACEHOLDERS = ('{name}', '{url}', '{music_info}')
# Opt-in title modes: module and the placeholders its title template must contain.
MODES = {beat_latin_seo.MODE: (beat_latin_seo, ('{artists}', '{style}')),
         beat_emotional_house_seo.MODE: (beat_emotional_house_seo, ('{style}', '{detail}')),
         beat_emotional_house_seo_v2.MODE: (beat_emotional_house_seo_v2, ('{style}', '{detail}')),
         beat_sad_seo.MODE: (beat_sad_seo, ('{style}',)),
         beat_guitar_seo.MODE: (beat_guitar_seo, ('{style}',)),
         beat_koena_seo.MODE: (beat_koena_seo, ('{style}',)),
         beat_latin_seo_v2.MODE: (beat_latin_seo_v2, ('{style}', '{detail}')),
         beat_latin_taimet_seo.MODE: (beat_latin_taimet_seo, ('{style}',)),
         beat_latin_dysmo_seo.MODE: (beat_latin_dysmo_seo, ('{style}', '{detail}')),
         beat_latin_dysmo_default_seo.MODE: (beat_latin_dysmo_default_seo, ('{style}', '{detail}')),
         beat_latin_dysmo_afro_seo.MODE: (beat_latin_dysmo_afro_seo, ('{style}', '{detail}')),
         beat_afro_seo.MODE: (beat_afro_seo, ('{style}',)),
         beat_house_seo.MODE: (beat_house_seo, ('{style}',)),
         beat_club_seo.MODE: (beat_club_seo, ('{style}',)),
         beat_club_seo_v2.MODE: (beat_club_seo_v2, ('{style}', '{detail}')),
         beat_indie_seo.MODE: (beat_indie_seo, ('{style}',)),
         beat_melodic_seo.MODE: (beat_melodic_seo, ('{style}',)),
         beat_melodic_fixed_seo.MODE: (beat_melodic_fixed_seo, ()),
         beat_murray_seo.MODE: (beat_murray_seo, ()),
         beat_rnb_seo.MODE: (beat_rnb_seo, ('{style}',)),
         beat_matwyre_seo.MODE: (beat_matwyre_seo, ('{style}',))}


def _mode(profile):
    entry = MODES.get(profile.get('title_mode'))
    return entry[0] if entry else None


def _plain(value, mode=None):
    for token in PLACEHOLDERS + (mode.TOKENS if mode else ()):
        value = value.replace(token, 'x')
    return value


def manual_profile(channel):
    cid = text(channel.get('id'), 200)
    profile = deepcopy(channel.get('seo', {
        'tags': channel.get('tags', []), 'description': ''}))
    # title_template is optional so snapshots created before it existed stay valid.
    fields(profile, ('tags', 'description') + (('title_template',) if 'title_template' in profile else ())
           + (('title_mode',) if 'title_mode' in profile else ()))
    if 'title_mode' in profile and (profile['title_mode'] not in MODES
            or not all(token in profile.get('title_template', '')
                       for token in MODES[profile['title_mode']][1])):
        raise ValueError('seo_title_mode_invalid')
    texts(profile['tags'])
    description = profile['description']
    if description != '':
        if type(description) is not str:
            raise ValueError('seo_text_invalid')
        text(_plain(description, _mode(profile)).replace(chr(10), ' '), 4000)
    if 'title_template' in profile:
        template = profile['title_template']
        if type(template) is not str or '{name}' not in template:
            raise ValueError('seo_text_invalid')
        text(_plain(template, _mode(profile)), 90)
    return cid, profile


def beat_url(track):
    """BeatStars page URL: slug(title)-numeric id (matches all public catalog tracks)."""
    ascii_title = unicodedata.normalize('NFKD', track['title']).encode('ascii', 'ignore').decode().lower()
    return f'https://www.beatstars.com/beat/{re.sub("[^a-z0-9]+", "-", ascii_title).strip("-")}-{track["id"][2:]}'


def render(value, track, link=None):
    """{url} stays a placeholder (resolved to the short link at upload) unless a link is given."""
    value = value.replace('{name}', clean_name(track['title']))
    return value.replace('{url}', link) if link else value


def track_input(track):
    tid = track.get('id')
    if type(tid) is not str or not re.fullmatch(r'TK[0-9]{1,20}', tid):
        raise ValueError('seo_track_invalid')
    title = track.get('title')
    if isinstance(title, str):
        # Catalog names may contain hearts or markup. Normalize only this input;
        # reports, manual templates and tags keep their strict text boundary.
        title = title.replace('<3', '♥').replace('\u200d', '')
        title = re.sub(r'[<>{}]', '', title).strip()
    result = {'id': tid, 'title': text(title, 500), 'tags': texts(track.get('tags'))}
    # BPM, key and collaborators come from the BeatStars page; optional so old snapshots stay valid.
    bpm = track.get('bpm')
    if type(bpm) in (int, float) and 0 < bpm < 1000:
        result['bpm'] = bpm
    key = track.get('key')
    if isinstance(key, str) and key.strip():
        result['key'] = re.sub(r'[<>{}\x00-\x1f]', '', key).strip()[:40]
    people = [re.sub(r'[<>{}\x00-\x1f]', '', n).strip()[:100] for n in track.get('collaborators') or ()
              if isinstance(n, str)]
    people = [n for n in dict.fromkeys(people) if n and n.casefold() != 'matwyre'][:10]
    if people:
        result['collaborators'] = people
    return result


def candidates(track, profile, scores, job):
    mode = _mode(profile)
    if mode and mode is not beat_murray_seo:
        return mode.variants(track, profile)
    template = profile.get('title_template')
    if template:
        # Fixed title and tag list; only the beat name and link change. Repeats rotate the tag order.
        title = mode.title(track, profile, job['slot']) if mode else render(template, track)
        if len(title) > 100:
            raise ValueError('seo_title_too_long')
        base = list(profile['tags'])
        return [{'title': title, 'tags': base[i:] + base[:i]} for i in range(max(1, len(base)))]
    # Intersection prevents unrelated manual artists or report keywords being invented.
    allowed = {v.casefold() for v in profile['tags']}
    tags = [v for v in track['tags'] if v.casefold() in allowed]
    tags.sort(key=lambda v: (-scores.get(v.casefold(), 0), v.casefold()))
    options = []
    for tag in tags:
        title = f'{tag} Type Beat | {track["title"]}'
        if len(title) <= 100:
            options.append({'title': title, 'tags': [tag]})
    if not options:
        title = track['title']
        if len(title) > 100:
            raise ValueError('seo_title_too_long')
        options.append({'title': title, 'tags': []})
    return options


def music_info(track):
    """«BPM: 160» / «Key: A Sharp Minor» según el título del beat en BeatStars (solo lo que traiga)."""
    info = parse_track(track)
    return '\n'.join(label + info[key] for label, key in (('BPM: ', 'bpm'), ('Key: ', 'key')) if info[key])


def _with_music_info(value, track):
    """Rellena {music_info} en cualquier canal; sin datos quita el token y su línea en blanco."""
    if '{music_info}' not in value:
        return value
    info = music_info(track)
    if not info:
        value = re.sub(r'\n\n\{music_info\}(?=\n\n)', '', value)
        value = re.sub(r'^\{music_info\}\n+|\n*\{music_info\}$', '', value)
    return value.replace('{music_info}', info)


def _with_collaborators(value, track):
    """Append collaborators to the producer credit, inside parentheses when present."""
    people = track.get('collaborators')
    if not people:
        return value
    credits = ''.join(' x ' + name for name in people)
    return re.sub(r'(?m)^(?:Prod\. MatWyre\b(?! x )|\(prod\. matwyre(?=\)$))',
                  lambda match: match.group() + credits, value)


def description(profile, track, option, link=None, *, legacy=False):
    mode = _mode(profile)
    if legacy and mode is beat_matwyre_seo:
        value = mode.description(profile, track, option, legacy=True)
    else:
        value = mode.description(profile, track, option) if mode else profile['description']
    return render(_with_collaborators(_with_music_info(value, track), track), track, link)


def build_snapshot(job, track, channel, now, payload=None, cached=None, *, previous_selected=None):
    """No network, LLM, report templates, eval, or free-text recommendations."""
    now = moment(now).isoformat()
    cid, profile = manual_profile(channel)
    track = track_input(track)
    if job.get('track_id') != track['id'] or job.get('channel') != cid:
        raise ValueError('seo_job_mismatch')
    fingerprint = digest({'channel': cid, 'manual': profile})
    report, source = None, 'manual'
    if payload is not None:
        try:
            report = parse_report(payload, cid, now)
            source = 'report'
        except ValueError:
            pass
    if report is None and cached is not None:
        try:
            fields(cached, ('manual_hash', 'report'))
            if cached['manual_hash'] != fingerprint:
                raise ValueError()
            report = validate_report(deepcopy(cached['report']), cid, now, max_age_days=30)
            source = 'last_good'
        except Exception:
            report = None
    # Discard all report strings; normalized scores refer ONLY to current allowlisted tags.
    allowed = {v.casefold() for v in profile['tags']} & {v.casefold() for v in track['tags']}
    scores = {row['tag'].casefold(): row['score'] for row in report['keywords']
              if row['tag'].casefold() in allowed} if report else {}
    options = candidates(track, profile, scores, job)
    eligible = [option for option in options
                if previous_selected is None or
                (option['title'], option['tags']) !=
                (previous_selected['title'], previous_selected['tags'])]
    if not eligible:
        raise ValueError('repeat_seo_exhausted')
    snapshot = {'schema_version': 1, 'job_id': job['id'], 'channel_id': cid,
        'track': track, 'manual': profile, 'as_of': now, 'source': source,
        'report_hash': digest(report) if report else None,
        'scores': scores, 'candidates': options,
        'selected': dict(eligible[0], description=description(profile, track, eligible[0]))}
    if _mode(profile) in (beat_rnb_seo, beat_matwyre_seo):
        snapshot['experiment'] = _mode(profile).experiment(track, profile, snapshot['selected'])
    snapshot['sha256'] = digest(snapshot)
    cache = {'manual_hash': fingerprint, 'report': deepcopy(report)} if source == 'report' else None
    return snapshot, cache


def _matches_options(snapshot, job, track, profile, options, *, legacy=False):
    # Pre-review snapshots repeated the description in every option.
    if snapshot['candidates'] != options:
        expanded = [dict(option, description=description(profile, track, option, legacy=legacy))
                    for option in options]
        if snapshot['candidates'] != expanded:
            return False
    chosen = options if job['cycle'] > 1 else options[:1]
    # Early snapshots used the full page URL in place of the upload placeholder.
    return any(snapshot['selected'] == dict(option, description=description(
        profile, track, option, link, legacy=legacy))
        for option in chosen for link in (None, beat_url(track)))


def validate_snapshot(snapshot, job):
    fields(snapshot, ('schema_version', 'job_id', 'channel_id', 'track', 'manual', 'as_of',
                      'source', 'report_hash', 'scores', 'candidates', 'selected', 'sha256')
           + (('experiment',) if 'experiment' in snapshot else ()))
    if type(snapshot['schema_version']) is not int or snapshot['schema_version'] != 1:
        raise ValueError('seo_snapshot_invalid')
    if snapshot['job_id'] != job['id'] or snapshot['channel_id'] != job['channel']:
        raise ValueError('seo_snapshot_invalid')
    moment(snapshot['as_of'])
    fields(snapshot['track'], ('id', 'title', 'tags') + tuple(
        k for k in ('bpm', 'key', 'collaborators') if k in snapshot['track']))
    track = track_input(snapshot['track'])
    if track['id'] != job['track_id']:
        raise ValueError('seo_snapshot_invalid')
    _, profile = manual_profile({'id': job['channel'], 'seo': snapshot['manual']})
    scores = snapshot['scores']
    allowed = {v.casefold() for v in profile['tags']} & {v.casefold() for v in track['tags']}
    if type(scores) is not dict or not set(scores) <= allowed:
        raise ValueError('seo_snapshot_invalid')
    for value in scores.values():
        if type(value) not in (int, float) or not 0 <= value <= 100:
            raise ValueError('seo_snapshot_invalid')
    if snapshot['source'] not in ('manual', 'report', 'last_good'):
        raise ValueError('seo_snapshot_invalid')
    rh = snapshot['report_hash']
    if ((snapshot['source'] == 'manual' and (rh is not None or scores))
            or (snapshot['source'] != 'manual' and (type(rh) is not str or not re.fullmatch('[0-9a-f]{64}', rh)))):
        raise ValueError('seo_snapshot_invalid')
    body = {k: v for k, v in snapshot.items() if k != 'sha256'}
    if snapshot['sha256'] != digest(body):
        raise ValueError('seo_snapshot_invalid')

    mode = _mode(profile)
    legacy = not _matches_options(snapshot, job, track, profile, candidates(track, profile, scores, job))
    # These modes changed before receiving distinct identifiers. Replay both known outputs.
    if legacy and (mode not in (beat_indie_seo, beat_matwyre_seo) or len(snapshot['track']) != 3
                   or not _matches_options(snapshot, job, track, profile,
                                           mode.variants(track, profile, legacy=True), legacy=True)):
        raise ValueError('seo_snapshot_invalid')
    if mode in (beat_rnb_seo, beat_matwyre_seo):
        options = {'legacy': True} if legacy else {}
        if snapshot.get('experiment') != mode.experiment(track, profile, snapshot['selected'], **options):
            raise ValueError('seo_experiment_invalid')
    elif 'experiment' in snapshot:
        raise ValueError('seo_experiment_invalid')
    return deepcopy(snapshot)
