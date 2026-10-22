# -*- coding: utf-8 -*-
"""Pestaña «Manual»: arrastrar beats locales y generar videos al toque, sin nube.

La lógica vive en ``core.manual_render``; acá solo la UI y el hilo de trabajo.
"""
import os
import subprocess
import sys

from PyQt5.QtCore import QStandardPaths, Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox,
                             QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
                             QLineEdit, QListWidget, QMessageBox, QPlainTextEdit, QProgressBar,
                             QPushButton, QRadioButton, QVBoxLayout, QWidget)

from core import manual_render as mr
from ui_theme import ACCENT_GENERATE, ACCENT_GENERATE_HOVER


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
        except mr.ManualError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - mostrar algo en vez de cerrar la app
            self.failed.emit(f'Error inesperado: {exc}')


class ManualPanel(QWidget):
    def __init__(self, parent=None, root='.', settings_path=mr.SETTINGS_FILE):
        super().__init__(parent)
        self.root = root
        self.settings_path = settings_path
        self.settings = mr.load_settings(settings_path)
        if not self.settings.get('output_folder_custom'):
            self.settings['output_folder'] = desktop_output_folder()
        self.worker = None
        self.beats = []
        self._channels = {}
        self._build()
        self.reload_channels()

    # --- UI ---

    def _build(self):
        layout = QVBoxLayout(self)

        intro = QLabel('Arrastrá beats (o carpetas con beats) a la lista. Se generan en esta PC '
                       'con las imágenes o videos stock del canal; no se sube nada.')
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

        opts = QGroupBox('Canal y estilo del video')
        form = QFormLayout(opts)
        channel_row = QHBoxLayout()
        self.channel_combo = QComboBox()
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        self.group_combo = QComboBox()
        self.group_combo.currentTextChanged.connect(self._refresh_counts)
        self.btn_reload = QPushButton('Recargar')
        self.btn_reload.clicked.connect(self.reload_channels)
        channel_row.addWidget(self.channel_combo, 2)
        channel_row.addWidget(QLabel('Grupo:'))
        channel_row.addWidget(self.group_combo, 1)
        channel_row.addWidget(self.btn_reload)
        form.addRow('Canal:', channel_row)

        mode_row = QHBoxLayout()
        self.radio_image = QRadioButton('Imagen')
        self.radio_video = QRadioButton('Video stock')
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_image)
        self.mode_group.addButton(self.radio_video)
        (self.radio_video if self.settings['mode'] == mr.MODE_VIDEO else self.radio_image).setChecked(True)
        self.radio_image.toggled.connect(self._refresh_counts)
        mode_row.addWidget(self.radio_image)
        mode_row.addWidget(self.radio_video)
        mode_row.addStretch()
        form.addRow('Fondo:', mode_row)

        content_row = QHBoxLayout()
        self.content_label = QLabel()
        content_row.addWidget(self.content_label, 1)
        self.btn_open_content = QPushButton('Abrir carpeta del fondo')
        self.btn_open_content.clicked.connect(lambda: self._open_content(self.mode()))
        self.btn_open_thumbs = QPushButton('Abrir carpeta de miniaturas')
        self.btn_open_thumbs.clicked.connect(lambda: self._open_content('thumbnail'))
        content_row.addWidget(self.btn_open_content)
        content_row.addWidget(self.btn_open_thumbs)
        form.addRow('Contenido:', content_row)

        self.template_edit = QLineEdit()
        self.template_edit.setToolTip('{name} = nombre del archivo del beat. También {channel} y {group}.')
        self.template_edit.textChanged.connect(self._refresh_preview)
        form.addRow('Título:', self.template_edit)
        self.preview_label = QLabel()
        self.preview_label.setStyleSheet('color: #888;')
        form.addRow('', self.preview_label)

        self.check_title_thumb = QCheckBox('Poner el título sobre la miniatura')
        self.check_title_thumb.setChecked(bool(self.settings.get('title_on_thumbnail')))
        form.addRow('', self.check_title_thumb)

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

    # --- Canal y contenido ---

    def mode(self):
        return mr.MODE_VIDEO if self.radio_video.isChecked() else mr.MODE_IMAGE

    def reload_channels(self):
        self._channels = mr.channels(self.root)
        current = self.channel_combo.currentText() or self.settings.get('channel', '')
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self.channel_combo.addItems(list(self._channels))
        index = self.channel_combo.findText(current)
        self.channel_combo.setCurrentIndex(index if index >= 0 else 0)
        self.channel_combo.blockSignals(False)
        self._on_channel_changed(self.channel_combo.currentText())

    def _on_channel_changed(self, channel):
        groups = self._channels.get(channel, [])
        self.group_combo.blockSignals(True)
        self.group_combo.clear()
        self.group_combo.addItems(groups)
        saved = self.settings.get('group', '') if channel == self.settings.get('channel') else ''
        index = self.group_combo.findText(saved)
        self.group_combo.setCurrentIndex(index if index >= 0 else 0)
        self.group_combo.blockSignals(False)
        template = self.settings['templates'].get(channel) or mr.title_template(channel, self.root)
        self.template_edit.setText(template)
        self._refresh_counts()

    def _refresh_counts(self):
        channel, group = self.channel_combo.currentText(), self.group_combo.currentText()
        if not channel or not group:
            self.content_label.setText('Sin canales: creá carpetas en images/<canal>/<grupo>.')
            self._update_buttons()
            return
        n = mr.counts(channel, group, self.root)
        thumbs = (f"{n['thumbnail']} miniaturas propias" if n['thumbnail']
                  else 'miniatura = el mismo fondo')
        self.content_label.setText(f"{n[mr.MODE_IMAGE]} imágenes · {n[mr.MODE_VIDEO]} videos · {thumbs}")
        self._update_buttons()

    def _refresh_preview(self):
        name = mr.beat_name(self.beats[0]) if self.beats else 'Nombre del beat'
        title = self.template_edit.text().replace('{name}', name).replace(
            '{channel}', self.channel_combo.currentText()).replace('{group}', self.group_combo.currentText())
        self.preview_label.setText(f'Ej.: {title}')

    def _open_content(self, kind):
        channel, group = self.channel_combo.currentText(), self.group_combo.currentText()
        if channel and group:
            _open_path(os.path.abspath(mr.content_folder(kind, channel, group, self.root)))

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
        ready = bool(self.beats) and bool(self.channel_combo.currentText()) and bool(self.group_combo.currentText())
        self.btn_generate.setEnabled(ready and not busy)
        self.btn_cancel.setEnabled(busy)
        for widget in (self.btn_add_files, self.btn_add_folder, self.btn_remove, self.btn_clear,
                       self.channel_combo, self.group_combo, self.radio_image, self.radio_video,
                       self.template_edit, self.check_title_thumb, self.btn_reload):
            widget.setEnabled(not busy)
        self.beat_list.setAcceptDrops(not busy)

    def _say(self, text):
        self.log.appendPlainText(text)

    def _save(self):
        channel = self.channel_combo.currentText()
        self.settings.update(channel=channel, group=self.group_combo.currentText(), mode=self.mode(),
                             title_on_thumbnail=self.check_title_thumb.isChecked())
        if channel:
            self.settings['templates'][channel] = self.template_edit.text()
        try:
            mr.save_settings(self.settings, self.settings_path)
        except OSError:
            pass  # preferencias de comodidad: no frenan la generación

    def job(self):
        return dict(beats=list(self.beats), channel=self.channel_combo.currentText(),
                    group=self.group_combo.currentText(), mode=self.mode(),
                    template=self.template_edit.text().strip() or '{name}',
                    output_root=self.settings['output_folder'],
                    title_on_thumbnail=self.check_title_thumb.isChecked(), root=self.root)

    def start(self):
        if self.worker is not None or not self.beats:
            return
        job = self.job()
        if not mr.list_media(job['mode'], job['channel'], job['group'], self.root):
            kind = 'imágenes' if job['mode'] == mr.MODE_IMAGE else 'videos'
            folder = os.path.abspath(mr.content_folder(job['mode'], job['channel'], job['group'], self.root))
            QMessageBox.warning(self, 'Falta contenido',
                                f'No hay {kind} para {job["channel"]}/{job["group"]}.\n\n'
                                f'Agregalos en:\n{folder}')
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
        self._say(f'Generando {len(job["beats"])} videos para {job["channel"]}/{job["group"]}…')
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
        folder = os.path.join(self.settings['output_folder'], self.channel_combo.currentText())
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
