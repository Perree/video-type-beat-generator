"""Read-only Qt model: large simulations do not allocate one widget per cell."""
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, Qt


class BeatJobModel(QAbstractTableModel):
    keys = ("slot", "channel", "track_id", "cycle")
    headers = ("Publicación (Buenos Aires)", "Canal", "Track ID", "Ciclo")

    def __init__(self, parent=None):
        super().__init__(parent)
        self.jobs = []

    def set_jobs(self, jobs):
        self.beginResetModel()
        self.jobs = sorted(jobs, key=lambda j: (j["slot"], j["channel"]))
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.jobs)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.keys)

    def data(self, index, role=Qt.DisplayRole):
        if (role == Qt.DisplayRole and index.isValid()
                and 0 <= index.row() < len(self.jobs) and 0 <= index.column() < len(self.keys)):
            return str(self.jobs[index.row()][self.keys[index.column()]])

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal and 0 <= section < len(self.headers):
                return self.headers[section]
            if orientation == Qt.Vertical:
                return section + 1
