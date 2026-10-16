#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke offline de la pestaña Conexiones: estado real local sin mostrar valores.

Uso: ``py -3 scripts/smoke_automation_status.py``. No usa red ni gh ni modifica archivos.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from core import automation_status as st


def main():
    print('dropbox:', st.dropbox_worker_status())
    print('notion :', st.beat_notion_status())
    print('gh     :', st.gh_available())
    from PyQt5.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])  # noqa: F841
    from core.beat_panel import BeatPanel
    panel = BeatPanel()
    assert panel.tabs.tabText(0) == 'Conexiones'
    panel.reload_connection_channels()
    assert set(panel.light_labels) == {'youtube', 'dropbox', 'notion', 'gh'}
    from core.beat_connections_form import sanitize_log
    assert '[oculto]' in sanitize_log('x ' + 'A' * 50)
    print('smoke_automation_status: ok')
    return 0


if __name__ == '__main__':
    sys.exit(main())
