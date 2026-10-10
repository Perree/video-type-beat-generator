# -*- coding: utf-8 -*-
"""Panel de Marca personal: transcribir un video largo, elegir clips y renderizar Shorts."""
import json
import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from clip_dialog import ClipDialog
from core.clip_select import ClipSelectError, export_prompt, import_response
from core.sections import SECTION_PERSONAL, channel_names_for_section
from core import shorts_store, youtube
from core.shorts_worker import ShortsWorker
from core.upload_worker import YouTubeUploadWorker

_OUTPUT_DIR = os.path.join("exported_videos", "personal", "shorts")
# People & Blogs. Los beats siguen en categoría 10 dentro de youtube.upload.
CATEGORY_SHORTS = "22"
_TITLE_LIMIT = 100
_SHORTS_TAG = "#Shorts"
_UPLOAD_STATES = ("aprobado", "renderizado")


def title_with_shorts(titulo):
    """Título de YouTube. Agrega « #Shorts» solo si el total cabe en 100 caracteres.

    Args:
        titulo: título del clip.

    Returns:
        Texto listo para videos.insert (máximo 100 caracteres).
    """
    base = (titulo or "").strip() or "Short"
    if base.endswith(_SHORTS_TAG):
        return base[:_TITLE_LIMIT]
    suffixed = f"{base} {_SHORTS_TAG}"
    if len(suffixed) <= _TITLE_LIMIT:
        return suffixed
    return base[:_TITLE_LIMIT]


def build_upload_jobs(clips, channel):
    """Arma trabajos privados (categoría 22) para el canal elegido.

    El token OAuth no viaja en el job: youtube.upload lo lee de tokens/<canal>.json.
    Omite clips ya marcados subido, sin mp4, o que no estén aprobados/renderizados.
    Si hay youtube_id pero el estado no es subido, el job sigue: el worker no
    vuelve a llamar a YouTube y solo completa la fila de uploads.

    Args:
        clips: filas de shorts_store (dict con id, titulo, estado, render_path, youtube_id).
        channel: nombre del canal de la app, sección personal.

    Returns:
        Lista de dicts para YouTubeUploadWorker.
    """
    channel = (channel or "").strip()
    jobs = []
    for clip in clips:
        if clip.get("estado") == "subido":
            continue
        if clip.get("estado") not in _UPLOAD_STATES:
            continue
        path = clip.get("render_path") or ""
        if not path:
            continue
        jobs.append({
            "channel": channel,
            "group": "",
            "path": path,
            "title": title_with_shorts(clip.get("titulo")),
            "description": clip.get("gancho") or "",
            "tags": "",
            "thumbnail": None,
            "privacy": "private",
            "publish_at": None,
            "beat_id": None,
            "clip_id": clip["id"],
            "category_id": CATEGORY_SHORTS,
        })
    return jobs


class ShortsPanel(QWidget):
    """Carga un video, corre el pipeline y lista los clips. El hilo de UI solo usa señales."""

    def __init__(self, config_path, ffmpeg_provider=None, clip_output_dir=None, parent=None):
        super().__init__(parent)
        self._config_path = config_path
        self._ffmpeg_provider = ffmpeg_provider
        self._clip_output_dir = clip_output_dir
        self._video_path = ""
        self._video_id = None
        self._worker = None
        self._upload_worker = None
        self._reloading = False
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        file_row = QHBoxLayout()
        self.btn_file = QPushButton("Elegir video")
        self.btn_file.clicked.connect(self._pick_video)
        self.file_label = QLabel("Ningún video cargado")
        self.file_label.setWordWrap(True)
        file_row.addWidget(self.btn_file)
        file_row.addWidget(self.file_label, 1)
        layout.addLayout(file_row)

        meta_row = QHBoxLayout()
        meta_row.addWidget(QLabel("Canal:"))
        self.channel_combo = QComboBox()
        self.channel_combo.setMinimumWidth(180)
        meta_row.addWidget(self.channel_combo)
        meta_row.addWidget(QLabel("Layout:"))
        self.layout_combo = QComboBox()
        # recorte y split llegan en la fase siguiente; el render solo acepta obs_unico.
        self.layout_combo.addItem("OBS único (fondo difuminado)", "obs_unico")
        meta_row.addWidget(self.layout_combo)
        meta_row.addStretch(1)
        layout.addLayout(meta_row)

        buttons = QHBoxLayout()
        self.btn_transcribe = QPushButton("Transcribir")
        self.btn_transcribe.clicked.connect(self._start_transcribe)
        self.btn_select = QPushButton("Elegir clips")
        self.btn_select.clicked.connect(self._start_select)
        self.btn_render = QPushButton("Renderizar")
        self.btn_render.clicked.connect(self._start_render)
        self.btn_cancel = QPushButton("Cancelar")
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self._cancel)
        for btn in (self.btn_transcribe, self.btn_select, self.btn_render, self.btn_cancel):
            buttons.addWidget(btn)
        layout.addLayout(buttons)

        extra = QHBoxLayout()
        self.btn_prompt = QPushButton("Guardar prompt")
        self.btn_prompt.clicked.connect(self._save_prompt)
        self.btn_json = QPushButton("Cargar JSON")
        self.btn_json.clicked.connect(self._load_json)
        self.btn_open = QPushButton("Abrir")
        self.btn_open.clicked.connect(self._open_selected)
        self.btn_brand_clip = QPushButton("Nuevo clip de marca")
        self.btn_brand_clip.clicked.connect(self._open_brand_clip)
        self.btn_upload = QPushButton("Subir aprobados (privado)")
        self.btn_upload.clicked.connect(self._upload_approved)
        for btn in (self.btn_prompt, self.btn_json, self.btn_open,
                    self.btn_brand_clip, self.btn_upload):
            extra.addWidget(btn)
        layout.addLayout(extra)

        self.stage_label = QLabel("Listo")
        layout.addWidget(self.stage_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        layout.addWidget(self.progress)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Tiempo", "Título", "Puntaje", "Estado"])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.cellDoubleClicked.connect(lambda *_: self._open_selected())
        self.table.itemSelectionChanged.connect(self._load_editor)
        layout.addWidget(self.table, 1)

        review = QHBoxLayout()
        self.edit_title = QLineEdit()
        self.edit_title.setPlaceholderText("Título del clip")
        review.addWidget(self.edit_title, 1)
        self.spin_start = QDoubleSpinBox()
        self.spin_end = QDoubleSpinBox()
        for spin in (self.spin_start, self.spin_end):
            spin.setRange(0, 86400)
            spin.setDecimals(2)
            spin.setSingleStep(0.5)
            spin.setSuffix(" s")
        review.addWidget(QLabel("Inicio"))
        review.addWidget(self.spin_start)
        review.addWidget(QLabel("Fin"))
        review.addWidget(self.spin_end)
        layout.addLayout(review)

        review_btns = QHBoxLayout()
        self.btn_approve = QPushButton("Aprobar")
        self.btn_approve.clicked.connect(self._approve)
        self.btn_reject = QPushButton("Rechazar")
        self.btn_reject.clicked.connect(self._reject)
        self.btn_rerender = QPushButton("Re-renderizar este clip")
        self.btn_rerender.clicked.connect(self._rerender)
        for btn in (self.btn_approve, self.btn_reject, self.btn_rerender):
            review_btns.addWidget(btn)
        layout.addLayout(review_btns)
        self._set_editor_enabled(False)

    def showEvent(self, event):
        """Recarga canales de Marca personal al mostrar la sección."""
        super().showEvent(event)
        self._reload_channels()

    def _reload_channels(self):
        current = self.channel_combo.currentText()
        self.channel_combo.blockSignals(True)
        self.channel_combo.clear()
        self.channel_combo.addItem("")
        for name in channel_names_for_section(self._channels(), SECTION_PERSONAL):
            self.channel_combo.addItem(name)
        index = self.channel_combo.findText(current)
        if index >= 0:
            self.channel_combo.setCurrentIndex(index)
        self.channel_combo.blockSignals(False)

    def _channels(self):
        cfg = self._read_config()
        return cfg.get("channels") or {}

    def _shorts_cfg(self):
        return self._read_config().get("shorts") or {}

    def _read_config(self):
        try:
            with open(self._config_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _pick_video(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Video largo", "",
            "Video (*.mp4 *.mov *.mkv *.webm);;Todos (*.*)")
        if not path:
            return
        self._video_path = path
        self._video_id = None
        self.file_label.setText(path)
        self.table.setRowCount(0)
        self.stage_label.setText("Video elegido. Falta transcribir.")

    def _start_transcribe(self):
        if not self._video_path:
            self._warn("Elegí un video primero.")
            return
        self._start_worker(ShortsWorker(
            self._video_path, self._shorts_cfg(),
            job="transcribir",
            canal=self.channel_combo.currentText().strip(),
            layout_profile=self.layout_combo.currentData() or "obs_unico",
        ))

    def _start_select(self):
        if not self._video_id:
            self._warn("Primero transcribí el video.")
            return
        self._start_worker(ShortsWorker(
            self._video_path, self._shorts_cfg(),
            job="elegir", video_id=self._video_id,
        ))

    def _start_render(self):
        if not self._video_id:
            self._warn("Primero transcribí el video y elegí clips.")
            return
        self._start_worker(ShortsWorker(
            self._video_path, self._shorts_cfg(),
            job="renderizar", video_id=self._video_id,
            output_dir=_OUTPUT_DIR,
            layout_profile=self.layout_combo.currentData() or "obs_unico",
        ))

    def _start_worker(self, worker):
        if self._worker is not None and self._worker.isRunning():
            return
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.finished_ok.connect(self._on_ok)
        worker.failed.connect(self._on_fail)
        worker.cancelled.connect(self._on_cancel)
        worker.finished.connect(self._on_thread_done)
        self._set_busy(True)
        worker.start()

    def _cancel(self):
        if self._worker is not None:
            self._worker.stop()
            self.stage_label.setText("Cancelando…")

    def _on_progress(self, etapa, pct, texto):
        self.progress.setValue(int(pct))
        self.stage_label.setText(f"{etapa}: {texto}")

    def _on_ok(self, video_id):
        self._video_id = int(video_id)
        self.progress.setValue(100)
        self.stage_label.setText("Listo")
        self._reload_table()

    def _on_fail(self, message):
        self.stage_label.setText("Error")
        self._warn(message)
        self._reload_table()

    def _on_cancel(self):
        self.stage_label.setText("Cancelado")
        self._reload_table()

    def _on_thread_done(self):
        self._set_busy(False)

    def _set_busy(self, busy):
        for btn in (self.btn_file, self.btn_transcribe, self.btn_select, self.btn_render,
                    self.btn_prompt, self.btn_json, self.btn_open, self.btn_brand_clip,
                    self.btn_approve, self.btn_reject, self.btn_rerender, self.btn_upload):
            btn.setEnabled(not busy)
        self.edit_title.setEnabled(not busy and self._selected_clip_id() is not None)
        self.spin_start.setEnabled(not busy and self._selected_clip_id() is not None)
        self.spin_end.setEnabled(not busy and self._selected_clip_id() is not None)
        self.btn_cancel.setEnabled(busy)
        if not busy:
            self._set_editor_enabled(self._selected_clip_id() is not None)

    def _reload_table(self):
        keep_id = self._selected_clip_id()
        self._reloading = True
        self.table.setRowCount(0)
        select_row = -1
        if self._video_id:
            for clip in shorts_store.list_clips(self._video_id):
                row = self.table.rowCount()
                self.table.insertRow(row)
                tiempo = f"{float(clip['start_s']):.1f}–{float(clip['end_s']):.1f} s"
                puntaje = clip.get("puntaje")
                cells = [
                    tiempo,
                    clip.get("titulo") or "",
                    "" if puntaje is None else f"{float(puntaje):.2f}",
                    clip.get("estado") or "",
                ]
                for col, text in enumerate(cells):
                    item = QTableWidgetItem(text)
                    if col == 0:
                        item.setData(Qt.UserRole, int(clip["id"]))
                        item.setData(Qt.UserRole + 1, clip.get("render_path") or "")
                    self.table.setItem(row, col, item)
                if keep_id is not None and int(clip["id"]) == int(keep_id):
                    select_row = row
        self._reloading = False
        if select_row >= 0:
            self.table.selectRow(select_row)
        else:
            self._clear_editor()

    def _selected_clip_id(self):
        """Id del clip de la fila elegida, o None."""
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        if item is None:
            return None
        clip_id = item.data(Qt.UserRole)
        return int(clip_id) if clip_id is not None else None

    def _selected_render_path(self):
        row = self.table.currentRow()
        if row < 0:
            return ""
        item = self.table.item(row, 0)
        return (item.data(Qt.UserRole + 1) or "") if item else ""

    def _set_editor_enabled(self, enabled):
        self.edit_title.setEnabled(enabled)
        self.spin_start.setEnabled(enabled)
        self.spin_end.setEnabled(enabled)
        self.btn_approve.setEnabled(enabled)
        self.btn_reject.setEnabled(enabled)
        self.btn_rerender.setEnabled(enabled)

    def _clear_editor(self):
        self.edit_title.clear()
        self.spin_start.setValue(0)
        self.spin_end.setValue(0)
        self._set_editor_enabled(False)

    def _load_editor(self):
        """Copia título e inicio/fin del clip elegido. No escribe la base."""
        if self._reloading:
            return
        clip_id = self._selected_clip_id()
        if clip_id is None:
            self._clear_editor()
            return
        clip = shorts_store.get_clip(clip_id)
        if not clip:
            self._clear_editor()
            return
        self.edit_title.setText(clip.get("titulo") or "")
        self.spin_start.setValue(float(clip["start_s"]))
        self.spin_end.setValue(float(clip["end_s"]))
        self._set_editor_enabled(True)

    def _edited_fields(self):
        """Título e inicio/fin del formulario, o None si el rango no sirve."""
        title = self.edit_title.text().strip()
        if len(title) > 90:
            self._warn("El título no puede pasar de 90 caracteres.")
            return None
        start_s = float(self.spin_start.value())
        end_s = float(self.spin_end.value())
        if end_s <= start_s:
            self._warn("El fin tiene que ser mayor que el inicio.")
            return None
        return {"titulo": title, "start_s": start_s, "end_s": end_s}

    def _save_edit(self, estado=None):
        """Persiste título e inicio/fin. No manda start_modelo ni end_modelo.

        Args:
            estado: si viene, también cambia el estado del clip.

        Returns:
            True si se escribió la fila.
        """
        clip_id = self._selected_clip_id()
        if clip_id is None:
            self._warn("Elegí un clip de la lista.")
            return False
        fields = self._edited_fields()
        if fields is None:
            return False
        if estado:
            fields["estado"] = estado
        shorts_store.update_clip(clip_id, **fields)
        return True

    def _approve(self):
        if self._save_edit("aprobado"):
            self._reload_table()
            self.stage_label.setText("Clip aprobado")

    def _reject(self):
        """Marca rechazado. La fila queda: no entra a un render ni a una subida."""
        if self._save_edit("rechazado"):
            self._reload_table()
            self.stage_label.setText("Clip rechazado")

    def _rerender(self):
        clip_id = self._selected_clip_id()
        if clip_id is None:
            self._warn("Elegí un clip de la lista.")
            return
        clip = shorts_store.get_clip(clip_id)
        if not clip:
            self._warn("Ese clip ya no está en la base.")
            return
        if clip.get("estado") == "rechazado":
            self._warn("Un clip rechazado no se re-renderiza.")
            return
        if clip.get("estado") not in ("aprobado", "renderizado", "error"):
            self._warn("Aprobá el clip antes de re-renderizarlo.")
            return
        if not self._save_edit():
            return
        self._start_worker(ShortsWorker(
            self._video_path, self._shorts_cfg(),
            job="renderizar_uno", video_id=self._video_id, clip_id=clip_id,
            output_dir=_OUTPUT_DIR,
        ))

    def _open_selected(self):
        path = self._selected_render_path()
        if not path or not os.path.isfile(path):
            self._warn("Ese clip todavía no tiene un mp4. Renderizalo primero.")
            return
        os.startfile(path)  # reproductor de Windows; sin QMediaPlayer

    def _save_prompt(self):
        words, duration = self._words_or_warn()
        if words is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar prompt", "prompt_shorts.txt", "Texto (*.txt)")
        if not path:
            return
        try:
            export_prompt(words, self._shorts_cfg(), path=path, duration=duration)
        except ClipSelectError as exc:
            self._warn(str(exc))

    def _load_json(self):
        if not self._video_id:
            self._warn("Primero transcribí el video.")
            return
        words, duration = self._words_or_warn()
        if words is None:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Respuesta JSON", "", "JSON (*.json *.txt)")
        if not path:
            return
        try:
            import_response(
                path, words, self._video_id, self._shorts_cfg(), duration=duration)
        except (OSError, ClipSelectError) as exc:
            self._warn(str(exc))
            return
        self._reload_table()
        self.stage_label.setText("Clips cargados desde JSON")

    def _words_or_warn(self):
        if not self._video_id:
            self._warn("Primero transcribí el video.")
            return None, None
        model = (self._shorts_cfg().get("whisper_model") or "small")
        words = shorts_store.get_transcript(self._video_id, model)
        if not words:
            self._warn("No hay transcripción para este video.")
            return None, None
        video = shorts_store.get_video(self._video_id) or {}
        return words, video.get("duration_s")

    def _upload_approved(self):
        """Sube los clips aprobados o renderizados del video cargado, en privado."""
        if self._upload_worker is not None and self._upload_worker.isRunning():
            return
        if not self._video_id:
            self._warn("Primero cargá un video y renderizá los clips.")
            return
        channel = self.channel_combo.currentText().strip()
        if not channel:
            self._warn("Elegí un canal de Marca personal.")
            return
        if not youtube.is_connected(channel):
            self._warn(f"'{channel}' no está conectado. Conectalo en Gestión de Canales.")
            return
        clips = shorts_store.list_clips(self._video_id)
        jobs = build_upload_jobs(clips, channel)
        if not jobs:
            self._warn("No hay clips aprobados con mp4 pendientes de subir.")
            return
        self.stage_label.setText(f"Subiendo {len(jobs)} Short(s) en privado…")
        self._upload_worker = YouTubeUploadWorker(jobs, self)
        self._upload_worker.progress.connect(self.stage_label.setText)
        self._upload_worker.finished_all.connect(self._upload_finished)
        self._set_busy(True)
        # Cancelar corta el render, no esta subida.
        self.btn_cancel.setEnabled(False)
        self._upload_worker.start()

    def _upload_finished(self, done, errors):
        self._set_busy(False)
        self._reload_table()
        if errors:
            self.stage_label.setText("Subida con errores")
            self._warn("\n".join(errors))
            return
        self.stage_label.setText(f"Subidos en privado: {len(done)}")

    def _open_brand_clip(self):
        """El diálogo Estudio/Loop/Hook sigue disponible desde esta sección."""
        if not self._ffmpeg_provider:
            self._warn("No hay FFmpeg configurado.")
            return
        output = self._clip_output_dir() if self._clip_output_dir else _OUTPUT_DIR
        dialog = ClipDialog(self._ffmpeg_provider(), output, self._channels(), self.window())
        dialog.exec_()

    def _warn(self, text):
        QMessageBox.warning(self, "Shorts", str(text))
