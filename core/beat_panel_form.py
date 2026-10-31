"""Widget construction for the independent Beats automation panel."""
from PyQt5.QtCore import QTime, QRegularExpression
from PyQt5.QtGui import QRegularExpressionValidator
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit,
    QComboBox, QCheckBox, QPushButton, QLabel, QPlainTextEdit,
    QListWidget, QTableWidget, QHeaderView, QTimeEdit, QScrollArea,
    QAbstractItemView, QTableView, QTabWidget,
)
from core.beat_job_model import BeatJobModel
from core.beat_visual_form import BeatVisualForm
from core.beat_connections_form import BeatConnectionsForm
from core.automation_save_bar import AutomationSaveBar, BEATS_PILOT_REQUIRED
from core.seo_report_box import SeoReportBox
from core.seo_report_status import BEATS, local_status
from core import automation_status as status
import ui_theme as theme

DAYS = ("Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo")


class BeatPanelForm(BeatVisualForm, BeatConnectionsForm, AutomationSaveBar):
    def _build(self):
        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()

        connections = QWidget()
        conn_layout = QVBoxLayout(connections)
        self._build_connections(conn_layout)
        # Con scroll, como en Loop kits: sin él las filas se aplastaban en ventanas bajas.
        conn_scroll = QScrollArea()
        conn_scroll.setWidgetResizable(True)
        conn_scroll.setFrameShape(QScrollArea.NoFrame)
        conn_scroll.setWidget(connections)
        self.tabs.addTab(conn_scroll, "Conexiones")

        canal_scroll = QScrollArea()
        canal_scroll.setWidgetResizable(True)
        canal_scroll.setFrameShape(QScrollArea.NoFrame)
        canal_body = QWidget()
        canal_layout = QVBoxLayout(canal_body)
        canal_layout.setSpacing(theme.SPACE['s'])

        # Lista de canales y sus acciones.
        box, lay = theme.section("Canales automatizados")
        lay.addWidget(theme.muted(QLabel("Elegí un canal de la lista para editarlo abajo.")))
        self.automations = QListWidget()
        self.automations.setMaximumHeight(140)
        self.automations.currentRowChanged.connect(self._select)
        lay.addWidget(self.automations)
        self.add_button = QPushButton("+ Agregar canal")
        self.add_button.clicked.connect(self.add_channel)
        self.wizard_button = QPushButton("Asistente de alta…")
        self.wizard_button.clicked.connect(self.open_wizard_clicked)
        self.distribution_button = theme.flat(QPushButton('Distribuir publicaciones…'))
        from core.beat_distribution_dialog import open_distribution
        self.distribution_button.clicked.connect(lambda: open_distribution(self))
        self.remove_button = theme.danger(QPushButton("Quitar canal"))
        self.remove_button.clicked.connect(self.remove_channel)
        lay.addLayout(theme.button_row(self.add_button, self.wizard_button, self.distribution_button,
                                       None, self.remove_button, align=None))
        canal_layout.addWidget(box)

        # Formulario del canal elegido (se habilita al elegir uno).
        self.editor = QWidget()
        editor_col = QVBoxLayout(self.editor)
        editor_col.setContentsMargins(0, 0, 0, 0)
        editor_col.setSpacing(theme.SPACE['s'])
        box, editor_form = theme.section("Canal y horarios", form=True)
        self.channel = QComboBox()
        self.active = QCheckBox("Activa (publica sola)")
        self.priority = QLineEdit("0")
        self.priority.setValidator(QRegularExpressionValidator(QRegularExpression(r"-?\d*"), self.priority))
        self.genres, self.images = QLineEdit(), QLineEdit()
        self.genres.setPlaceholderText("Separados por comas")
        editor_form.addRow("Canal de YouTube", self.channel)
        self.channel.currentTextChanged.connect(lambda _t: self.refresh_publish_readiness())
        editor_form.addRow("Estado", self.active)
        editor_form.addRow("Géneros", self.genres)
        self.slots = QTableWidget(0, 2)
        self.slots.setHorizontalHeaderLabels(("Día", "Hora (Buenos Aires)"))
        self.slots.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.slots.verticalHeader().setVisible(False)
        self.slots.setMaximumHeight(180)
        editor_form.addRow("Horarios", self.slots)
        add_slot = theme.flat(QPushButton("+ Agregar horario"))
        add_slot.clicked.connect(lambda: self._add_slot())
        remove_slot = theme.flat(QPushButton("Quitar horario"))
        remove_slot.clicked.connect(lambda: self.slots.removeRow(self.slots.currentRow()))
        editor_form.addRow("", theme.button_row(add_slot, remove_slot))
        editor_col.addWidget(box)

        box, visual_form = theme.section("Fondo del video", form=True)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.images)
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self.browse_images)
        folder_row.addWidget(browse)
        visual_form.addRow("Carpeta de imágenes", folder_row)
        more = theme.Collapsible("Más opciones (prioridad, fragmentos y miniatura)")
        more_form = theme.form_layout()
        more.body.addLayout(more_form)
        more_form.addRow("Prioridad", self.priority)
        more_form.addRow("", theme.muted(QLabel("Con varios canales, publica primero el de número mayor.")))
        self._build_visual(visual_form, more_form)
        editor_col.addWidget(box)
        editor_col.addWidget(more)
        canal_layout.addWidget(self.editor)

        # Detectar géneros y tags desde BeatStars: poco usado, va plegado.
        beatstars = theme.Collapsible("Analizar un perfil de BeatStars")
        profile_form = theme.form_layout()
        self.profile = QLineEdit()
        self.profile.setPlaceholderText("https://www.beatstars.com/usuario")
        self.profile.textChanged.connect(self._profile_changed)
        profile_form.addRow("Perfil público", self.profile)
        beatstars.body.addLayout(profile_form)
        self.analyze_button = QPushButton("Analizar perfil")
        self.analyze_button.clicked.connect(self.analyze_profile)
        self.cancel_button = theme.flat(QPushButton("Cancelar"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        beatstars.body.addLayout(theme.button_row(self.analyze_button, self.cancel_button))
        canal_layout.addWidget(beatstars)
        canal_layout.addStretch(1)
        canal_scroll.setWidget(canal_body)
        canal_tab = QWidget()
        canal_tab_layout = QVBoxLayout(canal_tab)
        canal_tab_layout.setContentsMargins(0, 0, 0, 0)
        canal_tab_layout.addWidget(canal_scroll)
        self.tabs.addTab(canal_tab, "Canal")

        self.seo_editor = QWidget()
        seo_col = QVBoxLayout(self.seo_editor)
        box, seo_form = theme.section("Título, descripción y tags", form=True)
        self._build_seo(seo_form)
        seo_col.addWidget(box)
        # Informe de Claude Code: la clave es el id interno del canal (no el nombre de YouTube).
        self.seo_report_box = SeoReportBox(BEATS, lambda: {
            'key': self.channel.currentText(),
            'names': [s.strip() for s in self.tags.text().split(",") if s.strip()]})
        seo_col.addWidget(self.seo_report_box)
        seo_col.addStretch(1)
        self.channel.currentTextChanged.connect(lambda _t: self.seo_report_box.refresh())
        self.channel.currentTextChanged.connect(lambda _t: self.refresh_publish_readiness())
        self.tags.textChanged.connect(lambda _t: self.seo_report_box.refresh())
        seo_scroll = QScrollArea()
        seo_scroll.setWidgetResizable(True)
        seo_scroll.setFrameShape(QScrollArea.NoFrame)
        seo_scroll.setWidget(self.seo_editor)
        seo_tab = QWidget()
        seo_tab_layout = QVBoxLayout(seo_tab)
        seo_tab_layout.setContentsMargins(0, 0, 0, 0)
        seo_tab_layout.addWidget(seo_scroll)
        self.tabs.addTab(seo_tab, "SEO y tendencias")

        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        box, lay = theme.section("Estado del robot")
        self.quota = theme.muted(QLabel("Límite local: 6 intentos por día (incluye fallos); no es la cuota "
                                        "real de YouTube. Reserva: 14 días."))
        lay.addWidget(self.quota)
        self.state_button = QPushButton("Consultar estado en Dropbox")
        self.state_button.clicked.connect(self.read_state)
        self.cloud_reload_button = theme.flat(QPushButton('Recargar desde Dropbox'))
        self.cloud_reload_button.clicked.connect(self.reload_cloud_config)
        lay.addLayout(theme.button_row(self.state_button, self.cloud_reload_button))
        advanced_layout.addWidget(box)
        box, lay = theme.section("Prueba sin publicar")
        lay.addWidget(theme.muted(QLabel("Arma el plan de publicación sin subir nada a YouTube.")))
        self.remote = QCheckBox("Usar el estado consultado en la prueba")
        lay.addWidget(self.remote)
        self.simulate_button = QPushButton('Probar sin subir')
        self.simulate_button.clicked.connect(self.simulate)
        lay.addLayout(theme.button_row(self.simulate_button))
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setPlaceholderText("Acá aparece el resultado de la prueba.")
        lay.addWidget(self.output, 1)
        self.jobs = QTableView()
        self.job_model = BeatJobModel(self.jobs)
        self.jobs.setModel(self.job_model)
        self.jobs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.jobs.setEditTriggers(QAbstractItemView.NoEditTriggers)
        lay.addWidget(self.jobs, 1)
        advanced_layout.addWidget(box, 1)
        self.tabs.addTab(advanced, "Avanzado")

        outer.addWidget(self.tabs, 2)
        self._build_save_bar(outer)
        self.status = theme.muted(QLabel())
        outer.addWidget(self.status)

    def refresh_publish_readiness(self):
        """Checklist de piloto: YouTube/SEO del combo vivo; slug de la automatización en edición."""
        if not getattr(self, 'publish_checklist', None):
            return
        if getattr(self, 'selected', -1) < 0:
            self._refresh_publish_readiness([], status.MISSING, BEATS_PILOT_REQUIRED)
            return
        channel = self.channel.currentText()
        slug = self.config['channels'][self.selected].get('actions_slug', '') or ''
        items = status.readiness_beats(channel, slug)
        seo = local_status(BEATS, channel, notion_state=status.beat_notion_status())
        self._refresh_publish_readiness(items, seo['state'], BEATS_PILOT_REQUIRED)

    def _add_slot(self, spec=None):
        spec = spec or {"weekday": 0, "hour": 18, "minute": 0}
        row = self.slots.rowCount()
        self.slots.insertRow(row)
        day, time = QComboBox(), QTimeEdit()
        day.addItems(DAYS)
        day.setCurrentIndex(spec["weekday"])
        time.setDisplayFormat("HH:mm")
        time.setTime(QTime(spec["hour"], spec["minute"]))
        self.slots.setCellWidget(row, 0, day)
        self.slots.setCellWidget(row, 1, time)
