"""WyreScapes Fase 4: flujo diario prepare → metadata → publish (render y subida simulados)."""
import json
import os
import random
from datetime import date, datetime, timezone

import pytest

from core import wyrescapes_daily as wd
from core import wyrescapes_upload as wu

DAY = date(2026, 11, 22)
GOOD = {'title': 'the one who never leaves your side.',
        'description': '31 minutes of calm, original music to rest, think, or fall asleep to.',
        'tags': list(wd.BASE_TAGS), 'pinned_comment': 'who would you sit with here?'}


def _base(tmp_path, tracks=3, images=2):
    base = tmp_path / 'WyreScapes'
    (base / 'Tracks').mkdir(parents=True)
    (base / 'Imagenes' / 'Refes').mkdir(parents=True)
    for i in range(tracks):
        (base / 'Tracks' / f't{i}.wav').write_bytes(b'x')
    for i in range(images):
        (base / 'Imagenes' / f'img{i}.jpg').write_bytes(b'x')
    (base / 'Imagenes' / 'Refes' / 'ref.jpg').write_bytes(b'x')
    return base


def _fake_render(calls):
    def renderer(paths, image, out, seconds):
        calls.append((paths, image, out, seconds))
        with open(out, 'wb') as fh:
            fh.write(b'mp4')
        return out
    return renderer


def _prepare(tmp_path, base, calls, record=True):
    return wd.prepare(DAY, base=str(base), track_state=str(tmp_path / 'ts.json'),
                      image_state=str(tmp_path / 'is.json'), log_path=str(tmp_path / 'log.json'),
                      renderer=_fake_render(calls), probe=lambda p: 600.0,
                      can_open=lambda p: True, record=record, rng=random.Random(1))


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


def test_prepare_builds_day_folder(tmp_path):
    base, calls = _base(tmp_path), []
    info = _prepare(tmp_path, base, calls)
    folder = base / 'Videos' / '2026-11-22'
    assert info['video'] == str(folder / 'wyrescapes_20261122.mp4')
    assert info['minutes'] == 30 and len(calls[0][0]) == 3
    assert 'Refes' not in info['image']
    assert (folder / 'imagen.txt').read_text(encoding='utf-8').strip() == info['image']
    meta = json.loads((folder / 'metadata.json').read_text(encoding='utf-8'))
    assert meta == wd.empty_metadata()
    assert 'someone is still beside you.' in info['used_titles']
    assert os.path.isfile(tmp_path / 'ts.json') and os.path.isfile(tmp_path / 'is.json')


def test_prepare_is_idempotent_and_keeps_metadata(tmp_path):
    base, calls = _base(tmp_path), []
    first = _prepare(tmp_path, base, calls)
    meta_path = base / 'Videos' / '2026-11-22' / 'metadata.json'
    meta_path.write_text(json.dumps(GOOD), encoding='utf-8')
    second = _prepare(tmp_path, base, calls)
    assert len(calls) == 1 and second['reused_render'] and second['image'] == first['image']
    assert json.loads(meta_path.read_text(encoding='utf-8')) == GOOD


def test_prepare_no_record_leaves_states(tmp_path):
    base, calls = _base(tmp_path), []
    _prepare(tmp_path, base, calls, record=False)
    assert not os.path.exists(tmp_path / 'ts.json') and not os.path.exists(tmp_path / 'is.json')


def test_validate_metadata_ok_and_spotify_first():
    clean = wd.validate_metadata(GOOD)
    assert clean['description'].splitlines()[0] == wu.SPOTIFY_URL
    assert wd.tags_length(wd.BASE_TAGS) <= wd.TAGS_MAX_CHARS


@pytest.mark.parametrize('change, fragment', [
    ({'title': ''}, 'falta el título'),
    ({'title': 'x' * 100 + '.'}, 'máx. 100'),
    ({'title': 'You are not alone.'}, 'minúscula'),
    ({'title': "you're not alone tonight"}, 'punto'),
    ({'title': 'someone is still beside you.'}, 'ya usado'),
    ({'description': ''}, 'descripción'),
    ({'tags': ['a' * 300, 'b' * 300]}, 'máx. 500'),
    ({'tags': []}, 'faltan los tags'),
    ({'tags': ['nowayout']}, 'otros canales'),
    ({'pinned_comment': ''}, 'comentario'),
])
def test_validate_metadata_rejects(change, fragment):
    with pytest.raises(wd.DailyError, match=fragment):
        wd.validate_metadata(dict(GOOD, **change))


def test_validate_metadata_rejects_title_from_log():
    with pytest.raises(wd.DailyError, match='ya usado'):
        wd.validate_metadata(GOOD, [{'title': 'The one who never leaves your side.'}])


def test_tags_length_counts_quotes_and_commas():
    assert wd.tags_length(['a b', 'c']) == len('"a b",c')


def test_slot_for_same_day_noon_or_refuses():
    slot = wd.slot_for(DAY, _utc(2026, 11, 22, 12, 0))  # 09:00 AR
    assert wu.publish_at_utc(slot) == '2026-11-22T15:00:00Z'
    with pytest.raises(wd.DailyError, match='no se sube para otro horario'):
        wd.slot_for(DAY, _utc(2026, 11, 22, 14, 30))  # 11:30 AR: sin margen


def _ready(tmp_path):
    base, calls = _base(tmp_path), []
    _prepare(tmp_path, base, calls)
    (base / 'Videos' / '2026-11-22' / 'metadata.json').write_text(json.dumps(GOOD),
                                                                   encoding='utf-8')
    return base


def test_publish_dry_run_does_not_upload(tmp_path):
    base = _ready(tmp_path)
    def boom(*a, **k):
        raise AssertionError('no debería subir')
    status, detail = wd.publish(DAY, base=str(base), log_path=str(tmp_path / 'log.json'),
                                dry_run=True, now=_utc(2026, 11, 22, 12), upload=boom)
    assert status == 'dry-run' and detail['publish_at'] == '2026-11-22T15:00:00Z'
    assert detail['title'] == GOOD['title']


def test_publish_uploads_once(tmp_path):
    base, log = _ready(tmp_path), str(tmp_path / 'log.json')
    calls = []
    def fake_upload(video, meta, image, slot, log_path):
        calls.append(video)
        entry = {'video': os.path.basename(video), 'title': meta['title'], 'youtube_id': 'abc',
                 'url': 'https://youtu.be/abc', 'publish_at': slot.isoformat()}
        wu.append_log(entry, log_path)
        return entry
    status, _ = wd.publish(DAY, base=str(base), log_path=log, now=_utc(2026, 11, 22, 12),
                           upload=fake_upload)
    assert status == 'uploaded' and len(calls) == 1
    assert (base / 'Videos' / '2026-11-22' / 'published.json').is_file()
    status, detail = wd.publish(DAY, base=str(base), log_path=log, now=_utc(2026, 11, 22, 12),
                                upload=fake_upload)
    assert status == 'already' and detail['youtube_id'] == 'abc' and len(calls) == 1


def test_publish_refuses_late_or_empty_metadata(tmp_path):
    base, calls = _base(tmp_path), []
    _prepare(tmp_path, base, calls)
    with pytest.raises(wd.DailyError, match='falta el título'):
        wd.publish(DAY, base=str(base), log_path=str(tmp_path / 'log.json'),
                   now=_utc(2026, 11, 22, 12))
    (base / 'Videos' / '2026-11-22' / 'metadata.json').write_text(json.dumps(GOOD),
                                                                   encoding='utf-8')
    with pytest.raises(wd.DailyError, match='otro horario'):
        wd.publish(DAY, base=str(base), log_path=str(tmp_path / 'log.json'),
                   now=_utc(2026, 11, 22, 16))


def test_publish_without_video(tmp_path):
    with pytest.raises(wd.DailyError, match='prepare'):
        wd.publish(DAY, base=str(tmp_path), log_path=str(tmp_path / 'log.json'))
