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
        canal_body = QWidget()
        canal_layout = QVBoxLayout(canal_body)
        profile_form = QFormLayout()
        self.profile = QLineEdit()
        self.profile.setPlaceholderText("https://www.beatstars.com/usuario")
        self.profile.textChanged.connect(self._profile_changed)
        profile_form.addRow("Perfil público BeatStars:", self.profile)
        canal_layout.addLayout(profile_form)
        row = QHBoxLayout()
        self.analyze_button = QPushButton("Analizar perfil")
        self.analyze_button.clicked.connect(self.analyze_profile)
        row.addWidget(self.analyze_button)
        self.cancel_button = QPushButton("Cancelar")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        row.addWidget(self.cancel_button)
        canal_layout.addLayout(row)

        self.automations = QListWidget()
        self.automations.setMaximumHeight(120)
        self.automations.currentRowChanged.connect(self._select)
        canal_layout.addWidget(QLabel("Automatizaciones de Beats"))
        canal_layout.addWidget(self.automations)
        row = QHBoxLayout()
        self.add_button = QPushButton("Agregar canal")
        self.add_button.clicked.connect(self.add_channel)
        self.remove_button = QPushButton("Quitar canal")
        self.remove_button.clicked.connect(self.remove_channel)
        self.wizard_button = QPushButton("Asistente de alta…")
        self.wizard_button.clicked.connect(self.open_wizard_clicked)
        row.addWidget(self.add_button)
        row.addWidget(self.remove_button)
        row.addWidget(self.wizard_button)
        canal_layout.addLayout(row)
        self.distribution_button = QPushButton('Distribuir publicaciones…')
        from core.beat_distribution_dialog import open_distribution
        self.distribution_button.clicked.connect(lambda: open_distribution(self))
        canal_layout.addWidget(self.distribution_button)

        self.editor = QWidget()
        editor_form = QFormLayout(self.editor)
        self.channel = QComboBox()
        self.active = QCheckBox("Activa")
        self.priority = QLineEdit("0")
        self.priority.setValidator(QRegularExpressionValidator(QRegularExpression(r"-?\d*"), self.priority))
        self.genres, self.images = QLineEdit(), QLineEdit()
        self.genres.setPlaceholderText("Separados por comas")
        editor_form.addRow("Canal de Beats:", self.channel)
        self.channel.currentTextChanged.connect(lambda _t: self.refresh_publish_readiness())
        editor_form.addRow("Estado:", self.active)
        editor_form.addRow("Prioridad (mayor primero):", self.priority)
        editor_form.addRow("Géneros:", self.genres)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.images)
        browse = QPushButton("Elegir…")
        browse.clicked.connect(self.browse_images)
        folder_row.addWidget(browse)
        editor_form.addRow("Carpeta de imágenes:", folder_row)
        self._build_visual(editor_form)
        self.slots = QTableWidget(0, 2)
        self.slots.setHorizontalHeaderLabels(("Día", "Hora Buenos Aires"))
        self.slots.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.slots.setMaximumHeight(180)
        editor_form.addRow("Horarios semanales:", self.slots)
        row = QHBoxLayout()
        add_slot = QPushButton("Agregar horario")
        add_slot.clicked.connect(lambda: self._add_slot())
        remove_slot = QPushButton("Quitar horario")
        remove_slot.clicked.connect(lambda: self.slots.removeRow(self.slots.currentRow()))
        row.addWidget(add_slot)
        row.addWidget(remove_slot)
        editor_form.addRow(row)
        canal_layout.addWidget(self.editor)
        canal_scroll.setWidget(canal_body)
        canal_tab = QWidget()
        canal_tab_layout = QVBoxLayout(canal_tab)
        canal_tab_layout.setContentsMargins(0, 0, 0, 0)
        canal_tab_layout.addWidget(canal_scroll)
        self.tabs.addTab(canal_tab, "Canal")

        self.seo_editor = QWidget()
        seo_form = QFormLayout(self.seo_editor)
        self._build_seo(seo_form)
        # Informe de Claude Code: la clave es el id interno del canal (no el nombre de YouTube).
        self.seo_report_box = SeoReportBox(BEATS, lambda: {
            'key': self.channel.currentText(),
            'names': [s.strip() for s in self.tags.text().split(",") if s.strip()]})
        seo_form.addRow(self.seo_report_box)
        self.channel.currentTextChanged.connect(lambda _t: self.seo_report_box.refresh())
        self.channel.currentTextChanged.connect(lambda _t: self.refresh_publish_readiness())
        self.tags.textChanged.connect(lambda _t: self.seo_report_box.refresh())
        seo_scroll = QScrollArea()
        seo_scroll.setWidgetResizable(True)
        seo_scroll.setWidget(self.seo_editor)
        seo_tab = QWidget()
        seo_tab_layout = QVBoxLayout(seo_tab)
        seo_tab_layout.setContentsMargins(0, 0, 0, 0)
        seo_tab_layout.addWidget(seo_scroll)
        self.tabs.addTab(seo_tab, "SEO y tendencias")

        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        self.quota = QLabel("Límite local de Beats: 6 intentos diarios (incluye fallos). "
                            "No representa la cuota real del proyecto en YouTube. Buffer: 14 días.")
        self.quota.setWordWrap(True)
        advanced_layout.addWidget(self.quota)
        row = QHBoxLayout()
        self.state_button = QPushButton("Consultar estado de Beats en Dropbox")
        self.state_button.clicked.connect(self.read_state)
        self.cloud_reload_button = QPushButton('Recargar desde Dropbox')
        self.cloud_reload_button.clicked.connect(self.reload_cloud_config)
        row.addWidget(self.state_button)
        row.addWidget(self.cloud_reload_button)
        advanced_layout.addLayout(row)
        self.remote = QCheckBox("Usar el estado consultado en la simulación")
        advanced_layout.addWidget(self.remote)
        self.simulate_button = QPushButton('Probar sin subir')
        self.simulate_button.clicked.connect(self.simulate)
        advanced_layout.addWidget(self.simulate_button)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        advanced_layout.addWidget(self.output, 1)
        self.jobs = QTableView()
        self.job_model = BeatJobModel(self.jobs)
        self.jobs.setModel(self.job_model)
        self.jobs.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.jobs.setEditTriggers(QAbstractItemView.NoEditTriggers)
        advanced_layout.addWidget(self.jobs, 1)
        self.tabs.addTab(advanced, "Avanzado")

        outer.addWidget(self.tabs, 2)
        self._build_save_bar(outer)
        self.status = QLabel()
        self.status.setWordWrap(True)
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
