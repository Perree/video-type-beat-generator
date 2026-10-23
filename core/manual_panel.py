# -*- coding: utf-8 -*-
"""Pestaña «Manual»: arrastrar beats locales y generar videos al toque, sin nube.

El estilo de cada canal vive en su perfil (``core.channel_profile``), dentro de la carpeta local
de canales (normalmente ``<Dropbox>/TypeBeat Local``). La lógica de render está en
``core.manual_render``; acá solo la UI y el hilo de trabajo.
"""
import os
import subprocess
import sys

from PyQt5.QtCore import QStandardPaths, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QApplication, QComboBox, QFileDialog,
                             QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                             QListWidget, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QVBoxLayout, QWidget)

from core import channel_profile as cp
from core import local_migration
from core import manual_render as mr
from core.profile_editor import ProfileEditor
from ui_theme import ACCENT_GENERATE, ACCENT_GENERATE_HOVER

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


class BeatDropList(QListWidget):
    """Lista que acepta archivos y carpetas arrastrados (se queda solo con los audios)."""
    paths_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

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


class ManualWorker(QThread):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(list, list)     # resultados, errores
    failed = pyqtSignal(str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def run(self):
        try:
            results, errors = mr.run_batch(
                progress=lambda d, t, text: self.progress.emit(d, t, text),
                cancelled=lambda: self._cancel, **self.job)
            self.done.emit(results, errors)
        except mr.Cancelled:
            self.failed.emit('Cancelado. Los videos ya terminados quedaron en la carpeta.')
        except (mr.ManualError, cp.ProfileError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - mostrar algo en vez de cerrar la app
            self.failed.emit(f'Error inesperado: {exc}')


class ManualPanel(QWidget):
    def __init__(self, parent=None, settings_path=mr.SETTINGS_FILE, local_root=None,
                 legacy_root=REPO_ROOT):
        super().__init__(parent)
        self.settings_path = settings_path
        self.legacy_root = legacy_root
        self.settings = mr.load_settings(settings_path)
        if local_root is not None:
            self.settings['local_root'] = local_root
        if not self.settings.get('output_folder_custom'):
            self.settings['output_folder'] = desktop_output_folder()
        self.worker = None
        self.beats = []
        self.profile = None
        self._build()
        self.reload_channels()

    @property
    def local_root(self):
        return self.settings.get('local_root') or ''

    # --- UI ---

    def _build(self):
        layout = QVBoxLayout(self)

        intro = QLabel('Arrastrá beats (o carpetas con beats) a la lista. Se generan en esta PC con el '
                       'estilo del canal elegido; no se sube nada.')
        intro.setWordWrap(True)
        layout.addWidget(intro)

        beats_box = QGroupBox('Beats')
        beats_layout = QVBoxLayout(beats_box)
        self.beat_list = BeatDropList()
        self.beat_list.setMinimumHeight(140)
        self.beat_list.paths_dropped.connect(self.add_paths)
        beats_layout.addWidget(self.beat_list)
        row = QHBoxLayout()
        self.btn_add_files = QPushButton('Agregar archivos')
        self.btn_add_files.clicked.connect(self._pick_files)
        self.btn_add_folder = QPushButton('Agregar carpeta')
        self.btn_add_folder.clicked.connect(self._pick_folder)
        self.btn_remove = QPushButton('Quitar seleccionados')
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_clear = QPushButton('Vaciar')
        self.btn_clear.clicked.connect(self.clear_beats)
        for button in (self.btn_add_files, self.btn_add_folder, self.btn_remove, self.btn_clear):
            row.addWidget(button)
        row.addStretch()
        self.count_label = QLabel()
        row.addWidget(self.count_label)
        beats_layout.addLayout(row)
        layout.addWidget(beats_box, 1)

        opts = QGroupBox('Canal')
        form = QFormLayout(opts)
        root_row = QHBoxLayout()
        self.root_label = QLabel()
        self.root_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        root_row.addWidget(self.root_label, 1)
        self.btn_root = QPushButton('Cambiar')
        self.btn_root.clicked.connect(self._pick_root)
        self.btn_open_root = QPushButton('Abrir')
        self.btn_open_root.clicked.connect(lambda: self.local_root and _open_path(self.local_root))
        root_row.addWidget(self.btn_root)
        root_row.addWidget(self.btn_open_root)
        form.addRow('Carpeta de canales:', root_row)

        channel_row = QHBoxLayout()
        self.channel_combo = QComboBox()
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        channel_row.addWidget(self.channel_combo, 1)
        self.btn_edit = QPushButton('Editar perfil')
        self.btn_edit.clicked.connect(self.edit_profile)
        self.btn_new = QPushButton('Nuevo canal')
        self.btn_new.clicked.connect(self.new_channel)
        self.btn_import = QPushButton('Importar canales anteriores')
        self.btn_import.clicked.connect(self.import_legacy)
        self.btn_reload = QPushButton('Recargar')
        self.btn_reload.clicked.connect(self.reload_channels)
        for button in (self.btn_edit, self.btn_new, self.btn_import, self.btn_reload):
            channel_row.addWidget(button)
        form.addRow('Canal:', channel_row)

        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        form.addRow('Estilo:', self.summary_label)
        self.preview_label = QLabel()
        self.preview_label.setWordWrap(True)
        self.preview_label.setStyleSheet('color: #888;')
        form.addRow('Título:', self.preview_label)

        out_row = QHBoxLayout()
        self.output_label = QLabel(self.settings['output_folder'])
        self.output_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        btn_out = QPushButton('Cambiar')
        btn_out.clicked.connect(self._pick_output)
        btn_open_out = QPushButton('Abrir')
        btn_open_out.clicked.connect(lambda: _open_path(self.settings['output_folder']))
        out_row.addWidget(self.output_label, 1)
        out_row.addWidget(btn_out)
        out_row.addWidget(btn_open_out)
        form.addRow('Guardar en:', out_row)
        layout.addWidget(opts)

        actions = QHBoxLayout()
        self.btn_generate = QPushButton('Generar videos')
        self.btn_generate.setStyleSheet(
            f'QPushButton {{ background: {ACCENT_GENERATE}; color: white; font-weight: bold;'
            f' padding: 8px 18px; }} QPushButton:hover {{ background: {ACCENT_GENERATE_HOVER}; }}'
            ' QPushButton:disabled { background: #555; color: #aaa; }')
        self.btn_generate.clicked.connect(self.start)
        self.btn_cancel = QPushButton('Cancelar')
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        actions.addWidget(self.btn_generate)
        actions.addWidget(self.btn_cancel)
        actions.addWidget(self.progress, 1)
        layout.addLayout(actions)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(130)
        layout.addWidget(self.log)
        self._refresh_beats()

    # --- Beats ---

    def add_paths(self, paths):
        known = {os.path.normcase(p) for p in self.beats}
        added = [p for p in mr.collect_audio(paths) if os.path.normcase(p) not in known]
        self.beats.extend(added)
        self._refresh_beats()
        if paths and not added:
            self._say('No se agregó nada: no hay audios nuevos (mp3, wav, m4a, aac, flac, ogg).')
        return added

    def clear_beats(self):
        self.beats = []
        self._refresh_beats()

    def _remove_selected(self):
        rows = sorted((self.beat_list.row(i) for i in self.beat_list.selectedItems()), reverse=True)
        for row in rows:
            del self.beats[row]
        self._refresh_beats()

    def _refresh_beats(self):
        self.beat_list.clear()
        for path in self.beats:
            self.beat_list.addItem(os.path.basename(path))
            self.beat_list.item(self.beat_list.count() - 1).setToolTip(path)
        self.count_label.setText(f'{len(self.beats)} beats')
        self._refresh_preview()
        self._update_buttons()

    def _pick_files(self):
        start = self.settings.get('last_beats_folder', '')
        files, _ = QFileDialog.getOpenFileNames(
            self, 'Elegir beats', start,
            'Audio (' + ' '.join('*' + s for s in mr.AUDIO_SUFFIXES) + ')')
        if files:
            self.settings['last_beats_folder'] = os.path.dirname(files[0])
            self.add_paths(files)

    def _pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Elegir carpeta con beats',
                                                  self.settings.get('last_beats_folder', ''))
        if folder:
            self.settings['last_beats_folder'] = folder
            self.add_paths([folder])

    # --- Canales y perfiles ---

    def channel(self):
        return self.channel_combo.currentText()

    def reload_channels(self, select=None):
        root = self.local_root
        self.root_label.setText(root or 'Sin carpeta: elegila con «Cambiar».')
        names = cp.list_channels(root) if root else []
        current = select or self.channel() or self.settings.get('channel', '')
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self.channel_combo.addItems(names)
        index = self.channel_combo.findText(current)
        self.channel_combo.setCurrentIndex(index if index >= 0 else 0)
        self.channel_combo.blockSignals(False)
        self._on_channel_changed(self.channel())

    def _on_channel_changed(self, channel):
        self.profile = None
        if not channel:
            hint = ('No hay canales todavía. Usá «Importar canales anteriores» o «Nuevo canal».'
                    if self.local_root else 'Elegí la carpeta de canales.')
            self.summary_label.setText(hint)
            self._refresh_preview()
            self._update_buttons()
            return
        try:
            self.profile = cp.load(self.local_root, channel)
        except cp.ProfileError as exc:
            self.summary_label.setText(f'⚠ {exc}')
            self._refresh_preview()
            self._update_buttons()
            return
        mode = self.profile['fondo']
        ready, remote = cp.media(self.local_root, channel, mode)
        thumbs, _ = cp.media(self.local_root, channel, 'thumbnail')
        kind = 'Imagen' if mode == cp.MODE_IMAGE else 'Video stock'
        noun = 'imágenes' if mode == cp.MODE_IMAGE else 'videos'
        parts = [f'Fondo: {kind}', f'{len(ready)} {noun}',
                 f'{len(thumbs)} miniaturas propias' if thumbs else 'miniatura = el mismo fondo']
        if self.profile['miniatura_con_titulo']:
            parts.append('título en la miniatura')
        if remote:
            parts.append(f'⚠ {len(remote)} sin bajar de Dropbox')
        if cp.conflicts(self.local_root, channel):
            parts.append('⚠ hay copias en conflicto de Dropbox')
        self.summary_label.setText(' · '.join(parts))
        self._refresh_preview()
        self._update_buttons()

    def _refresh_preview(self):
        if not self.profile:
            self.preview_label.setText('')
            return
        name = mr.beat_name(self.beats[0]) if self.beats else 'Nombre del beat'
        title = mr.beat_title(self.profile, name, self.channel())
        self.preview_label.setText(f'Ej.: {title}  ({len(title)}/100)')

    def edit_profile(self):
        if not self.channel():
            return
        dialog = ProfileEditor(self.local_root, self.channel(), self)
        if dialog.exec_():
            self.reload_channels(select=dialog.created or self.channel())

    def new_channel(self):
        if not self.local_root:
            self._pick_root()
            if not self.local_root:
                return
        name, ok = QInputDialog.getText(self, 'Nuevo canal', 'Nombre del canal:')
        if not ok or not name.strip():
            return
        try:
            if name.strip() in cp.list_channels(self.local_root):
                raise cp.ProfileError(f'Ya existe un canal llamado {name.strip()}.')
            cp.create(self.local_root, name.strip())
        except cp.ProfileError as exc:
            QMessageBox.warning(self, 'Nuevo canal', str(exc))
            return
        self.reload_channels(select=name.strip())
        self.edit_profile()

    def import_legacy(self):
        """Copia los canales del modo manual anterior (images/, videos/, app_config) sin borrar nada."""
        if not self.local_root:
            self._pick_root()
            if not self.local_root:
                return
        actions = local_migration.plan(self.legacy_root, self.local_root)
        if not actions:
            QMessageBox.information(self, 'Importar canales', 'No se encontraron canales anteriores.')
            return
        lines = local_migration.summary(actions)
        shown = '\n'.join(lines[:30]) + (f'\n… y {len(lines) - 30} más' if len(lines) > 30 else '')
        answer = QMessageBox.question(
            self, 'Importar canales anteriores',
            f'Se copian a:\n{self.local_root}\n\n{shown}\n\nNo se borra ni se pisa nada. ¿Copiar?',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = local_migration.apply(actions, self.local_root)
        except OSError as exc:
            result = {'canales': 0, 'archivos': 0, 'errores': [f'No se pudo copiar: {exc}']}
        finally:
            QApplication.restoreOverrideCursor()
        self._say(f"Importados: {result['canales']} canales nuevos, {result['archivos']} archivos copiados.")
        for error in result['errores']:
            self._say(f'✗ {error}')
        self.reload_channels()

    def _pick_root(self):
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta de canales (dentro de Dropbox)',
                                                  self.local_root or os.path.expanduser('~'))
        if folder:
            self.settings['local_root'] = os.path.normpath(folder)
            self._save()
            self.reload_channels()

    def _pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta donde guardar los videos',
                                                  self.settings['output_folder'])
        if folder:
            folder = os.path.normpath(folder)
            self.settings['output_folder'] = folder
            self.settings['output_folder_custom'] = True
            self.output_label.setText(folder)
            self._save()

    # --- Generar ---

    def _update_buttons(self):
        busy = self.worker is not None
        ready = bool(self.beats) and self.profile is not None
        self.btn_generate.setEnabled(ready and not busy)
        self.btn_cancel.setEnabled(busy)
        self.btn_edit.setEnabled(bool(self.channel()) and not busy)
        for widget in (self.btn_add_files, self.btn_add_folder, self.btn_remove, self.btn_clear,
                       self.channel_combo, self.btn_new, self.btn_import, self.btn_reload,
                       self.btn_root):
            widget.setEnabled(not busy)
        self.beat_list.setAcceptDrops(not busy)

    def _say(self, text):
        self.log.appendPlainText(text)

    def _save(self):
        self.settings['channel'] = self.channel()
        try:
            mr.save_settings(self.settings, self.settings_path)
        except OSError:
            pass  # preferencias de comodidad: no frenan la generación

    def job(self):
        return dict(beats=list(self.beats), channel=self.channel(), local_root=self.local_root,
                    output_root=self.settings['output_folder'], profile=self.profile)

    def start(self):
        if self.worker is not None or not self.beats or not self.profile:
            return
        job = self.job()
        ready, remote = cp.media(job['local_root'], job['channel'], self.profile['fondo'])
        if not ready:
            noun = 'imágenes' if self.profile['fondo'] == cp.MODE_IMAGE else 'videos'
            folder = os.path.join(cp.channel_dir(job['local_root'], job['channel']), cp.BACKGROUNDS_DIR)
            extra = f'\n\nHay {len(remote)} archivos que Dropbox todavía no bajó a esta PC.' if remote else ''
            QMessageBox.warning(self, 'Falta contenido',
                                f'No hay {noun} para {job["channel"]}.\n\nAgregalos en:\n{folder}{extra}')
            return
        self._save()
        self.worker = ManualWorker(job, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)
        self.progress.setRange(0, len(job['beats']))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self._say(f'Generando {len(job["beats"])} videos para {job["channel"]}…')
        self._update_buttons()
        self.worker.start()

    def cancel(self):
        if self.worker is not None:
            self.worker.cancel()
            self._say('Cancelando…')

    def _on_progress(self, done, total, text):
        self.progress.setValue(done)
        self._say(text)

    def _on_done(self, results, errors):
        for name, error in errors:
            self._say(f'✗ {name}: {error}')
        folder = os.path.join(self.settings['output_folder'], self.channel())
        self._say(f'✓ {len(results)} videos listos en {folder}')
        if results and not errors:
            self.clear_beats()

    def _on_failed(self, text):
        self._say(f'✗ {text}')

    def _on_finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.progress.setVisible(False)
        self._update_buttons()

    def shutdown(self, wait_ms=5000):
        """Al cerrar la app: corta la tanda en curso (ffmpeg incluido)."""
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait(wait_ms)
