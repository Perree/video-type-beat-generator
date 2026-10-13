"""Deterministic SEO options. Report text can only match existing tag options."""
from copy import deepcopy
import hashlib
import json
import re
import unicodedata
from core.beat_names import clean_name
from core.beat_seo_report import fields, text, texts, moment, parse_report, validate_report


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()


PLACEHOLDERS = ('{name}', '{url}')


def _plain(value):
    for token in PLACEHOLDERS:
        value = value.replace(token, 'x')
    return value


def manual_profile(channel):
    cid = text(channel.get('id'), 200)
    profile = deepcopy(channel.get('seo', {
        'tags': channel.get('tags', []), 'description': ''}))
    # title_template is optional so snapshots created before it existed stay valid.
    fields(profile, ('tags', 'description') + (('title_template',) if 'title_template' in profile else ()))
    texts(profile['tags'])
    description = profile['description']
    if description != '':
        if type(description) is not str:
            raise ValueError('seo_text_invalid')
        text(_plain(description).replace(chr(10), ' '), 4000)
    if 'title_template' in profile:
        template = profile['title_template']
        if type(template) is not str or '{name}' not in template:
            raise ValueError('seo_text_invalid')
        text(_plain(template), 90)
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
    return {'id': tid, 'title': text(track.get('title'), 500), 'tags': texts(track.get('tags'))}


def candidates(track, profile, scores):
    template = profile.get('title_template')
    if template:
        # Fixed title and tag list; only the beat name and link change. Repeats rotate the tag order.
        title = render(template, track)
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
    options = candidates(track, profile, scores)
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
        'selected': dict(eligible[0], description=render(profile['description'], track))}
    snapshot['sha256'] = digest(snapshot)
    cache = {'manual_hash': fingerprint, 'report': deepcopy(report)} if source == 'report' else None
    return snapshot, cache


def validate_snapshot(snapshot, job):
    fields(snapshot, ('schema_version', 'job_id', 'channel_id', 'track', 'manual', 'as_of',
                      'source', 'report_hash', 'scores', 'candidates', 'selected', 'sha256'))
    if type(snapshot['schema_version']) is not int or snapshot['schema_version'] != 1:
        raise ValueError('seo_snapshot_invalid')
    if snapshot['job_id'] != job['id'] or snapshot['channel_id'] != job['channel']:
        raise ValueError('seo_snapshot_invalid')
    moment(snapshot['as_of'])
    fields(snapshot['track'], ('id', 'title', 'tags'))
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
    options = candidates(track, profile, scores)
    # Pre-review v1 snapshots repeated the manual description in every option.
    # Accept that equivalent encoding on replay; new snapshots store it once.
    legacy = [dict(option, description=render(profile['description'], track)) for option in options]
    chosen = options if job['cycle'] > 1 else options[:1]
    # Early snapshots stored the page URL instead of the {url} placeholder.
    selections = [dict(option, description=render(profile['description'], track, link))
                  for option in chosen for link in (None, beat_url(track))]
    if (snapshot['candidates'] != options and snapshot['candidates'] != legacy
            or snapshot['selected'] not in selections):
        raise ValueError('seo_snapshot_invalid')
    body = {k: v for k, v in snapshot.items() if k != 'sha256'}
    if snapshot['sha256'] != digest(body):
        raise ValueError('seo_snapshot_invalid')
    return deepcopy(snapshot)
