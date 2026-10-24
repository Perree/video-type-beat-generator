"""Select public BeatStars previews for a frozen local channel and destination."""
import json
from pathlib import Path

from PyQt5.QtCore import Qt, QUrl, pyqtSignal
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFormLayout,
                             QHeaderView, QHBoxLayout, QLabel, QLineEdit, QProgressBar,
                             QPushButton, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
                             QVBoxLayout, QWidget)

from core.beat_http import BeatError, PROFILE_HOSTS, check_url
from core.beat_source import profile_username
from core.manual_beatstars import ManualBeatStars, filter_tags
from core.manual_beatstars_task import ManualBeatStarsTask, error_message


def initial_preferences(settings, config_path):
    stored = settings.get('beatstars', {})
    stored = stored if isinstance(stored, dict) else {}
    profile = stored.get('profile_url')
    if not isinstance(profile, str):
        try:
            config = json.loads(Path(config_path).read_text(encoding='utf-8'))
            profile = config.get('beat_automation', {}).get('beatstars_profile_url', '')
        except (OSError, ValueError, AttributeError):
            profile = ''
    count = stored.get('quantity', 10)
    return dict(profile_url=profile if isinstance(profile, str) else '',
                tags=stored.get('tags') if isinstance(stored.get('tags'), str) else '',
                quantity=min(100, max(1, count)) if type(count) is int else 10,
                match=stored.get('match') if stored.get('match') in ('any', 'all') else 'any',
                include_downloaded=stored.get('include_downloaded') is True)


class ManualBeatStarsDialog(QDialog):
    packages_ready = pyqtSignal(list)
    preferences_changed = pyqtSignal(dict)

    def __init__(self, channel, destination, preferences, parent=None, service_factory=ManualBeatStars):
        super().__init__(parent)
        self.channel, self.destination = channel, str(Path(destination).resolve())
        self.service_factory = service_factory
        self.task = None
        self.search_result = None
        self.last_batch = None
        self._close_pending = False
        self.setWindowTitle('Descargar desde BeatStars')
        self.setWindowModality(Qt.WindowModal)
        self.setMinimumSize(650, 500)
        self.resize(900, 640)
        self.setStyleSheet('QDialog { background-color: #2b2b2b; }')
        layout = QVBoxLayout(self)
        destination_label = QLabel(f'Canal: {channel}\nCarpeta de entrada: {self.destination}')
        destination_label.setTextFormat(Qt.PlainText)
        destination_label.setWordWrap(True)
        layout.addWidget(destination_label)
        hint = QLabel('Se descarga el audio público del reproductor; puede incluir el tag de productor. '
                      'Después elegís cómo generar los videos en la pantalla manual.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        fields = QWidget()
        fields.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        form = QFormLayout(fields)
        form.setContentsMargins(0, 0, 0, 0)
        self.profile_edit = QLineEdit(preferences['profile_url'])
        self.profile_edit.setPlaceholderText('https://www.beatstars.com/tu_perfil')
        form.addRow('Tu perfil:', self.profile_edit)
        self.tags_edit = QLineEdit(preferences['tags'])
        self.tags_edit.setPlaceholderText('trap, dark, travis scott (vacío: todo el catálogo)')
        self.tags_edit.setToolTip('Coincide con tags completos, sin distinguir mayúsculas. Separá los tags con comas.')
        form.addRow('Tags:', self.tags_edit)
        options = QHBoxLayout()
        self.quantity = QSpinBox()
        self.quantity.setRange(1, 100)
        self.quantity.setValue(preferences['quantity'])
        options.addWidget(QLabel('Cantidad:'))
        options.addWidget(self.quantity)
        self.match = QComboBox()
        self.match.addItem('Cualquiera de los tags', 'any')
        self.match.addItem('Todos los tags', 'all')
        self.match.setCurrentIndex(self.match.findData(preferences['match']))
        options.addWidget(self.match)
        options.addStretch()
        form.addRow(options)
        self.include_downloaded = QCheckBox('Incluir ya descargados (historial compartido entre canales)')
        self.include_downloaded.setChecked(preferences['include_downloaded'])
        form.addRow(self.include_downloaded)
        layout.addWidget(fields)
        self.selection_label = QLabel('Buscá beats para elegir cuáles descargar.')
        self.selection_label.setWordWrap(True)
        layout.addWidget(self.selection_label)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['✓', 'Beat', 'Tags', 'Enlace', 'Estado'])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setWordWrap(False)
        self.table.verticalHeader().hide()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 230)
        self.table.setColumnWidth(4, 115)
        layout.addWidget(self.table, 1)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.search_button = QPushButton('Buscar beats')
        self.download_button = QPushButton('Descargar seleccionados')
        self.cancel_button = QPushButton('Cancelar operación')
        self.close_button = QPushButton('Cerrar')
        for button in (self.search_button, self.download_button, self.cancel_button, self.close_button):
            button.setAutoDefault(False)
            actions.addWidget(button)
        layout.addLayout(actions)
        self.search_button.clicked.connect(self.search)
        self.download_button.clicked.connect(self.download)
        self.cancel_button.clicked.connect(self.cancel)
        self.close_button.clicked.connect(self.reject)
        self.profile_edit.returnPressed.connect(self.search)
        self.tags_edit.returnPressed.connect(self.search)
        for signal in (self.profile_edit.textChanged, self.tags_edit.textChanged,
                       self.match.currentIndexChanged, self.include_downloaded.toggled):
            signal.connect(self._invalidate)
        self.quantity.valueChanged.connect(self._preselect)
        self.table.itemChanged.connect(self._checked)
        self.table.cellDoubleClicked.connect(self._open_link)
        # Wrapped error summaries must not squeeze the search fields below their text.
        for field in (self.profile_edit, self.tags_edit, self.quantity, self.match, self.include_downloaded,
                      *fields.findChildren(QLabel)):
            field.ensurePolished()
            field.setMinimumHeight(field.minimumSizeHint().height())
        self._update_controls()

    def preferences(self):
        return dict(profile_url=self.profile_edit.text().strip(), tags=self.tags_edit.text().strip(),
                    quantity=self.quantity.value(), match=self.match.currentData(),
                    include_downloaded=self.include_downloaded.isChecked())

    def _invalidate(self):
        self.search_result = None
        self.table.setRowCount(0)
        self.selection_label.setText('Los filtros cambiaron. Volvé a buscar los beats.')
        self.status.clear()
        self._update_controls()

    def selected_ids(self):
        return [self.table.item(row, 0).data(Qt.UserRole) for row in range(self.table.rowCount())
                if self.table.item(row, 0).checkState() == Qt.Checked]

    def _preselect(self):
        self.table.blockSignals(True)
        remaining = self.quantity.value()
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            checked = remaining > 0 and bool(item.flags() & Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
            remaining -= int(checked)
        self.table.blockSignals(False)
        self._update_controls()

    def _checked(self, item):
        if item.column() != 0:
            return
        if len(self.selected_ids()) > self.quantity.value():
            self.table.blockSignals(True)
            item.setCheckState(Qt.Unchecked)
            self.table.blockSignals(False)
            self.status.setText(f'Podés seleccionar hasta {self.quantity.value()} beats para esta tanda.')
        self._update_controls()

    def _update_controls(self):
        busy = self.task is not None
        for widget in (self.profile_edit, self.tags_edit, self.quantity, self.match,
                       self.include_downloaded, self.table, self.search_button):
            widget.setEnabled(not busy)
        selected = len(self.selected_ids())
        self.download_button.setEnabled(not busy and self.search_result is not None and selected > 0)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy and not self.task.cancel_event.is_set())
        if self.search_result is not None:
            total = self.table.rowCount()
            self.selection_label.setText(f'{total} beats encontrados · {selected} seleccionados '
                                         f'(hasta {self.quantity.value()}).')

    def search(self):
        if self.task is not None:
            return
        prefs = self.preferences()
        self._invalidate()
        try:
            profile_username(prefs['profile_url'])
            tuple(filter_tags((), prefs['tags'], prefs['match']))
        except (BeatError, ValueError) as exc:
            self.status.setText(error_message(str(exc)))
            return
        self.preferences_changed.emit(prefs)
        self._start('search', {key: prefs[key] for key in ('profile_url', 'tags', 'match', 'include_downloaded')})

    def download(self):
        if self.task is not None or self.search_result is None or not self.selected_ids():
            return
        self.preferences_changed.emit(self.preferences())
        self._start('download', dict(search=self.search_result, track_ids=tuple(self.selected_ids()),
                                    destination=self.destination,
                                    include_downloaded=self.include_downloaded.isChecked()))

    def _start(self, action, parameters):
        self.task = ManualBeatStarsTask(action, parameters, self, self.service_factory)
        self.task.progress.connect(self._progress)
        self.task.finished.connect(self._finished)
        self.progress.setRange(0, 0) if action == 'search' else self.progress.setRange(0, len(parameters['track_ids']))
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText('Buscando en tu catálogo de BeatStars…' if action == 'search' else 'Iniciando descarga…')
        self._update_controls()
        self.task.start()

    def _progress(self, done, total, track_id):
        if self.task is None or self.task.cancel_event.is_set():
            return
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(done)
        self.status.setText(f'Descargando {track_id} ({done + 1}/{total})…' if track_id else 'Finalizando…')

    def _finished(self):
        task, self.task = self.task, None
        if task.action == 'search' and task.value is not None and not task.cancel_event.is_set():
            self.search_result = task.value
            self._fill_results()
            self.status.setText('Elegí los beats y tocá «Descargar seleccionados».' if task.value.candidates
                                else 'No hay beats disponibles con esos filtros. Probá otros tags o incluí los ya descargados.')
        elif task.action == 'download' and task.value is not None:
            self._batch_done(task.value)
        if task.error:
            summary = self.status.text() + '\n' if task.action == 'download' and task.value is not None else ''
            self.status.setText(summary + error_message(task.error))
        task.deleteLater()
        self.progress.hide()
        self._update_controls()
        if self._close_pending:
            self.reject()

    def _fill_results(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.search_result.candidates))
        for row, candidate in enumerate(self.search_result.candidates):
            track = candidate.track
            select = QTableWidgetItem()
            select.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            select.setData(Qt.UserRole, track.id)
            select.setToolTip(f'Seleccionar {track.title}')
            select.setCheckState(Qt.Unchecked)
            self.table.setItem(row, 0, select)
            for col, text in enumerate((track.title, ', '.join(track.tags), track.url,
                                        'Ya descargado' if candidate.downloaded else 'Nuevo'), 1):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        self._preselect()

    def _batch_done(self, result):
        self.last_batch = result
        paths = [str(path) for path in result.downloads]
        success_ids = {Path(path).name.split(' - ', 1)[0] for path in paths}
        errors = dict(result.errors)
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            tid = item.data(Qt.UserRole)
            if tid in success_ids or tid in result.skipped:
                item.setCheckState(Qt.Unchecked)
                status = self.table.item(row, 4)
                status.setText('Descargado' if tid in success_ids else 'Ya descargado')
                status.setToolTip(status.text())
                if not self.include_downloaded.isChecked():
                    item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
            elif tid in errors:
                self.table.item(row, 4).setText('Error')
                self.table.item(row, 4).setToolTip(error_message(errors[tid]))
        self.table.blockSignals(False)
        prefix = 'Cancelado: ' if result.cancelled else ''
        summary = (f'{prefix}{len(paths)} descargados, {len(errors)} con error, '
                   f'{len(result.skipped)} ya descargados omitidos.')
        details = [f'{tid}: {error_message(code)}' for tid, code in result.errors[:5]]
        self.status.setText('\n'.join([summary, *details]))
        if paths:
            self.packages_ready.emit(paths)

    def _open_link(self, row, column):
        if column == 3:
            url = self.table.item(row, column).text()
            try:
                check_url(url, PROFILE_HOSTS)
            except BeatError:
                return
            QDesktopServices.openUrl(QUrl(url))

    def cancel(self):
        if self.task is not None:
            self.task.cancel()
            self.status.setText('Cancelando… Se conservan las descargas completas. Esperá a que termine la operación.')
            self._update_controls()

    def request_close(self):
        self.reject()
        return self.task is None

    def reject(self):
        self.done(QDialog.Rejected)

    def done(self, result):
        if self.task is not None:
            self._close_pending = True
            self.cancel()
            return
        self.preferences_changed.emit(self.preferences())
        super().done(result)

    def closeEvent(self, event):
        if self.task is not None:
            self._close_pending = True
            self.cancel()
            event.ignore()
        else:
            super().closeEvent(event)
