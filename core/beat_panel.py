"""Independent Phase 3 UI for Type Beats (no rendering or publishing)."""
from copy import deepcopy
from datetime import datetime

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import QWidget, QDialog, QVBoxLayout, QFileDialog, QInputDialog

from core import automation_status as status, beat_settings, channel_kind, cloud_registry, kit_channel
from core.beat_panel_form import BeatPanelForm
from core.beat_schema import BA, migrate
from core.beat_source import profile_username
from core.beat_tasks import BeatTask, analyze, checkpoint, load_state
from core.beat_remote_form import BeatRemoteForm
from core.beat_panel_cloud import local_transport
from core.channel_wizard import BEATS, ChannelWizardHost


class BeatPanel(QWidget, BeatPanelForm, BeatRemoteForm, ChannelWizardHost):
    """Dropbox es la única fuente: /type-beats/config.json y /automatizacion/canales.json."""
    wizard_kind = BEATS

    def __init__(self, parent=None, transport=None, state_reader=None,
                 cloud_provider=local_transport, autoload=True):
        super().__init__(parent)
        self.transport, self.state_reader = transport, state_reader
        self.cloud_provider = cloud_provider
        self.cloud_rev, self.cloud_loaded, self.cloud_base = None, False, None
        self.registry = cloud_registry.empty('canales')
        self.registry_base, self.registry_rev = None, None
        self.ajustes = cloud_registry.empty('ajustes')
        self.task = None
        self.analysis = None
        self.state = None
        self.config = migrate({}, "config")
        self.selected = -1
        self.config_readable = False
        self._reload_pending = False
        self._templates_key = None
        self._build()
        self.channel.currentTextChanged.connect(self._channel_changed)
        self._set_editable(False)
        self.status.setText("Configuración sin cargar: se lee de Dropbox.")
        if autoload:
            self.reload()

    def _set_editable(self, on):
        for widget in (self.save_publish_button, self.add_button, self.remove_button,
                       self.simulate_button, self.automations, self.editor, self.seo_editor):
            widget.setEnabled(on)

    def reload(self):
        """Relee todo de Dropbox; nunca lee ni escribe config/app_config.json."""
        self.reload_cloud_config()

    def _channel_changed(self, key):
        """Al cambiar el canal de la fila, guarda las plantillas mostradas y carga las nuevas."""
        if self.selected < 0 or key == self._templates_key:
            return
        self._store_templates(None, channel_kind.find(self.registry, self._templates_key))
        row = channel_kind.find(self.registry, key)
        checked = self.use_templates.isChecked()
        self._load_templates({}, row.get("plantillas") if row else None, key)
        self.use_templates.setChecked(checked)

    def _fill_channels(self):
        self.channel.blockSignals(True)
        self.channel.clear()
        self.channel.addItems(sorted(beat_settings.beat_channels(self.registry)))
        self.channel.blockSignals(False)

    def request_reload(self):
        """Recarga ahora o, si hay una tarea en curso, apenas termine."""
        if self.task is None:
            self.reload()
        else:
            self._reload_pending = True

    def _profile_changed(self):
        self.analysis = None
        self.job_model.set_jobs([])
        self.output.clear()

    def _refresh_list(self, selected=0):
        self.automations.blockSignals(True)
        self.automations.clear()
        for ch in self.config["channels"]:
            self.automations.addItem(self._list_text(ch))
        self.automations.setCurrentRow(selected)
        self.automations.blockSignals(False)
        self.selected = -1
        self._select(self.automations.currentRow())
        self.reload_connection_channels()
        self.refresh_channel_chips()

    def _list_text(self, ch):
        """Texto de la lista: estado de la automatización + chip de avance del alta (5 pasos)."""
        text, _color = self.channel_chip(ch["id"], ch.get("actions_slug", "") or "", ch["id"])
        return f'{ch["id"]} — {"Activa" if ch["active"] else "Pausada"} · {text}'

    def refresh_channel_chips(self):
        """Repinta texto y color del chip de cada canal (se llama al cambiar flags o conexiones)."""
        for row, ch in enumerate(self.config["channels"]):
            item = self.automations.item(row)
            if item is None:
                continue
            item.setText(self._list_text(ch))
            _text, color = self.channel_chip(ch["id"], ch.get("actions_slug", "") or "", ch["id"])
            item.setForeground(QColor(color))

    # --- Hooks del asistente de alta (core/channel_wizard.py) ---

    def wizard_target(self):
        """``(canal, slug, clave de flags)`` del canal elegido en la lista."""
        if self.selected < 0:
            return "", "", ""
        channel = self.channel.currentText()
        return channel, self.config["channels"][self.selected].get("actions_slug", "") or "", channel

    def wizard_focus(self, channel, slug, key):
        """Elige en la lista y en Conexiones el canal congelado del asistente."""
        row = next((i for i, ch in enumerate(self.config["channels"]) if ch["id"] == channel), -1)
        if row < 0:
            return
        if self.automations.currentRow() != row:
            self.automations.setCurrentRow(row)
        self.conn_channel.setCurrentText(channel)

    def wizard_set_slug(self, channel, slug):
        """Escribe el slug en la fila de ``channel``, no en la que esté seleccionada ahora."""
        # El slug no puede ser de otro canal (config o registro) ni distinto del registrado:
        # sus secretos BEAT_*_<SLUG> son de un solo canal.
        text = status.beat_slug_error(channel, slug, self.config["channels"], self.registry)
        if text:
            self.status.setText(text)
            self.wizard_notify(False, text)
            return False
        if not self.wizard_bind(channel, slug, channel):
            return False
        row = next((i for i, ch in enumerate(self.config["channels"]) if ch["id"] == channel), -1)
        if row < 0:
            return False
        self.config["channels"][row]["actions_slug"] = slug
        self.refresh_connections()
        self.refresh_channel_chips()
        return True

    def wizard_activate(self):
        """Activa la fila del asistente (ya bindeada) y publica. El éxito lo avisa Dropbox."""
        row = next((i for i, ch in enumerate(self.config["channels"])
                    if ch["id"] == getattr(self._wizard, 'channel', None)), -1)
        if row < 0:
            return False
        if self.selected != row:
            return False
        self.active.setChecked(True)
        return self.save_and_publish() is not False

    def open_wizard_clicked(self):
        self._store_editor()
        self.open_channel_wizard()

    def _store_editor(self):
        if self.selected < 0:
            return
        ch = self.config["channels"][self.selected]
        self._store_visual(ch)
        # Ficha cuyos valores muestra el formulario (no la del combo, que pudo cambiar).
        self._store_templates(ch, channel_kind.find(self.registry, self._templates_key))
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
        self.automations.item(self.selected).setText(self._list_text(ch))
        self.reload_connection_channels()
        self.refresh_publish_readiness()

    def _select(self, index):
        self._store_editor()
        self.selected = index
        self.editor.setEnabled(index >= 0)
        self.seo_editor.setEnabled(index >= 0)
        if index < 0:
            self.refresh_publish_readiness()
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
        row = channel_kind.find(self.registry, ch["id"])
        self._load_templates(ch, row.get("plantillas") if row else None, ch["id"])
        self.slots.setRowCount(0)
        for slot in ch["slots"]:
            self._add_slot(slot)
        self.refresh_publish_readiness()

    def add_channel(self):
        self._store_editor()
        used = {ch["id"] for ch in self.config["channels"]}
        free = [key for key in sorted(beat_settings.beat_channels(self.registry)) if key not in used]
        if not free:
            created = self.create_registry_channel()
            if created is None:
                return
            free = [created]
        self.config["channels"].append(dict(id=free[0], active=False, priority=0, selection_tags=[],
                                            slots=[dict(weekday=0, hour=18, minute=0)]))
        self._refresh_list(len(self.config["channels"]) - 1)

    def ask_new_channel_name(self):
        name, ok = QInputDialog.getText(self, "Nuevo canal de Beats",
                                        "Nombre del canal (el slug sale del nombre y no cambia):")
        return name.strip() if ok else ""

    def create_registry_channel(self):
        """Ficha nueva de Beats en el registro (se publica con «Publicar al robot»)."""
        name = self.ask_new_channel_name()
        if not name:
            return None
        slug = kit_channel.slug(name)
        try:
            row = cloud_registry.new_channel(channel_kind.BEATS, slug, slug, nombre=name)
            candidate = deepcopy(self.registry)
            candidate["canales"].append(row)
            cloud_registry.normalize("canales", candidate)
        except ValueError as exc:
            self.status.setText(f"No se creó el canal: {exc}")
            return None
        self.registry = candidate
        self._fill_channels()
        self.status.setText(f"Canal «{name}» agregado al registro (slug {slug}). "
                            "Se guarda al publicar.")
        return slug

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
        return beat_settings.validate(config, self.registry)

    def save_and_publish(self):
        """Publica el registro de canales y ``/type-beats/config.json`` por CAS (con merge)."""
        if not self.config_readable:
            self.wizard_notify(False, 'No se pudo leer la configuración.')
            return False
        self.status.setText('Publicando en Dropbox…')
        return self.save_cloud_config()

    def _start(self, fn, done):
        if self.task is not None:
            return
        self.task = BeatTask(fn, self)
        self.task.done.connect(lambda value: self._deliver(value, done))
        self.task.failed.connect(self._task_failed)
        self.task.cancelled.connect(self._task_cancelled)
        self.task.progress.connect(self.status.setText)
        self.task.finished.connect(self._finished)
        for button in (self.analyze_button, self.state_button, self.simulate_button,
                       self.save_publish_button, self.cloud_reload_button,
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
        for button in (self.analyze_button, self.state_button, self.cloud_reload_button):
            button.setEnabled(True)
        self.profile.setEnabled(True)
        self.remote.setEnabled(True)
        self._set_editable(self.config_readable)
        self.editor.setEnabled(self.config_readable and self.selected >= 0)
        self.seo_editor.setEnabled(self.config_readable and self.selected >= 0)
        self.cancel_button.setEnabled(False)
        window = self.window()
        if getattr(window, "close_pending", False):
            window.close()
        elif self._reload_pending and self.task is None:
            self._reload_pending = False
            self.reload()

    def _task_failed(self, text):
        self.status.setText(text)
        self.wizard_notify(False, text)

    def _task_cancelled(self):
        self.status.setText("Operación cancelada; resultado descartado.")
        self.wizard_notify(False, 'Publicación cancelada.')

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
                state = load_state(event, self.cloud_provider())
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
            self.panel.stop_connections()
            super().closeEvent(event)

    def reject(self):
        if self.panel.task is not None:
            self.close_pending = True
            self.panel.cancel()
        else:
            self.panel.stop_connections()
            super().reject()


def open_beat_panel(parent=None):
    dialog = BeatDialog(parent)
    dialog.setAttribute(Qt.WA_DeleteOnClose)
    dialog.setWindowTitle('Automatizaciones de Beats')
    dialog.resize(900, 850)
    dialog.panel = BeatPanel(dialog)
    layout = QVBoxLayout(dialog)
    layout.addWidget(dialog.panel)
    dialog.exec_()
