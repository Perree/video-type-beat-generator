# -*- coding: utf-8 -*-
"""Diálogo de Marca personal: clip 9:16 (Estudio, Loop o Hook) + .txt con título y descripción."""
import os
import re
import shutil
import subprocess
import tempfile

from PyQt5.QtCore import Qt, QPoint, QRectF, QThread, QTimer, pyqtSignal, QDateTime
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDoubleSpinBox,
                             QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                             QSizePolicy, QSlider, QVBoxLayout, QWidget)

from core import channel_templates, clips, description, youtube
from core.publish_at import publish_at_from_qdatetime
from core.sections import SECTION_PERSONAL, channel_names_for_section
from core.upload_worker import YouTubeUploadWorker

_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
_PRESET_LABELS = (
    (clips.PRESET_ESTUDIO, "Estudio (video + audio de un beat)"),
    (clips.PRESET_LOOP, "Loop (video con el audio de la toma)"),
    (clips.PRESET_HOOK, "Hook (fondo + texto, sin audio)"),
)
_VIDEO_FILTER = "Video o imagen (*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.jpg *.jpeg *.png *.webp *.bmp);;Todos (*.*)"
_AUDIO_FILTER = "Audio (*.mp3 *.wav *.m4a *.flac *.ogg);;Todos (*.*)"
_PREVIEW_MAX_EDGE = 1280


def _probe_duration(ffmpeg, path):
    """Duración en segundos leyendo la salida de `ffmpeg -i`; None si no se puede."""
    try:
        r = subprocess.run([ffmpeg, '-hide_banner', '-i', path], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=20, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', r.stderr or '')
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else None


class FramePreview(QWidget):
    """Un frame en 9:16 con cuadrícula; arrastrar mueve el encuadre y la rueda escala."""
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(270, 480)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._pix = None
        self._src_w = self._src_h = 0
        self.zoom, self.offset_x, self.offset_y = 1.0, 0.5, 0.5
        self.hook_text = ''
        self._drag_from = None

    def set_source(self, pixmap, src_w, src_h):
        self._src_w, self._src_h = src_w, src_h
        if max(pixmap.width(), pixmap.height()) > _PREVIEW_MAX_EDGE:
            pixmap = pixmap.scaled(_PREVIEW_MAX_EDGE, _PREVIEW_MAX_EDGE, Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
        self._pix = pixmap
        self.update()

    def has_source(self):
        return self._pix is not None

    def framing(self):
        return clips.Framing(self._src_w, self._src_h, self.zoom, self.offset_x, self.offset_y)

    def set_zoom(self, zoom):
        self.zoom = max(1.0, min(clips.MAX_ZOOM, zoom))
        self.update()

    def center(self):
        self.offset_x = self.offset_y = 0.5
        self.update()
        self.changed.emit()

    def _view_rect(self):
        w, h = self.width() - 8, self.height() - 8
        vw = min(w, h * clips.OUT_W / clips.OUT_H)
        vh = vw * clips.OUT_H / clips.OUT_W
        return QRectF((self.width() - vw) / 2, (self.height() - vh) / 2, vw, vh)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        view = self._view_rect()
        p.fillRect(view, QColor("#111"))
        if self._pix is not None:
            f = view.width() / clips.OUT_W
            fr = self.framing()
            sw, sh = clips.scaled_size(fr)
            x, y = clips.crop_origin(fr)
            p.save()
            p.setClipRect(view)
            p.drawPixmap(QRectF(view.x() - x * f, view.y() - y * f, sw * f, sh * f),
                         self._pix, QRectF(self._pix.rect()))
            p.restore()
            if self.hook_text.strip():
                font = QFont()
                font.setPixelSize(max(8, round(84 * f)))
                font.setBold(True)
                p.setFont(font)
                p.setPen(QColor("white"))
                p.drawText(view, Qt.AlignCenter | Qt.TextWordWrap, self.hook_text.strip())
        else:
            p.setPen(QColor("#888"))
            p.drawText(view, Qt.AlignCenter | Qt.TextWordWrap, "Soltá o elegí un video\no una imagen")
        p.setPen(QPen(QColor(255, 255, 255, 110), 1))
        for i in (1, 2):
            gx = view.x() + view.width() * i / 3
            gy = view.y() + view.height() * i / 3
            p.drawLine(int(gx), int(view.top()), int(gx), int(view.bottom()))
            p.drawLine(int(view.left()), int(gy), int(view.right()), int(gy))
        p.setPen(QPen(QColor("#0078D4"), 2))
        p.drawRect(view)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_from = event.pos()
            self.setCursor(Qt.ClosedHandCursor)

    def mouseMoveEvent(self, event):
        if self._drag_from is None or self._pix is None:
            return
        delta = event.pos() - self._drag_from
        self._drag_from = QPoint(event.pos())
        f = self._view_rect().width() / clips.OUT_W
        sw, sh = clips.scaled_size(self.framing())
        if sw > clips.OUT_W:
            self.offset_x = max(0.0, min(1.0, self.offset_x - delta.x() / f / (sw - clips.OUT_W)))
        if sh > clips.OUT_H:
            self.offset_y = max(0.0, min(1.0, self.offset_y - delta.y() / f / (sh - clips.OUT_H)))
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, _event):
        self._drag_from = None
        self.setCursor(Qt.ArrowCursor)

    def wheelEvent(self, event):
        step = 0.1 if event.angleDelta().y() > 0 else -0.1
        self.set_zoom(self.zoom + step)
        self.changed.emit()


class _ExportThread(QThread):
    done = pyqtSignal(bool, str)

    def __init__(self, cmd, parent=None):
        super().__init__(parent)
        self._cmd = cmd

    def run(self):
        try:
            r = subprocess.run(self._cmd, capture_output=True, text=True, encoding='utf-8',
                               errors='replace', creationflags=_NO_WINDOW)
        except OSError as e:
            self.done.emit(False, str(e))
            return
        tail = '\n'.join((r.stderr or '').strip().splitlines()[-6:])
        self.done.emit(r.returncode == 0, tail)


class ClipDialog(QDialog):
    """Arma un clip 9:16 y escribe al lado un .txt con título y descripción del canal."""

    def __init__(self, ffmpeg_path, output_dir, channels=None, parent=None):
        super().__init__(parent)
        self._ffmpeg = ffmpeg_path
        self._channels = channels or {}
        self._tmp = tempfile.mkdtemp(prefix='clip_preview_')
        self._source = ''
        self._duration = None
        self._worker = None
        self._upload_worker = None
        self._txt_dirty = False
        self._frame_timer = QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.timeout.connect(self._refresh_frame)
        self.setAcceptDrops(True)
        self.setWindowTitle("Nuevo clip de Marca personal")
        self.setMinimumSize(900, 680)
        self.resize(1000, 760)
        self._build_ui(output_dir)
        self._on_preset_changed()

    # ---------- UI ----------
    def _build_ui(self, output_dir):
        root = QHBoxLayout(self)
        self.preview = FramePreview()
        self.preview.changed.connect(self._sync_zoom_slider)
        root.addWidget(self.preview, 2)

        right = QVBoxLayout()
        root.addLayout(right, 3)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        right.addLayout(form)

        self.preset_combo = QComboBox()
        for pid, label in _PRESET_LABELS:
            self.preset_combo.addItem(label, pid)
        self.preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        form.addRow("Preset:", self.preset_combo)

        self.source_edit, row = self._file_row(self._choose_source)
        self.source_label = QLabel("Video / fondo:")
        form.addRow(self.source_label, row)
        self.audio_edit, self.audio_row = self._file_row(self._choose_audio)
        self.audio_label = QLabel("Audio del beat:")
        form.addRow(self.audio_label, self.audio_row)
        self.audio_start = self._seconds_spin()
        self.audio_start_label = QLabel("Inicio en el beat:")
        form.addRow(self.audio_start_label, self.audio_start)

        self.start_spin = self._seconds_spin()
        self.start_spin.valueChanged.connect(self._on_times_changed)
        self.end_spin = self._seconds_spin()
        self.end_spin.valueChanged.connect(self._on_times_changed)
        times = QHBoxLayout()
        times.addWidget(self.start_spin)
        self.end_label = QLabel("Fin:")
        times.addWidget(self.end_label)
        times.addWidget(self.end_spin)
        self.hook_secs = QComboBox()
        for s in clips.HOOK_SECONDS_OPTIONS:
            self.hook_secs.addItem(f"{s} s", s)
        times.addWidget(self.hook_secs)
        self.times_label = QLabel("Inicio:")
        form.addRow(self.times_label, times)
        self.length_label = QLabel("")
        form.addRow("", self.length_label)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(100, int(clips.MAX_ZOOM * 100))
        self.zoom_slider.valueChanged.connect(lambda v: self.preview.set_zoom(v / 100))
        btn_center = QPushButton("Centrar")
        btn_center.clicked.connect(self.preview.center)
        zrow = QHBoxLayout()
        zrow.addWidget(self.zoom_slider, 1)
        zrow.addWidget(btn_center)
        form.addRow("Escala:", zrow)
        hint = QLabel("Arrastrá el preview para mover el encuadre; la rueda escala.")
        hint.setWordWrap(True)
        form.addRow("", hint)

        self.hook_edit = QPlainTextEdit()
        self.hook_edit.setPlaceholderText("Texto del hook")
        self.hook_edit.setMaximumHeight(80)
        self.hook_edit.textChanged.connect(self._on_hook_text)
        self.hook_label = QLabel("Texto del hook:")
        form.addRow(self.hook_label, self.hook_edit)

        self.name_edit = QLineEdit()
        self.name_edit.textChanged.connect(self._update_txt)
        form.addRow("Nombre:", self.name_edit)
        self.channel_combo = QComboBox()
        self.channel_combo.addItem("(sin canal)", "")
        for name in channel_names_for_section(self._channels, SECTION_PERSONAL):
            self.channel_combo.addItem(name, name)
        self.channel_combo.currentIndexChanged.connect(self._update_txt)
        form.addRow("Canal:", self.channel_combo)

        self.txt_edit = QPlainTextEdit()
        self.txt_edit.setMinimumHeight(100)
        self.txt_edit.textChanged.connect(self._on_txt_edited)
        self._txt_programmatic = False
        right.addWidget(QLabel("Título y descripción (.txt):"))
        right.addWidget(self.txt_edit, 1)

        self.out_edit, out_row = self._file_row(self._choose_output, folder=True)
        self.out_edit.setText(output_dir)
        orow = QFormLayout()
        orow.addRow("Carpeta:", out_row)
        right.addLayout(orow)

        self.check_youtube_upload = QCheckBox("Subir a YouTube al exportar (privado)")
        self.check_youtube_upload.setToolTip(
            "Sube el clip al canal elegido (conectalo antes en Gestión de Canales).")
        self.check_youtube_upload.stateChanged.connect(self._on_youtube_schedule_ui)
        right.addWidget(self.check_youtube_upload)
        yt_schedule = QHBoxLayout()
        self.check_schedule_publish = QCheckBox("Programar")
        self.check_schedule_publish.setEnabled(False)
        self.check_schedule_publish.stateChanged.connect(self._on_youtube_schedule_ui)
        yt_schedule.addWidget(self.check_schedule_publish)
        self.schedule_datetime = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        self.schedule_datetime.setCalendarPopup(True)
        self.schedule_datetime.setDisplayFormat("dd/MM/yyyy HH:mm")
        self.schedule_datetime.setEnabled(False)
        yt_schedule.addWidget(self.schedule_datetime, 1)
        right.addLayout(yt_schedule)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        right.addWidget(self.progress)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        right.addWidget(self.status)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.btn_close = QPushButton("Cerrar")
        self.btn_close.clicked.connect(self.reject)
        self.btn_export = QPushButton("Exportar")
        self.btn_export.setDefault(True)
        self.btn_export.clicked.connect(self._export)
        buttons.addWidget(self.btn_close)
        buttons.addWidget(self.btn_export)
        right.addLayout(buttons)

    def _file_row(self, slot, folder=False):
        edit = QLineEdit()
        edit.setReadOnly(not folder)
        btn = QPushButton("Elegir…")
        btn.clicked.connect(slot)
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(edit, 1)
        lay.addWidget(btn)
        return edit, row

    @staticmethod
    def _seconds_spin():
        s = QDoubleSpinBox()
        s.setDecimals(1)
        s.setSingleStep(0.5)
        s.setRange(0, 36000)
        s.setSuffix(" s")
        return s

    def _preset(self):
        return self.preset_combo.currentData()

    # ---------- Preset y tiempos ----------
    def _on_preset_changed(self):
        preset = self._preset()
        estudio, hook = preset == clips.PRESET_ESTUDIO, preset == clips.PRESET_HOOK
        for w in (self.audio_label, self.audio_row, self.audio_start_label, self.audio_start):
            w.setVisible(estudio)
        for w in (self.hook_label, self.hook_edit, self.hook_secs):
            w.setVisible(hook)
        for w in (self.end_label, self.end_spin):
            w.setVisible(not hook)
        self.source_label.setText("Fondo (imagen o video):" if hook else "Video:")
        self.times_label.setText("Inicio:")
        self._on_times_changed()

    def _on_times_changed(self):
        preset = self._preset()
        if preset == clips.PRESET_HOOK:
            self.length_label.setText("")
        else:
            length = self.end_spin.value() - self.start_spin.value()
            text = f"Duración: {max(length, 0):.1f} s"
            if preset == clips.PRESET_ESTUDIO and length > clips.MAX_ESTUDIO_SECONDS:
                text += f" (se exporta hasta {clips.MAX_ESTUDIO_SECONDS:.0f} s)"
            self.length_label.setText(text)
        self._frame_timer.start(400)

    def _on_hook_text(self):
        self.preview.hook_text = self.hook_edit.toPlainText()
        self.preview.update()

    def _sync_zoom_slider(self):
        self.zoom_slider.blockSignals(True)
        self.zoom_slider.setValue(round(self.preview.zoom * 100))
        self.zoom_slider.blockSignals(False)

    # ---------- Archivos ----------
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self._set_source(url.toLocalFile())
                break

    def _choose_source(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir video o imagen", "", _VIDEO_FILTER)
        if path:
            self._set_source(path)

    def _choose_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir audio del beat", "", _AUDIO_FILTER)
        if path:
            self.audio_edit.setText(path)

    def _choose_output(self):
        path = QFileDialog.getExistingDirectory(self, "Carpeta de salida", self.out_edit.text())
        if path:
            self.out_edit.setText(path)

    def _set_source(self, path):
        self._source = path
        self.source_edit.setText(path)
        if not self.name_edit.text().strip():
            self.name_edit.setText(os.path.splitext(os.path.basename(path))[0])
        self._duration = None if clips.is_image(path) else _probe_duration(self._ffmpeg, path)
        total = self._duration or 0
        for spin in (self.start_spin, self.end_spin):
            spin.blockSignals(True)
            spin.setMaximum(total or 36000)
        self.start_spin.setValue(0)
        self.end_spin.setValue(total)
        for spin in (self.start_spin, self.end_spin):
            spin.blockSignals(False)
        self.preview.offset_x = self.preview.offset_y = 0.5
        self.preview.set_zoom(1.0)
        self._sync_zoom_slider()
        self._on_times_changed()
        self._refresh_frame()

    def _refresh_frame(self):
        """Muestra un solo frame (nunca decodifica el video entero)."""
        if not self._source:
            return
        if clips.is_image(self._source):
            pix = QPixmap(self._source)
        else:
            frame = os.path.join(self._tmp, 'frame.png')
            if os.path.exists(frame):
                os.remove(frame)
            try:
                subprocess.run([self._ffmpeg, '-y', '-hide_banner', '-loglevel', 'error',
                                '-ss', f"{self.start_spin.value():.3f}", '-i', self._source,
                                '-frames:v', '1', frame],
                               capture_output=True, timeout=30, creationflags=_NO_WINDOW)
            except (OSError, subprocess.SubprocessError):
                pass
            pix = QPixmap(frame)
        if pix.isNull():
            self.status.setText("No se pudo leer un frame del archivo.")
            return
        self.status.setText("")
        self.preview.set_source(pix, pix.width(), pix.height())

    # ---------- Título y descripción ----------
    def _channel(self):
        return self.channel_combo.currentData() or ''

    def _render_txt(self):
        name = self.name_edit.text().strip()
        channel = self._channel()
        if not channel:
            return name
        cfg = self._channels.get(channel, {})
        groups = cfg.get('groups') or ['']
        tpl = channel_templates.get_title_template(cfg, global_default='{name}')
        title = channel_templates.render_title(tpl, name, channel, groups[0])
        desc = description.render_for_channel(channel, name)
        return f"{title}\n\n{desc}".strip() + "\n"

    def _update_txt(self):
        if self._txt_dirty:
            return
        self._txt_programmatic = True
        self.txt_edit.setPlainText(self._render_txt())
        self._txt_programmatic = False

    def _on_txt_edited(self):
        if not self._txt_programmatic:
            self._txt_dirty = True

    def _on_youtube_schedule_ui(self, _state=None):
        yt = self.check_youtube_upload.isChecked()
        self.check_schedule_publish.setEnabled(yt)
        sched = yt and self.check_schedule_publish.isChecked()
        self.schedule_datetime.setEnabled(sched)

    @staticmethod
    def _title_and_description(txt_body: str):
        """Primera línea = título; el resto = descripción."""
        text = (txt_body or '').strip()
        if not text:
            return '', ''
        parts = text.split('\n', 1)
        title = parts[0].strip()
        desc = parts[1].strip() if len(parts) > 1 else ''
        return title, desc

    def _start_youtube_upload(self, video_path: str, txt_body: str):
        channel = self._channel()
        if not channel:
            QMessageBox.warning(self, "YouTube", "Elegí un canal antes de subir.")
            return
        if not youtube.is_connected(channel):
            QMessageBox.warning(
                self, "YouTube",
                f"'{channel}' no está conectado. Conectalo en Gestión de Canales.")
            return
        title, desc = self._title_and_description(txt_body)
        if not title:
            QMessageBox.warning(self, "YouTube", "El .txt debe tener al menos un título (primera línea).")
            return
        publish_at = publish_at_from_qdatetime(
            self.check_schedule_publish.isChecked(), self.schedule_datetime.dateTime())
        job = {
            'channel': channel,
            'group': '',
            'path': video_path,
            'title': title,
            'description': desc,
            'tags': '',
            'thumbnail': None,
            'privacy': 'private',
            'publish_at': publish_at,
            'beat_id': None,
        }
        self.status.setText("Subiendo a YouTube…")
        self._upload_worker = YouTubeUploadWorker([job], self)
        self._upload_worker.progress.connect(self.status.setText)
        self._upload_worker.finished_all.connect(self._youtube_upload_finished)
        self._upload_worker.start()

    def _youtube_upload_finished(self, done, errors):
        if errors:
            self.status.setText("Exportado; problemas en YouTube:\n" + "\n".join(errors))
            QMessageBox.warning(self, "Subida a YouTube", "\n".join(errors))
            return
        if done:
            d = done[0]
            if d.get('publish_at'):
                self.status.setText(f"Exportado y programado en YouTube: {d.get('url', '')}")
            else:
                self.status.setText(f"Exportado y subido (privado): {d.get('url', '')}")

    # ---------- Export ----------
    def _export(self):
        preset = self._preset()
        if not self._ffmpeg:
            QMessageBox.warning(self, "FFmpeg", "No se encontró FFmpeg (bin/ffmpeg.exe o PATH).")
            return
        if not self._source or not self.preview.has_source():
            QMessageBox.warning(self, "Clip", "Elegí primero un video o una imagen.")
            return
        audio = self.audio_edit.text().strip()
        name = channel_templates.sanitize_filename(self.name_edit.text().strip() or 'clip')
        out_dir = self.out_edit.text().strip() or os.path.join('exported_videos', 'personal')
        try:
            os.makedirs(out_dir, exist_ok=True)
            output = clips.unique_path(os.path.join(out_dir, f"{name}.mp4"))
            cmd = clips.build_clip_cmd(
                preset, self._ffmpeg, self._source, output, self.preview.framing(),
                start=self.start_spin.value(), end=self.end_spin.value(),
                audio_path=audio, audio_start=self.audio_start.value(),
                hook_text=self.hook_edit.toPlainText(),
                hook_seconds=self.hook_secs.currentData())
        except (ValueError, OSError) as e:
            QMessageBox.warning(self, "Clip", str(e))
            return
        self._output = output
        self.btn_export.setEnabled(False)
        self.progress.setVisible(True)
        self.status.setText("Exportando…")
        self._worker = _ExportThread(cmd, self)
        self._worker.done.connect(self._on_export_done)
        self._worker.start()

    def _on_export_done(self, ok, detail):
        self.progress.setVisible(False)
        self.btn_export.setEnabled(True)
        if not ok:
            self.status.setText("FFmpeg falló:\n" + detail)
            return
        txt_path = os.path.splitext(self._output)[0] + ".txt"
        txt_body = self.txt_edit.toPlainText().strip() + "\n"
        try:
            with open(txt_path, 'w', encoding='utf-8') as f:
                f.write(txt_body)
        except OSError as e:
            self.status.setText(f"Video exportado, pero no se pudo escribir el .txt: {e}")
            return
        if self.check_youtube_upload.isChecked():
            self._start_youtube_upload(self._output, txt_body)
        else:
            self.status.setText(f"Exportado: {self._output}\n y {txt_path}")

    def done(self, result):
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait()
        if self._upload_worker is not None and self._upload_worker.isRunning():
            self._upload_worker.wait()
        shutil.rmtree(self._tmp, ignore_errors=True)
        super().done(result)
