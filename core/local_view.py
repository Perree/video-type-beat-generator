# -*- coding: utf-8 -*-
"""«Crear videos ahora»: el modo local en 3 pasos — canal, beats, generar.

Los beats salen de dos lados y se ven juntos en la misma tabla: los que el usuario arrastra y
los que dejó en ``entrada/<canal>/`` (carpeta de Dropbox). Lo poco usado (carpetas, importar,
caché) vive en ⚙ Configuración. La lógica está en ``manual_render`` y ``bulk_queue``.
"""
import os

from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
                             QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from core import bulk_queue as bq
from core import channel_profile as cp
from core import local_migration
from core import manual_render as mr
from core.guide_panel import GuideStep
from core.manual_panel import REPO_ROOT, BeatDropTable, _open_path, desktop_output_folder
from core.profile_editor import ProfileEditor
from ui_theme import ACCENT_GENERATE, ACCENT_GENERATE_HOVER

_STEP = 'QFrame#step { border: 1px solid #555; border-radius: 8px; }'
_GENERATE = (f'QPushButton {{ background: {ACCENT_GENERATE}; color: white; font-size: 16px; font-weight: bold;'
             f' padding: 12px 24px; }} QPushButton:hover {{ background: {ACCENT_GENERATE_HOVER}; }}'
             ' QPushButton:disabled { background: #555; color: #aaa; }')


class LocalWorker(QThread):
    """Genera un canal (beats arrastrados + su carpeta de entrada) o todos los canales con entrada."""
    progress = pyqtSignal(int, int, str)
    message = pyqtSignal(str)
    done = pyqtSignal(dict)
    failed = pyqtSignal(str)

    def __init__(self, job, parent=None):
        super().__init__(parent)
        self.job = job
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def _emit(self, done, total, text):
        self.progress.emit(done, total, text)

    def run(self):
        job = self.job
        try:
            if job['mode'] == 'all':
                ready = self._settled(bq.scan(job['root'])[0])
                summary = bq.run_bulk(job['root'], job['output'], ready, job['titles'], progress=self._emit,
                                      cancelled=lambda: self._cancel)
                self.done.emit({'summary': summary})
                return
            channel, root = job['channel'], job['root']
            inbox = {b['path'] for b in self._settled([{'channel': channel, 'path': p} for p in job['inbox']])}
            beats = [p for p in job['beats'] if p in inbox or p not in job['inbox']]

            def done(audio, result):
                if audio in inbox:
                    try:
                        bq.mark_done(root, channel, audio)
                    except OSError as exc:
                        self.message.emit(f'No se pudo mover {os.path.basename(audio)} a hechos: {exc}')

            def error(audio, message):
                if audio in inbox:
                    bq.log_error(root, channel, audio, message)

            results, errors = mr.run_batch(beats, channel, root, job['output'], job['profile'],
                                           progress=self._emit, cancelled=lambda: self._cancel,
                                           titles=job['titles'], on_done=done, on_error=error)
            self.done.emit({'summary': {channel: {'ok': len(results), 'errores': errors}}})
        except mr.Cancelled:
            self.failed.emit('Cancelado. Los videos ya terminados quedaron en la carpeta.')
        except (mr.ManualError, cp.ProfileError) as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # noqa: BLE001 - mostrar algo en vez de cerrar la app
            self.failed.emit(f'Error inesperado: {exc}')

    def _settled(self, beats):
        ready, busy = bq.settled(beats)
        for beat in busy:
            self.message.emit(f'… {os.path.basename(beat["path"])} se está copiando: queda para la próxima.')
        return ready


class LocalView(QWidget):
    assistant_requested = pyqtSignal()

    def __init__(self, parent=None, settings_path=mr.SETTINGS_FILE, local_root=None, legacy_root=REPO_ROOT):
        super().__init__(parent)
        self.settings_path = settings_path
        self.legacy_root = legacy_root
        self.settings = mr.load_settings(settings_path)
        if local_root is not None:
            self.settings['local_root'] = local_root
        if not self.settings.get('output_folder_custom'):
            self.settings['output_folder'] = desktop_output_folder()
        self.worker = None
        self.dropped = []        # beats arrastrados o elegidos a mano
        self.inbox = []          # beats en entrada/<canal>/ del canal elegido
        self.title_overrides = {}
        self.profile = None
        self.generated = 0       # videos hechos en esta sesión (para la guía)
        self._build()
        self.reload_channels()

    # --- Propiedades ---

    @property
    def local_root(self):
        return self.settings.get('local_root') or ''

    @property
    def output_root(self):
        return self.settings['output_folder']

    @property
    def beats(self):
        return self.dropped + [p for p in self.inbox if p not in self.dropped]

    def channel(self):
        return self.channel_combo.currentText()

    # --- UI ---

    def _step(self, layout, title):
        frame = QFrame()
        frame.setObjectName('step')
        frame.setStyleSheet(_STEP)
        inner = QVBoxLayout(frame)
        label = QLabel(title)
        label.setStyleSheet('font-size: 15px; font-weight: bold;')
        inner.addWidget(label)
        layout.addWidget(frame)
        return frame, inner

    def _build(self):
        layout = QVBoxLayout(self)
        header = QHBoxLayout()
        title = QLabel('Crear videos en esta PC')
        title.setStyleSheet('font-size: 18px; font-weight: bold;')
        header.addWidget(title)
        header.addStretch()
        self.btn_assistant = QPushButton('🧭 Guiame paso a paso')
        self.btn_assistant.clicked.connect(self.assistant_requested)
        header.addWidget(self.btn_assistant)
        self.btn_settings = QPushButton('⚙ Configuración')
        self.btn_settings.clicked.connect(self.open_settings)
        header.addWidget(self.btn_settings)
        layout.addLayout(header)

        self.step1, inner = self._step(layout, '1 · Elegí el canal')
        row = QHBoxLayout()
        self.channel_combo = QComboBox()
        self.channel_combo.setMinimumWidth(260)
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        row.addWidget(self.channel_combo, 1)
        self.btn_style = QPushButton('Editar estilo del canal')
        self.btn_style.clicked.connect(self.edit_profile)
        row.addWidget(self.btn_style)
        self.btn_backgrounds = QPushButton('Abrir fondos')
        self.btn_backgrounds.setToolTip('Carpeta con las imágenes o videos stock del canal.')
        self.btn_backgrounds.clicked.connect(self.open_backgrounds)
        row.addWidget(self.btn_backgrounds)
        inner.addLayout(row)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        inner.addWidget(self.summary_label)

        self.step2, inner = self._step(layout, '2 · Sumá beats')
        hint = QLabel('Arrastralos a la tabla (archivos o carpetas). También aparecen solos los que dejes en la '
                      'carpeta de entrada del canal. Doble clic en un título para cambiarlo.')
        hint.setWordWrap(True)
        hint.setStyleSheet('color: #bbb;')
        inner.addWidget(hint)
        self.table = BeatDropTable()
        self.table.setMinimumHeight(170)
        self.table.paths_dropped.connect(self.add_paths)
        self.table.itemChanged.connect(self._on_title_edited)
        inner.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.btn_add = QPushButton('Agregar beats…')
        self.btn_add.clicked.connect(self.pick_files)
        self.btn_add_folder = QPushButton('Agregar carpeta…')
        self.btn_add_folder.clicked.connect(self.pick_folder)
        self.btn_remove = QPushButton('Quitar')
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_reset = QPushButton('Restablecer títulos')
        self.btn_reset.clicked.connect(self.reset_titles)
        for button in (self.btn_add, self.btn_add_folder, self.btn_remove, self.btn_reset):
            row.addWidget(button)
        row.addStretch()
        self.count_label = QLabel()
        row.addWidget(self.count_label)
        inner.addLayout(row)
        layout.setStretchFactor(self.step2, 1)

        self.step3, inner = self._step(layout, '3 · Generá')
        row = QHBoxLayout()
        self.btn_generate = QPushButton()
        self.btn_generate.setStyleSheet(_GENERATE)
        self.btn_generate.clicked.connect(self.start)
        row.addWidget(self.btn_generate)
        self.btn_cancel = QPushButton('Cancelar')
        self.btn_cancel.clicked.connect(self.cancel)
        row.addWidget(self.btn_cancel)
        self.progress = QProgressBar()
        self.progress.setVisible(False)
        row.addWidget(self.progress, 1)
        self.btn_open_output = QPushButton('Abrir carpeta de videos')
        self.btn_open_output.clicked.connect(lambda: self.open_folder(self.output_root))
        row.addWidget(self.btn_open_output)
        inner.addLayout(row)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setVisible(False)
        inner.addWidget(self.status)
        self.others = QFrame()
        others = QHBoxLayout(self.others)
        others.setContentsMargins(0, 0, 0, 0)
        self.others_label = QLabel()
        self.others_label.setWordWrap(True)
        self.others_label.setStyleSheet('color: #f1c40f;')
        others.addWidget(self.others_label, 1)
        self.btn_all = QPushButton('Generar todos esos canales')
        self.btn_all.clicked.connect(self.start_all)
        others.addWidget(self.btn_all)
        inner.addWidget(self.others)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(90)
        self.log.setPlaceholderText('Acá aparece el avance.')
        layout.addWidget(self.log)
        self._refresh()

    # --- Canales ---

    def reload_channels(self, select=None):
        names = cp.list_channels(self.local_root) if self.local_root else []
        current = select or self.channel() or self.settings.get('channel', '')
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self.channel_combo.addItems(names)
        index = self.channel_combo.findText(current)
        self.channel_combo.setCurrentIndex(index if index >= 0 else 0)
        self.channel_combo.blockSignals(False)
        self._on_channel_changed(self.channel())

    def _on_channel_changed(self, channel):
        if channel != getattr(self, '_loaded_channel', None):
            self.title_overrides = {}
        self._loaded_channel = channel
        self.profile = None
        self.inbox = []
        if channel:
            try:
                self.profile = cp.load(self.local_root, channel)
            except cp.ProfileError as exc:
                self.summary_label.setText(f'⚠ {exc}')
        self.scan_inbox()

    def scan_inbox(self):
        """Relee las carpetas de entrada: las del canal van a la tabla, las demás al aviso de abajo."""
        beats, notes = bq.scan(self.local_root) if self.local_root else ([], [])
        channel = self.channel()
        self.inbox = [b['path'] for b in beats if b['channel'] == channel]
        counts = {}
        for beat in beats:
            if beat['channel'] != channel:
                counts[beat['channel']] = counts.get(beat['channel'], 0) + 1
        self.other_inbox = counts
        self.inbox_notes = notes
        self._refresh()

    def summary_text(self):
        if not self.local_root:
            return 'Primero elegí la carpeta de canales en ⚙ Configuración.'
        if not self.channel():
            return 'No hay canales todavía: creá uno o importá los anteriores en ⚙ Configuración.'
        if not self.profile:
            return self.summary_label.text()
        mode = self.profile['fondo']
        ready, remote = cp.media(self.local_root, self.channel(), mode)
        noun = 'imágenes' if mode == cp.MODE_IMAGE else 'videos stock'
        parts = [f'Fondo: {len(ready)} {noun}' if ready else f'⚠ Faltan {noun}: abrí «Abrir fondos» y agregalos']
        if remote:
            parts.append(f'⚠ {len(remote)} sin bajar de Dropbox')
        if cp.conflicts(self.local_root, self.channel()):
            parts.append('⚠ Dropbox dejó copias en conflicto del perfil')
        return ' · '.join(parts)

    def backgrounds_ready(self):
        return bool(self.profile) and bool(cp.media(self.local_root, self.channel(), self.profile['fondo'])[0])

    # --- Beats y títulos ---

    def add_paths(self, paths):
        known = {os.path.normcase(p) for p in self.beats}
        added = [p for p in mr.collect_audio(paths) if os.path.normcase(p) not in known]
        self.dropped.extend(added)
        if paths and not added:
            self.say('No se agregó nada: no hay audios nuevos (mp3, wav, m4a, aac, flac, ogg).')
        self._refresh()
        return added

    def pick_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, 'Elegir beats', self.settings.get('last_beats_folder', ''),
                                                'Audio (' + ' '.join('*' + s for s in mr.AUDIO_SUFFIXES) + ')')
        if files:
            self.settings['last_beats_folder'] = os.path.dirname(files[0])
            self.add_paths(files)

    def pick_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Elegir carpeta con beats',
                                                  self.settings.get('last_beats_folder', ''))
        if folder:
            self.settings['last_beats_folder'] = folder
            self.add_paths([folder])

    def remove_selected(self):
        beats = self.beats
        for row in reversed(self.table.selected_rows()):
            path = beats[row]
            self.title_overrides.pop(path, None)
            if path in self.dropped:
                self.dropped.remove(path)
            elif path in self.inbox:
                self.inbox.remove(path)  # sigue en la carpeta de entrada; vuelve al releer
        self._refresh()

    def clear_beats(self):
        self.dropped, self.title_overrides = [], {}
        self.scan_inbox()

    def reset_titles(self):
        self.title_overrides = {}
        self._refresh()

    def auto_title(self, path):
        name = mr.beat_name(path)
        return mr.beat_title(self.profile, name, self.channel()) if self.profile else name

    def titles(self):
        return [self.title_overrides.get(p) or self.auto_title(p) for p in self.beats]

    def _on_title_edited(self, item):
        beats = self.beats
        if item.column() != BeatDropTable.COL_TITLE or item.row() >= len(beats):
            return
        path = beats[item.row()]
        text = ' '.join(item.text().split())
        if text and text != self.auto_title(path):
            self.title_overrides[path] = text
        else:
            self.title_overrides.pop(path, None)
        self._refresh()

    # --- Refresco ---

    def _refresh(self):
        self.summary_label.setText(self.summary_text())
        table, beats = self.table, self.beats
        table.blockSignals(True)
        table.setRowCount(len(beats))
        for row, (path, title) in enumerate(zip(beats, self.titles())):
            from_inbox = path in self.inbox and path not in self.dropped
            beat = QTableWidgetItem(('📥 ' if from_inbox else '') + os.path.basename(path))
            beat.setFlags(beat.flags() & ~Qt.ItemIsEditable)
            beat.setToolTip(path + ('\n(de la carpeta de entrada: al terminar pasa a «hechos»)' if from_inbox else ''))
            table.setItem(row, BeatDropTable.COL_BEAT, beat)
            cell = QTableWidgetItem(title)
            if path in self.title_overrides:
                cell.setForeground(QColor('#f1c40f'))
                cell.setToolTip('Editado a mano (solo para esta tanda).')
            table.setItem(row, BeatDropTable.COL_TITLE, cell)
            length = QTableWidgetItem(f'{len(title)}/100')
            length.setFlags(length.flags() & ~Qt.ItemIsEditable)
            if len(title) > 100:
                length.setForeground(QColor('#e74c3c'))
            table.setItem(row, BeatDropTable.COL_LEN, length)
        table.blockSignals(False)
        from_inbox = sum(1 for p in self.inbox if p not in self.dropped)
        parts = [f'{len(beats)} beats']
        if from_inbox:
            parts.append(f'{from_inbox} de la carpeta de entrada')
        if self.title_overrides:
            parts.append(f'{len(self.title_overrides)} títulos editados')
        self.count_label.setText(' · '.join(parts))
        others = getattr(self, 'other_inbox', {})
        if others:
            listing = ', '.join(f'{c} ({n})' for c, n in sorted(others.items()))
            self.others_label.setText(f'También hay beats esperando en otras carpetas de entrada: {listing}.')
        self.others.setVisible(bool(others))
        self._update_buttons()

    def _update_buttons(self):
        busy = self.worker is not None
        n = len(self.beats)
        self.btn_generate.setText(f'Generar {n} video{"s" if n != 1 else ""}' if n else 'Generar videos')
        self.btn_generate.setEnabled(bool(n) and self.backgrounds_ready() and not busy)
        self.btn_cancel.setVisible(busy)
        self.btn_reset.setVisible(bool(self.title_overrides))
        self.btn_style.setEnabled(bool(self.channel()) and not busy)
        self.btn_backgrounds.setEnabled(bool(self.channel()))
        for widget in (self.btn_add, self.btn_add_folder, self.btn_remove, self.channel_combo,
                       self.btn_settings, self.btn_all, self.btn_reset):
            widget.setEnabled(not busy)
        self.table.setAcceptDrops(not busy)
        self.table.setEditTriggers(self.table.NoEditTriggers if busy else
                                   self.table.DoubleClicked | self.table.EditKeyPressed)
        if not busy and n and not self.backgrounds_ready() and self.channel():
            self.set_status('Para generar, el canal necesita fondos: tocá «Abrir fondos» y agregá archivos.')

    def say(self, text):
        self.log.appendPlainText(text)

    def set_status(self, text):
        self.status.setText(text)
        self.status.setVisible(bool(text))

    # --- Acciones de canal y carpetas ---

    def open_folder(self, path):
        if path:
            _open_path(path)

    def open_backgrounds(self):
        if self.channel():
            self.open_folder(os.path.join(cp.channel_dir(self.local_root, self.channel()), cp.BACKGROUNDS_DIR))

    def edit_profile(self):
        if not self.channel():
            return
        dialog = ProfileEditor(self.local_root, self.channel(), self)
        if dialog.exec_():
            self.reload_channels(select=dialog.created or self.channel())

    def open_settings(self):
        from core.local_settings import LocalSettingsDialog
        LocalSettingsDialog(self).exec_()
        self.reload_channels()

    def pick_root(self):
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta de canales (dentro de Dropbox)',
                                                  self.local_root or os.path.expanduser('~'))
        if folder:
            self.settings['local_root'] = os.path.normpath(folder)
            self.save_settings()
            self.reload_channels()

    def pick_output(self):
        folder = QFileDialog.getExistingDirectory(self, 'Carpeta donde guardar los videos', self.output_root)
        if folder:
            self.settings['output_folder'] = os.path.normpath(folder)
            self.settings['output_folder_custom'] = True
            self.save_settings()

    def new_channel(self):
        if not self.local_root:
            self.pick_root()
            if not self.local_root:
                return
        name, ok = QInputDialog.getText(self, 'Nuevo canal', 'Nombre del canal:')
        name = name.strip()
        if not ok or not name:
            return
        try:
            if name in cp.list_channels(self.local_root):
                raise cp.ProfileError(f'Ya existe un canal llamado {name}.')
            cp.create(self.local_root, name)
        except cp.ProfileError as exc:
            QMessageBox.warning(self, 'Nuevo canal', str(exc))
            return
        self.reload_channels(select=name)
        self.edit_profile()

    def import_legacy(self):
        """Copia los canales del modo manual anterior (images/, videos/, app_config) sin borrar nada."""
        if not self.local_root:
            self.pick_root()
            if not self.local_root:
                return
        actions = local_migration.plan(self.legacy_root, self.local_root)
        if not actions:
            QMessageBox.information(self, 'Importar canales', 'No se encontraron canales anteriores.')
            return
        lines = local_migration.summary(actions)
        shown = '\n'.join(lines[:30]) + (f'\n… y {len(lines) - 30} más' if len(lines) > 30 else '')
        if QMessageBox.question(self, 'Importar canales anteriores',
                                f'Se copian a:\n{self.local_root}\n\n{shown}\n\nNo se borra ni se pisa nada. ¿Copiar?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            result = local_migration.apply(actions, self.local_root)
        except OSError as exc:
            result = {'canales': 0, 'archivos': 0, 'errores': [f'No se pudo copiar: {exc}']}
        finally:
            QApplication.restoreOverrideCursor()
        self.say(f"Importados: {result['canales']} canales nuevos, {result['archivos']} archivos copiados.")
        for error in result['errores']:
            self.say(f'✗ {error}')
        self.reload_channels()

    def save_settings(self):
        self.settings['channel'] = self.channel()
        try:
            mr.save_settings(self.settings, self.settings_path)
        except OSError:
            pass  # preferencias de comodidad: no frenan nada

    # --- Generar ---

    def job(self):
        return dict(mode='channel', root=self.local_root, channel=self.channel(), profile=self.profile,
                    beats=list(self.beats), inbox=list(self.inbox), output=self.output_root,
                    titles=dict(self.title_overrides))

    def start(self):
        if self.worker is not None or not self.beats or not self.backgrounds_ready():
            return
        self._run(self.job(), len(self.beats), f'Generando {len(self.beats)} videos para {self.channel()}…')

    def start_all(self):
        """Genera todos los canales que tienen beats en su carpeta de entrada (cada uno con su estilo)."""
        if self.worker is not None:
            return
        total = sum(getattr(self, 'other_inbox', {}).values()) + len(self.inbox)
        if QMessageBox.question(self, 'Generar todos los canales',
                                f'Se generan {total} beats de las carpetas de entrada, cada canal con su estilo. '
                                'Los beats arrastrados a mano no entran en esta tanda. ¿Seguir?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes) != QMessageBox.Yes:
            return
        self._run(dict(mode='all', root=self.local_root, output=self.output_root, titles=dict(self.title_overrides)),
                  total, f'Generando {total} beats de todas las carpetas de entrada…')

    def _run(self, job, total, text):
        self.save_settings()
        self.worker = LocalWorker(job, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.message.connect(self.say)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_finished)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.set_status(text)
        self.say(text)
        self._update_buttons()
        self.worker.start()

    def cancel(self):
        if self.worker is not None:
            self.worker.cancel()
            self.say('Cancelando…')

    def _on_progress(self, done, total, text):
        self.progress.setValue(done)
        self.set_status(text)
        self.say(text)

    def _on_done(self, data):
        ok = 0
        for channel, entry in data['summary'].items():
            ok += entry['ok']
            line = f'{channel}: {entry["ok"]} videos'
            if entry['errores']:
                line += f', {len(entry["errores"])} con error'
                for name, error in entry['errores'][:5]:
                    self.say(f'✗ {name}: {error}')
            self.say(line)
        self.generated += ok
        folder = mr.day_folder(self.output_root)
        self.set_status(f'✓ {ok} videos listos en {folder}. Subilos a YouTube a mano '
                            f'(cada carpeta tiene el video, la miniatura y el texto para copiar).')
        if ok:
            self.dropped, self.title_overrides = [], {}

    def _on_failed(self, text):
        self.set_status(f'✗ {text}')
        self.say(f'✗ {text}')

    def _on_finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.progress.setVisible(False)
        self.scan_inbox()  # lo generado de la entrada ya pasó a «hechos»

    def shutdown(self, wait_ms=5000):
        if self.worker is not None:
            self.worker.cancel()
            self.worker.wait(wait_ms)

    # --- Guía ---

    def guide(self):
        root_ok = lambda: bool(self.local_root) and bool(cp.list_channels(self.local_root))
        return ('Crear videos en esta PC',
                'Seguí los pasos de arriba a abajo. Se tildan solos cuando los completás.',
                [GuideStep('Tener tus canales listos',
                           'Están en la carpeta «TypeBeat Local» de Dropbox. Si no aparece ninguno, importá los '
                           'anteriores o creá uno en ⚙ Configuración.', done=root_ok,
                           action=self.open_settings, action_text='Abrir Configuración'),
                 GuideStep('Elegir el canal', 'Paso 1 de la pantalla. Cada canal tiene su propio estilo.',
                           done=lambda: bool(self.profile), action=self.channel_combo.showPopup,
                           action_text='Elegir canal'),
                 GuideStep('Que el canal tenga fondos',
                           'Imágenes o videos stock en la carpeta «fondos» del canal.',
                           done=self.backgrounds_ready, action=self.open_backgrounds, action_text='Abrir fondos'),
                 GuideStep('Revisar el estilo del canal (opcional)',
                           'Imagen o video, estilo del título y artista. Se guarda para la próxima.',
                           action=self.edit_profile, action_text='Editar estilo'),
                 GuideStep('Sumar beats', 'Arrastralos a la tabla o dejalos en la carpeta de entrada del canal.',
                           done=lambda: bool(self.beats), action=self.pick_files, action_text='Agregar beats'),
                 GuideStep('Generar', 'Paso 3. Mientras genera podés seguir usando la PC.',
                           done=lambda: self.generated > 0, action=self.start, action_text='Generar ahora'),
                 GuideStep('Subirlos a YouTube a mano',
                           'Cada video tiene su carpeta con el .mp4, la miniatura y un .txt con título, descripción '
                           'y tags para copiar y pegar en YouTube Studio.',
                           action=lambda: self.open_folder(self.output_root), action_text='Abrir carpeta de videos')])
