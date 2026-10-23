# -*- coding: utf-8 -*-
"""Subpestaña «Tandas por canal»: genera todo lo que hay en ``entrada/<canal>/`` de una vez.

Usa la carpeta de canales y la carpeta de salida de la subpestaña «Arrastrar» (``ManualPanel``).
La lógica vive en ``core.bulk_queue``.
"""
import os

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
                             QProgressBar, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from core import bulk_queue as bq
from core import channel_profile as cp
from core import manual_render as mr
from core.manual_panel import _open_path
from ui_theme import ACCENT_GENERATE, ACCENT_GENERATE_HOVER

COL_CHANNEL, COL_BEAT, COL_TITLE, COL_LEN = range(4)


class BulkWorker(QThread):
    progress = pyqtSignal(int, int, str)
    message = pyqtSignal(str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, root, output_root, beats, titles, parent=None):
        super().__init__(parent)
        self.args = (root, output_root, beats, titles)
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        root, output_root, beats, titles = self.args
        try:
            ready, busy = bq.settled(beats)
            for beat in busy:
                self.message.emit(f'… {os.path.basename(beat["path"])} se está copiando: queda para la próxima.')
            summary = bq.run_bulk(root, output_root, ready, titles,
                                  progress=lambda d, t, text: self.progress.emit(d, t, text),
                                  cancelled=lambda: self._cancel)
            self.done.emit(summary)
        except mr.Cancelled:
            self.failed.emit('Cancelado. Lo ya generado quedó en la carpeta y sus beats pasaron a hechos/.')
        except mr.ManualError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - mostrar algo en vez de cerrar la app
            self.failed.emit(f'Error inesperado: {exc}')


class BulkPanel(QWidget):
    def __init__(self, source, parent=None):
        """``source``: el ``ManualPanel`` del que salen la carpeta de canales y la de salida."""
        super().__init__(parent)
        self.source = source
        self.beats = []
        self.title_overrides = {}
        self.profiles = {}
        self.worker = None
        self._build()

    @property
    def root(self):
        return self.source.local_root

    def _build(self):
        layout = QVBoxLayout(self)
        self.intro = QLabel()
        self.intro.setWordWrap(True)
        layout.addWidget(self.intro)

        row = QHBoxLayout()
        self.btn_scan = QPushButton('Revisar carpetas de entrada')
        self.btn_scan.clicked.connect(self.scan)
        self.btn_open = QPushButton('Abrir carpeta de entrada')
        self.btn_open.clicked.connect(lambda: self.root and _open_path(os.path.join(self.root, cp.INPUT_DIR)))
        self.btn_reset = QPushButton('Restablecer títulos')
        self.btn_reset.clicked.connect(self.reset_titles)
        for button in (self.btn_scan, self.btn_open, self.btn_reset):
            row.addWidget(button)
        row.addStretch()
        self.count_label = QLabel()
        row.addWidget(self.count_label)
        layout.addLayout(row)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Canal', 'Beat', 'Título (doble clic para editar)', 'Largo'])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_CHANNEL, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_BEAT, QHeaderView.Interactive)
        header.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_LEN, QHeaderView.ResizeToContents)
        self.table.setColumnWidth(COL_BEAT, 240)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.itemChanged.connect(self._on_title_edited)
        layout.addWidget(self.table, 1)

        self.notes = QLabel()
        self.notes.setWordWrap(True)
        self.notes.setStyleSheet('color: #d98e04;')
        self.notes.setVisible(False)
        layout.addWidget(self.notes)

        actions = QHBoxLayout()
        self.btn_generate = QPushButton('Generar todo')
        self.btn_generate.setStyleSheet(
            f'QPushButton {{ background: {ACCENT_GENERATE}; color: white; font-weight: bold;'
            f' padding: 8px 18px; }} QPushButton:hover {{ background: {ACCENT_GENERATE_HOVER}; }}'
            ' QPushButton:disabled { background: #555; color: #aaa; }')
        self.btn_generate.clicked.connect(self.start)
        self.btn_cancel = QPushButton('Cancelar')
        self.btn_cancel.clicked.connect(self.cancel)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        actions.addWidget(self.btn_generate)
        actions.addWidget(self.btn_cancel)
        actions.addWidget(self.progress, 1)
        layout.addLayout(actions)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(140)
        layout.addWidget(self.log)
        self._refresh()

    # --- Cola ---

    def scan(self):
        self.beats, notes = bq.scan(self.root) if self.root else ([], ['Elegí la carpeta de canales en «Arrastrar».'])
        self.profiles = {}
        for channel in {b['channel'] for b in self.beats}:
            try:
                self.profiles[channel] = cp.load(self.root, channel)
            except cp.ProfileError as exc:
                notes.append(f'{channel}: {exc}')
        self.beats = [b for b in self.beats if b['channel'] in self.profiles]
        known = {b['path'] for b in self.beats}
        self.title_overrides = {p: t for p, t in self.title_overrides.items() if p in known}
        self.notes.setText('\n'.join(notes))
        self.notes.setVisible(bool(notes))
        self._refresh()

    def reset_titles(self):
        self.title_overrides = {}
        self._refresh()

    def auto_title(self, beat):
        return mr.beat_title(self.profiles[beat['channel']], mr.beat_name(beat['path']), beat['channel'])

    def titles(self):
        return [self.title_overrides.get(b['path']) or self.auto_title(b) for b in self.beats]

    def _refresh(self):
        root = self.root or '(sin carpeta de canales)'
        self.intro.setText(f'Soltá beats en «{os.path.join(root, cp.INPUT_DIR)}\\<canal>», revisá los títulos y '
                           'generá todo de una. Cada canal usa su perfil; lo terminado pasa a «hechos».')
        table = self.table
        table.blockSignals(True)
        table.setRowCount(len(self.beats))
        for row, (beat, title) in enumerate(zip(self.beats, self.titles())):
            for col, text in ((COL_CHANNEL, beat['channel']), (COL_BEAT, os.path.basename(beat['path']))):
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                table.setItem(row, col, item)
            cell = QTableWidgetItem(title)
            if beat['path'] in self.title_overrides:
                cell.setForeground(QColor('#f1c40f'))
                cell.setToolTip('Editado a mano (solo para esta tanda).')
            table.setItem(row, COL_TITLE, cell)
            length = QTableWidgetItem(f'{len(title)}/100')
            length.setFlags(length.flags() & ~Qt.ItemIsEditable)
            if len(title) > 100:
                length.setForeground(QColor('#e74c3c'))
            table.setItem(row, COL_LEN, length)
        table.blockSignals(False)
        channels = len({b['channel'] for b in self.beats})
        edited = len(self.title_overrides)
        self.count_label.setText(f'{len(self.beats)} beats en {channels} canales'
                                 + (f' · {edited} títulos editados' if edited else ''))
        self._update_buttons()

    def _on_title_edited(self, item):
        if item.column() != COL_TITLE or item.row() >= len(self.beats):
            return
        beat = self.beats[item.row()]
        text = ' '.join(item.text().split())
        if text and text != self.auto_title(beat):
            self.title_overrides[beat['path']] = text
        else:
            self.title_overrides.pop(beat['path'], None)
        self._refresh()

    # --- Generar ---

    def _update_buttons(self):
        busy = self.worker is not None
        self.btn_generate.setEnabled(bool(self.beats) and not busy)
        self.btn_cancel.setEnabled(busy)
        self.btn_scan.setEnabled(not busy)
        self.btn_reset.setEnabled(bool(self.title_overrides) and not busy)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers if busy else
                                   QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)

    def _say(self, text):
        self.log.appendPlainText(text)

    def start(self):
        if self.worker is not None or not self.beats:
            return
        output_root = self.source.settings['output_folder']
        self.worker = BulkWorker(self.root, output_root, list(self.beats), dict(self.title_overrides), self)
        self.worker.progress.connect(self._on_progress)
        self.worker.message.connect(self._say)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(lambda text: self._say(f'✗ {text}'))
        self.worker.finished.connect(self._on_finished)
        self.progress.setRange(0, len(self.beats))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._say(f'Generando {len(self.beats)} beats…')
        self._update_buttons()
        self.worker.start()

    def cancel(self):
        if self.worker is not None:
            self.worker.cancel()
            self._say('Cancelando…')

    def _on_progress(self, done, total, text):
        self.progress.setValue(done)
        self._say(text)

    def _on_done(self, summary):
        total = sum(entry['ok'] for entry in summary.values())
        for channel, entry in summary.items():
            line = f'{channel}: {entry["ok"]} videos'
            if entry['errores']:
                line += f', {len(entry["errores"])} con error (ver entrada/{channel}/errores.txt)'
            self._say(line)
        folder = mr.day_folder(self.source.settings['output_folder'])
        self._say(f'✓ {total} videos listos en {folder} (lista en {mr.PENDING_CSV}).')

    def _on_finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.progress.setVisible(False)
        self.scan()  # lo generado ya pasó a hechos/

    def shutdown(self, wait_ms=5000):
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait(wait_ms)
