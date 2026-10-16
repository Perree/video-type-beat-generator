#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke offline del puente informe SEO: validación, import local y UI. Sin red ni gh.

Uso: ``py -3 scripts/smoke_seo_report_status.py``. Escribe solo en una carpeta temporal.
"""
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from core import seo_report_status as sr

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
SECRET = 'SECRETO-NO-DEBE-APARECER'


def beat_report(**over):
    doc = {'schema_version': 1, 'generated_at': (NOW - timedelta(days=2)).isoformat(),
           'channel_id': 'beats', 'sources': ['claude_code', 'vidiq', 'youtube_analytics'],
           'keywords': [{'tag': 'trap', 'score': 80, 'views': 10, 'ctr': 4, 'average_view_percentage': 50},
                        {'tag': 'drill', 'score': 60, 'views': 5, 'ctr': 3, 'average_view_percentage': 40}]}
    doc.update(over)
    return doc


def kit_report(**over):
    doc = {'version': 1, 'generated_at': (NOW - timedelta(days=1)).isoformat(),
           'channel': {'top_videos': []},
           'genres': {'guitarras': {'keywords': [
               {'keyword': 'emotional guitar loop kit', 'monthly_searches': 900,
                'competition': 10, 'growth_pct': 2}]}}}
    doc.update(over)
    return doc


def write(folder, name, doc):
    path = os.path.join(folder, name)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(doc if isinstance(doc, str) else json.dumps(doc))
    return path


def expect(kind, path, key, code, base):
    try:
        sr.import_report(kind, path, key, NOW, base)
    except sr.SeoReportError as exc:
        assert exc.code == code, (exc.code, code)
        assert SECRET not in str(exc) and SECRET not in sr.label(exc.code)
        return
    raise AssertionError(f'se esperaba {code}')


def main():
    with tempfile.TemporaryDirectory() as tmp:
        src, base = os.path.join(tmp, 'src'), os.path.join(tmp, 'out')
        os.makedirs(src)
        # Beats: válido, y cada error devuelve un código fijo sin eco del contenido.
        info = sr.import_report('beats', write(src, 'ok.json', beat_report()), 'beats', NOW, base)
        assert info['keywords'] == 2 and info['age_days'] == 2.0, info
        expect('beats', write(src, 'c.json', beat_report(channel_id='otro')), 'beats', 'channel', base)
        old = (NOW - timedelta(days=30)).isoformat()
        expect('beats', write(src, 'o.json', beat_report(generated_at=old)), 'beats', 'expired', base)
        expect('beats', write(src, 'x.json', beat_report(extra=SECRET)), 'beats', 'schema', base)
        expect('beats', write(src, 'j.json', '{"a": ' + SECRET), 'beats', 'json', base)
        # keywords vacías: el worker las acepta, así que también se copian (otro canal, no pisa la buena).
        empty = sr.import_report('beats', write(src, 'e.json', beat_report(channel_id='vacio', keywords=[])),
                                  'vacio', NOW, base)
        assert empty['keywords'] == 0 and sr.local_status('beats', 'vacio', NOW, base)['state'] == 'ok'
        expect('beats', os.path.join(src, 'no-existe.json'), 'beats', 'file', base)
        expect('beats', write(src, 'b.json', 'x' * (200 * 1024)), 'beats', 'size', base)
        # Un rechazo no pisa la copia buena anterior.
        assert sr.local_status('beats', 'beats', NOW, base)['state'] == 'ok'
        # El nombre de canal no puede escapar de la carpeta.
        assert os.path.dirname(sr.report_path('beats', '../../x', base)) == base
        # Kits: válido, viejo y sin keywords.
        sr.import_report('kits', write(src, 'k.json', kit_report()), '', NOW, base)
        assert sr.local_status('kits', '', NOW, base)['state'] == 'ok'
        expect('kits', write(src, 'kv.json', kit_report(generated_at=old)), '', 'expired', base)
        expect('kits', write(src, 'kn.json', kit_report(version=2)), '', 'version', base)
        sr.import_report('kits', write(src, 'ke.json', kit_report(genres={})), 'vacio', NOW, base)
        assert sr.local_status('kits', 'vacio', NOW, base)['keywords'] == 0
        # 15 días: vencido con el default (10) y vigente si el canal permite 20.
        mid = write(src, 'kmid.json', kit_report(generated_at=(NOW - timedelta(days=15)).isoformat()))
        expect('kits', mid, 'medio', 'expired', base)
        sr.import_report('kits', mid, 'medio', NOW, base, max_age_days=20)
        assert sr.local_status('kits', 'medio', NOW, base, max_age_days=20)['state'] == 'ok'
        assert sr.local_status('kits', 'medio', NOW, base)['state'] == 'expired'
        # Edad: la misma copia vence con el tiempo.
        later = NOW + timedelta(days=20)
        assert sr.local_status('beats', 'beats', later, base)['state'] == 'expired'
        assert sr.local_status('beats', 'otro', NOW, base)['state'] == 'missing'
        # Sugerencias de solo lectura y schema.
        tips = sr.suggestions('beats', 'beats', ['trap'], NOW, base)
        assert 'trap' in tips[0] and 'Se usarían' not in tips[0] and 'drill' in tips[1], tips
        assert 'guitarras' in sr.suggestions('kits', '', ['guitarras'], NOW, base)[0]
        assert json.loads(sr.schema_text('beats', 'beats', ['trap'], NOW))['channel_id'] == 'beats'
        assert 'genres' in json.loads(sr.schema_text('kits', '', ['guitarras'], NOW))
        # UI: el cuadro importa y muestra estado sin red.
        from PyQt5.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])  # noqa: F841
        from core.seo_report_box import SeoReportBox
        box = SeoReportBox('beats', lambda: {'key': 'beats', 'names': ['trap']}, base=base)
        assert 'vigente' in box.state.text() or 'vencido' in box.state.text(), box.state.text()
        assert not box.import_file(write(src, 'bad.json', beat_report(channel_id='otro')))
        assert SECRET not in box.state.text() and 'channel_id' in box.state.text()
        assert 'a mano' in box.thumbnail_notes.toPlainText().casefold()
        kit_doc = kit_report(thumbnail_suggestions=['Contraste alto', 'Texto corto'])
        sr.import_report('kits', write(src, 'kthumb.json', kit_doc), 'thumb', NOW, base)
        tips = sr.thumbnail_recommendations('kits', 'thumb', NOW, base)
        assert 'Contraste alto' in '\n'.join(tips)
    print('smoke_seo_report_status: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
