# -*- coding: utf-8 -*-
"""Diálogo de la biblioteca de beats: lista, filtros y selección para el flujo principal."""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                             QComboBox, QLineEdit, QPushButton, QLabel, QAbstractItemView,
                             QHeaderView, QFileDialog)
from core import library


class LibraryDialog(QDialog):
    """Permite filtrar beats y seleccionarlos. `selected_paths` queda con las rutas elegidas."""

    FILTERS = [("Todos", None), ("Nunca subidos", 'nunca'),
               ("Sin subir al canal", 'sin_canal'), ("Subidos hace > 6 meses", 'antiguos')]

    def __init__(self, channels=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Biblioteca de beats")
        self.resize(780, 460)
        self.selected_paths = []
        self._beats = []

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Buscar por nombre...")
        self.filter_combo = QComboBox()
        for label, _ in self.FILTERS:
            self.filter_combo.addItem(label)
        self.channel_combo = QComboBox()
        self.channel_combo.addItem("Cualquier canal", None)
        for ch in channels or []:
            self.channel_combo.addItem(ch, ch)
        btn_import = QPushButton("Importar audios...")
        btn_import.clicked.connect(self._import)
        btn_dropbox = QPushButton("Dropbox...")
        btn_dropbox.clicked.connect(self._import_dropbox)
        top.addWidget(self.search, 1)
        top.addWidget(self.filter_combo)
        top.addWidget(self.channel_combo)
        top.addWidget(btn_import)
        top.addWidget(btn_dropbox)
        layout.addLayout(top)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Nombre", "BPM", "Key", "Última subida"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        layout.addWidget(self.table)

        bottom = QHBoxLayout()
        self.count_label = QLabel("")
        btn_use = QPushButton("Usar seleccionados")
        btn_use.clicked.connect(self._accept_selection)
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        bottom.addWidget(self.count_label, 1)
        bottom.addWidget(btn_use)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

        self.search.textChanged.connect(self.refresh)
        self.filter_combo.currentIndexChanged.connect(self.refresh)
        self.channel_combo.currentIndexChanged.connect(self.refresh)
        self.refresh()

    def refresh(self):
        filtro = self.FILTERS[self.filter_combo.currentIndex()][1]
        canal = self.channel_combo.currentData()
        self._beats = library.list_beats(filtro=filtro, canal=canal, texto=self.search.text().strip())
        self.table.setRowCount(len(self._beats))
        for row, b in enumerate(self._beats):
            vals = [b['nombre'], '' if b['bpm'] is None else f"{b['bpm']:g}", b['key'] or '',
                    library.humanize_ago(b['ultima_subida'])]
            for col, v in enumerate(vals):
                self.table.setItem(row, col, QTableWidgetItem(v))
        self.count_label.setText(f"{len(self._beats)} beats")

    def _import(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Importar a la biblioteca", "", "Audio Files (*.mp3 *.wav *.m4a *.aac *.flac)")
        for f in files:
            library.import_beat(f)
        self.refresh()

    def _import_dropbox(self):
        from dropbox_browser_dialog import DropboxBrowserDialog
        DropboxBrowserDialog(self).exec_()
        self.refresh()

    def _accept_selection(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        self.selected_paths = [self._beats[r]['ruta'] for r in rows]
        self.accept()
