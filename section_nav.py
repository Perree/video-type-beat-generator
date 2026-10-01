# -*- coding: utf-8 -*-
"""Barra superior para cambiar entre Beats, Loop kits y Marca personal."""

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from core.sections import (
    ALL_SECTIONS,
    DEFAULT_SECTION,
    SECTION_BEATS,
    SECTION_LOOP_KITS,
    SECTION_PERSONAL,
)

_SECTION_LABELS = {
    SECTION_BEATS: "Beats",
    SECTION_LOOP_KITS: "Loop kits",
    SECTION_PERSONAL: "Marca personal",
}


class SectionNavBar(QFrame):
    """Tres botones de sección; emite section_changed con el id de sección."""

    section_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._current = DEFAULT_SECTION
        self._buttons = {}
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        for section_id in ALL_SECTIONS:
            btn = QPushButton(_SECTION_LABELS[section_id])
            btn.setMinimumHeight(36)
            btn.clicked.connect(lambda _checked=False, s=section_id: self._activate(s))
            self._buttons[section_id] = btn
            layout.addWidget(btn, 1)
        self._refresh_styles()

    def current_section(self) -> str:
        return self._current

    def set_section(self, section_id: str) -> None:
        """Selecciona la sección sin emitir señal (carga inicial)."""
        if section_id not in ALL_SECTIONS:
            section_id = DEFAULT_SECTION
        self._current = section_id
        self._refresh_styles()

    def _activate(self, section_id: str) -> None:
        if section_id == self._current:
            return
        self._current = section_id
        self._refresh_styles()
        self.section_changed.emit(section_id)

    def _refresh_styles(self) -> None:
        for sid, btn in self._buttons.items():
            btn.setObjectName("section_nav_active" if sid == self._current else "")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
