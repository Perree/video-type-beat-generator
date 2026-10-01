# -*- coding: utf-8 -*-
"""Pregunta el link de BeatStars de un beat recién importado."""
from PyQt5.QtWidgets import QInputDialog, QLineEdit


def ask_beatstars_url(parent, beat_name):
    """Devuelve el link (puede ser '') o None si el usuario cancela."""
    text, ok = QInputDialog.getText(
        parent, "Link de BeatStars",
        f"Link de BeatStars para:\n{beat_name}\n\n(dejalo vacío si todavía no lo tenés)",
        QLineEdit.Normal, "")
    return text.strip() if ok else None
