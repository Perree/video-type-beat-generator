# -*- coding: utf-8 -*-
"""Navegador de carpetas de Dropbox (solo mp3/wav) con importación a la biblioteca."""
import webbrowser
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
                             QPushButton, QLabel, QAbstractItemView, QInputDialog, QMessageBox)
from core import dropbox_client


class _ImportWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(int, int, list)

    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def run(self):
        try:
            n, d, errs = dropbox_client.import_files(
                self.paths, progress=lambda i, t, name: self.progress.emit(i, t, name))
        except Exception as e:
            n, d, errs = 0, 0, [str(e)]
        self.done.emit(n, d, errs)


class DropboxBrowserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Importar desde Dropbox")
        self.resize(560, 480)
        self.current = ''
        self._worker = None

        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.btn_up = QPushButton("⬆ Subir")
        self.btn_up.clicked.connect(self._go_up)
        self.path_label = QLabel("/")
        self.btn_connect = QPushButton("Conectar Dropbox")
        self.btn_connect.clicked.connect(self._connect)
        top.addWidget(self.btn_up)
        top.addWidget(self.path_label, 1)
        top.addWidget(self.btn_connect)
        layout.addLayout(top)

        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.list.itemDoubleClicked.connect(self._open_item)
        layout.addWidget(self.list)

        bottom = QHBoxLayout()
        self.status = QLabel("")
        self.btn_import = QPushButton("Importar a biblioteca")
        self.btn_import.clicked.connect(self._import)
        btn_close = QPushButton("Cerrar")
        btn_close.clicked.connect(self.reject)
        bottom.addWidget(self.status, 1)
        bottom.addWidget(self.btn_import)
        bottom.addWidget(btn_close)
        layout.addLayout(bottom)

        if dropbox_client.is_connected():
            self._load('')
        else:
            self.status.setText("Conectá tu cuenta de Dropbox para empezar.")

    def _connect(self):
        try:
            flow, url = dropbox_client.start_auth()
            webbrowser.open(url)
            code, ok = QInputDialog.getText(
                self, "Conectar Dropbox",
                "Autorizá la app en el navegador y pegá acá el código:")
            if not ok or not code.strip():
                return
            dropbox_client.finish_auth(flow, code)
        except dropbox_client.DropboxError as e:
            QMessageBox.warning(self, "Dropbox", str(e))
            return
        self._load('')

    def _load(self, path):
        try:
            items = dropbox_client.list_folder(path)
        except dropbox_client.DropboxError as e:
            QMessageBox.warning(self, "Dropbox", str(e))
            return
        self.current = path
        self.path_label.setText(path or "/")
        self.list.clear()
        for it in items:
            label = f"📁 {it['name']}" if it['is_folder'] else f"🎵 {it['name']}"
            li = QListWidgetItem(label)
            li.setData(Qt.UserRole, it)
            self.list.addItem(li)
        self.status.setText(f"{len(items)} elementos")

    def _open_item(self, li):
        it = li.data(Qt.UserRole)
        if it['is_folder']:
            self._load(it['path'])

    def _go_up(self):
        if self.current:
            self._load(self.current.rsplit('/', 1)[0])

    def _import(self):
        paths = [i.data(Qt.UserRole)['path'] for i in self.list.selectedItems()
                 if not i.data(Qt.UserRole)['is_folder']]
        if not paths:
            QMessageBox.information(self, "Dropbox", "Seleccioná uno o más archivos de audio.")
            return
        self.btn_import.setEnabled(False)
        self._worker = _ImportWorker(paths)
        self._worker.progress.connect(
            lambda i, t, name: self.status.setText(f"Descargando {i + 1}/{t}: {name}"))
        self._worker.done.connect(self._on_done)
        self._worker.start()

    def _on_done(self, nuevos, duplicados, errores):
        self.btn_import.setEnabled(True)
        msg = f"Importados: {nuevos}. Ya existían: {duplicados}."
        if errores:
            msg += "\n\nErrores:\n" + "\n".join(errores[:10])
        self.status.setText(f"Importados {nuevos}, duplicados {duplicados}, errores {len(errores)}")
        QMessageBox.information(self, "Dropbox", msg)
