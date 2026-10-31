# -*- coding: utf-8 -*-
"""Cuadro "Informe de Claude Code" compartido por las pestañas SEO de Beats y Loop kits.

Solo muestra estado y sugerencias de solo lectura; la lógica vive en ``seo_report_status``.
El informe nunca llega a títulos ni a la ficha desde acá.
"""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QApplication, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QVBoxLayout,
)

from core import automation_status as status
from core import seo_report_status as sr
import ui_theme as theme

_COLORS = {status.OK: theme.color('success'), status.MISSING: theme.color('text_muted'),
           status.UNKNOWN: theme.color('text_muted'), status.INVALID: theme.color('danger'),
           sr.EXPIRED: theme.color('warning')}


class SeoReportBox(QGroupBox):
    """Estado del informe, import de JSON local, copia del schema y sugerencias.

    Args:
        kind: ``sr.BEATS`` o ``sr.KITS``.
        context: callable sin args que devuelve ``{'key', 'names'}`` (+ ``max_age_days`` en kits):
            id del canal / slug de automatización y tags manuales / géneros del panel.
        base: carpeta de copias (solo tests); por defecto ``tokens/seo_reports``.
    """

    def __init__(self, kind, context, base=None, parent=None):
        super().__init__('Informe de Claude Code (vidIQ + Analytics)', parent)
        self.kind, self._context, self._base = kind, context, base
        lay = QVBoxLayout(self)
        self.state = QLabel()
        self.state.setWordWrap(True)
        self.state.setTextFormat(Qt.PlainText)
        lay.addWidget(self.state)
        self.import_button = QPushButton('Importar informe JSON…')
        self.import_button.clicked.connect(self.choose_file)
        self.schema_button = theme.flat(QPushButton('Copiar schema'))
        self.schema_button.clicked.connect(self.copy_schema)
        lay.addLayout(theme.button_row(self.import_button, self.schema_button))
        self.hint = theme.muted(QLabel('Sugerencias (solo lectura, no cambian títulos ni la ficha):'))
        lay.addWidget(self.hint)
        self.suggestions = QPlainTextEdit()
        self.suggestions.setReadOnly(True)
        self.suggestions.setMaximumHeight(90)
        lay.addWidget(self.suggestions)
        self.thumbnail_hint = theme.muted(QLabel('Recomendaciones de miniaturas (solo lectura):'))
        lay.addWidget(self.thumbnail_hint)
        self.thumbnail_notes = QPlainTextEdit()
        self.thumbnail_notes.setReadOnly(True)
        self.thumbnail_notes.setMaximumHeight(72)
        lay.addWidget(self.thumbnail_notes)
        self.refresh()

    def _ctx(self):
        ctx = self._context() or {}
        return (ctx.get('key') or '', list(ctx.get('names') or []),
                ctx.get('max_age_days') or None)

    def refresh(self):
        """Recalcula estado y sugerencias desde la copia local (sin red)."""
        key, names, max_age = self._ctx()
        notion = (status.beat_notion_status() if self.kind == sr.BEATS
                  else status.kit_notion_status())
        info = sr.local_status(self.kind, key, base=self._base, max_age_days=max_age,
                               notion_state=notion)
        self.state.setText(sr.describe(info))
        self.state.setStyleSheet(f"color: {_COLORS.get(info['state'], theme.color('text_muted'))};")
        self.suggestions.setPlainText('\n'.join(sr.suggestions(
            self.kind, key, names, base=self._base, max_age_days=max_age)))
        self.thumbnail_notes.setPlainText('\n'.join(sr.thumbnail_recommendations(
            self.kind, key, base=self._base, max_age_days=max_age)))
        self.import_button.setEnabled(bool(key) or self.kind == sr.KITS)

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Informe SEO', '', 'JSON (*.json)')
        if path:
            self.import_file(path)

    def import_file(self, path):
        """Importa ``path``; muestra solo el código de error. Devuelve True si se copió."""
        key, _names, max_age = self._ctx()
        try:
            sr.import_report(self.kind, path, key, base=self._base, max_age_days=max_age)
        except sr.SeoReportError as exc:
            self.refresh()
            self.state.setText(f'No se importó: {sr.label(exc.code)}')
            self.state.setStyleSheet(f"color: {_COLORS[status.INVALID]};")
            return False
        self.refresh()
        return True

    def copy_schema(self):
        key, names, _ = self._ctx()
        QApplication.clipboard().setText(sr.schema_text(self.kind, key, names))
        self.hint.setText('Schema copiado. Sugerencias (solo lectura, no cambian títulos ni la ficha):')
