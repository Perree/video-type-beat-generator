"""Independent Phase 3 UI for Type Beats (no rendering or publishing)."""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QDialog, QVBoxLayout, QFileDialog

from core import beat_settings
from core.beat_panel_form import BeatPanelForm
from core.beat_schema import BA, migrate
from core.beat_source import profile_username
from core.beat_tasks import BeatTask, analyze, checkpoint, load_state
from core.sections import SECTION_BEATS, channel_names_for_section

ROOT = Path(__file__).resolve().parents[1]


class BeatPanel(QWidget, BeatPanelForm):
    def __init__(self, parent=None, config_path=None, transport=None, state_reader=None):
        super().__init__(parent)
        self.config_path = Path(config_path or ROOT / "config/app_config.json")
        self.transport, self.state_reader = transport, state_reader
        self.task = None
        self.analysis = None
        self.state = None
        self.config = migrate({}, "config")
        self.selected = -1
        self.config_readable = True
        self._build()
        self.reload()

    def reload(self):
        try:
            app = beat_settings.read_app(self.config_path)
            self.config = beat_settings.settings(app)
            self.channel.clear()
            self.channel.addItems(channel_names_for_section(app.get("channels", {}), SECTION_BEATS))
            self.profile.setText(self.config.get("beatstars_profile_url", ""))
            self._refresh_list()
            self.config_readable = True
            self.status.setText("Configuración local. Analizá el perfil para simular; el estado remoto se consulta explícitamente.")
        except Exception:
            self.config_readable = False
            self.status.setText("No se pudo leer la configuración. No se sobrescribirá el archivo.")
            for widget in (self.save_button, self.add_button, self.remove_button,
                           self.simulate_button, self.automations, self.editor):
                widget.setEnabled(False)

    def _profile_changed(self):
        self.analysis = None
        self.job_model.set_jobs([])
        self.output.clear()

    def _refresh_list(self, selected=0):
        self.automations.blockSignals(True)
        self.automations.clear()
        for ch in self.config["channels"]:
            self.automations.addItem(f'{ch["id"]} — {"Activa" if ch["active"] else "Pausada"}')
        self.automations.setCurrentRow(selected)
        self.automations.blockSignals(False)
        self.selected = -1
        self._select(self.automations.currentRow())

    def _store_editor(self):
        if self.selected < 0:
            return
        ch = self.config["channels"][self.selected]
        self._store_visual(ch)
        try:
            priority = int(self.priority.text())
        except ValueError:
            priority = self.priority.text()  # preserve invalid drafts until validation
        ch.update(id=self.channel.currentText(), active=self.active.isChecked(),
                  priority=priority,
                  tags=[s.strip() for s in self.tags.text().split(",") if s.strip()],
                  selection_tags=[s.strip() for s in self.selection_tags.text().split(",") if s.strip()],
                  genres=[s.strip() for s in self.genres.text().split(",") if s.strip()],
                  images_folder=self.images.text().strip(),
                  slots=[{"weekday": self.slots.cellWidget(i, 0).currentIndex(),
                          "hour": self.slots.cellWidget(i, 1).time().hour(),
                          "minute": self.slots.cellWidget(i, 1).time().minute()}
                         for i in range(self.slots.rowCount())])
        self.automations.item(self.selected).setText(
            f'{ch["id"]} — {"Activa" if ch["active"] else "Pausada"}')

    def _select(self, index):
        self._store_editor()
        self.selected = index
        self.editor.setEnabled(index >= 0)
        if index < 0:
            return
        ch = self.config["channels"][index]
        # Retain an unavailable ID so it cannot silently become another channel.
        if self.channel.findText(ch["id"]) < 0:
            self.channel.addItem(ch["id"])
        self.channel.setCurrentText(ch["id"])
        self.active.setChecked(ch["active"])
        self.priority.setText(str(ch["priority"]))
        self.tags.setText(", ".join(ch.get("tags", [])))
        self.selection_tags.setText(", ".join(ch.get("selection_tags", [])))
        self.genres.setText(", ".join(ch.get("genres", [])))
        self.images.setText(ch.get("images_folder", ""))
        self._load_visual(ch)
        self.slots.setRowCount(0)
        for slot in ch["slots"]:
            self._add_slot(slot)

    def add_channel(self):
        self._store_editor()
        try:
            app = beat_settings.read_app(self.config_path)
        except Exception:
            self.status.setText("No se pudo leer la configuración para agregar un canal.")
            return
        used = {ch["id"] for ch in self.config["channels"]}
        free = [ch for ch in channel_names_for_section(app.get("channels", {}), SECTION_BEATS) if ch not in used]
        if not free:
            self.status.setText("No hay canales libres de Beats. Crealos en Gestionar Canales.")
            return
        self.config["channels"].append(dict(id=free[0], active=False, priority=0, selection_tags=[],
                                            slots=[dict(weekday=0, hour=18, minute=0)]))
        self._refresh_list(len(self.config["channels"]) - 1)

    def remove_channel(self):
        if self.selected >= 0:
            del self.config["channels"][self.selected]
            self._refresh_list()

    def browse_images(self):
        folder = QFileDialog.getExistingDirectory(self, "Carpeta de imágenes", self.images.text())
        if folder:
            self.images.setText(folder)

    def draft(self):
        self._store_editor()
        config = deepcopy(self.config)
        config["beatstars_profile_url"] = self.profile.text().strip()
        return beat_settings.validate(config, beat_settings.read_app(self.config_path))

    def save(self):
        if not self.config_readable:
            return
        try:
            beat_settings.save(self.config_path, self.draft())
            self.status.setText("Configuración de Beats guardada localmente.")
        except Exception as exc:
            self.status.setText(f"No se guardó: {exc}" if isinstance(exc, ValueError) else "No se pudo guardar la configuración.")

    def _start(self, fn, done):
        if self.task is not None:
            return
        self.task = BeatTask(fn, self)
        self.task.done.connect(lambda value: self._deliver(value, done))
        self.task.failed.connect(self.status.setText)
        self.task.cancelled.connect(lambda: self.status.setText("Operación cancelada; resultado descartado."))
        self.task.progress.connect(self.status.setText)
        self.task.finished.connect(self._finished)
        for button in (self.analyze_button, self.state_button, self.simulate_button, self.save_button,
                       self.add_button, self.remove_button):
            button.setEnabled(False)
        self.profile.setEnabled(False)
        self.editor.setEnabled(False)
        self.automations.setEnabled(False)
        self.remote.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.status.setText("Procesando…")
        self.task.start()

    def _deliver(self, value, done):
        if self.task is not None and not self.task.event.is_set():
            done(value)
        else:
            self.status.setText("Operación cancelada; resultado descartado.")

    def _finished(self):
        task, self.task = self.task, None
        task.deleteLater()
        for button in (self.analyze_button, self.state_button, self.simulate_button, self.save_button,
                       self.add_button, self.remove_button):
            button.setEnabled(True)
        self.profile.setEnabled(True)
        self.editor.setEnabled(self.config_readable and self.selected >= 0)
        self.automations.setEnabled(self.config_readable)
        self.remote.setEnabled(True)
        for widget in (self.save_button, self.add_button, self.remove_button, self.simulate_button):
            widget.setEnabled(self.config_readable)
        self.cancel_button.setEnabled(False)
        window = self.window()
        if getattr(window, "close_pending", False):
            window.close()

    def cancel(self):
        if self.task:
            self.task.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText("Cancelando… Se espera a que termine la solicitud en curso.")

    def analyze_profile(self):
        url = self.profile.text().strip()
        try:
            profile_username(url)
        except Exception:
            self.status.setText("Ingresá una URL HTTPS de perfil público de BeatStars válida.")
            return
        self.analysis = None
        self.output.clear()
        self.job_model.set_jobs([])
        self._start(lambda event, progress: analyze(url, event, progress, self.transport), self._analyzed)

    def _analyzed(self, result):
        self.analysis = result
        tags = ", ".join(f"{tag} ({count})" for tag, count in result["tags"])
        self.output.setPlainText(f'Tracks: {len(result["tracks"])}\n'
                                 f'Duración informada: {result["duration_count"]} tracks; '
                                 f'{result["duration_total"] / 60:.1f} minutos en total.\n'
                                 f'Tags frecuentes: {tags or "sin tags"}')
        self.status.setText("Análisis terminado. Metadata pública; no se descargaron audios.")

    def read_state(self):
        def read(event, progress):
            checkpoint(event)
            if self.state_reader is not None:
                state = self.state_reader()
            else:
                state = load_state(event)
            checkpoint(event)
            return migrate(state, "state")
        self._start(read, self._state_loaded)

    def _state_loaded(self, state):
        self.state = state
        counts = {}
        for job in state["jobs"].values():
            counts[job["status"]] = counts.get(job["status"], 0) + 1
        day = datetime.now(BA).date().isoformat()
        used = len(state["attempts"].get(day, {}))
        self.quota.setText(f"Cuota global del {day}: {used}/6 intentos consumidos; {6 - used} disponibles.")
        self.output.setPlainText(f"Estado remoto consultado (sin escrituras).\nJobs: {counts}\n"
                                 f'Lock: {"presente" if state["lock"] else "libre"}')
        self.status.setText("Estado cargado. La simulación puede usar esta instantánea.")

    def simulate(self):
        try:
            config = self.draft()
            if self.analysis is None or self.analysis["url"] != config["beatstars_profile_url"]:
                raise ValueError("Analizá el perfil actual antes de simular.")
            if self.remote.isChecked() and self.state is None:
                raise ValueError("Consultá el estado de Dropbox antes de usarlo.")
            tracks = deepcopy(self.analysis["tracks"])
            state = deepcopy(self.state) if self.remote.isChecked() else None
        except Exception as exc:
            self.status.setText(str(exc) if isinstance(exc, ValueError) else "Revisá la configuración.")
            return
        self._start(lambda event, progress: beat_settings.simulate(config, tracks, state),
                    lambda result: self._simulated(result, state is not None))

    def _simulated(self, result, remote):
        jobs = result["jobs"]
        self.job_model.set_jobs(jobs)
        self.output.setPlainText(f'Simulación desde {result["as_of"]}, próximos 14 días.\n'
                                 f'Estado: {"instantánea de Dropbox" if remote else "vacío, escenario local"}.\n'
                                 f'Jobs nuevos: {len(jobs)}. Intentos disponibles hoy: {result["remaining"]}/6.\n'
                                 "La cuota se consume al intentar subir, no al planificar slots.\n"
                                 "Tags de selección filtran por coincidencia exacta, sin mayúsculas ni espacios exteriores.\n"
                                 "Sin tags de selección se conserva el catálogo activo completo; tags SEO y géneros no filtran.")
        self.status.setText("Simulación terminada; no se reservaron jobs ni intentos.")


class BeatDialog(QDialog):
    close_pending = False

    def closeEvent(self, event):
        if self.panel.task is not None:
            self.close_pending = True
            self.panel.cancel()
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        if self.panel.task is not None:
            self.close_pending = True
            self.panel.cancel()
        else:
            super().reject()


def open_beat_panel(parent=None):
    dialog = BeatDialog(parent)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setWindowTitle("Beats: configuración de automatizaciones")
    dialog.resize(900, 850)
    dialog.panel = BeatPanel(dialog)
    layout = QVBoxLayout(dialog)
    layout.addWidget(dialog.panel)
    dialog.exec_()
