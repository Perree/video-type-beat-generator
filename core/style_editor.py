# -*- coding: utf-8 -*-
"""Editor del estilo de video y miniatura de un canal, con vista previa en vivo.

Estilos listos + controles simples. La vista previa usa un fondo real del canal y un título de
ejemplo; «Probar con un beat» genera 10 segundos de video para verlo de verdad.
"""
import os
import shutil
import subprocess
import tempfile
from copy import deepcopy

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QImage, QPixmap
from PyQt5.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                             QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
                             QRadioButton, QSlider, QVBoxLayout, QWidget)

from core import channel_profile as cp
from core import manual_render as mr
from core import style as st
from core.cloud_worker import CallWorker
from core.ffmpeg_util import resolve_tool

SAMPLE = '(BEAT PRO-527) [juice wrld, sad] This is for me - 160bpm - key A Minor'
CUSTOM = 'Personalizado'


def _pixmap(img, width):
    img = img.convert('RGB')
    data = img.tobytes('raw', 'RGB')
    qimage = QImage(data, img.width, img.height, img.width * 3, QImage.Format_RGB888).copy()
    return QPixmap.fromImage(qimage).scaledToWidth(width, Qt.SmoothTransformation)


def sample_background(root, channel, mode):
    """Una imagen de ejemplo del canal: la primera imagen, o un cuadro del primer video."""
    from PIL import Image
    images = cp.media(root, channel, cp.MODE_IMAGE)[0]
    videos = cp.media(root, channel, cp.MODE_VIDEO)[0]
    if mode == cp.MODE_VIDEO and videos or not images and videos:
        ffmpeg = resolve_tool('ffmpeg')
        if ffmpeg:
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, 'frame.png')
                subprocess.run([ffmpeg, '-v', 'error', '-y', '-ss', '2', '-i', videos[0], '-frames:v', '1', out],
                               stdin=subprocess.DEVNULL, capture_output=True,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if os.path.isfile(out):
                    with Image.open(out) as img:
                        return img.convert('RGB')
    if images:
        with Image.open(images[0]) as img:
            return img.convert('RGB')
    return Image.new('RGB', st.FRAME, (40, 40, 60))


class StyleEditor(QDialog):
    def __init__(self, root, channel, parent=None):
        super().__init__(parent)
        self.root, self.channel = root, channel
        self.setWindowTitle(f'Estilo de video y miniatura — {channel}')
        self.setStyleSheet('QDialog { background-color: #2b2b2b; }')
        self.resize(1080, 720)
        self.profile = cp.load(root, channel)
        self.style = st.from_profile(self.profile)
        if 'estilo' not in self.profile and cp.media(root, channel, 'thumbnail')[0]:
            self.style['miniatura']['origen'] = 'miniaturas'
        self.title = mr.beat_title(self.profile, SAMPLE, channel)
        self.logo_path = os.path.join(cp.channel_dir(root, channel), st.LOGO_FILE)
        self.background = sample_background(root, channel, self.profile['fondo'])
        self.worker = None
        self._loading = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self.refresh_preview)
        self._build()
        self._load(self.style)

    # --- UI ---

    def _build(self):
        outer = QHBoxLayout(self)
        left = QVBoxLayout()
        row = QHBoxLayout()
        row.addWidget(QLabel('Estilo listo:'))
        self.preset = QComboBox()
        self.preset.addItems(list(st.PRESETS) + [CUSTOM])
        self.preset.activated.connect(self._apply_preset)
        row.addWidget(self.preset, 1)
        left.addLayout(row)

        video = QGroupBox('Video')
        form = QFormLayout(video)
        framing = QHBoxLayout()
        self.crop = QRadioButton('Llenar la pantalla')
        self.blur = QRadioButton('Centrado, fondo difuminado')
        self.bars = QRadioButton('Centrado con barras')
        group = QButtonGroup(self)
        for button in (self.crop, self.blur, self.bars):
            group.addButton(button)
            framing.addWidget(button)
            button.toggled.connect(self._changed)
        form.addRow('Encuadre:', framing)
        # Un solo ancho para el video y la miniatura: la foto no cambia las barras.
        self.bars_width = QSlider(Qt.Horizontal)
        self.bars_width.setRange(st.BARS_MIN, st.BARS_MAX)
        self.bars_width.valueChanged.connect(self._changed)
        self.bars_label = QLabel()
        self.bars_color_button = QPushButton('Color de las barras…')
        self.bars_color_button.clicked.connect(lambda: self._pick_color('barras_color'))
        bars_row = QHBoxLayout()
        bars_row.addWidget(self.bars_width, 1)
        bars_row.addWidget(self.bars_label)
        bars_row.addWidget(self.bars_color_button)
        self.bars_box = QWidget()
        self.bars_box.setLayout(bars_row)
        bars_row.setContentsMargins(0, 0, 0, 0)
        form.addRow('Ancho de cada barra:', self.bars_box)
        self.bars_note = QLabel('La miniatura usa el mismo ancho de barra.')
        form.addRow('', self.bars_note)
        self.darken = QSlider(Qt.Horizontal)
        self.darken.setRange(0, 80)
        self.darken.valueChanged.connect(self._changed)
        form.addRow('Oscurecer:', self.darken)
        tint_row = QHBoxLayout()
        self.tint_button = QPushButton('Elegir tinte…')
        self.tint_button.clicked.connect(lambda: self._pick_color('tinte'))
        self.tint_clear = QPushButton('Sin tinte')
        self.tint_clear.clicked.connect(lambda: self._set_color('tinte', ''))
        tint_row.addWidget(self.tint_button)
        tint_row.addWidget(self.tint_clear)
        form.addRow('Tinte de color:', tint_row)
        self.grain = QCheckBox('Grano (textura de película)')
        self.title_on = QCheckBox('Título sobre el video')
        self.title_pos = QComboBox()
        self.title_pos.addItems(['arriba', 'centro', 'abajo'])
        title_row = QHBoxLayout()
        title_row.addWidget(self.title_on)
        title_row.addWidget(self.title_pos)
        self.logo_on = QCheckBox('Logo / marca de agua')
        self.logo_pick = QPushButton('Elegir logo…')
        self.logo_pick.clicked.connect(self._pick_logo)
        logo_row = QHBoxLayout()
        logo_row.addWidget(self.logo_on)
        logo_row.addWidget(self.logo_pick)
        self.zoom = QCheckBox('Zoom lento (solo con imagen fija)')
        self.fade = QCheckBox('Fundido al empezar y al terminar')
        for widget in (self.grain, self.title_on, self.logo_on, self.zoom, self.fade):
            widget.toggled.connect(self._changed)
        self.title_pos.currentIndexChanged.connect(self._changed)
        form.addRow('', self.grain)
        form.addRow('', title_row)
        form.addRow('', logo_row)
        form.addRow('', self.zoom)
        form.addRow('', self.fade)
        left.addWidget(video)

        thumb = QGroupBox('Miniatura')
        form = QFormLayout(thumb)
        self.template = QComboBox()
        for key, label in (('solo', 'Solo la imagen'), ('franja', 'Título en franja abajo'),
                           ('grande', 'Título grande al centro'), ('logo', 'Imagen con logo')):
            self.template.addItem(label, key)
        self.font = QComboBox()
        self.font.addItems(list(st.FONTS))
        color_row = QHBoxLayout()
        self.color_button = QPushButton('Color del texto…')
        self.color_button.clicked.connect(lambda: self._pick_color('color'))
        color_row.addWidget(self.color_button)
        self.outline = QCheckBox('Contorno negro')
        color_row.addWidget(self.outline)
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(50, 200)
        self.origin = QComboBox()
        for key, label in (('fondo', 'El mismo fondo del video'), ('miniaturas', 'Carpeta «miniaturas» del canal'),
                           ('video', 'Un cuadro del video')):
            self.origin.addItem(label, key)
        for widget in (self.template, self.font, self.origin):
            widget.currentIndexChanged.connect(self._changed)
        self.size.valueChanged.connect(self._changed)
        self.outline.toggled.connect(self._changed)
        form.addRow('Plantilla:', self.template)
        form.addRow('Fuente:', self.font)
        form.addRow('', color_row)
        form.addRow('Tamaño del texto:', self.size)
        form.addRow('Imagen de la miniatura:', self.origin)
        left.addWidget(thumb)
        left.addStretch(1)
        outer.addLayout(left, 1)

        right = QVBoxLayout()
        right.addWidget(QLabel('<b>Así se ve el video</b>'))
        self.video_preview = QLabel()
        self.video_preview.setMinimumSize(520, 293)
        right.addWidget(self.video_preview)
        right.addWidget(QLabel('<b>Así se ve la miniatura</b>'))
        self.thumb_preview = QLabel()
        self.thumb_preview.setMinimumSize(384, 216)
        right.addWidget(self.thumb_preview)
        self.speed = QLabel()
        self.speed.setWordWrap(True)
        right.addWidget(self.speed)
        self.test_button = QPushButton('▶ Probar con un beat (10 segundos)…')
        self.test_button.clicked.connect(self.test_render)
        right.addWidget(self.test_button)
        self.test_status = QLabel()
        self.test_status.setWordWrap(True)
        self.test_status.setVisible(False)
        self.test_status.setText = self._status_text  # se muestra solo cuando hay algo que decir
        right.addWidget(self.test_status)
        right.addStretch(1)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Guardar estilo')
        buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        right.addWidget(buttons)
        outer.addLayout(right, 1)

    # --- Estado ↔ controles ---

    def _load(self, style):
        self._loading = True
        v, m = style['video'], style['miniatura']
        {'difuminado': self.blur, 'barras': self.bars}.get(v['encuadre'], self.crop).setChecked(True)
        self.bars_width.setValue(v['barras'])
        self.darken.setValue(v['oscurecer'])
        self.grain.setChecked(v['grano'])
        self.title_on.setChecked(v['titulo'])
        self.title_pos.setCurrentText(v['titulo_pos'])
        self.logo_on.setChecked(v['logo'])
        self.zoom.setChecked(v['zoom'])
        self.fade.setChecked(v['fundido'])
        self.template.setCurrentIndex(self.template.findData(m['plantilla']))
        self.font.setCurrentText(m['fuente'])
        self.outline.setChecked(m['contorno'])
        self.size.setValue(m['tamano'])
        self.origin.setCurrentIndex(self.origin.findData(m['origen']))
        self.style = deepcopy(style)
        self._loading = False
        self._sync_preset()
        self.refresh_preview()

    def current(self):
        style = deepcopy(self.style)
        v, m = style['video'], style['miniatura']
        encuadre = 'difuminado' if self.blur.isChecked() else 'barras' if self.bars.isChecked() else 'recortar'
        v.update(encuadre=encuadre, barras=self.bars_width.value(), oscurecer=self.darken.value(),
                 grano=self.grain.isChecked(), titulo=self.title_on.isChecked(),
                 titulo_pos=self.title_pos.currentText(), logo=self.logo_on.isChecked(), zoom=self.zoom.isChecked(),
                 fundido=self.fade.isChecked())
        m.update(plantilla=self.template.currentData(), fuente=self.font.currentText(),
                 contorno=self.outline.isChecked(), tamano=self.size.value(), origen=self.origin.currentData())
        return st.validate(style)

    def _changed(self, *_):
        if self._loading:
            return
        self.style = self.current()
        self._sync_preset()
        self.timer.start()

    def _sync_preset(self):
        match = next((name for name in st.PRESETS if st.preset(name) == self._comparable(self.style)), CUSTOM)
        self.preset.setCurrentText(match)

    @staticmethod
    def _comparable(style):
        style = deepcopy(style)
        style['miniatura']['origen'] = 'fondo'
        return style

    def _apply_preset(self, _index):
        name = self.preset.currentText()
        if name == CUSTOM:
            return
        style = st.preset(name)
        style['miniatura']['origen'] = self.style['miniatura']['origen']  # dónde sale la imagen no cambia
        self._load(style)

    def _pick_color(self, which):
        part = 'video' if which in ('tinte', 'barras_color') else 'miniatura'
        initial = QColor(self.style[part][which] or '#ffffff')
        color = QColorDialog.getColor(initial, self, 'Elegí un color')
        if color.isValid():
            self._set_color(which, color.name())

    def _set_color(self, which, value):
        part = 'video' if which in ('tinte', 'barras_color') else 'miniatura'
        self.style[part][which] = value
        self._sync_preset()
        self.refresh_preview()

    def _pick_logo(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Logo (PNG con fondo transparente)', '', 'Imágenes (*.png *.jpg)')
        if path:
            from PIL import Image
            with Image.open(path) as img:
                img.convert('RGBA').save(self.logo_path, 'PNG')
            self.logo_on.setChecked(True)
            self.refresh_preview()

    # --- Vista previa ---

    def refresh_preview(self):
        style = self.style
        on = style['video']['encuadre'] == 'barras'
        for widget in (self.bars_box, self.bars_note):
            widget.setVisible(on)
        self.bars_label.setText(f"{style['video']['barras']} %")
        frame = st.render_frame(self.background, style, self.title, self.logo_path)
        self.video_preview.setPixmap(_pixmap(frame, 520))
        thumb = st.render_thumbnail(self.background, style, self.title, self.logo_path)
        self.thumb_preview.setPixmap(_pixmap(thumb, 384))
        notes = []
        if self.profile['fondo'] == cp.MODE_VIDEO and st.video_overlays(style):
            notes.append('🐢 Con video stock, oscurecer, tinte, título, logo o fundido hacen que cada video tarde más '
                         '(se procesa entero, ~1 min por beat).')
        elif self.profile['fondo'] == cp.MODE_VIDEO:
            if on:
                notes.append('Con barras, la primera vez de cada ancho se prepara el video stock (puede tardar un minuto).')
            notes.append('⚡ Rápido: el video stock se copia sin procesar (~6 s por beat).')
        if style['video']['zoom'] and self.profile['fondo'] == cp.MODE_IMAGE:
            notes.append('🐢 El zoom lento procesa cada cuadro: tarda más que una imagen quieta.')
        if style['video']['zoom'] and self.profile['fondo'] == cp.MODE_VIDEO:
            notes.append('El zoom solo se aplica con imagen fija (este canal usa video stock).')
        if style['video']['logo'] and not os.path.isfile(self.logo_path):
            notes.append('Falta el logo: tocá «Elegir logo…».')
        self.speed.setText('<br>'.join(notes))
        self.speed.setVisible(bool(notes))

    # --- Probar y guardar ---

    def test_render(self):
        if self.worker is not None:
            return
        beat, _ = QFileDialog.getOpenFileName(self, 'Elegí un beat para probar', '',
                                              'Audio (' + ' '.join('*' + s for s in mr.AUDIO_SUFFIXES) + ')')
        if not beat:
            return
        style, profile = self.style, dict(self.profile)
        root, channel = self.root, self.channel

        def work():
            ffmpeg = resolve_tool('ffmpeg')
            if not ffmpeg:
                raise mr.ManualError('No se encontró FFmpeg.')
            tmp = tempfile.mkdtemp(prefix='prueba-estilo-')
            clip = os.path.join(tmp, mr.beat_name(beat) + '.mp3')
            subprocess.run([ffmpeg, '-v', 'error', '-y', '-i', beat, '-t', '10', '-c:a', 'libmp3lame', clip],
                           check=True, stdin=subprocess.DEVNULL, capture_output=True,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            mode = profile['fondo']
            content = cp.media(root, channel, mode)[0]
            if not content:
                raise mr.ManualError('El canal no tiene fondos para probar.')
            thumbs = cp.media(root, channel, 'thumbnail')[0]
            title = mr.beat_title(profile, mr.beat_name(beat), channel)
            return mr.render_beat(clip, mode, content[0], title, tmp, mr.Tools(), thumbs[0] if thumbs else None,
                                  style=style, logo_path=os.path.join(cp.channel_dir(root, channel), st.LOGO_FILE))

        self.worker = CallWorker(work, 'No se pudo generar la prueba.', self)
        self.worker.done.connect(self._tested)
        self.worker.failed.connect(lambda text: self.test_status.setText(f'✗ {text}'))
        self.worker.finished.connect(self._test_finished)
        self.test_button.setEnabled(False)
        self.test_status.setText('Generando 10 segundos de prueba…')
        self.worker.start()

    def _status_text(self, text):
        QLabel.setText(self.test_status, text)
        self.test_status.setVisible(bool(text))

    def _tested(self, result):
        self.test_status.setText('✓ Listo: se abrió la carpeta de la prueba.')
        try:
            os.startfile(result['folder'])  # noqa: S606 - carpeta temporal recién creada
        except OSError:
            self.test_status.setText(f'✓ Listo: {result["folder"]}')

    def _test_finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self.test_button.setEnabled(True)

    def save(self):
        try:
            style = self.current()
            profile = dict(self.profile, estilo=style, miniatura_con_titulo=style['miniatura']['plantilla'] == 'franja')
            self.profile = cp.save(self.root, self.channel, profile)
        except (st.StyleError, cp.ProfileError) as exc:
            QMessageBox.warning(self, 'Estilo', str(exc))
            return
        self.accept()

    def done(self, result):
        if self.worker is not None:
            self.worker.wait(100)
        super().done(result)
