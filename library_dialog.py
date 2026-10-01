# -*- coding: utf-8 -*-
"""Diálogo de la biblioteca de beats: lista, filtros y selección para el flujo principal."""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
                             QComboBox, QLineEdit, QPushButton, QLabel, QAbstractItemView,
                             QHeaderView, QFileDialog, QMessageBox)
from core import library, youtube
from core.upload_worker import ImportHistoryWorker


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
        self.btn_history = QPushButton("Importar historial YT")
        self.btn_history.setToolTip("Trae los videos ya publicados del canal elegido y los empareja con tus beats por nombre.")
        self.btn_history.clicked.connect(self._import_history)
        top.addWidget(self.search, 1)
        top.addWidget(self.filter_combo)
        top.addWidget(self.channel_combo)
        top.addWidget(btn_import)
        top.addWidget(btn_dropbox)
        top.addWidget(self.btn_history)
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

    def _import_history(self):
        channel = self.channel_combo.currentData()
        if not channel:
            QMessageBox.information(self, "Importar historial", "Elegí un canal en el selector de canal.")
            return
        if not youtube.is_connected(channel):
            QMessageBox.warning(self, "Importar historial",
                                f"'{channel}' no está conectado a YouTube (Gestión de Canales).")
            return
        self.btn_history.setEnabled(False)
        self.btn_history.setText("Importando...")
        self._history_worker = ImportHistoryWorker(channel, self)
        self._history_worker.finished_ok.connect(self._on_history_done)
        self._history_worker.failed.connect(self._on_history_failed)
        self._history_worker.start()

    def _reset_history_button(self):
        self.btn_history.setEnabled(True)
        self.btn_history.setText("Importar historial YT")

    def _on_history_done(self, channel, res):
        self._reset_history_button()
        self.refresh()
        msg = (f"{channel}: {res['imported']} importados, {res['skipped']} ya registrados, "
               f"{len(res['unmatched'])} sin beat en la biblioteca.")
        if res['unmatched']:
            msg += "\n\nSin emparejar (primeros 15):\n" + "\n".join(res['unmatched'][:15])
        QMessageBox.information(self, "Historial importado", msg)

    def _on_history_failed(self, channel, error):
        self._reset_history_button()
        QMessageBox.warning(self, "Error al importar historial", error)

    def _accept_selection(self):
        rows = sorted({i.row() for i in self.table.selectedIndexes()})
        self.selected_paths = [self._beats[r]['ruta'] for r in rows]
        self.accept()
