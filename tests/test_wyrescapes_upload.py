"""WyreScapes Fase 3: subida programada (API de YouTube simulada, sin red)."""
import json
import os
import subprocess
from datetime import datetime, timezone

import pytest

from core import wyrescapes_upload as wu
from core.ffmpeg_util import resolve_tool

META = {'title': 'someone is still beside you.', 'description': 'rest now.\n\n#sleep',
        'tags': ['ambient', 'sleep music'], 'pinned_comment': 'what are you letting go of tonight?'}


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_next_publish_time_is_noon_argentina():
    slot = wu.next_publish_time(_utc(2026, 11, 22, 3, 0))  # 00:00 AR
    assert (slot.year, slot.month, slot.day, slot.hour) == (2026, 11, 22, 12)
    assert wu.publish_at_utc(slot) == '2026-11-22T15:00:00Z'


def test_next_publish_time_rolls_to_tomorrow_without_margin():
    assert wu.publish_at_utc(wu.next_publish_time(_utc(2026, 11, 22, 14, 30))) == \
        '2026-11-23T15:00:00Z'
    assert wu.publish_at_utc(wu.next_publish_time(_utc(2026, 11, 22, 14, 0))) == \
        '2026-11-22T15:00:00Z'  # 11:00 AR: 1 h de margen, sale hoy
    assert wu.publish_at_utc(wu.next_publish_time(_utc(2026, 11, 22, 20, 0))) == \
        '2026-11-23T15:00:00Z'


def test_description_starts_with_spotify_once():
    desc = wu.build_description('rest now.\n' + wu.SPOTIFY_URL + '\n#sleep')
    assert desc.splitlines()[0] == wu.SPOTIFY_URL
    assert desc.count(wu.SPOTIFY_URL) == 1 and 'rest now.' in desc
    assert wu.build_description('') == wu.SPOTIFY_URL


def test_validate_meta():
    meta = wu.validate_meta({'title': ' hola. ', 'tags': 'a, b,,c'})
    assert meta['title'] == 'hola.' and meta['tags'] == ['a', 'b', 'c']
    for bad in ({}, {'title': ''}, {'title': 'x' * 101}, {'title': 'a <b>'}, []):
        with pytest.raises(wu.UploadError):
            wu.validate_meta(bad)


@pytest.fixture
def setup(tmp_path):
    tokens = tmp_path / 'tokens'
    tokens.mkdir()
    (tokens / 'wyrescapes.json').write_text('{}')
    video = tmp_path / 'wyrescapes_1.mp4'
    video.write_bytes(b'video')
    image = tmp_path / 'img.jfif'
    image.write_bytes(b'img')
    calls = []

    def uploader(channel, path, title, description, **kw):
        calls.append(dict(kw, channel=channel, path=path, title=title, description=description))
        return {'youtube_id': 'abc123', 'url': 'https://youtu.be/abc123', 'thumbnail_error': ''}

    def thumb(img, out):
        open(out, 'wb').close()
        return out

    return dict(tokens=str(tokens), video=str(video), image=str(image), calls=calls,
                uploader=uploader, thumb=thumb, log=str(tmp_path / 'log.json'))


def _upload(s, channel=wu.CHANNEL_ID, **kw):
    slot = wu.next_publish_time(_utc(2026, 11, 22, 3, 0))
    return wu.upload_scheduled(s['video'], META, s['image'], slot, tokens_dir=s['tokens'],
                               log_path=s['log'], uploader=s['uploader'],
                               channel_check=lambda d: channel, thumb_maker=s['thumb'], **kw)


def test_upload_is_private_scheduled_with_thumbnail_comment_and_log(setup):
    entry = _upload(setup)
    call = setup['calls'][0]
    assert call['channel'] == wu.TOKEN_NAME and call['privacy'] == 'private'
    assert call['publish_at'] == '2026-11-22T15:00:00Z'
    assert call['description'].startswith(wu.SPOTIFY_URL)
    assert call['thumbnail'].endswith('wyrescapes_1.miniatura.jpg')
    assert call['tags'] == META['tags']
    with open(entry['pinned_comment_file'], encoding='utf-8') as fh:
        assert fh.read().strip() == META['pinned_comment']
    log = wu.load_log(setup['log'])
    assert log[0]['title'] == META['title'] and log[0]['youtube_id'] == 'abc123'
    assert log[0]['image'] == 'img.jfif'


def test_never_uploads_twice_the_same_video(setup):
    _upload(setup)
    with pytest.raises(wu.UploadError, match='ya se subió'):
        _upload(setup)
    assert len(setup['calls']) == 1


def test_refuses_token_of_another_channel(setup):
    with pytest.raises(wu.UploadError, match='otro|no de AllusionBeatz'):
        _upload(setup, channel='UCotroCanal')
    assert setup['calls'] == [] and wu.load_log(setup['log']) == []


def test_refuses_when_not_connected(setup):
    os.remove(os.path.join(setup['tokens'], 'wyrescapes.json'))
    with pytest.raises(wu.UploadError, match='no está conectado'):
        _upload(setup)


def test_failed_upload_leaves_no_log(setup):
    def boom(*a, **k):
        raise wu.youtube.YouTubeError('cuota')
    setup['uploader'] = boom
    with pytest.raises(wu.UploadError, match='cuota'):
        _upload(setup)
    assert wu.load_log(setup['log']) == []


def test_connect_saves_token_only_for_allusionbeatz(tmp_path):
    with pytest.raises(wu.UploadError, match='No se guardó'):
        wu.connect(str(tmp_path), authorize=lambda: ('{"t": 1}', 'Otro', 'UCotro'))
    assert not os.listdir(tmp_path)
    title = wu.connect(str(tmp_path), authorize=lambda: ('{"t": 1}', 'AllusionBeatz',
                                                         wu.CHANNEL_ID))
    assert title == 'AllusionBeatz'
    with open(tmp_path / 'wyrescapes.json', encoding='utf-8') as fh:
        assert json.load(fh) == {'t': 1}


@pytest.mark.skipif(not resolve_tool('ffmpeg'), reason='ffmpeg no disponible')
def test_thumbnail_is_1280x720_under_2mb(tmp_path):
    src = tmp_path / 'vertical.png'
    subprocess.run([resolve_tool('ffmpeg'), '-y', '-v', 'error', '-f', 'lavfi',
                    '-i', 'testsrc2=s=1080x1920', '-frames:v', '1', str(src)],
                   check=True, stdin=subprocess.DEVNULL)
    out = wu.make_thumbnail(str(src), str(tmp_path / 'thumb.jpg'))
    assert os.path.getsize(out) <= wu.THUMB_MAX_BYTES
    probe = subprocess.run([resolve_tool('ffprobe'), '-v', 'error', '-show_entries',
                            'stream=width,height', '-of', 'csv=p=0', out],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert probe.stdout.strip() == '1280,720'
