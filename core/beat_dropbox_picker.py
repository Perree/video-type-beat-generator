"""Cancelable remote folder/file picker; network operations run in BeatTask."""
from pathlib import PurePosixPath
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
from core.beat_assets import IMAGE_SUFFIXES
from core.beat_tasks import BeatTask
from core.beat_panel_cloud import PanelCloud, local_transport
import ui_theme as theme


class DropboxPicker(QDialog):
    def __init__(self, parent=None, *, file=False, provider=local_transport):
        super().__init__(parent)
        self.file, self.provider = file, provider
        self.path, self.selected_path, self.task = '', None, None
        self.close_pending = False
        self.setWindowTitle('Dropbox: elegir imagen' if file else 'Dropbox: elegir carpeta')
        self.resize(620, 450)
        layout = QVBoxLayout(self)
        self.location = QLabel('Raíz visible de la app Dropbox')
        layout.addWidget(self.location)
        self.entries = QListWidget()
        self.entries.itemDoubleClicked.connect(self.enter)
        self.entries.currentItemChanged.connect(lambda *_: self._selection_changed())
        layout.addWidget(self.entries)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.up = QPushButton('Subir')
        self.up.clicked.connect(lambda: self.load(self.path.rsplit('/', 1)[0]))
        self.choose = theme.primary(QPushButton('Seleccionar archivo' if file else 'Seleccionar esta carpeta'))
        self.choose.clicked.connect(self.select)
        self.cancel_button = theme.flat(QPushButton('Cancelar'))
        self.cancel_button.clicked.connect(self.reject)
        for button in (self.up, self.choose, self.cancel_button):
            row.addWidget(button)
        layout.addLayout(row)
        self.load('')

    def load(self, path):
        if self.task is not None:
            return
        self.entries.clear()
        self.choose.setEnabled(False)
        self.up.setEnabled(False)
        self.entries.setEnabled(False)
        self.status.setText('Leyendo Dropbox…')
        self.task = BeatTask(lambda event, progress: PanelCloud(self.provider()).list_folder(path, event), self)
        self.task.done.connect(lambda rows: self.loaded(path, rows))
        self.task.failed.connect(self.status.setText)
        self.task.finished.connect(self.finished_task)
        self.task.start()

    def loaded(self, path, rows):
        if self.task.event.is_set():
            return
        self.path = path
        self.location.setText(path or 'Raíz visible de la app Dropbox')
        for row in rows:
            if self.file and not row['folder'] and PurePosixPath(row['path']).suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if not self.file and not row['folder']:
                continue
            item = QListWidgetItem(('Carpeta: ' if row['folder'] else 'Archivo: ') + row['name'])
            item.setData(Qt.UserRole, row)
            self.entries.addItem(item)
        self.status.setText('Doble clic para abrir una carpeta. Las rutas parten de la raíz visible de esta app.')

    def finished_task(self):
        task, self.task = self.task, None
        task.deleteLater()
        if self.close_pending:
            super().reject()
            return
        self.entries.setEnabled(True)
        self.up.setEnabled(bool(self.path))
        self._selection_changed()

    def _selection_changed(self):
        item = self.entries.currentItem()
        row = item.data(Qt.UserRole) if item else None
        self.choose.setEnabled(self.task is None and
                               (bool(row and not row['folder']) if self.file else bool(self.path)))

    def enter(self, item):
        row = item.data(Qt.UserRole)
        if row['folder']:
            self.load(row['path'])

    def select(self):
        if not self.choose.isEnabled():
            return
        item = self.entries.currentItem()
        self.selected_path = item.data(Qt.UserRole)['path'] if self.file else self.path
        self.accept()

    def reject(self):
        if self.task is not None:
            self.close_pending = True
            self.task.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText('Cancelando; se espera la solicitud en curso…')
        else:
            super().reject()

    def closeEvent(self, event):
        if self.task is not None:
            self.reject()
            event.ignore()
        else:
            super().closeEvent(event)
