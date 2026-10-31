# -*- coding: utf-8 -*-
"""Barra inferior compartida: CTA «Publicar al robot» y checklist de piloto. Sin lógica CAS."""
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton

from core import automation_status as status
import ui_theme as theme

# Requisitos mínimos de conexiones (informe SEO aparte).
BEATS_PILOT_REQUIRED = frozenset({'slug', 'youtube', 'dropbox', 'gh'})
KITS_PILOT_REQUIRED = frozenset({'env', 'youtube', 'dropbox', 'telegram', 'gh'})


def readiness_html(items):
    """HTML del checklist ``readiness_*`` (sin secretos)."""
    return '<br>'.join(('✔ ' if i['ok'] else '✘ ') + i['label'] for i in items)


def pilot_ready(items, required, seo_state):
    """``True`` solo si conexiones obligatorias e informe SEO local válido."""
    if seo_state != status.OK:
        return False
    return all(i['ok'] for i in items if i['id'] in required)


class AutomationSaveBar:
    """Mixin: construye la barra y refresca el resumen de piloto."""

    def _build_save_bar(self, outer):
        """Añade botón primario y checklist encima del ``status`` del panel."""
        row = QHBoxLayout()
        row.setContentsMargins(0, theme.SPACE['s'], 0, 0)
        self.pilot_ready_label = QLabel()
        self.pilot_ready_label.setWordWrap(True)
        row.addWidget(self.pilot_ready_label, 1)
        self.save_publish_button = theme.primary(QPushButton('Publicar al robot'))
        self.save_publish_button.clicked.connect(self.save_and_publish)
        row.addWidget(self.save_publish_button, 0)
        outer.addLayout(row)
        self.publish_checklist = theme.muted(QLabel())
        details = theme.Collapsible('Ver qué falta')
        details.body.addWidget(self.publish_checklist)
        outer.addWidget(details)

    def _refresh_publish_readiness(self, items, seo_state, required):
        """Actualiza checklist e indicador «listo para piloto»."""
        if not getattr(self, 'publish_checklist', None):
            return
        self.publish_checklist.setText(readiness_html(items))
        if pilot_ready(items, required, seo_state):
            self.pilot_ready_label.setText(f'<span style="color:{theme.color("success")}">✔ Listo para publicar</span>')
        else:
            self.pilot_ready_label.setText(
                f'<span style="color:{theme.color("warning")}">Falta completar algo antes de publicar '
                '(conexiones, informe SEO o secretos del canal).</span>')
