# -*- coding: utf-8 -*-
"""Panel de configuración de la automatización de Loop kits.

Independiente de Beats y Marca personal: se abre en un diálogo desde la sección Loop kits.
Lee y guarda ``kits.json`` y las claves ``kit_preview`` del worker en Dropbox (core/kit_settings).
Arriba se elige el canal: cada uno tiene su config, sus kits y su estado (core/kit_channel).
Los secretos nunca pasan por aquí: Telegram solo muestra si está "configurado".
"""
import json
import os
import sys

from PyQt5.QtCore import QProcess, Qt, QThread, QTime, pyqtSignal
from PyQt5.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFormLayout, QGroupBox,
                             QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                             QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QTimeEdit,
                             QVBoxLayout, QWidget)

from core import (kit_channel, kit_channel_setup, kit_cloud, kit_detect, kit_settings,
                  kit_source, kit_state)

_ROOT = os.path.dirname(os.path.abspath(__file__))
_HEADERS = ("Carpeta", "Nombre", "Link de PayHip", "Género", "Activo")
_SLOT_ROWS = 3
_DRY_RUN_TIMEOUT_MS = 10 * 60 * 1000


def _error_text(exc):
    """Mensaje seguro: los errores propios se muestran, el resto solo por tipo."""
    if isinstance(exc, (kit_settings.SettingsError, kit_cloud.KitCloudError,
                        kit_channel_setup.ChannelSetupError)):
        return str(exc)
    return f"Error ({type(exc).__name__})."


class _Task(QThread):
    """Corre ``fn`` fuera del hilo de la interfaz."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self._fn = fn

    def run(self):
        try:
            self.done.emit(self._fn())
        except Exception as exc:  # noqa: BLE001 - se informa a la UI sin traceback
            self.failed.emit(_error_text(exc))


class LoopKitPanel(QWidget):
    """Formulario de canal, horarios, carpeta de kits, kits, géneros, portada y estado."""

    def __init__(self, parent=None, dbx_provider=None, python=None, script_dir=None):
        super().__init__(parent)
        self._dbx_provider = dbx_provider  # None: kit_cloud arma el cliente de Dropbox
        self._python = python or sys.executable
        self._script_dir = script_dir or _ROOT
        self._kits_rev = None
        self._base_config = None  # config del canal por defecto: base de un canal nuevo
        self._task = None
        self._proc = None
        self._build()

    # --- Construcción ---

    def _build(self):
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Canal:"))
        self.automation = QComboBox()
        self.automation.addItem("Canal por defecto", '')
        self.automation.currentIndexChanged.connect(lambda _i: self.reload())
        top.addWidget(self.automation, 1)
        self.btn_new = QPushButton("Crear automatización…")
        self.btn_new.clicked.connect(self.ask_new_automation)
        top.addWidget(self.btn_new)
        outer.addLayout(top)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        body = QWidget()
        col = QVBoxLayout(body)
        col.addWidget(self._build_channel_box())
        col.addWidget(self._build_source_box())
        col.addWidget(self._build_kits_box(), 1)
        col.addWidget(self._build_genres_box())
        col.addWidget(self._build_cover_box())
        col.addWidget(self._build_telegram_box())
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        buttons = QHBoxLayout()
        self.btn_reload = QPushButton("Recargar")
        self.btn_save = QPushButton("Guardar en Dropbox")
        self.btn_dry = QPushButton("Probar dry-run")
        self.btn_state = QPushButton("Ver último estado")
        for btn in (self.btn_reload, self.btn_save, self.btn_dry, self.btn_state):
            btn.setMinimumHeight(32)
            buttons.addWidget(btn)
        self.btn_reload.clicked.connect(self.reload)
        self.btn_save.clicked.connect(self.save)
        self.btn_dry.clicked.connect(self.run_dry_run)
        self.btn_state.clicked.connect(self.show_last_state)
        outer.addLayout(buttons)

        self.status = QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(500)
        self.output.setMinimumHeight(90)
        outer.addWidget(self.output)

    def _build_channel_box(self):
        box = QGroupBox("Canal y horarios")
        form = QFormLayout(box)
        self.channel = QComboBox()
        self.channel.setEditable(True)
        form.addRow("Canal de Loop kits:", self.channel)
        self.slot_day, self.slot_time = [], []
        for i in range(_SLOT_ROWS):
            day, tm = QComboBox(), QTimeEdit()
            day.addItems(kit_settings.WEEKDAYS)
            tm.setDisplayFormat("HH:mm")
            row = QHBoxLayout()
            row.addWidget(day, 1)
            row.addWidget(tm)
            form.addRow(f"Horario {i + 1} (hora de Buenos Aires):", row)
            self.slot_day.append(day)
            self.slot_time.append(tm)
        return box

    def _build_source_box(self):
        box = QGroupBox("Carpeta de kits en Dropbox")
        form = QFormLayout(box)
        self.kits_root = QLineEdit()
        self.kits_root.setPlaceholderText("/ruta/en/Dropbox/tienda")
        self.btn_categories = QPushButton("Leer categorías")
        self.btn_categories.clicked.connect(self.read_categories)
        row = QHBoxLayout()
        row.addWidget(self.kits_root, 1)
        row.addWidget(self.btn_categories)
        form.addRow("Carpeta raíz:", row)
        self.categories = QListWidget()
        self.categories.setDragDropMode(QAbstractItemView.InternalMove)
        self.categories.setFixedHeight(110)
        form.addRow("Categorías a recorrer:", self.categories)
        self.loops_dirs = QLineEdit()
        self.loops_dirs.setPlaceholderText("loops")
        form.addRow("Carpetas de loops:", self.loops_dirs)
        self.ignore_names = QLineEdit()
        self.ignore_names.setPlaceholderText("tag, preview")
        form.addRow("Nombres a ignorar:", self.ignore_names)
        self.scan_depth = QSpinBox()
        self.scan_depth.setRange(1, kit_settings.MAX_SCAN_DEPTH)
        form.addRow("Profundidad máxima:", self.scan_depth)
        hint = QLabel("Las categorías se recorren en el orden de la lista (se puede arrastrar). "
                      "Sin ninguna marcada, los kits se buscan directo en la carpeta raíz. "
                      "Carpetas de loops y nombres a ignorar van separados por coma.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        form.addRow(hint)
        return box

    def _build_kits_box(self):
        box = QGroupBox("Kits")
        lay = QVBoxLayout(box)
        self.table = QTableWidget(0, len(_HEADERS))
        self.table.setHorizontalHeaderLabels(_HEADERS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setMinimumHeight(160)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QHeaderView.Interactive)
        head.setStretchLastSection(False)
        head.setSectionResizeMode(2, QHeaderView.Stretch)
        lay.addWidget(self.table)
        row = QHBoxLayout()
        add, rm = QPushButton("Agregar kit"), QPushButton("Quitar seleccionado")
        add.clicked.connect(lambda: self.add_kit_row())
        rm.clicked.connect(self.remove_selected_kit)
        self.btn_detect = QPushButton("Detectar kits")
        self.btn_detect.clicked.connect(self.detect_kits)
        row.addWidget(add)
        row.addWidget(rm)
        row.addWidget(self.btn_detect)
        row.addStretch(1)
        lay.addLayout(row)
        hint = QLabel("Un kit sin link se guarda, pero el worker no lo elige. \"Detectar kits\" "
                      "suma las carpetas con loops que falten en la tabla, sin link ni género.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #888;")
        lay.addWidget(hint)
        return box

    def _build_genres_box(self):
        box = QGroupBox("Géneros y carpetas de referencia")
        form = QFormLayout(box)
        self.genres = QPlainTextEdit()
        self.genres.setPlaceholderText("Un género por línea")
        self.genres.setFixedHeight(80)
        self.genres.textChanged.connect(self._refresh_folders)
        self.refs_root = QLineEdit()
        self.refs_root.setPlaceholderText("/ruta/en/Dropbox/referencias")
        self.refs_root.textChanged.connect(self._refresh_folders)
        self.ref_folders = QLabel("")
        self.ref_folders.setWordWrap(True)
        self.ref_folders.setStyleSheet("color: #888;")
        form.addRow("Géneros:", self.genres)
        form.addRow("Carpeta de referencias:", self.refs_root)
        form.addRow("Carpeta por género:", self.ref_folders)
        return box

    def _build_cover_box(self):
        box = QGroupBox("Portada")
        form = QFormLayout(box)
        self.cover_mode = QComboBox()
        self.cover_mode.addItem("Manual (imagen del pack)", 'manual')
        self.cover_mode.addItem("Auto (fondo generado con IA)", 'auto')
        form.addRow("Modo:", self.cover_mode)
        return box

    def _build_telegram_box(self):
        box = QGroupBox("Telegram")
        lay = QVBoxLayout(box)
        self.telegram = QLabel("")
        lay.addWidget(self.telegram)
        note = QLabel("Token y chat se cargan como secretos de GitHub o variables de entorno; "
                      "no se muestran ni se guardan acá.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #888;")
        lay.addWidget(note)
        self.refresh_telegram()
        return box

    # --- Tabla de kits ---

    def add_kit_row(self, kit=None):
        kit = kit or {}
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, key in enumerate(('folder', 'name', 'payhip_url', 'genre')):
            self.table.setItem(r, c, QTableWidgetItem(str(kit.get(key) or '')))
        active = QTableWidgetItem()
        active.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        active.setCheckState(Qt.Checked if kit.get('active', True) else Qt.Unchecked)
        self.table.setItem(r, 4, active)

    def remove_selected_kit(self):
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def _cell(self, r, c):
        item = self.table.item(r, c)
        return item.text() if item else ''

    def kit_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            active = self.table.item(r, 4)
            rows.append({'folder': self._cell(r, 0), 'name': self._cell(r, 1),
                         'payhip_url': self._cell(r, 2), 'genre': self._cell(r, 3),
                         'active': bool(active and active.checkState() == Qt.Checked)})
        return rows

    # --- Formulario ---

    def form_values(self):
        return {'channel': self.channel.currentText(),
                'slots': [{'weekday': self.slot_day[i].currentIndex(),
                           'hour': self.slot_time[i].time().hour(),
                           'minute': self.slot_time[i].time().minute()}
                          for i in range(_SLOT_ROWS)],
                'genres': kit_settings.parse_genres(self.genres.toPlainText()),
                'refs_root': self.refs_root.text(),
                'cover_mode': self.cover_mode.currentData(),
                'dropbox_root': self.kits_root.text(),
                'scan_folders': self.checked_categories(),
                'loops_dirs': self.loops_dirs.text(),
                'ignore_names': self.ignore_names.text(),
                'scan_max_depth': self.scan_depth.value()}

    def checked_categories(self):
        return [self.categories.item(i).text() for i in range(self.categories.count())
                if self.categories.item(i).checkState() == Qt.Checked]

    def set_categories(self, available, selected=None):
        """Casillas de categorías: primero las elegidas, en su orden, y después el resto."""
        selected = self.checked_categories() if selected is None else list(selected)
        chosen = {name.lower() for name in selected}
        names = selected + [n for n in available or [] if n.lower() not in chosen]
        self.categories.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if name.lower() in chosen else Qt.Unchecked)
            self.categories.addItem(item)

    def scan_values(self):
        """Reglas de recorrido tal como están en el formulario (validadas)."""
        form = self.form_values()
        scan = kit_settings._validate_scan(form)
        if not scan['dropbox_root']:
            raise kit_settings.SettingsError('Cargá la carpeta raíz de kits.')
        return scan['dropbox_root'], kit_source.scan_settings(scan)

    def set_form(self, form):
        self.channel.clear()
        self.channel.addItems([''] + list(form.get('channels') or []))
        self.channel.setCurrentText(form.get('channel') or '')
        slots = list(form.get('slots') or [])
        for i in range(_SLOT_ROWS):
            slot = slots[i] if i < len(slots) else slots[-1] if slots else {}
            self.slot_day[i].setCurrentIndex(min(max(int(slot.get('weekday', i * 2)), 0), 6))
            self.slot_time[i].setTime(QTime(int(slot.get('hour', 18)), int(slot.get('minute', 0))))
        self.genres.setPlainText('\n'.join(form.get('genres') or []))
        self.refs_root.setText(form.get('refs_root') or '')
        self.cover_mode.setCurrentIndex(max(0, self.cover_mode.findData(form.get('cover_mode'))))
        self.kits_root.setText(form.get('dropbox_root') or '')
        self.set_categories(form.get('categories'), form.get('scan_folders') or [])
        self.loops_dirs.setText(', '.join(form.get('loops_dirs') or []))
        self.ignore_names.setText(', '.join(form.get('ignore_names') or []))
        self.scan_depth.setValue(int(form.get('scan_max_depth') or kit_source.DEFAULT_MAX_DEPTH))

    def set_kits(self, kits):
        self.table.setRowCount(0)
        for kit in kits or []:
            self.add_kit_row(kit)

    def _refresh_folders(self):
        folders = kit_settings.reference_folders(
            self.refs_root.text().strip(), kit_settings.parse_genres(self.genres.toPlainText()))
        self.ref_folders.setText('\n'.join(folders) if folders else '(sin carpeta de referencias)')

    def refresh_telegram(self):
        ok = kit_settings.telegram_configured()
        self.telegram.setText("Configurado en esta PC." if ok else
                              "No configurado en esta PC (el worker usa los secretos de GitHub).")

    def serialize(self):
        """Valida todo y devuelve ``(catalogo, ajustes)``; SettingsError si algo está mal."""
        settings = kit_settings.validate_settings(self.form_values())
        rows = kit_settings.prune_blank(self.kit_rows())
        catalog = kit_settings.validate_kits(rows, settings['genres'])
        return catalog, settings

    # --- Dropbox (en hilo aparte) ---

    def _busy(self, on):
        for btn in (self.btn_reload, self.btn_save, self.btn_state, self.btn_new,
                    self.automation, self.btn_categories, self.btn_detect):
            btn.setEnabled(not on)

    # --- Canal elegido ---

    def paths(self):
        """Rutas de Dropbox del canal del selector."""
        return kit_channel.paths(self.automation.currentData())

    def _set_automations(self, registry, select=None):
        current = self.automation.currentData() if select is None else select
        self.automation.blockSignals(True)
        self.automation.clear()
        self.automation.addItem("Canal por defecto", '')
        for row in registry or []:
            self.automation.addItem(row['name'], row['slug'])
        self.automation.setCurrentIndex(max(0, self.automation.findData(current)))
        self.automation.blockSignals(False)

    def _local_config(self):
        try:
            with open(os.path.join(self._script_dir, 'config', 'app_config.json'),
                      encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def ask_new_automation(self):
        names = kit_channel_setup.loop_kit_channels(self._local_config(), self._base_config)
        taken = {self.automation.itemText(i) for i in range(1, self.automation.count())}
        name, ok = QInputDialog.getItem(
            self, "Crear automatización", "Canal de Loop kits:",
            [n for n in names if n not in taken], 0, True)
        if ok:
            self.create_automation(name)

    def create_automation(self, name):
        """Arma la config mínima del canal en Dropbox y lo deja elegido."""
        base, local = self._base_config, self._local_config()

        def work():
            dbx = self._dbx()
            if base is None:  # todavía no se leyó la config del canal por defecto
                default = kit_settings.load_all(dbx)['config']
            else:
                default = base
            created = kit_channel_setup.create(name, default, local, dbx)
            return created, kit_channel_setup.load_registry(dbx)

        def done(result):
            created, registry = result
            self._set_automations(registry, select=created.slug)
            self.reload(note="Automatización creada. Falta cargar los secretos de "
                             f"{kit_channel.environment(created.slug)} "
                             "(scripts/kit_secrets_sync.py) y sumar el canal a KIT_CHANNELS.")

        self._run(work, done, "Creando la automatización…")

    def _run(self, fn, on_done, message):
        if self._task is not None:
            return
        self._busy(True)
        self._say(message)
        task = _Task(fn, self)
        task.done.connect(lambda result: self._finish(task, on_done, result))
        task.failed.connect(lambda text: self._finish(task, None, None, text))
        self._task = task
        task.start()

    def _finish(self, task, on_done, result, error=None):
        task.wait()
        task.deleteLater()
        self._task = None
        self._busy(False)
        if error:
            self._say(error, error=True)
        elif on_done:
            on_done(result)

    def _say(self, text, error=False):
        self.status.setText(text)
        self.status.setStyleSheet("color: #d9534f;" if error else "")

    def reload(self, note=None):
        paths = self.paths()

        def work():
            dbx = self._dbx()
            data = kit_settings.load_all(dbx, None if paths.is_default else paths)
            data['registry'] = kit_channel_setup.load_registry(dbx)
            data['own'] = not paths.is_default
            root = ((data['config'] or {}).get('kit_preview') or {}).get('dropbox_root')
            try:
                data['categories'] = kit_detect.categories(root, dbx) if root else []
            except Exception:  # noqa: BLE001 - sin listado quedan las categorías guardadas
                data['categories'] = []
            return data

        self._run(work, lambda data: self._apply_loaded(data, note), "Leyendo desde Dropbox…")

    def _dbx(self):
        return self._dbx_provider() if self._dbx_provider else None

    def _apply_loaded(self, data, note=None):
        self._kits_rev = data['kits_rev']
        self._set_automations(data['registry'])
        if not data['own']:
            self._base_config = data['config']
        self.set_form({**kit_settings.form_from_config(data['config']),
                       'categories': data['categories']})
        # Un canal con automatización propia no puede apuntar a otro canal.
        self.channel.setEnabled(not data['own'])
        self.set_kits(data['kits'])
        self._say(note or "Configuración cargada." if data['config'] is not None else
                  "No hay config del worker en Dropbox: se pueden editar los kits, pero no "
                  "los ajustes hasta subirla (docs/KIT_WEEKLY.md).",
                  error=data['config'] is None)

    def save(self):
        try:
            catalog, settings = self.serialize()
        except kit_settings.SettingsError as exc:
            self._say(str(exc), error=True)
            return
        # Las filas vacías ya no están en el catálogo: se reflejan en la tabla.
        self.set_kits(catalog)
        rev = self._kits_rev
        paths = self.paths()
        paths = None if paths.is_default else paths

        def work():
            dbx, problems, kits_rev = self._dbx(), [], rev
            for label, op in (("kits", lambda: kit_settings.save_kits(catalog, rev, dbx, paths)),
                              ("ajustes", lambda: kit_settings.save_config(settings, dbx, paths))):
                try:
                    saved_rev = op()
                    if label == "kits":
                        kits_rev = saved_rev
                except kit_cloud.KitCloudConflict:
                    problems.append(f"{label}: cambió desde otro lado; recargá y repetí.")
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{label}: {_error_text(exc)}")
            return problems, kits_rev

        def done(result):
            # Si los kits no se guardaron queda el rev viejo: repetir sin recargar no pisa.
            problems, self._kits_rev = result
            self._say("Guardado en Dropbox." if not problems else
                      "No se guardó todo — " + " ".join(problems), error=bool(problems))

        self._run(work, done, "Guardando en Dropbox…")

    # --- Carpeta de kits ---

    def read_categories(self):
        """Arma las casillas con las subcarpetas de la raíz escrita en el formulario."""
        try:
            root, _scan = self.scan_values()
        except kit_settings.SettingsError as exc:
            self._say(str(exc), error=True)
            return

        def done(names):
            self.set_categories(names)
            self._say(f"{len(names)} categoría(s) en la carpeta raíz.")

        self._run(lambda: kit_detect.categories(root, self._dbx()), done,
                  "Leyendo las categorías…")

    def detect_kits(self):
        """Suma a la tabla los kits de Dropbox que falten, sin link ni género."""
        try:
            root, scan = self.scan_values()
        except kit_settings.SettingsError as exc:
            self._say(str(exc), error=True)
            return
        current = kit_settings.prune_blank(self.kit_rows())

        def done(detected):
            rows, added = kit_detect.merge(current, detected)
            self.set_kits(rows)
            self._say(f"{len(detected)} kit(s) detectados, {added} nuevo(s) en la tabla. "
                      "Completá link y género antes de guardar.")

        self._run(lambda: kit_detect.detect(root, scan, self._dbx()), done,
                  "Buscando kits en Dropbox…")

    def show_last_state(self):
        def done(state):
            self.output.setPlainText('\n'.join(kit_settings.last_state_lines(state)))
            self._say("Estado leído.")
        path = self.paths().state
        self._run(lambda: kit_state.load(path, dbx=self._dbx()), done, "Leyendo el estado…")

    def shutdown(self):
        """Espera la tarea en curso y corta el dry-run antes de destruir el panel."""
        if self._proc is not None:
            self._proc.kill()
            self._proc.waitForFinished(3000)
        if self._task is not None:
            self._task.wait()

    # --- Dry-run ---

    def run_dry_run(self):
        if self._proc is not None:
            return
        script = os.path.join(self._script_dir, 'scripts', 'run_kit_weekly.py')
        proc = QProcess(self)
        proc.setWorkingDirectory(self._script_dir)
        proc.setProcessChannelMode(QProcess.MergedChannels)
        proc.finished.connect(lambda code, _status: self._dry_run_done(code))
        proc.errorOccurred.connect(lambda _e: self._dry_run_done(-1))
        self._proc = proc
        self.btn_dry.setEnabled(False)
        self.output.setPlainText("")
        self._say("Corriendo dry-run (no renderiza ni sube)…")
        paths = self.paths()
        proc.start(self._python, [script, '--dry-run', '--cloud-config']
                   + ([] if paths.is_default else ['--automation', paths.slug]))

    def _dry_run_done(self, code):
        proc, self._proc = self._proc, None
        if proc is None:
            return
        text = bytes(proc.readAll()).decode('utf-8', errors='replace').strip()
        self.output.setPlainText('\n'.join(text.splitlines()[-40:]))
        self.btn_dry.setEnabled(True)
        proc.deleteLater()
        self._say("Dry-run terminado." if code == 0 else
                  "El dry-run falló; revisá el detalle de abajo.", error=code != 0)


def open_loop_kit_panel(parent=None):
    """Abre el panel en un diálogo y carga lo guardado en Dropbox."""
    dialog = QDialog(parent)
    dialog.setWindowTitle("Loop kits: configuración de la automatización")
    dialog.resize(820, 760)
    lay = QVBoxLayout(dialog)
    panel = LoopKitPanel(dialog)
    lay.addWidget(panel)
    panel.reload()
    dialog.exec_()
    panel.shutdown()
    return panel
