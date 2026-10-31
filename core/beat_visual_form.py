"""Small per-channel visual editor for the Beats panel only."""
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QLineEdit, QDoubleSpinBox, QHBoxLayout, QLabel,
                             QPushButton, QFileDialog, QPlainTextEdit)
from core.beat_visual import options
import ui_theme as theme


class BeatVisualForm:
    def _build_seo(self, form):
        """Campos de filtro y metadata SEO por canal (pestaña SEO y tendencias)."""
        self.selection_tags = QLineEdit()
        self.selection_tags.setPlaceholderText("Separados por comas; vacío conserva la selección anterior")
        self.tags = QLineEdit()
        self.tags.setPlaceholderText("Separados por comas")
        form.addRow("Tags para elegir beats", self.selection_tags)
        form.addRow("Tags de YouTube", self.tags)
        self._build_templates(form)

    def _build_templates(self, form):
        """Plantillas del canal: se guardan en /automatizacion/canales.json (registro)."""
        self.use_templates = QCheckBox("Usar estas plantillas para el título y la descripción")
        form.addRow("Plantillas", self.use_templates)
        self.title_template = QLineEdit()
        self.title_template.setPlaceholderText('[Type] {name} | Free for Profit')
        form.addRow("Título", self.title_template)
        self.description_template = QPlainTextEdit()
        self.description_template.setMinimumHeight(120)
        self.description_template.setPlaceholderText('{name} Type Beat\n\n{beatstars_url}\n\n{socials}')
        form.addRow("Descripción", self.description_template)
        self.socials, self.hashtags = QLineEdit(), QLineEdit()
        form.addRow("Redes", self.socials)
        form.addRow("Hashtags", self.hashtags)
        hint = theme.muted(QLabel("Podés usar {name}, {beatstars_url} o {url}, {channel}, {socials}, "
                                  "{hashtags} y {tags}. Se guardan al publicar."))
        form.addRow("", hint)

    def _template_fields(self):
        return {'title_template': self.title_template.text().strip(),
                'description_template': self.description_template.toPlainText(),
                'socials': self.socials.text().strip(), 'hashtags': self.hashtags.text().strip()}

    def _load_templates(self, channel, saved, key=None):
        self._templates_key = key
        saved = saved or {}
        self.use_templates.setChecked(channel.get('use_channel_templates') is True)
        self.title_template.setText(saved.get('title_template', ''))
        self.description_template.setPlainText(saved.get('description_template', ''))
        self.socials.setText(saved.get('socials', ''))
        self.hashtags.setText(saved.get('hashtags', ''))

    def _store_templates(self, channel, row):
        """Vuelca el formulario al canal y a su ficha; no agrega claves que no cambiaron."""
        if channel is not None and (self.use_templates.isChecked()
                                    or 'use_channel_templates' in channel):
            channel['use_channel_templates'] = self.use_templates.isChecked()
        if row is None:
            return
        current = row.get('plantillas') or {}
        changed = {key: value for key, value in self._template_fields().items()
                   if value != current.get(key, '')}
        if changed:
            row['plantillas'] = dict(current, **changed)

    def _build_visual(self, form, more=None):
        """Filas del fondo en ``form``; fragmentos y miniatura (poco usados) en ``more``."""
        more = form if more is None else more
        self.visual_mode = QComboBox()
        self.visual_mode.addItem('Imagen fija', 'image')
        self.visual_mode.addItem('Montaje de videos', 'video')
        self.visual_mode.addItem('Alternar imagen y video', 'alternate')
        form.addRow('Tipo de fondo', self.visual_mode)
        self.dropbox_images = QPlainTextEdit()
        self.dropbox_images.setMaximumHeight(80)
        self.dropbox_images.setPlaceholderText('trap=/type-beats/images/trap (una carpeta por género)')
        form.addRow('Imágenes por género', self.dropbox_images)
        button = QPushButton('Elegir carpeta de Dropbox…')
        button.clicked.connect(lambda: self.browse_remote('images'))
        form.addRow('', theme.button_row(button))
        self.video_source = QComboBox()
        self.video_source.addItem('Carpeta local', 'local')
        self.video_source.addItem('Dropbox', 'dropbox')
        form.addRow('Videos desde', self.video_source)
        self.videos_folder = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(self.videos_folder)
        button = QPushButton('Carpeta local…')
        button.clicked.connect(self._browse_videos)
        row.addWidget(button)
        button = QPushButton('Dropbox…')
        button.clicked.connect(lambda: self.browse_remote('videos'))
        row.addWidget(button)
        form.addRow('Carpeta de videos', row)
        self.clip_min, self.clip_max = QDoubleSpinBox(), QDoubleSpinBox()
        row = QHBoxLayout()
        for widget, value in ((self.clip_min, 3), (self.clip_max, 6)):
            widget.setRange(.5, 30)
            widget.setDecimals(2)
            widget.setSuffix(' s')
            widget.setValue(value)
            row.addWidget(widget)
        more.addRow('Largo de cada clip (mín. / máx.)', row)
        self.thumbnail_source = QComboBox()
        for label, value in (('Automática', 'auto'), ('Archivo local', 'local'), ('Dropbox', 'dropbox')):
            self.thumbnail_source.addItem(label, value)
        more.addRow('Miniatura', self.thumbnail_source)
        self.thumbnail_path = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(self.thumbnail_path)
        button = QPushButton('Archivo local…')
        button.clicked.connect(self._browse_thumbnail)
        row.addWidget(button)
        button = QPushButton('Dropbox…')
        button.clicked.connect(lambda: self.browse_remote('thumbnail'))
        row.addWidget(button)
        more.addRow('Archivo de miniatura', row)

    def _browse_videos(self):
        path = QFileDialog.getExistingDirectory(self, 'Carpeta de videos', self.videos_folder.text())
        if path:
            self.video_source.setCurrentIndex(0)
            self.videos_folder.setText(path)

    def _browse_thumbnail(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Miniatura', self.thumbnail_path.text(),
                                             'Imágenes (*.png *.jpg *.jpeg *.jfif *.webp)')
        if path:
            self.thumbnail_source.setCurrentIndex(1)
            self.thumbnail_path.setText(path)

    def _store_visual(self, channel):
        # Preserve unknown future fields and existing catalog configuration.
        channel.setdefault('visual', {}).update(
            mode=self.visual_mode.currentData(), video_source=self.video_source.currentData(),
            videos_folder=self.videos_folder.text().strip(), clip_min_seconds=self.clip_min.value(),
            clip_max_seconds=self.clip_max.value(), thumbnail_source=self.thumbnail_source.currentData(),
            thumbnail_path=self.thumbnail_path.text().strip())
        folders = {}
        for line in self.dropbox_images.toPlainText().splitlines():
            if line.strip():
                genre, separator, path = line.partition('=')
                if not separator or not genre.strip() or genre.strip() in folders:
                    # Keep the invalid draft so validation cannot silently discard it.
                    channel['dropbox_images'] = None
                    channel['_dropbox_images_draft'] = self.dropbox_images.toPlainText()
                    return
                folders[genre.strip()] = path.strip()
        channel['dropbox_images'] = folders
        channel.pop('_dropbox_images_draft', None)

    def _load_visual(self, channel):
        # Drafts may be invalid: loading them must not validate/raise in a Qt slot.
        spec = options({})
        spec.update(channel.get('visual', {}))
        for combo, key in ((self.visual_mode, 'mode'), (self.video_source, 'video_source'),
                           (self.thumbnail_source, 'thumbnail_source')):
            combo.setCurrentIndex(combo.findData(spec[key]))
        self.videos_folder.setText(spec['videos_folder'])
        self.clip_min.setValue(spec['clip_min_seconds'])
        self.clip_max.setValue(spec['clip_max_seconds'])
        self.thumbnail_path.setText(spec['thumbnail_path'])
        folders = channel.get('dropbox_images', {})
        self.dropbox_images.setPlainText(channel.get('_dropbox_images_draft',
            '\n'.join(f'{genre}={path}' for genre, path in folders.items())
            if isinstance(folders, dict) else ''))
