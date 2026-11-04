"""The title counts the loops rendered in a preview, rather than the whole pack."""
from datetime import datetime
from unittest.mock import Mock
import random

from core import kit_publish, kit_week


def test_preview_title_counts_selected_loops(tmp_path, monkeypatch):
    pack = {'name': 'MIDNIGHT', 'dropbox_path': '/kits/midnight',
            'loops': [{'path': f'/loops/{i}.wav'} for i in range(8)]}
    segments = [{'path': f'/loops/{i}.wav', 'start': 0, 'end': 35} for i in range(4)]
    plan = {'ok': True, 'warnings': [], 'segments': segments, 'mode': 'assembled',
            'short': False, 'exhausted': False}
    templates = {'title_template': '(FREE) Guitar Sample Pack "{name}" ({loop_count} loops)',
                 'description_template': 'Download: {link}', 'track_links': False}
    original = dict(templates)
    monkeypatch.setattr(kit_week.kit_audio, 'plan_audio', lambda *a, **kw: plan)
    monkeypatch.setattr(kit_week.kit_art, 'for_cover', lambda *a, **kw: ('cover.png', [], False))
    monkeypatch.setattr(kit_week.kit_names, 'remember', lambda *a: None)
    captured = {}

    def publish(channel, video, thumbnail, name, slots, resolved, **kw):
        title, body, _ = kit_publish._metadata(channel, name, resolved, kw['title'])
        captured.update(title=title, body=body, segments=kw['loops_json'])
        return {'youtube_id': 'fake', 'title': title}

    monkeypatch.setattr(kit_week, 'publish_preview', publish)
    now = datetime(2026, 11, 9, 18)
    kit_week.make_video(
        {'pack': pack, 'image': None},
        {'name': 'MIDNIGHT', 'genre': 'guitarras', 'payhip_url': 'https://rkns.link/example'},
        kit_cfg={}, channel='kiezsa loops', channel_templates=templates,
        slots_cfg=[{'weekday': 0, 'hour': 18, 'minute': 0}], slot=now, now=now,
        state={}, store=Mock(), rng=random.Random(1), output_dir=str(tmp_path),
        hooks={'cut_fn': lambda *a, **kw: ['loop.wav'],
               'cover_fn': lambda *a: ('frame.png', 'thumb.png'),
               'render_fn': lambda *a: None})
    assert captured['title'] == '(FREE) Guitar Sample Pack "MIDNIGHT" (4 loops)'
    assert captured['body'] == 'Download: https://rkns.link/example'
    assert captured['segments'] == segments
    assert templates == original
