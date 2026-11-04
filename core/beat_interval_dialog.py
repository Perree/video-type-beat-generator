"""Small editor for the anchored interval used by a Beats channel."""
from PyQt5.QtCore import QDateTime
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QDateTimeEdit
from core.beat_schema import instant
from core.beat_interval import settings


def schedule_text(channel):
    days, anchor = settings(channel)
    return f'Cada {days} días · {anchor:%H:%M} (Argentina) · desde {anchor:%d/%m/%Y}'


class IntervalDialog(QDialog):
    def __init__(self, channel, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'Publicación — {channel["id"]}')
        days, anchor = settings(channel)
        layout = QFormLayout(self)
        self.days = QSpinBox()
        self.days.setRange(1, 30)
        self.days.setValue(days)
        layout.addRow('Cada cuántos días', self.days)
        self.anchor = QDateTimeEdit(QDateTime(anchor.replace(tzinfo=None)))
        self.anchor.setDisplayFormat('dd/MM/yyyy HH:mm')
        self.anchor.setCalendarPopup(True)
        layout.addRow('Fecha base y hora (Argentina)', self.anchor)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def value(self):
        from core.beat_schema import BA
        anchor = self.anchor.dateTime().toPyDateTime().replace(tzinfo=BA, second=0, microsecond=0)
        return {'days': self.days.value(), 'anchor': instant(anchor).isoformat()}
