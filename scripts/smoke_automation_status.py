#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke offline de la pestaña Conexiones: estado desde gh (simulado) sin mostrar valores.

Uso: ``py -3 scripts/smoke_automation_status.py``. No usa red ni gh real ni modifica archivos:
``gh`` y el llavero son dobles en memoria (``core/cloud_fakes``).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from core import automation_status as st, cloud_login, gh_status
from core.cloud_fakes import FakeGhRun, MemoryKeyring


def _settle(app, panel, timeout=5):
    import time
    deadline = time.monotonic() + timeout
    while panel.task is not None and time.monotonic() < deadline:
        app.processEvents()


def main():
    fake = FakeGhRun()
    fake.put('kit-weekly', *st.KIT_DROPBOX_KEYS, 'BEAT_YT_TOKEN_JSON_EY_MAT')
    gh_status.set_default(gh_status.GhStatus(run=fake))
    cloud_login.set_backend(MemoryKeyring())
    print('dropbox:', st.dropbox_worker_status())
    print('notion :', st.beat_notion_status())
    print('gh     :', st.gh_auth_status())
    assert st.dropbox_worker_status() == st.OK and st.beat_notion_status() == st.MISSING
    assert st.beat_youtube_status('ey-mat') == st.OK
    code, text = st.secrets_badge(st.KIT_DROPBOX_KEYS)
    assert code == st.OK and text == 'cargado ✓ (2026-10-13)', text
    assert st.dropbox_desktop_status() == st.MISSING
    reads = [c[0] for c in fake.calls]
    assert all(a[:2] in (['auth', 'status'], ['secret', 'list'], ['variable', 'get'])
               for a in reads), reads
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from core.beat_panel import BeatPanel
    from core.beat_fakes import MemoryDropbox
    panel = BeatPanel(cloud_provider=MemoryDropbox)  # sin Dropbox real
    _settle(app, panel)
    assert panel.tabs.tabText(0) == 'Conexiones'
    panel.reload_connection_channels()
    assert set(panel.light_labels) == {'youtube', 'dropbox', 'notion', 'gh'}
    assert 'cargado ✓' in panel.light_labels['dropbox'].text()
    assert hasattr(panel, 'login_box') and 'Falta' in panel.login_box.dropbox_light.text()
    from core.beat_connections_form import sanitize_log
    assert '[oculto]' in sanitize_log('x ' + 'A' * 50)
    print('smoke_automation_status: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
