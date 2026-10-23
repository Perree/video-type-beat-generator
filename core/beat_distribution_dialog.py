"""Two-step, offline scheduling guide; acceptance only changes the panel draft."""
from copy import deepcopy

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QCheckBox, QDialog, QFormLayout, QHBoxLayout, QLabel,
                             QPlainTextEdit, QPushButton, QSpinBox, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView)
from core.beat_distribution import distribute, recommend_counts
from core.wizard import Wizard, WizardPage

DAYS = ('Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom')


class DistributionDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Distribuir publicaciones de Beats')
        self.resize(850, 680)
        self.original = deepcopy(config)
        self.result_config = None
        self.rows = {}
        options = QWidget()
        layout = QVBoxLayout(options)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(('Canal activo', 'Conservar horarios', 'Videos / semana'))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        for ch in config['channels']:
            if not ch['active']:
                continue
            i = self.table.rowCount()
            self.table.insertRow(i)
            item = QTableWidgetItem(ch['id'])
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(i, 0, item)
            fixed, count = QCheckBox(), QSpinBox()
            fixed.setChecked(True)
            count.setRange(1, 7)
            count.setValue(min(7, len(ch['slots'])))
            count.setEnabled(False)
            fixed.toggled.connect(lambda on, spin=count: spin.setEnabled(not on))
            self.table.setCellWidget(i, 1, fixed)
            self.table.setCellWidget(i, 2, count)
            self.rows[ch['id']] = fixed, count
        layout.addWidget(self.table)
        form = QFormLayout()
        self.ceiling = QSpinBox()
        self.ceiling.setRange(1, 6)
        self.ceiling.setValue(6)
        form.addRow('Tope diario para esta propuesta:', self.ceiling)
        reserve_row = QHBoxLayout()
        self.external = []
        for day in DAYS:
            reserve_row.addWidget(QLabel(day))
            spin = QSpinBox()
            spin.setRange(0, 6)
            self.external.append(spin)
            reserve_row.addWidget(spin)
        form.addRow('Reservas externas por día:', reserve_row)
        layout.addLayout(form)
        note = QLabel('Si ey mat está en la tabla, dejalo fijo. Si publica desde Loop kits u otra app, '
                      'reservá su cantidad los lunes y jueves arriba, sin contarlo dos veces. '
                      'Las reservas son solo para esta propuesta; no coordinan otros workers.')
        note.setWordWrap(True)
        layout.addWidget(note)
        sources = QLabel('<a href="https://developers.google.com/youtube/data/determine_quota_cost">'
                         'Cuotas oficiales</a> · '
                         '<a href="https://support.google.com/youtube/answer/2801973">Política de spam</a>')
        sources.setOpenExternalLinks(True)
        layout.addWidget(sources)
        button = QPushButton('Recomendar frecuencias según capacidad y prioridad')
        button.clicked.connect(self.recommend)
        layout.addWidget(button)
        self.message = QLabel()
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        preview = QWidget()
        preview_layout = QVBoxLayout(preview)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        preview_layout.addWidget(self.preview)
        self.wizard = Wizard('Distribución semanal', [
            WizardPage('1. Elegí qué se puede cambiar',
                       'Destildá «Conservar horarios» solo en los canales que querés redistribuir. '
                       'Elegí de 1 a 7 videos por semana: 7 significa diario. '
                       'Con dos o tres por semana los días serán fijos, no intervalos exactos de 48/72 horas.',
                       options, on_next=self.calculate),
            WizardPage('2. Revisá la propuesta',
                       'La propuesta equilibra la carga y separa los días cuando hay capacidad. '
                       'Aplicar cambia el borrador: después usá «Guardar cambios». '
                       'Los videos ya reservados o programados conservan su fecha.',
                       preview, next_text='Aplicar al borrador', on_next=self.apply),
        ], self)
        self.wizard.cancelled.connect(self.reject)
        QVBoxLayout(self).addWidget(self.wizard)

    def values(self):
        fixed = {cid for cid, (check, _) in self.rows.items() if check.isChecked()}
        counts = {cid: spin.value() for cid, (check, spin) in self.rows.items() if not check.isChecked()}
        return fixed, counts, [spin.value() for spin in self.external], self.ceiling.value()

    def recommend(self):
        fixed, _, external, ceiling = self.values()
        try:
            counts = recommend_counts(self.original, fixed, external, ceiling)
        except ValueError as exc:
            self.message.setText(str(exc))
            return
        for cid, count in counts.items():
            self.rows[cid][1].setValue(count)
        self.message.setText('Frecuencias sugeridas; podés ajustarlas antes de ver la propuesta.' if counts
                             else 'Todos los horarios están fijos. Destildá los que quieras redistribuir.')

    def calculate(self):
        fixed, counts, external, ceiling = self.values()
        self.result_config = None
        try:
            result, loads = distribute(self.original, counts, fixed, external, ceiling)
        except ValueError as exc:
            self.message.setText(str(exc))
            return False
        self.result_config = result
        lines = ['Carga por día (incluye reservas externas):',
                 ' · '.join(f'{day}: {n}/{ceiling}' for day, n in zip(DAYS, loads)), '']
        for ch in result['channels']:
            slots = ', '.join(f'{DAYS[s["weekday"]]} {s["hour"]:02d}:{s["minute"]:02d}' for s in ch['slots'])
            label = 'pausado, sin cambios' if not ch['active'] else ('fijo' if ch['id'] in fixed else 'propuesto')
            lines.append(f'{ch["id"]} ({label}): {slots}')
        lines += ['', 'El tope de seis es una política local, no una garantía contra bloqueos de YouTube.',
                  'La cuota real se verifica por proyecto en Google Cloud. Subir y publicar son fechas distintas.',
                  'No repitas el mismo contenido entre canales; cambiar título o imagen no garantiza evitar spam.',
                  'Usá contenido propio o autorizado y metadatos fieles. Esta guía no evalúa derechos ni spam.']
        self.preview.setPlainText('\n'.join(lines))
        return True

    def apply(self):
        if self.result_config is None:
            return False
        self.accept()
        return False


def open_distribution(panel):
    if panel.task is not None or not panel.config_readable:
        panel.status.setText('Esperá a que termine la carga de configuración de Beats.')
        return
    panel._store_editor()
    before = deepcopy(panel.config)
    dialog = DistributionDialog(before, panel)
    try:
        if dialog.exec_() != QDialog.Accepted or dialog.result_config is None:
            return
        # A deferred reload or another editor must never be silently overwritten.
        if panel.task is not None or panel.config != before or not panel.config_readable:
            panel.status.setText('La configuración cambió. Abrí nuevamente el asistente de distribución.')
            return
        selected = panel.selected
        panel.config = deepcopy(dialog.result_config)
        # _refresh_list calls _select: do not store the old editor over the new slots.
        panel.selected = -1
        panel._refresh_list(selected)
        panel.status.setText('Distribución aplicada al borrador. Revisá y guardá los cambios en Dropbox.')
    finally:
        dialog.deleteLater()
