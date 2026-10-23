# -*- coding: utf-8 -*-
"""Diálogo para editar el perfil de estilo de un canal (modo Manual)."""
import os

from PyQt5.QtWidgets import (QButtonGroup, QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                             QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
                             QPlainTextEdit, QPushButton, QRadioButton, QVBoxLayout)

from core import channel_profile as cp
from core import beat_title as bt
from core import manual_render as mr

SAMPLE = '(BEAT PRO-527) [juice wrld, sad] This is for me - 160bpm - key A Minor'
SAMPLE_PLAIN = 'Legends Fall'
VARIABLES_HELP = ('{name} nombre limpio · {artist} artista · {bpm} · {key} tono · {mood} · {channel}\n'
                  '[[ … ]] = bloque opcional: desaparece si le falta algún dato, '
                  'p. ej. [[({mood})]] o [[{key} · ]]')


def open_folder(path):
    os.makedirs(path, exist_ok=True)
    os.startfile(path)  # noqa: S606 - carpeta local del canal


class ProfileEditor(QDialog):
    """Edita ``perfil.json``; ``created`` queda con el nombre si se duplicó el canal."""

    def __init__(self, root, name, parent=None):
        super().__init__(parent)
        self.root, self.name, self.created = root, name, None
        self.setWindowTitle(f'Perfil del canal — {name}')
        self.setMinimumWidth(640)
        self.setStyleSheet('QDialog { background-color: #2b2b2b; }')  # textos claros del tema
        self.profile = cp.load(root, name)
        self._build()
        self._fill(self.profile)

    def _build(self):
        layout = QVBoxLayout(self)
        conflicts = cp.conflicts(self.root, self.name)
        if conflicts:
            warn = QLabel('⚠ Dropbox dejó copias en conflicto en la carpeta del canal: '
                          + ', '.join(conflicts) + '. Revisalas y borrá la que sobre.')
            warn.setWordWrap(True)
            warn.setStyleSheet('color: #d98e04;')
            layout.addWidget(warn)
        form = QFormLayout()
        mode_row = QHBoxLayout()
        self.radio_image = QRadioButton('Imagen')
        self.radio_video = QRadioButton('Video stock')
        group = QButtonGroup(self)
        group.addButton(self.radio_image)
        group.addButton(self.radio_video)
        mode_row.addWidget(self.radio_image)
        mode_row.addWidget(self.radio_video)
        mode_row.addStretch()
        form.addRow('Fondo:', mode_row)

        media_row = QHBoxLayout()
        self.media_label = QLabel()
        media_row.addWidget(self.media_label, 1)
        folder = cp.channel_dir(self.root, self.name)
        for text, sub in (('Abrir fondos', cp.BACKGROUNDS_DIR), ('Abrir miniaturas', cp.THUMBNAILS_DIR)):
            button = QPushButton(text)
            button.clicked.connect(lambda _c=False, s=sub: open_folder(os.path.join(folder, s)))
            media_row.addWidget(button)
        form.addRow('Contenido:', media_row)

        self.title_edit = QLineEdit()
        self.title_edit.setToolTip(VARIABLES_HELP)
        self.title_edit.textChanged.connect(self._refresh_preview)
        form.addRow('Título:', self.title_edit)
        self.title_preview = QLabel()
        self.title_preview.setWordWrap(True)
        form.addRow('', self.title_preview)
        self.artists_edit = QLineEdit()
        self.artists_edit.setPlaceholderText('Juice WRLD, Lil Peep  (así se escriben en el título)')
        self.artists_edit.setToolTip('Si el nombre del beat menciona uno de estos artistas, se usa con esta '
                                     'escritura en {artist}. Si no, se toma del primer [corchete] del nombre.')
        self.artists_edit.textChanged.connect(self._refresh_preview)
        form.addRow('Artistas:', self.artists_edit)

        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setMinimumHeight(140)
        self.desc_edit.setToolTip(VARIABLES_HELP + '\nAdemás: {tags} {socials} {hashtags} {beatstars_url}')
        form.addRow('Descripción:', self.desc_edit)
        self.socials_edit = QPlainTextEdit()
        self.socials_edit.setMaximumHeight(70)
        form.addRow('Redes ({socials}):', self.socials_edit)
        self.hashtags_edit = QLineEdit()
        form.addRow('Hashtags:', self.hashtags_edit)
        self.tags_edit = QLineEdit()
        self.tags_edit.setToolTip('Separados por coma. Usan las mismas variables; un tag con una variable '
                                  'vacía (p. ej. {artist} sin artista) se omite.')
        self.tags_edit.textChanged.connect(self._refresh_preview)
        form.addRow('Tags:', self.tags_edit)
        self.tags_count = QLabel()
        form.addRow('', self.tags_count)
        self.thumb_check = QCheckBox('Poner el título sobre la miniatura')
        form.addRow('', self.thumb_check)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText('Guardar')
        buttons.button(QDialogButtonBox.Cancel).setText('Cancelar')
        self.btn_duplicate = buttons.addButton('Duplicar como…', QDialogButtonBox.ActionRole)
        self.btn_duplicate.clicked.connect(self._duplicate)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _fill(self, profile):
        (self.radio_video if profile['fondo'] == cp.MODE_VIDEO else self.radio_image).setChecked(True)
        self.title_edit.setText(profile['titulo'])
        self.desc_edit.setPlainText(profile['descripcion'])
        self.socials_edit.setPlainText(profile['socials'])
        self.hashtags_edit.setText(profile['hashtags'])
        self.tags_edit.setText(', '.join(profile['tags']))
        self.artists_edit.setText(', '.join(profile['artistas']))
        self.thumb_check.setChecked(profile['miniatura_con_titulo'])
        images, img_remote = cp.media(self.root, self.name, cp.MODE_IMAGE)
        videos, vid_remote = cp.media(self.root, self.name, cp.MODE_VIDEO)
        thumbs, _ = cp.media(self.root, self.name, 'thumbnail')
        remote = len(img_remote) + len(vid_remote)
        self.media_label.setText(f'{len(images)} imágenes · {len(videos)} videos · {len(thumbs)} miniaturas'
                                 + (f' · ⚠ {remote} sin bajar de Dropbox' if remote else ''))
        self._refresh_preview()

    def form_profile(self):
        """Perfil armado con lo que hay en el formulario (sin validar)."""
        return dict(self.profile,
                    fondo=cp.MODE_VIDEO if self.radio_video.isChecked() else cp.MODE_IMAGE,
                    titulo=self.title_edit.text().strip(),
                    descripcion=self.desc_edit.toPlainText(),
                    socials=self.socials_edit.toPlainText(),
                    hashtags=self.hashtags_edit.text().strip(),
                    tags=[t.strip() for t in self.tags_edit.text().split(',') if t.strip()],
                    artistas=[a.strip() for a in self.artists_edit.text().split(',') if a.strip()],
                    miniatura_con_titulo=self.thumb_check.isChecked())

    def _refresh_preview(self):
        profile = self.form_profile()
        if not profile['titulo']:
            self.title_preview.setText('La plantilla está vacía.')
            return
        values = mr.beat_values(profile, SAMPLE, self.name)
        title = mr.beat_title(profile, SAMPLE, self.name)
        full = ' '.join(bt.fill(profile['titulo'], values).split())
        note = ' — se corta a 100 caracteres' if len(full) > cp.TITLE_MAX else ''
        plain = mr.beat_title(profile, SAMPLE_PLAIN, self.name)
        self.title_preview.setText(f'Ej.: {title}  ({len(title)}/100{note})\nSin datos: {plain}')
        tags = cp.render_tags(profile, values)
        total = len(', '.join(tags))
        dropped = len(profile['tags']) - len(tags)
        self.tags_count.setText(f'{total}/500 caracteres'
                                + (f' — {dropped} tags no entran o están repetidos' if dropped > 0 else ''))

    def _save(self):
        try:
            self.profile = cp.save(self.root, self.name, self.form_profile())
        except cp.ProfileError as exc:
            QMessageBox.warning(self, 'Perfil inválido', str(exc))
            return False
        self.accept()
        return True

    def _duplicate(self):
        new, ok = QInputDialog.getText(self, 'Duplicar canal',
                                       'Nombre del canal nuevo (mismo estilo, fondos vacíos):',
                                       text=f'{self.name} 2')
        if not ok or not new.strip():
            return
        try:
            cp.save(self.root, self.name, self.form_profile())
            cp.duplicate(self.root, self.name, new.strip())
        except cp.ProfileError as exc:
            QMessageBox.warning(self, 'No se pudo duplicar', str(exc))
            return
        self.created = new.strip()
        self.accept()
