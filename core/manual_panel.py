# -*- coding: utf-8 -*-
"""Piezas de UI compartidas del modo local: tabla de beats con arrastrar/soltar y utilidades.

La pantalla en sí es ``core.local_view.LocalView``.
"""
import os
import subprocess
import sys

from PyQt5.QtCore import QStandardPaths, pyqtSignal
from PyQt5.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget

from core import manual_render as mr

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _open_path(path):
    os.makedirs(path, exist_ok=True)
    if sys.platform == 'win32':
        os.startfile(path)  # noqa: S606 - carpeta local elegida por el usuario
    else:
        subprocess.run(['xdg-open' if sys.platform != 'darwin' else 'open', path], check=False)


def desktop_output_folder():
    desktop = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
    return os.path.normpath(os.path.join(desktop, mr.OUTPUT_DIRNAME) if desktop else mr.default_output_folder())


class BeatDropTable(QTableWidget):
    """Tabla beat | título (editable) | largo; acepta archivos y carpetas arrastrados."""
    paths_dropped = pyqtSignal(list)
    COL_BEAT, COL_TITLE, COL_LEN = 0, 1, 2

    def __init__(self, parent=None):
        super().__init__(0, 3, parent)
        self.setHorizontalHeaderLabels(['Beat', 'Título (doble clic para editar)', 'Largo'])
        header = self.horizontalHeader()
        header.setSectionResizeMode(self.COL_BEAT, QHeaderView.Interactive)
        header.setSectionResizeMode(self.COL_TITLE, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_LEN, QHeaderView.ResizeToContents)
        self.setColumnWidth(self.COL_BEAT, 260)
        self.verticalHeader().setVisible(False)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

    def selected_rows(self):
        return sorted({index.row() for index in self.selectedIndexes()})

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.paths_dropped.emit(paths)
        else:
            event.ignore()
