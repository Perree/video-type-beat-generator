# -*- coding: utf-8 -*-
"""«Mis canales automatizados»: una tarjeta por canal, con lo justo para administrarlos.

Beats: pausar/reanudar, cambiar horario, quitar, agregar y «Guardar cambios», todo sobre el mismo
modelo del panel de Beats (``BeatPanel.config``) y con su mismo guardado (CAS + merge con la otra
PC). Loop kits: salud del canal y acceso directo a su pestaña (el robot de kits no tiene «pausa»).
Las pestañas técnicas quedan en «Modo avanzado».
"""
from PyQt5.QtCore import Qt, QTime, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                             QMessageBox, QPushButton, QScrollArea, QTimeEdit, QVBoxLayout, QWidget)

from core.guide_panel import GuideStep
from ui_theme import ACCENT_GENERATE, ACCENT_GENERATE_HOVER

DAYS = ('Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo')
SHORT = ('Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom')
_CARD = ('QFrame#channel {{ border: 1px solid {border}; border-radius: 10px; background: #333; }}'
         ' QFrame#channel QLabel {{ border: none; background: transparent; }}')
_SAVE = (f'QPushButton {{ background: {ACCENT_GENERATE}; color: white; font-weight: bold; padding: 10px 22px; }}'
         f' QPushButton:hover {{ background: {ACCENT_GENERATE_HOVER}; }}')


def schedule_text(slots):
    """``[{weekday, hour, minute}]`` → «Lun, Jue · 18:00» (agrupa por hora)."""
    if not slots:
        return 'Sin horario'
    by_time = {}
    for slot in sorted(slots, key=lambda s: (s['weekday'], s['hour'], s['minute'])):
        by_time.setdefault((slot['hour'], slot['minute']), []).append(slot['weekday'])
    parts = []
    for (hour, minute), days in sorted(by_time.items()):
        names = 'Todos los días' if sorted(set(days)) == list(range(7)) else ', '.join(SHORT[d] for d in days)
        parts.append(f'{names} · {hour:02d}:{minute:02d}')
    return '  |  '.join(parts)


def health_text(chip):
    """Chip del asistente de alta («◐ 1/5», «✔ Listo») → frase simple."""
    if chip.startswith('✔'):
        return '✔ Listo para publicar'
    try:
        done, total = (int(x) for x in chip.split()[-1].split('/'))
    except ValueError:
        return f'Configuración: {chip}'
    return f'Faltan {total - done} de {total} pasos para publicar'


class ScheduleDialog(QDialog):
    """Días tildados + una hora para todos (lo común). Devuelve slots con ``slots()``."""

    def __init__(self, name, slots, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Horario — {name}')
        self.setStyleSheet('QDialog { background-color: #2b2b2b; }')
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel('¿Qué días publica?'))
        grid = QGridLayout()
        days = {s['weekday'] for s in slots}
        self.checks = []
        for index, day in enumerate(DAYS):
            check = QCheckBox(day)
            check.setChecked(index in days)
            self.checks.append(check)
            grid.addWidget(check, index // 4, index % 4)
        layout.addLayout(grid)
        row = QHBoxLayout()
        row.addWidget(QLabel('¿A qué hora? (hora de Argentina)'))
        self.time = QTimeEdit()
        self.time.setDisplayFormat('HH:mm')
        first = slots[0] if slots else {'hour': 18, 'minute': 0}
        self.time.setTime(QTime(first['hour'], first['minute']))
        row.addWidget(self.time)
        row.addStretch()
        layout.addLayout(row)
        if len({(s['hour'], s['minute']) for s in slots}) > 1:
            note = QLabel('Ahora tiene horas distintas según el día: al guardar, todos los días usan esta hora.')
            note.setWordWrap(True)
            note.setStyleSheet('color: #f1c40f;')
            layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('Listo')
        buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def slots(self):
        time = self.time.time()
        return [{'weekday': i, 'hour': time.hour(), 'minute': time.minute()}
                for i, check in enumerate(self.checks) if check.isChecked()]

    def _accept(self):
        if not self.slots():
            QMessageBox.warning(self, 'Horario', 'Elegí al menos un día.')
            return
        self.accept()


class BeatCard(QFrame):
    def __init__(self, view, index, channel, parent=None):
        super().__init__(parent)
        self.setObjectName('channel')
        self.view, self.index = view, index
        slug = channel.get('actions_slug', '') or ''
        chip, color = view.beat_panel.channel_chip(channel['id'], slug, channel['id'])
        ready = chip.startswith('✔')
        self.setStyleSheet(_CARD.format(border='#2ecc71' if ready and channel['active'] else '#555'))
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel(f'<b style="font-size:15px">{channel["id"]}</b>  <span style="color:#bbb">🎵 Beats</span>'), 1)
        self.active = QCheckBox('Activa' if channel['active'] else 'Pausada')
        self.active.setChecked(channel['active'])
        self.active.setToolTip('Destildá para pausarla sin borrarla.')
        self.active.toggled.connect(lambda on: view.set_active(index, on))
        top.addWidget(self.active)
        layout.addLayout(top)
        row = QHBoxLayout()
        row.addWidget(QLabel(f'🕒 {schedule_text(channel.get("slots", []))}'), 1)
        self.btn_schedule = QPushButton('Cambiar horario')
        self.btn_schedule.clicked.connect(lambda: view.edit_schedule(index))
        row.addWidget(self.btn_schedule)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel(f'<span style="color:{color}">{health_text(chip)}</span>'), 1)
        if not ready:
            fix = QPushButton('Arreglar')
            fix.setToolTip('Abre el asistente de alta de este canal: te dice qué falta y cómo resolverlo.')
            fix.clicked.connect(lambda: view.fix(index))
            row.addWidget(fix)
        remove = QPushButton('Quitar')
        remove.clicked.connect(lambda: view.remove(index))
        row.addWidget(remove)
        layout.addLayout(row)


class KitCard(QFrame):
    def __init__(self, view, name, slug, parent=None):
        super().__init__(parent)
        self.setObjectName('channel')
        chip, color = view.kit_panel.channel_chip(name, slug, slug)
        ready = chip.startswith('✔')
        self.setStyleSheet(_CARD.format(border='#2ecc71' if ready else '#555'))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f'<b style="font-size:15px">{name}</b>  <span style="color:#bbb">📦 Loop kits</span>'))
        row = QHBoxLayout()
        row.addWidget(QLabel(f'<span style="color:{color}">{health_text(chip)}</span>'), 1)
        button = QPushButton('Editar horario y estilo')
        button.clicked.connect(lambda: view.open_kit(slug))
        row.addWidget(button)
        layout.addLayout(row)


class MyChannelsView(QWidget):
    connections_requested = pyqtSignal()
    advanced_requested = pyqtSignal()   # pestañas técnicas (Beats / Loop kits)

    def __init__(self, beat_panel, kit_panel, open_kit=None, ensure_kits=None, parent=None):
        super().__init__(parent)
        self.beat_panel, self.kit_panel = beat_panel, kit_panel
        self._open_kit, self._ensure_kits = open_kit, ensure_kits
        self.dirty = False
        self.saving = False
        self._signature = None
        layout = QVBoxLayout(self)
        head = QHBoxLayout()
        title = QLabel('Mis canales automatizados')
        title.setStyleSheet('font-size: 22px; font-weight: bold;')
        head.addWidget(title, 1)
        self.btn_add = QPushButton('+ Agregar canal')
        self.btn_add.clicked.connect(self.add)
        self.btn_reload = QPushButton('🔄 Recargar')
        self.btn_reload.clicked.connect(self.reload)
        self.btn_advanced = QPushButton('Modo avanzado')
        self.btn_advanced.setToolTip('Las pestañas completas de Beats y Loop kits.')
        self.btn_advanced.clicked.connect(self.advanced_requested)
        for button in (self.btn_add, self.btn_reload, self.btn_advanced):
            head.addWidget(button)
        layout.addLayout(head)

        self.blocked = QFrame()
        blocked = QVBoxLayout(self.blocked)
        self.blocked_text = QLabel()
        self.blocked_text.setWordWrap(True)
        self.blocked_text.setStyleSheet('font-size: 14px;')
        blocked.addWidget(self.blocked_text)
        go = QPushButton('🔌 Ir a Conexiones')
        go.clicked.connect(self.connections_requested)
        blocked.addWidget(go, 0, Qt.AlignLeft)
        layout.addWidget(self.blocked)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet('QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }')
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.body)
        layout.addWidget(scroll, 1)

        bar = QHBoxLayout()
        self.status = QLabel()
        self.status.setWordWrap(True)
        bar.addWidget(self.status, 1)
        self.btn_save = QPushButton('💾 Guardar cambios')
        self.btn_save.setStyleSheet(_SAVE)
        self.btn_save.clicked.connect(self.save)
        bar.addWidget(self.btn_save)
        layout.addLayout(bar)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.tick)
        self.rebuild()

    # --- Estado ---

    def beats_loaded(self):
        panel = self.beat_panel
        return bool(getattr(panel, 'cloud_loaded', False)) and bool(getattr(panel, 'config_readable', False))

    def channels(self):
        return self.beat_panel.config.get('channels', []) if self.beats_loaded() else []

    def kits(self):
        combo = getattr(self.kit_panel, 'automation', None)
        if combo is None:
            return []
        return [(combo.itemText(i), combo.itemData(i) or '') for i in range(combo.count())]

    def blocked_reason(self):
        panel = self.beat_panel
        if panel.task is not None and not self.saving:
            return 'Leyendo tus canales de Dropbox…'
        if not self.beats_loaded():
            return ('No se pudieron leer tus canales automatizados. Lo más común: Dropbox no está conectado en '
                    'esta PC o falta «Preparar la nube». Resolvelo en Conexiones y tocá «Recargar».')
        if getattr(panel, 'registry_rev', None) is None:
            return ('Falta «Preparar la nube» (una sola vez): crea la lista de canales en Dropbox. '
                    'Está en Conexiones.')
        return ''

    def tick(self):
        if self.saving and self.beat_panel.task is None:
            self.saving = False
            ok = self.beats_loaded()
            self.dirty = not ok
            self.status.setText('✓ Cambios guardados. El robot ya usa la configuración nueva.' if ok
                                else f'✗ {self.beat_panel.status.text()}')
            self._signature = None
        signature = (self.blocked_reason(), repr(self.channels()), tuple(self.kits()), self.dirty, self.saving)
        if signature != self._signature:
            self.rebuild()

    def rebuild(self):
        self._signature = (self.blocked_reason(), repr(self.channels()), tuple(self.kits()), self.dirty,
                           self.saving)
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        reason = self.blocked_reason()
        self.blocked_text.setText(reason)
        self.blocked.setVisible(bool(reason) and not self.saving)
        channels = self.channels()
        if channels or self.beats_loaded():
            self.body_layout.addWidget(self._heading(f'🎵 Beats ({len(channels)})'))
            for index, channel in enumerate(channels):
                self.body_layout.addWidget(BeatCard(self, index, channel))
            if not channels:
                self.body_layout.addWidget(QLabel('Todavía no hay canales de Beats. Tocá «+ Agregar canal».'))
        kits = self.kits()
        if kits:
            self.body_layout.addWidget(self._heading(f'📦 Loop kits ({len(kits)})'))
            for name, slug in kits:
                self.body_layout.addWidget(KitCard(self, name, slug))
        busy = self.beat_panel.task is not None
        self.btn_save.setVisible(self.dirty or self.saving)
        self.btn_save.setEnabled(self.dirty and not busy)
        self.btn_save.setText('Guardando…' if self.saving else '💾 Guardar cambios')
        self.btn_add.setEnabled(self.beats_loaded() and not busy)
        if self.dirty and not self.saving:
            self.status.setText('Tenés cambios sin guardar: tocá «Guardar cambios» para que el robot los use.')
        elif not self.saving and not self.status.text().startswith(('✓', '✗')):
            self.status.setText('')

    def _heading(self, text):
        label = QLabel(text)
        label.setStyleSheet('font-size: 15px; font-weight: bold; color: #ddd; margin-top: 6px;')
        return label

    # --- Acciones de Beats (sobre el modelo del panel) ---

    def _edit(self, change):
        panel = self.beat_panel
        panel._store_editor()  # lo que haya en el formulario del panel no se pierde
        change(panel.config['channels'])
        rows = len(panel.config['channels'])
        panel._refresh_list(max(0, min(panel.selected, rows - 1)) if rows else 0)
        self.dirty = True
        self.status.setText('')
        self.rebuild()

    def set_active(self, index, on):
        self._edit(lambda channels: channels[index].update(active=bool(on)))

    def edit_schedule(self, index):
        channel = self.channels()[index]
        dialog = ScheduleDialog(channel['id'], channel.get('slots', []), self)
        if dialog.exec_():
            slots = dialog.slots()
            self._edit(lambda channels: channels[index].update(slots=slots))

    def remove(self, index):
        name = self.channels()[index]['id']
        if QMessageBox.question(self, 'Quitar canal', f'¿Quitar la automatización de «{name}»? El robot deja de '
                                'publicar en ese canal cuando guardes. No se borra nada de YouTube.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            self._edit(lambda channels: channels.pop(index))

    def add(self):
        panel = self.beat_panel
        before = len(panel.config.get('channels', []))
        panel.add_channel()  # elige un canal libre del registro o pide el nombre de uno nuevo
        if len(panel.config['channels']) > before:
            self.dirty = True
            self.rebuild()
            self.fix(len(panel.config['channels']) - 1)

    def fix(self, index):
        """Selecciona el canal en el panel y abre su asistente de alta (dice qué falta)."""
        panel = self.beat_panel
        panel.automations.setCurrentRow(index)
        panel.open_wizard_clicked()

    def save(self):
        if not self.dirty or self.beat_panel.task is not None:
            return
        if self.beat_panel.save_and_publish() is not False:
            self.saving = True
            self.status.setText('Guardando en Dropbox…')
        else:
            self.status.setText(f'✗ {self.beat_panel.status.text()}')
        self.rebuild()

    def reload(self):
        if self.dirty and QMessageBox.question(
                self, 'Recargar', 'Tenés cambios sin guardar. ¿Descartarlos y recargar?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.dirty = False
        self.status.setText('')
        self.beat_panel.request_reload()
        if self._ensure_kits:
            self._ensure_kits(force=True)
        self.rebuild()

    def open_kit(self, slug):
        if self._open_kit:
            self._open_kit(slug)

    # --- Pantalla ---

    def showEvent(self, event):
        if self._ensure_kits:
            self._ensure_kits()
        self.timer.start()
        self.tick()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def guide(self):
        return ('Mis canales automatizados',
                'Cada tarjeta es un canal que el robot publica solo. Los cambios se aplican cuando tocás «Guardar '
                'cambios».',
                [GuideStep('Tener las conexiones listas', 'Si no ves tus canales, completá Conexiones.',
                           done=lambda: self.beats_loaded() and not self.blocked_reason(),
                           action=self.connections_requested.emit, action_text='Ir a Conexiones'),
                 GuideStep('Pausar o reanudar', 'Destildá «Activa» para pausar un canal sin borrarlo.'),
                 GuideStep('Cambiar el horario', '«Cambiar horario»: elegís días y hora.'),
                 GuideStep('Arreglar lo que falta', 'Si un canal no dice «✔ Listo», tocá «Arreglar».'),
                 GuideStep('Guardar', 'Hasta que no guardes, el robot sigue con lo anterior.',
                           done=lambda: not self.dirty, action=self.save, action_text='Guardar cambios')])
