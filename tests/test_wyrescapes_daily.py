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


def test_slot_for_noon_when_on_time():
    assert wu.publish_at_utc(wd.slot_for(DAY, _utc(2026, 11, 22, 12, 0))) == \
        '2026-11-22T15:00:00Z'  # 09:00 AR
    assert wu.publish_at_utc(wd.slot_for(DAY, _utc(2026, 11, 22, 14, 30))) == \
        '2026-11-22T15:00:00Z'  # 11:30 AR: las 12:00 siguen siendo más tarde que +15 min


def test_slot_for_after_noon_publishes_soon():
    slot = wd.slot_for(DAY, _utc(2026, 11, 22, 19, 7, 30))  # 16:07:30 AR
    assert wu.publish_at_utc(slot) == '2026-11-22T19:23:00Z'  # 16:23 AR
    assert wu.publish_at_utc(wd.slot_for(DAY, _utc(2026, 11, 22, 14, 50))) == \
        '2026-11-22T15:06:00Z'  # 11:50 AR -> 12:06


def test_slot_for_never_an_old_day():
    with pytest.raises(wd.DailyError, match='día viejo'):
        wd.slot_for(DAY, _utc(2026, 11, 23, 12))


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


def test_publish_refuses_empty_metadata(tmp_path):
    base, calls = _base(tmp_path), []
    _prepare(tmp_path, base, calls)
    with pytest.raises(wd.DailyError, match='falta el título'):
        wd.publish(DAY, base=str(base), log_path=str(tmp_path / 'log.json'),
                   now=_utc(2026, 11, 22, 12))


def _uploader(calls, fail=0):
    def fake_upload(video, meta, image, slot, log_path):
        calls.append(slot)
        if len(calls) <= fail:
            raise wu.UploadError('sin red')
        entry = {'video': os.path.basename(video), 'title': meta['title'], 'youtube_id': 'abc',
                 'url': 'https://youtu.be/abc', 'publish_at': slot.isoformat()}
        wu.append_log(entry, log_path)
        return entry
    return fake_upload


def test_publish_after_noon_uploads_soon(tmp_path):
    base, log, calls = _ready(tmp_path), str(tmp_path / 'log.json'), []
    status, _ = wd.publish(DAY, base=str(base), log_path=log, now=_utc(2026, 11, 22, 21),
                           upload=_uploader(calls))  # 18:00 AR
    assert status == 'uploaded' and wu.publish_at_utc(calls[0]) == '2026-11-22T21:16:00Z'


def test_publish_failure_retries_next_run(tmp_path):
    base, log, calls = _ready(tmp_path), str(tmp_path / 'log.json'), []
    upload = _uploader(calls, fail=1)
    with pytest.raises(wd.DailyError, match='sin red'):
        wd.publish(DAY, base=str(base), log_path=log, now=_utc(2026, 11, 22, 12), upload=upload)
    assert wd.status(DAY, base=str(base), log_path=log)['state'] == 'prepared'
    status, _ = wd.publish(DAY, base=str(base), log_path=log, now=_utc(2026, 11, 22, 13),
                           upload=upload)
    assert status == 'uploaded' and len(calls) == 2
    assert wd.status(DAY, base=str(base), log_path=log)['state'] == 'uploaded'


def test_status_steps_and_prepared_is_reused(tmp_path):
    base, log, calls = _base(tmp_path), str(tmp_path / 'log.json'), []
    assert wd.status(DAY, base=str(base), log_path=log)['state'] == 'pending'
    _prepare(tmp_path, base, calls)
    assert wd.status(DAY, base=str(base), log_path=log)['state'] == 'rendered'
    meta = base / 'Videos' / '2026-11-22' / 'metadata.json'
    meta.write_text(json.dumps(GOOD), encoding='utf-8')
    assert wd.status(DAY, base=str(base), log_path=log)['state'] == 'prepared'
    _prepare(tmp_path, base, calls)  # corrida siguiente: no re-renderiza ni pisa el texto
    assert len(calls) == 1 and json.loads(meta.read_text(encoding='utf-8')) == GOOD


def test_already_uploaded_does_nothing(tmp_path):
    base, log, calls = _ready(tmp_path), str(tmp_path / 'log.json'), []
    wd.publish(DAY, base=str(base), log_path=log, now=_utc(2026, 11, 22, 12),
               upload=_uploader([]))
    os.remove(base / 'Videos' / '2026-11-22' / 'wyrescapes_20261122.mp4')
    with pytest.raises(wd.DailyError, match='ya se subió'):
        _prepare(tmp_path, base, calls)
    assert calls == []
    status, _ = wd.publish(DAY, base=str(base), log_path=log, now=_utc(2026, 11, 22, 13),
                           upload=_uploader(calls))
    assert status == 'already' and calls == []


def test_missed_day_is_logged_once(tmp_path):
    log = str(tmp_path / 'log.json')
    wu.append_log({'video': 'wyrescapes_20261122.mp4', 'title': 'a.', 'youtube_id': 'x'}, log)
    # PC apagada el 23 y el 24: el 25 se anotan los dos días perdidos, una sola vez.
    assert wd.record_missed_days(date(2026, 11, 25), log) == [date(2026, 11, 23),
                                                               date(2026, 11, 24)]
    assert wd.record_missed_days(date(2026, 11, 25), log) == []
    entries = wu.load_log(log)
    assert [e['day'] for e in entries if e.get('missed')] == ['2026-11-23', '2026-11-24']
    assert not wu.already_uploaded('wyrescapes_20261123.mp4', entries)
    assert wd.used_titles(entries) == {'a.', 'someone is still beside you.'}


def test_missed_day_never_two_videos_same_day(tmp_path):
    base, log, calls = _base(tmp_path), str(tmp_path / 'log.json'), []
    day = date(2026, 11, 24)
    wu.append_log({'video': 'wyrescapes_20261122.mp4', 'title': 'a.', 'youtube_id': 'x'}, log)
    wd.record_missed_days(day, log)
    info = wd.prepare(day, base=str(base), track_state=str(tmp_path / 'ts.json'),
                      image_state=str(tmp_path / 'is.json'), log_path=log,
                      renderer=_fake_render([]), probe=lambda p: 600.0,
                      can_open=lambda p: True, rng=random.Random(1))
    with open(info['metadata'], 'w', encoding='utf-8') as fh:
        json.dump(GOOD, fh)
    upload = _uploader(calls)
    for hour in (12, 13, 14):  # corridas horarias del mismo día
        wd.publish(day, base=str(base), log_path=log, now=_utc(2026, 11, 24, hour), upload=upload)
    assert len(calls) == 1
    assert not os.path.exists(base / 'Videos' / '2026-11-23')
    with pytest.raises(wd.DailyError, match='día viejo'):
        wd.publish(date(2026, 11, 23), base=str(base), log_path=log,
                   now=_utc(2026, 11, 24, 15), upload=upload)


def test_publish_without_video(tmp_path):
    with pytest.raises(wd.DailyError, match='prepare'):
        wd.publish(DAY, base=str(tmp_path), log_path=str(tmp_path / 'log.json'),
                   now=_utc(2026, 11, 22, 12))
