# -*- coding: utf-8 -*-
"""Panel de configuración de la automatización de Loop kits.

Independiente de Beats: se abre en un diálogo desde la sección Loop kits.
Lee y guarda ``kits.json`` y las claves ``kit_preview`` del worker en Dropbox (core/kit_settings).
Arriba se elige el canal: cada uno tiene su config, sus kits y su estado (core/kit_channel).
Los secretos nunca pasan por aquí: Telegram solo muestra si está "configurado".
"""
import copy
import os
import sys

from PyQt5.QtCore import QProcess, Qt, QThread, QTime, pyqtSignal
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDoubleSpinBox,
                             QFormLayout, QGroupBox,
                             QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QListWidget, QListWidgetItem, QPlainTextEdit, QPushButton,
                             QScrollArea, QSpinBox, QTabWidget, QTableWidget, QTableWidgetItem,
                             QTimeEdit, QVBoxLayout, QWidget)

from core import (channel_kind, cloud_merge, cloud_registry, dropbox_layout, kit_channel,
                  kit_channel_setup, kit_cloud, kit_detect, kit_seo, kit_settings, kit_source, kit_spend,
                  kit_state, kit_trends)
from core.automation_status import AutomationError
from core import automation_status as status
from core.automation_save_bar import AutomationSaveBar, KITS_PILOT_REQUIRED
from core.kit_connections_form import KitConnectionsForm
from core.channel_wizard import KITS, ChannelWizardHost
from core.seo_report_box import SeoReportBox
from core.seo_report_status import KITS, local_status
import ui_theme as theme

_ROOT = os.path.dirname(os.path.abspath(__file__))
_HEADERS = ("Carpeta", "Nombre", "Link de PayHip", "Género", "Descripción", "Activo")
_TEXT_COLS = ('folder', 'name', 'payhip_url', 'genre', 'description')
_ACTIVE_COL = len(_TEXT_COLS)
_SLOT_ROWS = 3
_DRY_RUN_TIMEOUT_MS = 10 * 60 * 1000


def _error_text(exc):
    """Mensaje seguro: los errores propios se muestran, el resto solo por tipo."""
    if isinstance(exc, (kit_settings.SettingsError, kit_cloud.KitCloudError,
                        kit_channel_setup.ChannelSetupError, AutomationError,
                        channel_kind.ChannelKindError, cloud_registry.RegistryError)):
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


def _picker(parent, current):
    """Selector de carpetas de Dropbox (el mismo de Beats), abierto en la carpeta actual."""
    from core.beat_dropbox_picker import DropboxPicker
    return DropboxPicker(parent, start=current)


class LoopKitPanel(QWidget, KitConnectionsForm, AutomationSaveBar, ChannelWizardHost):
    """Formulario de canal, horarios, carpeta de kits, kits, géneros, SEO, portada y estado."""
    wizard_kind = KITS

    def __init__(self, parent=None, dbx_provider=None, python=None, script_dir=None):
        super().__init__(parent)
        self._dbx_provider = dbx_provider  # None: kit_cloud arma el cliente de Dropbox
        self._python = python or sys.executable
        self._script_dir = script_dir or _ROOT
        self._kits_rev = None
        self._kits_base = None    # kits.json tal como se leyó (base del merge de 3 vías)
        self._config_base, self._config_rev = None, None
        self._base_config = None  # config del canal por defecto: base de un canal nuevo
        # Registro de canales (/automatizacion/canales.json): nombres y plantillas de Loops.
        self._registry, self._registry_rev = cloud_registry.empty('canales'), None
        self._registry_error = None
        self._task = None
        self._proc = None
        self._seo = {}            # fichas de SEO por género, tal como están en el formulario
        self._seo_current = None  # género cuya ficha se ve en los campos
        self._trends_max_age = None  # kit_preview.trends.max_age_days, cuando la config ya cargó
        self._build()

    # --- Construcción ---

    def _build(self):
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("Automatización"))
        self.automation = QComboBox()
        self.automation.addItem("Canal por defecto", '')
        self.automation.currentIndexChanged.connect(lambda _i: self.reload())
        top.addWidget(self.automation, 1)
        self.chip_label = QLabel("")
        top.addWidget(self.chip_label)
        self.btn_new = QPushButton("+ Nueva automatización…")
        self.btn_new.clicked.connect(self.ask_new_automation)
        top.addWidget(self.btn_new)
        self.btn_wizard = theme.flat(QPushButton("Asistente de alta…"))
        self.btn_wizard.clicked.connect(lambda: self.open_channel_wizard())
        top.addWidget(self.btn_wizard)
        outer.addLayout(top)
        self.tabs = QTabWidget()

        connections = QWidget()
        conn_layout = QVBoxLayout(connections)
        self._build_connections(conn_layout)
        conn_scroll = QScrollArea()
        conn_scroll.setWidgetResizable(True)
        conn_scroll.setFrameShape(QScrollArea.NoFrame)
        conn_scroll.setWidget(connections)
        conn_tab = QWidget()
        conn_tab_layout = QVBoxLayout(conn_tab)
        conn_tab_layout.setContentsMargins(0, 0, 0, 0)
        conn_tab_layout.addWidget(conn_scroll)
        self.tabs.addTab(conn_tab, "Conexiones")

        canal_body = QWidget()
        canal_col = QVBoxLayout(canal_body)
        canal_col.addWidget(self._build_channel_box())
        canal_col.addWidget(self._build_source_box())
        canal_col.addWidget(self._build_kits_box(), 1)
        canal_col.addWidget(self._build_genres_box())
        canal_col.addWidget(self._build_cover_box())
        self.tabs.addTab(self._scroll_tab(canal_body), "Canal")

        seo_body = QWidget()
        seo_col = QVBoxLayout(seo_body)
        seo_col.addWidget(self._build_seo_box())
        # Informe de Claude Code: clave = slug de la automatización ('' = canal por defecto).
        self.seo_report_box = SeoReportBox(KITS, lambda: {
            'key': self.automation.currentData() or '',
            'names': kit_settings.parse_genres(self.genres.toPlainText()),
            'max_age_days': self._trends_max_age})
        seo_col.addWidget(self.seo_report_box)
        self.automation.currentIndexChanged.connect(lambda _i: self.seo_report_box.refresh())
        self.tabs.currentChanged.connect(lambda _i: self.seo_report_box.refresh())
        seo_col.addStretch()
        self.tabs.addTab(self._scroll_tab(seo_body), "SEO y tendencias")

        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.addWidget(self._build_spend_box())
        buttons = QHBoxLayout()
        self.btn_reload = QPushButton("Recargar desde Dropbox")
        self.btn_save = QPushButton("Publicar solo en Dropbox")
        self.btn_dry = QPushButton('Probar sin subir')
        self.btn_state = QPushButton("Ver último estado")
        for btn in (self.btn_reload, self.btn_save, self.btn_dry, self.btn_state):
            buttons.addWidget(btn)
        buttons.addStretch(1)
        self.btn_reload.clicked.connect(self.reload)
        self.btn_save.clicked.connect(self.save)
        self.btn_dry.clicked.connect(self.run_dry_run)
        self.btn_state.clicked.connect(self.show_last_state)
        advanced_layout.addLayout(buttons)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setMaximumBlockCount(500)
        self.output.setMinimumHeight(90)
        advanced_layout.addWidget(self.output, 1)
        self.tabs.addTab(advanced, "Avanzado")

        outer.addWidget(self.tabs, 1)
        self._build_save_bar(outer)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.channel.currentTextChanged.connect(self.refresh_connections)
        self.automation.currentIndexChanged.connect(lambda _i: self.refresh_publish_readiness())
        self.refresh_connections()

    def refresh_publish_readiness(self):
        """Checklist de piloto del canal/automatización actual (barra inferior)."""
        channel = (self.channel.currentText() or '').strip()
        slug = self.automation.currentData() or ''
        items = status.readiness_kits(channel, slug)
        seo = local_status(KITS, slug, max_age_days=self._trends_max_age,
                           notion_state=status.kit_notion_status())
        self._refresh_publish_readiness(items, seo['state'], KITS_PILOT_REQUIRED)
        self.refresh_channel_chips()

    # --- Hooks del asistente de alta (core/channel_wizard.py) ---

    def wizard_target(self):
        """``(canal, slug, clave de flags)``: la clave es el slug ('' = canal por defecto)."""
        slug = self.automation.currentData() or ''
        return (self.channel.currentText() or '').strip(), slug, slug

    def wizard_focus(self, channel, slug, key):
        """Vuelve el selector y el combo de YouTube al canal del asistente.

        Cambiar de automatización dispara ``reload()`` asíncrono: ``wizard_bind``
        fallará hasta que termine.
        """
        idx = self.automation.findData(slug)
        if idx < 0:
            return
        if self.automation.currentIndex() != idx:
            self.automation.setCurrentIndex(idx)
        name = (self.channel.currentText() or '').strip()
        if channel and name != channel:
            found = self.channel.findText(channel)
            if found >= 0:
                self.channel.setCurrentIndex(found)
            else:
                self.channel.setEditText(channel)

    def wizard_activate(self):
        """Publica el canal bindeado. El éxito lo avisa Dropbox, no este return."""
        if self._task is not None:
            return False
        return self.save_and_publish() is not False

    def refresh_channel_chips(self):
        """Color y tooltip del chip por automatización en el selector, y chip del canal actual.

        El texto del combo no cambia: otras partes lo usan como nombre del canal.
        """
        if not getattr(self, 'chip_label', None):
            return
        current = self.automation.currentIndex()
        for i in range(self.automation.count()):
            slug = self.automation.itemData(i) or ''
            # El nombre del canal por defecto solo se conoce cuando está elegido.
            name = self.automation.itemText(i) if slug else ''
            if i == current:
                name = (self.channel.currentText() or '').strip() or name
            text, color = self.channel_chip(name, slug, slug)
            self.automation.setItemData(i, QColor(color), Qt.ForegroundRole)
            self.automation.setItemData(i, text, Qt.ToolTipRole)
            if i == current:
                self.chip_label.setText(f'<span style="color:{color}">{text}</span>')

    def save_and_publish(self):
        """Publica kits y config del worker en Dropbox (no hay copia local de kits)."""
        self.save()

    def _scroll_tab(self, body):
        """Pestaña con scroll, sin marco, para no achicar los formularios largos."""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setWidget(body)
        tab = QWidget()
        lay = QVBoxLayout(tab)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)
        return tab

    def _build_channel_box(self):
        box = QGroupBox("Canal y horarios")
        form = theme.form_layout(box)
        self.channel = QComboBox()
        self.channel.setEditable(True)
        form.addRow("Canal de Loop kits", self.channel)
        self.slot_day, self.slot_time = [], []
        for i in range(_SLOT_ROWS):
            day, tm = QComboBox(), QTimeEdit()
            day.addItems(kit_settings.WEEKDAYS)
            tm.setDisplayFormat("HH:mm")
            row = QHBoxLayout()
            row.addWidget(day, 1)
            row.addWidget(tm)
            form.addRow(f"Horario {i + 1}", row)
            self.slot_day.append(day)
            self.slot_time.append(tm)
        hint = QLabel("Hora de Buenos Aires. Sale un video por horario distinto (hasta 3). Para publicar menos, "
                      "repetí el mismo horario en las filas que sobran.")
        hint.setWordWrap(True)
        theme.muted(hint)
        form.addRow(hint)
        return box

    def _build_source_box(self):
        box = QGroupBox("Carpeta de kits en Dropbox")
        form = theme.form_layout(box)
        self.kits_root = QLineEdit()
        self.kits_root.setPlaceholderText("Tocá «Elegir en Dropbox…» (o escribí la ruta)")
        self.btn_pick_root = QPushButton("Elegir en Dropbox…")
        self.btn_pick_root.setToolTip("Navegá tu Dropbox con clics y elegí la carpeta de los kits.")
        self.btn_pick_root.clicked.connect(lambda: self.pick_dropbox_folder(self.kits_root))
        self.btn_categories = theme.flat(QPushButton("Leer categorías"))
        self.btn_categories.clicked.connect(self.read_categories)
        row = QHBoxLayout()
        row.addWidget(self.kits_root, 1)
        row.addWidget(self.btn_pick_root)
        row.addWidget(self.btn_categories)
        form.addRow("Carpeta raíz", row)
        self.categories = QListWidget()
        self.categories.setDragDropMode(QAbstractItemView.InternalMove)
        self.categories.setFixedHeight(110)
        form.addRow("Categorías a recorrer", self.categories)
        self.loops_dirs = QLineEdit()
        self.loops_dirs.setPlaceholderText("loops")
        form.addRow("Carpetas de loops", self.loops_dirs)
        self.ignore_names = QLineEdit()
        self.ignore_names.setPlaceholderText("tag, preview")
        form.addRow("Nombres a ignorar", self.ignore_names)
        self.scan_depth = QSpinBox()
        self.scan_depth.setRange(1, kit_settings.MAX_SCAN_DEPTH)
        form.addRow("Profundidad máxima", self.scan_depth)
        hint = QLabel("Las categorías se recorren en el orden de la lista (se puede arrastrar). "
                      "Sin ninguna marcada, los kits se buscan directo en la carpeta raíz. "
                      "Carpetas de loops y nombres a ignorar van separados por coma.")
        hint.setWordWrap(True)
        theme.muted(hint)
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
        hint = QLabel("Un kit sin link se guarda, pero el robot no lo elige. \"Detectar kits\" "
                      "suma las carpetas con loops que falten en la tabla, sin link ni género. "
                      "La descripción (opcional, 1 o 2 líneas, hasta 200 caracteres) le da "
                      "contexto al modelo que propone el nombre de cada video.")
        hint.setWordWrap(True)
        theme.muted(hint)
        lay.addWidget(hint)
        return box

    def _build_genres_box(self):
        box = QGroupBox("Géneros y carpetas de referencia")
        form = theme.form_layout(box)
        self.genres = QPlainTextEdit()
        self.genres.setPlaceholderText("Un género por línea")
        self.genres.setFixedHeight(80)
        self.genres.textChanged.connect(self._refresh_folders)
        self.refs_root = QLineEdit()
        self.refs_root.setPlaceholderText("Tocá «Elegir en Dropbox…» (o escribí la ruta)")
        self.refs_root.textChanged.connect(self._refresh_folders)
        self.btn_pick_refs = QPushButton("Elegir en Dropbox…")
        self.btn_pick_refs.setToolTip("Navegá tu Dropbox con clics y elegí la carpeta de referencias.")
        self.btn_pick_refs.clicked.connect(lambda: self.pick_dropbox_folder(self.refs_root))
        refs_row = QHBoxLayout()
        refs_row.addWidget(self.refs_root, 1)
        refs_row.addWidget(self.btn_pick_refs)
        self.ref_folders = QLabel("")
        self.ref_folders.setWordWrap(True)
        theme.muted(self.ref_folders)
        form.addRow("Géneros", self.genres)
        form.addRow("Carpeta de referencias", refs_row)
        form.addRow("Carpeta por género", self.ref_folders)
        return box

    def _build_seo_box(self):
        box = QGroupBox("SEO por género")
        form = theme.form_layout(box)
        self.seo_genre = QComboBox()
        self.seo_genre.currentIndexChanged.connect(lambda _i: self._seo_changed())
        form.addRow("Género", self.seo_genre)
        self.seo_phrase = QLineEdit()
        self.seo_phrase.setPlaceholderText("Frase que la gente busca")
        form.addRow("Frase principal", self.seo_phrase)
        self.seo_artists = QPlainTextEdit()
        self.seo_artists.setPlaceholderText("Un artista por línea")
        self.seo_tags = QPlainTextEdit()
        self.seo_tags.setPlaceholderText("Una etiqueta por línea")
        self.seo_template = QLineEdit()
        self.seo_template.setPlaceholderText(kit_seo.DEFAULT_TEMPLATE)
        self.seo_examples = QPlainTextEdit()
        self.seo_examples.setPlaceholderText("Un título de ejemplo por línea")
        for edit in (self.seo_artists, self.seo_tags, self.seo_examples):
            edit.setFixedHeight(70)
        form.addRow("Artistas", self.seo_artists)
        form.addRow("Etiquetas", self.seo_tags)
        form.addRow("Plantilla del título", self.seo_template)
        form.addRow("Títulos de ejemplo", self.seo_examples)
        self.vary_name = QCheckBox("Variar también el nombre")
        form.addRow("", self.vary_name)
        hint = QLabel("Con ficha, el título lo arma el programa: nombre real del kit, la frase "
                      "al principio y, en cada video del kit, otro artista y otra mezcla de "
                      "etiquetas. La plantilla admite {artist}, {artists}, {phrase}, {name} y "
                      "{tags}; vacía usa la de fábrica. La frase tiene que terminar dentro de "
                      "los primeros 40 caracteres del título, artista incluido. Un género sin "
                      "frase no tiene ficha y sigue con la plantilla de título del canal. En la descripción del canal, "
                      "{hook} es el gancho y {chapters} los capítulos. Variar el nombre lo "
                      "reemplaza por uno de una sola palabra (necesita el modelo de texto "
                      "configurado).")
        hint.setWordWrap(True)
        theme.muted(hint)
        form.addRow(hint)
        self.genres.textChanged.connect(self._refresh_seo_genres)
        return box

    def _seo_fields(self):
        return {'phrase': self.seo_phrase.text(),
                'artists': kit_seo.lines(self.seo_artists.toPlainText()),
                'tags': kit_seo.lines(self.seo_tags.toPlainText()),
                'title_template': self.seo_template.text(),
                'examples': kit_seo.lines(self.seo_examples.toPlainText())}

    def _seo_keep(self):
        """Guarda en memoria lo que hay en los campos, bajo el género que se está viendo."""
        if self._seo_current is not None:
            self._seo[self._seo_current] = self._seo_fields()

    def _seo_show(self, genre):
        self._seo_current = genre or None
        ficha = kit_seo.form(self._seo.get(kit_seo.find_key(self._seo, genre) or genre))
        self.seo_phrase.setText(ficha['phrase'])
        self.seo_artists.setPlainText('\n'.join(ficha['artists']))
        self.seo_tags.setPlainText('\n'.join(ficha['tags']))
        self.seo_template.setText(ficha['title_template'])
        self.seo_examples.setPlainText('\n'.join(ficha['examples']))

    def _seo_changed(self):
        self._seo_keep()
        self._seo_show(self.seo_genre.currentText())

    def _refresh_seo_genres(self):
        """El selector sigue a la lista de géneros; la ficha de cada uno se conserva."""
        self._seo_keep()
        genres = kit_settings.parse_genres(self.genres.toPlainText())
        # Una ficha guardada con otra capitalización pasa a la clave del género actual.
        for genre in genres:
            old = kit_seo.find_key(self._seo, genre)
            if old is not None and old != genre:
                self._seo[genre] = self._seo.pop(old)
        current = self._seo_current
        self.seo_genre.blockSignals(True)
        self.seo_genre.clear()
        self.seo_genre.addItems(genres)
        self.seo_genre.setCurrentIndex(max(0, self.seo_genre.findText(current or '')))
        self.seo_genre.blockSignals(False)
        self._seo_show(self.seo_genre.currentText())

    def seo_values(self):
        """Fichas de todos los géneros, incluida la que se está editando."""
        self._seo_keep()
        return {genre: dict(ficha) for genre, ficha in self._seo.items()}

    def _build_cover_box(self):
        box = QGroupBox("Portada")
        form = theme.form_layout(box)
        self.cover_mode = QComboBox()
        self.cover_mode.addItem("Manual (imagen del pack)", 'manual')
        self.cover_mode.addItem("Auto (fondo generado con IA)", 'auto')
        self.cover_mode.addItem("Plantilla + fondo (portada completa con IA)", 'template')
        form.addRow("Modo", self.cover_mode)
        self.art_prompt = QPlainTextEdit()
        self.art_prompt.setFixedHeight(120)
        form.addRow("Prompt de la portada", self.art_prompt)
        self.btn_prompt = QPushButton("Restaurar prompt por defecto")
        self.btn_prompt.clicked.connect(self.restore_prompt)
        row = QHBoxLayout()
        row.addWidget(self.btn_prompt)
        row.addStretch(1)
        form.addRow("", row)
        hint = QLabel("Plantilla + fondo usa, en la carpeta de referencias de cada género, "
                      "modelo.png y la subcarpeta fondos/. {titulo} en el prompt se reemplaza por el "
                      "título del video (si falta, se agrega al final). Los topes de gasto están "
                      "en Avanzado.")
        hint.setWordWrap(True)
        theme.muted(hint)
        form.addRow(hint)
        return box

    def restore_prompt(self):
        self.art_prompt.setPlainText(kit_settings.default_prompt())

    def _build_spend_box(self):
        box = QGroupBox("Topes de gasto e IA")
        form = theme.form_layout(box)
        self.monthly_cap = QDoubleSpinBox()
        self.monthly_cap.setRange(0, kit_settings.MAX_MONTHLY_CAP)
        self.monthly_cap.setDecimals(2)
        self.monthly_cap.setPrefix("USD ")
        form.addRow("Tope mensual estimado", self.monthly_cap)
        self.max_images = QSpinBox()
        self.max_images.setRange(0, kit_settings.MAX_IMAGES_PER_RUN)
        form.addRow("Máximo de imágenes por corrida", self.max_images)
        hint = QLabel("Al llegar a un tope no se generan más portadas: esos videos salen con la "
                      "imagen manual y llega un aviso por Telegram. El gasto es una estimación, "
                      "no la factura. Las claves LLM/imagen se cargan en Conexiones.")
        hint.setWordWrap(True)
        theme.muted(hint)
        form.addRow(hint)
        return box

    # --- Tabla de kits ---

    def add_kit_row(self, kit=None):
        kit = kit or {}
        r = self.table.rowCount()
        self.table.insertRow(r)
        for c, key in enumerate(_TEXT_COLS):
            self.table.setItem(r, c, QTableWidgetItem(str(kit.get(key) or '')))
        active = QTableWidgetItem()
        active.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        active.setCheckState(Qt.Checked if kit.get('active', True) else Qt.Unchecked)
        self.table.setItem(r, _ACTIVE_COL, active)

    def remove_selected_kit(self):
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)

    def _cell(self, r, c):
        item = self.table.item(r, c)
        return item.text() if item else ''

    def kit_rows(self):
        rows = []
        for r in range(self.table.rowCount()):
            active = self.table.item(r, _ACTIVE_COL)
            rows.append({**{key: self._cell(r, c) for c, key in enumerate(_TEXT_COLS)},
                         'active': bool(active and active.checkState() == Qt.Checked)})
        return rows

    # --- Formulario ---

    def form_values(self):
        slots = []
        for i in range(_SLOT_ROWS):
            slot = {'weekday': self.slot_day[i].currentIndex(),
                    'hour': self.slot_time[i].time().hour(),
                    'minute': self.slot_time[i].time().minute()}
            # Una fila igual a la anterior es "sin horario": así se cargan menos de 3.
            if not slots or slot != slots[-1]:
                slots.append(slot)
        return {'channel': self.channel.currentText(),
                'slots': slots,
                'seo': self.seo_values(),
                'vary_name': self.vary_name.isChecked(),
                'genres': kit_settings.parse_genres(self.genres.toPlainText()),
                'refs_root': self.refs_root.text(),
                'cover_mode': self.cover_mode.currentData(),
                'art_prompt': self.art_prompt.toPlainText(),
                'monthly_cap_usd': self.monthly_cap.value(),
                'max_images_per_run': self.max_images.value(),
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
        # Antes de tocar los géneros: lo que hay en los campos es de la config anterior.
        self._seo_current = None
        self._seo = {genre: dict(ficha) for genre, ficha in (form.get('seo') or {}).items()}
        self.vary_name.setChecked(bool(form.get('vary_name')))
        slots = list(form.get('slots') or [])
        for i in range(_SLOT_ROWS):
            slot = slots[i] if i < len(slots) else slots[-1] if slots else {}
            self.slot_day[i].setCurrentIndex(min(max(int(slot.get('weekday', i * 2)), 0), 6))
            self.slot_time[i].setTime(QTime(int(slot.get('hour', 18)), int(slot.get('minute', 0))))
        self.genres.setPlainText('\n'.join(form.get('genres') or []))
        self.refs_root.setText(form.get('refs_root') or '')
        self.cover_mode.setCurrentIndex(max(0, self.cover_mode.findData(form.get('cover_mode'))))
        self.art_prompt.setPlainText(form.get('art_prompt') or kit_settings.default_prompt())
        spend = {**kit_spend.DEFAULTS, **{k: form[k] for k in kit_settings.SPEND_KEYS
                                          if form.get(k) is not None}}
        self.monthly_cap.setValue(float(spend['monthly_cap_usd']))
        self.max_images.setValue(int(spend['max_images_per_run']))
        self.kits_root.setText(form.get('dropbox_root') or '')
        self.set_categories(form.get('categories'), form.get('scan_folders') or [])
        self.loops_dirs.setText(', '.join(form.get('loops_dirs') or []))
        self.ignore_names.setText(', '.join(form.get('ignore_names') or []))
        self.scan_depth.setValue(int(form.get('scan_max_depth') or kit_source.DEFAULT_MAX_DEPTH))
        self._refresh_seo_genres()
        self.refresh_connections()

    def set_kits(self, kits):
        self.table.setRowCount(0)
        for kit in kits or []:
            self.add_kit_row(kit)

    def _refresh_folders(self):
        folders = kit_settings.reference_folders(
            self.refs_root.text().strip(), kit_settings.parse_genres(self.genres.toPlainText()))
        self.ref_folders.setText('\n'.join(folders) if folders else '(sin carpeta de referencias)')

    def serialize(self):
        """Valida todo y devuelve ``(catalogo, ajustes)``; SettingsError si algo está mal."""
        settings = kit_settings.validate_settings(self.form_values())
        rows = kit_settings.prune_blank(self.kit_rows())
        catalog = kit_settings.validate_kits(rows, settings['genres'])
        return catalog, settings

    # --- Dropbox (en hilo aparte) ---

    def _busy(self, on):
        widgets = [self.btn_reload, self.btn_save, self.btn_state, self.btn_dry, self.btn_new,
                   self.automation, self.btn_categories, self.btn_detect, self.btn_pick_root,
                   self.btn_pick_refs, self.save_publish_button,
                   self.sync_button, self.connect_youtube_button, self.dbx_start_button,
                   self.dbx_finish_button, self.save_telegram_button, self.test_telegram_button,
                   self.save_kit_notion_button, self.save_keys_button]
        for btn in widgets:
            btn.setEnabled(not on)
        if not on:
            self.refresh_connections()

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
        self.refresh_channel_chips()

    def ask_new_automation(self, on_result=None):
        """Pide el canal y lo crea. ``on_result(ok, texto)`` avisa el final (también si falla).

        Devuelve True si empezó a crearlo; False si no (cancelado, ocupado o error).
        """
        def fail(text):
            self._say(text, error=True)
            if on_result:
                on_result(False, text)
            return False
        if self._task is not None:
            return fail("Loop kits todavía está leyendo Dropbox. Probá de nuevo en unos segundos.")
        if self._registry_error:
            return fail(self._registry_error)
        try:
            names = kit_channel_setup.loop_kit_channels(
                kit_channel_setup.registry_config(self._registry), self._base_config)
        except channel_kind.ChannelKindError as exc:
            return fail(str(exc))
        taken = {self.automation.itemText(i) for i in range(1, self.automation.count())}
        name, ok = QInputDialog.getItem(
            self, "Crear automatización", "Canal de Loop kits:",
            [n for n in names if n not in taken], 0, True)
        name = (name or '').strip()
        if not ok:
            return False
        if not name:
            return fail("Escribí el nombre del canal de Loop kits.")
        if name in taken:
            return fail(f"«{name}» ya tiene automatización de Loop kits.")
        return self.create_automation(name, on_result)

    def create_automation(self, name, on_result=None):
        """Arma la config mínima del canal en Dropbox y lo deja elegido."""
        base = self._base_config
        registry, registry_rev = self._registry, self._registry_rev

        def work():
            dbx = self._dbx()
            if base is None:  # todavía no se leyó la config del canal por defecto
                default = kit_settings.load_all(dbx)['config']
            else:
                default = base
            known = channel_kind.find(registry, name)
            if known is not None and known.get('tipo') != channel_kind.LOOPS:
                raise kit_channel_setup.ChannelSetupError(
                    "Ese canal es de Beats en el registro: no puede tener automatización de kits.")
            if known is None:
                # Canal nuevo: primero su ficha en el registro (tipo loops, inmutable).
                mine = copy.deepcopy(registry)
                mine['canales'].append(cloud_registry.new_channel(
                    channel_kind.LOOPS, kit_channel.slug(name), name))
                cloud_registry.save_with_dbx('canales', mine, registry, registry_rev, dbx)
            fresh, _rev = cloud_registry.read_with_dbx('canales', dbx)
            local = kit_channel_setup.registry_config(fresh)
            created = kit_channel_setup.create(name, default, local, dbx)
            return created, kit_channel_setup.load_registry(dbx)

        def done(result):
            created, registry = result
            self._set_automations(registry, select=created.slug)
            self.reload(note="Automatización creada. Falta conectar su YouTube (Conexiones de este "
                             "canal) y activarlo en «Mis canales». Telegram y Dropbox del robot "
                             "son los mismos de todos los canales.")
            if on_result:
                on_result(True, name)

        def failed(text):
            if on_result:
                on_result(False, text)

        return self._run(work, done, "Creando la automatización…", failed)

    def _run(self, fn, on_done, message, on_error=None):
        if self._task is not None:
            if on_error:
                on_error("Loop kits está ocupado. Probá de nuevo en unos segundos.")
            return False
        self._busy(True)
        self._say(message)
        task = _Task(fn, self)
        task.done.connect(lambda result: self._finish(task, on_done, result))
        task.failed.connect(lambda text: self._finish(task, None, None, text, on_error))
        self._task = task
        task.start()
        return True

    def _finish(self, task, on_done, result, error=None, on_error=None):
        if task is not self._task:
            # El panel se cerró (shutdown) mientras la tarea corría: esta señal llega tarde,
            # cuando el hilo y los widgets ya no existen. No hay nada que actualizar.
            return
        task.wait()
        task.deleteLater()
        self._task = None
        self._busy(False)
        if error:
            self._say(error, error=True)
            self.wizard_notify(False, error)
            if on_error:
                on_error(error)
        elif on_done:
            on_done(result)

    def _say(self, text, error=False):
        self.status.setText(text)
        theme.tone(self.status, 'error' if error else 'muted')

    def reload(self, note=None):
        paths = self.paths()

        def work():
            dbx = self._dbx()
            data = kit_settings.load_all(dbx, None if paths.is_default else paths)
            data['registry'] = kit_channel_setup.load_registry(dbx)
            # El registro roto no impide editar kits: se avisa y se bloquea el alta de canales.
            try:
                data['canales'], data['canales_rev'] = cloud_registry.read_with_dbx('canales', dbx)
                data['canales_error'] = None
            except Exception as exc:  # noqa: BLE001 - se informa en la barra de estado
                data['canales'], data['canales_rev'] = cloud_registry.empty('canales'), None
                data['canales_error'] = f"Registro de canales ilegible: {_error_text(exc)}"
            # Un canal sin section es un error explícito: falla la lectura, no la app.
            data['form'] = kit_settings.form_from_config(data['config'])
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
        self._kits_base = copy.deepcopy(data['kits'])
        self._config_base, self._config_rev = copy.deepcopy(data['config']), data['config_rev']
        self._registry, self._registry_rev = data['canales'], data['canales_rev']
        self._registry_error = data.get('canales_error')
        self._set_automations(data['registry'])
        if not data['own']:
            self._base_config = data['config']
        kit = (data.get('config') or {}).get('kit_preview') if isinstance(data.get('config'), dict) else None
        # La misma edad que usa el worker (default 10 si la config no la trae o es inválida).
        self._trends_max_age = kit_trends.settings(kit if isinstance(kit, dict) else {})['max_age_days']
        self.set_form({**data['form'], 'categories': data['categories']})
        # Un canal con automatización propia no puede apuntar a otro canal.
        self.channel.setEnabled(not data['own'])
        self.set_kits(data['kits'])
        self.seo_report_box.refresh()
        if self._registry_error:
            self._say(self._registry_error, error=True)
            return
        self._say(note or "Configuración cargada." if data['config'] is not None else
                  "No hay config del worker en Dropbox: se pueden editar los kits, pero no "
                  "los ajustes hasta subirla (docs/KIT_WEEKLY.md).",
                  error=data['config'] is None)

    def save(self):
        try:
            catalog, settings = self.serialize()
        except kit_settings.SettingsError as exc:
            self._say(str(exc), error=True)
            self.wizard_notify(False, str(exc))
            return False
        # Las filas vacías ya no están en el catálogo: se reflejan en la tabla.
        self.set_kits(catalog)
        rev, kits_base = self._kits_rev, self._kits_base
        config_base, config_rev = self._config_base, self._config_rev
        paths = self.paths()
        slug_key = self.automation.currentData() or ''  # misma clave que wizard_target
        paths = None if paths.is_default else paths
        notes = kit_settings.seo_notes(settings.get('seo'))

        def work():
            dbx, problems = self._dbx(), []
            saved = {'kits': (kits_base, rev), 'config': (config_base, config_rev)}
            for label, key, op in (
                    ("kits", 'kits', lambda: kit_settings.save_kits_merged(
                        catalog, kits_base, rev, dbx, paths)),
                    ("ajustes", 'config', lambda: kit_settings.save_config_merged(
                        settings, config_base, config_rev, dbx, paths))):
                try:
                    saved[key] = op()
                except cloud_merge.MergeConflict as exc:
                    routes = ', '.join(c['ruta'] for c in exc.choques[:5])
                    problems.append(f"{label}: otra PC cambió lo mismo ({routes}); recargá.")
                except kit_cloud.KitCloudConflict:
                    problems.append(f"{label}: cambió desde otro lado; recargá y repetí.")
                except Exception as exc:  # noqa: BLE001
                    problems.append(f"{label}: {_error_text(exc)}")
            return problems, saved

        def done(result):
            # Si algo no se guardó quedan su base y rev viejos: repetir sin recargar no pisa.
            problems, saved = result
            self._kits_base, self._kits_rev = copy.deepcopy(saved['kits'][0]), saved['kits'][1]
            self._config_base = copy.deepcopy(saved['config'][0])
            self._config_rev = saved['config'][1]
            lines = list(notes)
            if isinstance(saved['kits'][0], list) and saved['kits'][0] != catalog:
                self.set_kits(saved['kits'][0])  # se sumaron cambios de otra PC
                lines.append("Se fusionaron cambios de otra PC en los kits.")
            self._say(" ".join(["Guardado en Dropbox."] + lines) if not problems else
                      "No se guardó todo — " + " ".join(problems), error=bool(problems))
            if not problems:
                self.pilot_flag_set(slug_key, 'config')  # flag del asistente de alta
            self.wizard_notify(not problems, '' if not problems else ' '.join(problems))

        self._run(work, done, "Guardando en Dropbox…")
        return True

    # --- Carpeta de kits ---

    def pick_dropbox_folder(self, field):
        """Elige una carpeta de Dropbox con clics y la escribe en ``field``.

        En la carpeta raíz de kits, después lee sus categorías solo. Las referencias vacías
        abren en la carpeta estándar (``dropbox_layout.KITS_REFS_DIR``).
        """
        if self._task is not None:
            return
        current = field.text().strip()
        if not current and field is self.refs_root:
            current = dropbox_layout.KITS_REFS_DIR  # la carpeta estándar: un clic y listo
        picker = _picker(self, current)
        if picker.exec_() == QDialog.Accepted and picker.selected_path:
            field.setText(picker.selected_path)
            if field is self.kits_root:
                self.read_categories()
        picker.deleteLater()

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
        cap = self.monthly_cap.value()

        def done(state):
            self.output.setPlainText('\n'.join(kit_settings.last_state_lines(state, cap=cap)))
            self._say("Estado leído.")
        path = self.paths().state
        self._run(lambda: kit_state.load(path, dbx=self._dbx()), done, "Leyendo el estado…")

    def shutdown(self):
        """Espera la tarea en curso y corta el dry-run antes de destruir el panel."""
        self.stop_connections()  # OAuth o gh en curso: se sueltan sin esperar
        if self._proc is not None:
            self._proc.kill()
            self._proc.waitForFinished(3000)
            self._proc = None  # sus señales tardías no deben tocar widgets ya destruidos
        if self._task is not None:
            self._task.wait()
            self._task = None  # _finish ignora la señal pendiente de esta tarea

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
        self._dry_key = self.automation.currentData() or ''
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
        if code == 0:
            self.pilot_flag_set(self._dry_key, 'dryrun')
        self._say("Dry-run terminado." if code == 0 else
                  "El dry-run falló; revisá el detalle de abajo.", error=code != 0)


def open_loop_kit_panel(parent=None):
    """Abre el panel en un diálogo y carga lo guardado en Dropbox."""
    dialog = QDialog(parent)
    dialog.setWindowTitle('Configuración de automatización')
    dialog.resize(820, 760)
    lay = QVBoxLayout(dialog)
    panel = LoopKitPanel(dialog)
    lay.addWidget(panel)
    panel.reload()
    dialog.exec_()
    panel.shutdown()
    return panel
