from copy import deepcopy
import pytest
from core.beat_seo import build_snapshot, validate_snapshot
from core.beat_selection import eligible_tracks


def channel():
    return {'id': 'latin', 'selection_tags': ['latin trap', 'trap latino', 'reggaeton', 'trap r&b'],
            'seo': {'title_mode': 'latin_v1', 'title_template': '(FREE) {artists} - "{name}" | {style} Type Beat 2026',
                    'description': '{artists} | {style} Type Beat\n{bpm} BPM - {key}\nDownload: {url}',
                    'tags': ['type beat']}}


def snapshot(tags, title='"Noche" - 94bpm - key C Major', tid='TK123', previous=None):
    track = {'id': tid, 'title': title, 'tags': tags}
    job = {'id': 'j', 'channel': 'latin', 'track_id': tid, 'cycle': 2 if previous else 1}
    s, _ = build_snapshot(job, track, channel(), '2026-11-02T10:00:00-03:00', previous_selected=previous)
    assert validate_snapshot(s, job) == s
    return s


@pytest.mark.parametrize('tags,style', [(['reggaeton'], 'Reggaeton'), (['trap latino'], 'Latin Trap'),
    (['latin trap'], 'Latin Trap'), (['trap r&b'], 'Trap/R&B'), (['reggaeton rnb'], 'Reggaeton R&B')])
def test_only_matching_style_and_aligned_description(tags, style):
    s = snapshot(tags)
    assert f'| {style} Type Beat' in s['selected']['title']
    assert f'| {style} Type Beat' in s['selected']['description']
    assert '94 BPM - C Major' in s['selected']['description']
    assert '{url}' in s['selected']['description']


def test_stable_variation_repeat_and_missing_metadata():
    s = snapshot(['reggaeton'], title='Noche')
    assert s == snapshot(['reggaeton'], title='Noche')
    assert 'BPM' not in s['selected']['description']
    repeated = snapshot(['reggaeton'], title='Noche', previous=s['selected'])
    assert repeated['selected']['title'] != s['selected']['title']
    titles = {snapshot(['reggaeton'], tid=f'TK{i}')['selected']['title'] for i in range(20)}
    assert len(titles) > 1


def test_artist_tags_long_names_and_tamper_rejected():
    s = snapshot(['latin trap', 'Feid'], title='N' * 200)
    assert 'Feid' in s['selected']['title']
    assert len(s['selected']['title']) <= 100
    bad = deepcopy(s)
    bad['selected']['title'] = bad['selected']['title'].replace('Latin Trap', 'Reggaeton')
    with pytest.raises(ValueError):
        validate_snapshot(bad, {'id': 'j', 'channel': 'latin', 'track_id': 'TK123', 'cycle': 1})


def test_unrelated_beats_never_enter_selection():
    tracks = [{'id': 'a', 'tags': ['rnb']}, {'id': 'b', 'tags': ['trap latino']}]
    assert eligible_tracks(channel(), tracks) == [tracks[1]]
    with pytest.raises(ValueError, match='latin_style_missing'):
        snapshot(['rnb'])


def test_real_catalog_emoji_with_joiner_is_supported():
    s = snapshot(['reggaeton'], title='Spaceman 👨\u200d🚀🚀')
    assert 'Spaceman' in s['selected']['title']


def test_latin_templates_survive_registry_recompilation():
    from core.beat_templates import apply_channel_templates
    ch = channel()
    ch['use_channel_templates'] = True
    apply_channel_templates(ch, {'title_template': ch['seo']['title_template'],
                                'description_template': ch['seo']['description']})
    assert ch['seo']['title_mode'] == 'latin_v1'
