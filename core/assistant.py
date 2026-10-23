# -*- coding: utf-8 -*-
"""Asistente «Guiame paso a paso»: el usuario dice qué quiere lograr y lo lleva hasta el resultado.

Caminos: videos para un canal, videos para varios canales (carpetas de entrada) y crear un canal
nuevo. Usa el mismo motor que la pantalla local (perfiles, cola, render) y la misma configuración.
"""
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import (QButtonGroup, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                             QProgressBar, QPushButton, QRadioButton, QStackedWidget, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView, QAbstractItemView)

from core import beat_title as bt
from core import bulk_queue as bq
from core import channel_profile as cp
from core import manual_render as mr
from core.guide_panel import GuideStep
from core.local_view import LocalWorker
from core.manual_panel import BeatDropTable
from core.profile_editor import ProfileEditor, TITLE_STYLES, SAMPLE
from core.wizard import Wizard, WizardPage

UPLOAD_HELP = ('<b>Cómo subirlos a YouTube:</b><ol>'
               '<li>Abrí YouTube Studio → Crear → Subir videos.</li>'
               '<li>Arrastrá el <b>.mp4</b> de la carpeta del video (el título ya viene en el nombre).</li>'
               '<li>Copiá la descripción y los tags del <b>.txt</b> de la misma carpeta.</li>'
               '<li>En Miniatura, subí el archivo <b>«… - miniatura.jpg»</b>.</li>'
               '<li>Programá o publicá. Marcá «subido» en <b>pendientes.csv</b> para llevar la cuenta.</li></ol>')

_GOAL = ('QPushButton {{ background: {bg}; color: white; font-size: 15px; font-weight: bold; padding: 18px; '
         'border-radius: 8px; text-align: left; }} QPushButton:hover {{ background: {hover}; }}')


def _vbox(*widgets):
    box = QWidget()
    layout = QVBoxLayout(box)
    for widget in widgets:
        if isinstance(widget, int):
            layout.addStretch(widget)
        elif isinstance(widget, QHBoxLayout):
            layout.addLayout(widget)
        else:
            layout.addWidget(widget)
    return box, layout


def _row(*widgets):
    row = QHBoxLayout()
    for widget in widgets:
        if widget is None:
            row.addStretch()
        else:
            row.addWidget(widget)
    return row


def _button(text, slot):
    button = QPushButton(text)
    button.clicked.connect(slot)
    return button


class _Generation:
    """Corre un ``LocalWorker`` y avisa al asistente cuando termina."""

    def __init__(self, owner, progress, status, on_success):
        self.owner, self.progress, self.status, self.on_success = owner, progress, status, on_success
        self.worker = None
        self.summary = None

    def busy(self):
        return self.worker is not None

    def start(self, job, total):
        self.summary = None
        self.worker = LocalWorker(job, self.owner)
        self.worker.progress.connect(lambda d, t, text: (self.progress.setValue(d), self.status.setText(text)))
        self.worker.message.connect(self.status.setText)
        self.worker.done.connect(self._done)
        self.worker.failed.connect(lambda text: self.status.setText(f'✗ {text}'))
        self.worker.finished.connect(self._finished)
        self.progress.setRange(0, max(total, 1))
        self.progress.setValue(0)
        self.progress.setVisible(True)
        self.status.setText('Arrancando…')
        self.worker.start()
        return False  # el asistente avanza solo al terminar

    def _done(self, data):
        self.summary = data['summary']

    def _finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.progress.setVisible(False)
        if self.summary is not None and sum(e['ok'] for e in self.summary.values()):
            self.on_success()

    def cancel(self, wait_ms=0):
        if self.worker is not None:
            self.worker.cancel()
            if wait_ms:
                self.worker.wait(wait_ms)


def summary_text(summary, output_root):
    lines = []
    for channel, entry in summary.items():
        line = f'<b>{channel}</b>: {entry["ok"]} videos'
        if entry['errores']:
            line += f' — {len(entry["errores"])} con error: ' + '; '.join(
                f'{n} ({e})' for n, e in entry['errores'][:3])
        lines.append(line)
    folder = mr.day_folder(output_root)
    return '<br>'.join(lines) + f'<br><br>Quedaron en <b>{folder}</b>.'


class AssistantView(QWidget):
    home_requested = pyqtSignal()
    cloud_requested = pyqtSignal()

    def __init__(self, local_view, parent=None):
        """``local_view``: la pantalla local (de ahí salen carpetas, configuración y canales)."""
        super().__init__(parent)
        self.local = local_view
        self.wizard = None
        self.generation = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.goals = self._goal_page()
        self.stack.addWidget(self.goals)

    # --- Elegir objetivo ---

    def _goal_page(self):
        title = QLabel('¿Qué querés lograr?')
        title.setStyleSheet('font-size: 22px; font-weight: bold;')
        text = QLabel('Elegí una opción y te llevo paso a paso. En cada pantalla hay una sola cosa para hacer.')
        text.setWordWrap(True)
        self.btn_one = QPushButton('🎬  Hacer videos de beats nuevos para un canal   (recomendado)')
        self.btn_many = QPushButton('📥  Hacer videos para varios canales a la vez')
        self.btn_new = QPushButton('➕  Crear un canal nuevo')
        self.btn_cloud = QPushButton('☁  Automatizar un canal en la nube')
        styles = (('#27AE60', '#2ECC71'), ('#2c5d8f', '#3a75b0'), ('#7d5a9e', '#9670bb'), ('#555555', '#666666'))
        for button, (bg, hover) in zip((self.btn_one, self.btn_many, self.btn_new, self.btn_cloud), styles):
            button.setStyleSheet(_GOAL.format(bg=bg, hover=hover))
        self.btn_one.clicked.connect(lambda: self.start_one())
        self.btn_many.clicked.connect(self.start_many)
        self.btn_new.clicked.connect(self.start_new)
        self.btn_cloud.clicked.connect(self.cloud_requested)
        box, layout = _vbox(1, title, text, self.btn_one, self.btn_many, self.btn_new, self.btn_cloud, 2)
        return box

    def show_goals(self):
        self._drop_wizard()
        self.stack.setCurrentWidget(self.goals)

    def _drop_wizard(self):
        if self.generation is not None:
            self.generation.cancel()
        if self.wizard is not None:
            self.stack.removeWidget(self.wizard)
            self.wizard.hide()
            self.wizard.deleteLater()
        self.wizard, self.generation = None, None

    def _open(self, title, pages, on_finish=None):
        # Cada camino llama a _drop_wizard() al empezar, antes de crear su generación.
        self.wizard = Wizard(title, pages)
        self.wizard.cancelled.connect(self.show_goals)
        self.wizard.finished.connect(on_finish or self.show_goals)
        self.stack.addWidget(self.wizard)
        self.stack.setCurrentWidget(self.wizard)
        return self.wizard

    @property
    def root(self):
        return self.local.local_root

    def _recheck(self):
        """Actualiza «Siguiente» al toque cuando cambia algo (sin esperar al chequeo periódico)."""
        if self.wizard is not None:
            self.wizard.update_state()

    # --- Camino 1: videos para un canal ---

    def start_one(self, channel=None):
        self._drop_wizard()
        state = {'channel': channel or self.local.channel() or '', 'dropped': [], 'inbox': [], 'titles': {}}

        def profile():
            try:
                return cp.load(self.root, state['channel']) if state['channel'] else None
            except cp.ProfileError:
                return None

        def backgrounds():
            p = profile()
            return cp.media(self.root, state['channel'], p['fondo'])[0] if p else []

        def beats():
            return state['dropped'] + [b for b in state['inbox'] if b not in state['dropped']]

        # Paso 1: canal
        combo = QComboBox()
        combo.addItems(cp.list_channels(self.root) if self.root else [])
        preview = QHBoxLayout()
        info = QLabel()
        info.setWordWrap(True)

        def show_channel(name):
            state['channel'] = name
            state['titles'] = {}
            while preview.count():
                item = preview.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            p = profile()
            files = backgrounds()
            for path in files[:5]:
                thumb = QLabel()
                pixmap = QPixmap(path)
                if not pixmap.isNull():
                    thumb.setPixmap(pixmap.scaled(150, 85, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation))
                else:
                    thumb.setText('🎞 ' + os.path.basename(path)[:18])
                thumb.setFixedSize(150, 85)
                preview.addWidget(thumb)
            preview.addStretch()
            if p:
                kind = 'imágenes' if p['fondo'] == cp.MODE_IMAGE else 'videos stock'
                example = mr.beat_title(p, SAMPLE, name)
                info.setText(f'Fondo: <b>{len(files)} {kind}</b><br>Ejemplo de título: <b>{example}</b>')
            self._recheck()
        combo.currentTextChanged.connect(show_channel)
        if state['channel'] and combo.findText(state['channel']) >= 0:
            combo.setCurrentIndex(combo.findText(state['channel']))
        show_channel(combo.currentText())

        def open_backgrounds():
            if state['channel']:
                self.local.open_folder(os.path.join(cp.channel_dir(self.root, state['channel']), cp.BACKGROUNDS_DIR))

        def edit_style():
            if state['channel'] and ProfileEditor(self.root, state['channel'], self).exec_():
                show_channel(state['channel'])

        page1, _ = _vbox(combo, preview, info, _row(_button('Abrir fondos', open_backgrounds),
                                                   _button('Cambiar estilo del canal', edit_style), None), 1)

        def blocker1():
            if not self.root or not combo.count():
                return 'no hay canales: salí del asistente y elegí «Crear un canal nuevo».'
            if not profile():
                return 'elegí un canal.'
            return 'el canal no tiene fondos. Tocá «Abrir fondos», agregá imágenes o videos y volvé acá.'

        # Paso 2: beats
        drop = BeatDropTable()
        drop.setColumnHidden(BeatDropTable.COL_TITLE, True)
        drop.setColumnHidden(BeatDropTable.COL_LEN, True)
        drop.horizontalHeader().setSectionResizeMode(BeatDropTable.COL_BEAT, QHeaderView.Stretch)
        count = QLabel()

        def refresh_beats():
            items = beats()
            drop.setRowCount(len(items))
            for row, path in enumerate(items):
                label = ('📥 ' if path in state['inbox'] and path not in state['dropped'] else '') + os.path.basename(path)
                cell = QTableWidgetItem(label)
                cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                drop.setItem(row, BeatDropTable.COL_BEAT, cell)
            inbox = sum(1 for p in state['inbox'] if p not in state['dropped'])
            count.setText(f'{len(items)} beats' + (f' (📥 {inbox} de la carpeta de entrada)' if inbox else ''))
            self._recheck()

        def add(paths):
            known = {os.path.normcase(p) for p in beats()}
            state['dropped'] += [p for p in mr.collect_audio(paths) if os.path.normcase(p) not in known]
            refresh_beats()

        def pick_files():
            files, _ = QFileDialog.getOpenFileNames(self, 'Elegir beats', '',
                                                    'Audio (' + ' '.join('*' + s for s in mr.AUDIO_SUFFIXES) + ')')
            if files:
                add(files)

        def pick_folder():
            folder = QFileDialog.getExistingDirectory(self, 'Elegir carpeta con beats')
            if folder:
                add([folder])

        def remove():
            items = beats()
            for row in reversed(drop.selected_rows()):
                path = items[row]
                if path in state['dropped']:
                    state['dropped'].remove(path)
                elif path in state['inbox']:
                    state['inbox'].remove(path)
            refresh_beats()

        def enter_beats():
            scanned, _ = bq.scan(self.root) if self.root else ([], [])
            state['inbox'] = [b['path'] for b in scanned if b['channel'] == state['channel']]
            refresh_beats()

        drop.paths_dropped.connect(add)
        page2, _ = _vbox(drop, _row(_button('Agregar beats…', pick_files), _button('Agregar carpeta…', pick_folder),
                                    _button('Quitar', remove), None, count))

        # Paso 3: títulos
        titles = BeatDropTable()
        titles.setAcceptDrops(False)

        def auto(path):
            return mr.beat_title(profile(), mr.beat_name(path), state['channel'])

        def fill_titles():
            titles.blockSignals(True)
            items = beats()
            titles.setRowCount(len(items))
            for row, path in enumerate(items):
                title = state['titles'].get(path) or auto(path)
                name = QTableWidgetItem(os.path.basename(path))
                name.setFlags(name.flags() & ~Qt.ItemIsEditable)
                titles.setItem(row, BeatDropTable.COL_BEAT, name)
                cell = QTableWidgetItem(title)
                if path in state['titles']:
                    cell.setForeground(QColor('#f1c40f'))
                titles.setItem(row, BeatDropTable.COL_TITLE, cell)
                length = QTableWidgetItem(f'{len(title)}/100')
                length.setFlags(length.flags() & ~Qt.ItemIsEditable)
                titles.setItem(row, BeatDropTable.COL_LEN, length)
            titles.blockSignals(False)

        def edited(item):
            items = beats()
            if item.column() != BeatDropTable.COL_TITLE or item.row() >= len(items):
                return
            path, text = items[item.row()], ' '.join(item.text().split())
            if text and text != auto(path):
                state['titles'][path] = text
            else:
                state['titles'].pop(path, None)
            fill_titles()
        titles.itemChanged.connect(edited)
        page3, _ = _vbox(titles)

        # Paso 4: generar
        plan = QLabel()
        plan.setWordWrap(True)
        bar, status = QProgressBar(), QLabel()
        bar.setVisible(False)
        status.setWordWrap(True)
        page4, _ = _vbox(plan, bar, status, 1)
        result = QLabel()
        result.setWordWrap(True)
        generation = _Generation(self, bar, status, lambda: self.wizard.advance())
        self.generation = generation

        def enter_generate():
            n = len(beats())
            plan.setText(f'Se van a crear <b>{n} videos</b> para <b>{state["channel"]}</b>, cada uno con su miniatura '
                         f'y su texto para YouTube, en <b>{mr.day_folder(self.local.output_root)}</b>.<br><br>'
                         'Mientras tanto podés seguir usando la PC.')
            status.setText('')
            gen_page.next_text = f'🎬 Generar {n} videos'

        def run():
            job = dict(mode='channel', root=self.root, channel=state['channel'], profile=profile(), beats=beats(),
                       inbox=list(state['inbox']), output=self.local.output_root, titles=dict(state['titles']))
            return generation.start(job, len(beats()))

        # Paso 5: listo
        def enter_done():
            result.setText(summary_text(generation.summary or {}, self.local.output_root) + '<br>' + UPLOAD_HELP)
            self.local.scan_inbox()

        page5, _ = _vbox(result, _row(_button('📂 Abrir carpeta de videos',
                                              lambda: self.local.open_folder(mr.day_folder(self.local.output_root))),
                                      _button('Hacer otra tanda', lambda: self.start_one(state['channel'])), None), 1)

        gen_page = WizardPage('Generar', '', page4, on_enter=enter_generate, on_next=run, busy=generation.busy)
        pages = [
            WizardPage('¿Para qué canal?', 'Cada canal tiene su propio estilo de fondos y títulos.', page1,
                       ready=lambda: bool(backgrounds()), blocker=blocker1),
            WizardPage('Sumá los beats', 'Arrastrá archivos o carpetas a la lista, o usá los botones. Los que dejaste '
                       'en la carpeta de entrada del canal ya aparecen (📥).', page2, on_enter=enter_beats,
                       ready=lambda: bool(beats()),
                       blocker=lambda: 'sumá al menos un beat (arrastralo o usá «Agregar beats…»).'),
            WizardPage('Revisá los títulos', 'Así van a quedar. Si querés cambiar uno, hacé doble clic. '
                       'Si están bien, seguí.', page3, on_enter=fill_titles),
            gen_page,
            WizardPage('¡Listo!', 'Tus videos están hechos.', page5, on_enter=enter_done, next_text='Terminar',
                       can_back=False),
        ]
        return self._open('Videos para un canal', pages)

    # --- Camino 2: varios canales ---

    def start_many(self):
        self._drop_wizard()
        state = {'beats': [], 'notes': [], 'titles': {}, 'profiles': {}}
        listing = QLabel()
        listing.setWordWrap(True)

        def scan():
            scanned, notes = bq.scan(self.root) if self.root else ([], [])
            state['profiles'] = {}
            for channel in {b['channel'] for b in scanned}:
                try:
                    state['profiles'][channel] = cp.load(self.root, channel)
                except cp.ProfileError as exc:
                    notes.append(f'{channel}: {exc}')
            state['beats'] = [b for b in scanned if b['channel'] in state['profiles']]
            state['notes'] = notes
            counts = {}
            for beat in state['beats']:
                counts[beat['channel']] = counts.get(beat['channel'], 0) + 1
            lines = [f'• <b>{c}</b>: {n} beats' for c, n in sorted(counts.items())] or ['(no hay beats todavía)']
            extra = ''.join(f'<br><span style="color:#f1c40f">⚠ {n}</span>' for n in notes)
            folder = os.path.join(self.root, cp.INPUT_DIR, '<canal>') if self.root else '—'
            listing.setText(f'Carpeta: <b>{folder}</b><br><br>' + '<br>'.join(lines) + extra)
            self._recheck()

        page1, _ = _vbox(listing, _row(_button('📂 Abrir carpeta de entrada', lambda: self.root and self.local.open_folder(
            os.path.join(self.root, cp.INPUT_DIR))), _button('🔄 Volver a revisar', scan), None), 1)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(['Canal', 'Beat', 'Título (doble clic para cambiar)'])
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)

        def auto(beat):
            return mr.beat_title(state['profiles'][beat['channel']], mr.beat_name(beat['path']), beat['channel'])

        def fill():
            table.blockSignals(True)
            table.setRowCount(len(state['beats']))
            for row, beat in enumerate(state['beats']):
                for col, text in ((0, beat['channel']), (1, os.path.basename(beat['path']))):
                    cell = QTableWidgetItem(text)
                    cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
                    table.setItem(row, col, cell)
                title = state['titles'].get(beat['path']) or auto(beat)
                cell = QTableWidgetItem(title)
                if beat['path'] in state['titles']:
                    cell.setForeground(QColor('#f1c40f'))
                table.setItem(row, 2, cell)
            table.blockSignals(False)

        def edited(item):
            if item.column() != 2 or item.row() >= len(state['beats']):
                return
            beat, text = state['beats'][item.row()], ' '.join(item.text().split())
            if text and text != auto(beat):
                state['titles'][beat['path']] = text
            else:
                state['titles'].pop(beat['path'], None)
            fill()
        table.itemChanged.connect(edited)
        page2, _ = _vbox(table)

        plan, bar, status = QLabel(), QProgressBar(), QLabel()
        plan.setWordWrap(True)
        status.setWordWrap(True)
        bar.setVisible(False)
        page3, _ = _vbox(plan, bar, status, 1)
        generation = _Generation(self, bar, status, lambda: self.wizard.advance())
        self.generation = generation

        def enter_generate():
            n, channels = len(state['beats']), len({b['channel'] for b in state['beats']})
            plan.setText(f'Se van a crear <b>{n} videos</b> en <b>{channels} canales</b>, cada canal con su estilo. '
                         'Los beats terminados pasan a la carpeta «hechos» de su canal.')
            gen_page.next_text = f'🎬 Generar {n} videos'

        def run():
            job = dict(mode='all', root=self.root, output=self.local.output_root, titles=dict(state['titles']))
            return generation.start(job, len(state['beats']))

        result = QLabel()
        result.setWordWrap(True)

        def enter_done():
            result.setText(summary_text(generation.summary or {}, self.local.output_root) + '<br>' + UPLOAD_HELP)
            self.local.scan_inbox()

        page4, _ = _vbox(result, _row(_button('📂 Abrir carpeta de videos', lambda: self.local.open_folder(
            mr.day_folder(self.local.output_root))), None), 1)
        gen_page = WizardPage('Generar', '', page3, on_enter=enter_generate, on_next=run, busy=generation.busy)
        pages = [
            WizardPage('Beats en las carpetas de entrada', 'Dejá los beats de cada canal en su carpeta de entrada '
                       '(dentro de Dropbox). Cuando estén, tocá «Volver a revisar».', page1, on_enter=scan,
                       ready=lambda: bool(state['beats']),
                       blocker=lambda: 'no hay beats en ninguna carpeta de entrada. Abrí la carpeta, copiá los '
                                       'beats en la subcarpeta de cada canal y tocá «Volver a revisar».'),
            WizardPage('Revisá los títulos', 'Doble clic para cambiar uno. Si están bien, seguí.', page2, on_enter=fill),
            gen_page,
            WizardPage('¡Listo!', 'Tus videos están hechos.', page4, on_enter=enter_done, next_text='Terminar',
                       can_back=False),
        ]
        return self._open('Videos para varios canales', pages)

    # --- Camino 3: crear un canal ---

    def start_new(self):
        self._drop_wizard()
        state = {'created': False}
        name = QLineEdit()
        name.setPlaceholderText('Ej.: Sad Juice Beats')
        name.textChanged.connect(lambda _t: self._recheck())
        page1, _ = _vbox(name, 1)

        def name_problem():
            text = name.text().strip()
            if not self.root:
                return 'falta la carpeta de canales: elegila en ⚙ Configuración (pantalla «Crear videos ahora»).'
            if not text:
                return 'escribí el nombre del canal.'
            try:
                cp.check_name(text)
            except cp.ProfileError as exc:
                return str(exc)
            if text in cp.list_channels(self.root) and not state['created']:
                return f'ya existe un canal llamado {text}.'
            return ''

        base = QComboBox()
        base.addItem('No, empezar de cero', '')
        for channel in (cp.list_channels(self.root) if self.root else []):
            base.addItem(f'Copiar el estilo de {channel}', channel)
        page2, _ = _vbox(base, 1)

        image = QRadioButton('🖼  Imagen fija — rápido y simple (una foto por video)')
        video = QRadioButton('🎞  Video stock — clips en loop (más llamativo)')
        group = QButtonGroup(self)
        group.addButton(image)
        group.addButton(video)
        image.setChecked(True)
        page3, _ = _vbox(image, video, 1)

        style = QComboBox()
        for label, template in TITLE_STYLES:
            style.addItem(label, template)
        artists = QLineEdit()
        artists.setPlaceholderText('Ej.: Juice WRLD, Lil Peep (así se escriben en el título)')
        example = QLabel()
        example.setWordWrap(True)

        def show_example(*_):
            profile = dict(cp.default_profile('x'), titulo=style.currentData(),
                           artistas=[a.strip() for a in artists.text().split(',') if a.strip()])
            example.setText(f'Ejemplo: <b>{mr.beat_title(profile, SAMPLE, name.text().strip())}</b><br>'
                            f'Sin datos: <b>{mr.beat_title(profile, "Legends Fall", "")}</b>')
        style.currentIndexChanged.connect(show_example)
        artists.textChanged.connect(show_example)
        page4, _ = _vbox(QLabel('Estilo de título:'), style, QLabel('Artistas (opcional):'), artists, example, 1)

        def enter_base():
            copy = base.currentData()
            if copy:
                profile = cp.load(self.root, copy)
                (video if profile['fondo'] == cp.MODE_VIDEO else image).setChecked(True)
                index = style.findData(profile['titulo'])
                if index >= 0:
                    style.setCurrentIndex(index)
                artists.setText(', '.join(profile['artistas']))

        def create():
            channel = name.text().strip()
            copy = base.currentData()
            profile = dict(cp.load(self.root, copy)) if copy else cp.default_profile(channel)
            profile.update(nombre=channel, fondo=cp.MODE_VIDEO if video.isChecked() else cp.MODE_IMAGE,
                           titulo=style.currentData(),
                           artistas=[a.strip() for a in artists.text().split(',') if a.strip()])
            try:
                if state['created']:
                    cp.save(self.root, channel, profile)
                else:
                    cp.create(self.root, channel, profile)
                    state['created'] = True
            except cp.ProfileError as exc:
                example.setText(f'✗ {exc}')
                return False
            return None

        count = QLabel()
        count.setWordWrap(True)

        def backgrounds():
            channel = name.text().strip()
            mode = cp.MODE_VIDEO if video.isChecked() else cp.MODE_IMAGE
            return cp.media(self.root, channel, mode)[0] if state['created'] else []

        def open_backgrounds():
            self.local.open_folder(os.path.join(cp.channel_dir(self.root, name.text().strip()), cp.BACKGROUNDS_DIR))

        def enter_backgrounds():
            open_backgrounds()

        def refresh_count():
            noun = 'imágenes' if image.isChecked() else 'videos'
            count.setText(f'Hay <b>{len(backgrounds())} {noun}</b> en la carpeta de fondos.')
            return bool(backgrounds())

        page5, _ = _vbox(_row(_button('📂 Abrir carpeta de fondos', open_backgrounds), None), count, 1)
        done_label = QLabel()
        done_label.setWordWrap(True)

        def enter_done():
            self.local.reload_channels(select=name.text().strip())
            done_label.setText(f'El canal <b>{name.text().strip()}</b> está listo. Su estilo se puede cambiar cuando '
                               'quieras con «Editar estilo del canal».')

        page6, _ = _vbox(done_label, _row(_button('Terminar', self.show_goals), None), 1)
        pages = [
            WizardPage('¿Cómo se llama el canal?', 'El mismo nombre que vas a usar en YouTube, así lo reconocés.',
                       page1, ready=lambda: not name_problem(), blocker=name_problem),
            WizardPage('¿Querés copiar el estilo de otro canal?', 'Útil para subcanales del mismo nicho: después '
                       'cambiás solo lo que haga falta.', page2),
            WizardPage('¿Qué fondo querés para los videos?', 'Se puede cambiar después.', page3, on_enter=enter_base),
            WizardPage('¿Cómo querés los títulos?', 'Elegí un estilo. El nombre y el artista salen solos del nombre '
                       'de cada beat.', page4, on_enter=show_example, on_next=create, next_text='Crear canal →'),
            WizardPage('Agregá los fondos', 'Se abrió la carpeta de fondos del canal: copiá ahí las imágenes o los '
                       'videos. Esta pantalla se actualiza sola.', page5, on_enter=enter_backgrounds,
                       ready=refresh_count, blocker=lambda: 'agregá al menos un archivo en la carpeta de fondos.'),
            WizardPage('¡Canal creado!', '', page6, on_enter=enter_done, next_text='🎬 Hacer videos para este canal',
                       can_back=False),
        ]
        return self._open('Crear un canal nuevo', pages,
                          on_finish=lambda: self.start_one(name.text().strip()))

    # --- Varios ---

    def shutdown(self, wait_ms=5000):
        if self.generation is not None:
            self.generation.cancel(wait_ms)

    def guide(self):
        return ('Asistente paso a paso',
                'Elegí qué querés lograr y seguí los botones «Siguiente». El asistente te avisa abajo qué falta '
                'cuando algo no está listo.',
                [GuideStep('Elegir qué querés lograr', 'Si no sabés por dónde empezar: «Hacer videos de beats nuevos '
                           'para un canal».', action=self.show_goals, action_text='Ver opciones'),
                 GuideStep('Seguir los pasos', 'Una cosa por pantalla. «Atrás» para corregir.'),
                 GuideStep('Subir a YouTube a mano', 'Al final te muestra cómo hacerlo con los archivos generados.')])
