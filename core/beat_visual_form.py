"""Small per-channel visual editor for the Beats panel only."""
from PyQt5.QtWidgets import QComboBox, QLineEdit, QDoubleSpinBox, QHBoxLayout, QPushButton, QFileDialog, QPlainTextEdit
from core.beat_visual import options


class BeatVisualForm:
    def _build_visual(self, form):
        self.visual_mode = QComboBox()
        self.visual_mode.addItem('Imagen fija', 'image')
        self.visual_mode.addItem('Montaje de videos', 'video')
        form.addRow('Modo visual:', self.visual_mode)
        self.dropbox_images = QPlainTextEdit()
        self.dropbox_images.setMaximumHeight(80)
        self.dropbox_images.setPlaceholderText('trap=/type-beats/images/trap (una carpeta por género)')
        form.addRow('Imágenes Dropbox (género=carpeta):', self.dropbox_images)
        self.video_source = QComboBox()
        self.video_source.addItem('Carpeta local', 'local')
        self.video_source.addItem('Dropbox', 'dropbox')
        form.addRow('Origen de videos:', self.video_source)
        self.videos_folder = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(self.videos_folder)
        button = QPushButton('Elegir carpeta local…')
        button.clicked.connect(self._browse_videos)
        row.addWidget(button)
        form.addRow('Carpeta de videos:', row)
        self.clip_min, self.clip_max = QDoubleSpinBox(), QDoubleSpinBox()
        row = QHBoxLayout()
        for widget, value in ((self.clip_min, 3), (self.clip_max, 6)):
            widget.setRange(.5, 30)
            widget.setDecimals(2)
            widget.setSuffix(' s')
            widget.setValue(value)
            row.addWidget(widget)
        form.addRow('Fragmentos (mínimo / máximo):', row)
        self.thumbnail_source = QComboBox()
        for label, value in (('Automática', 'auto'), ('Archivo local', 'local'), ('Dropbox', 'dropbox')):
            self.thumbnail_source.addItem(label, value)
        form.addRow('Imagen de miniatura:', self.thumbnail_source)
        self.thumbnail_path = QLineEdit()
        row = QHBoxLayout()
        row.addWidget(self.thumbnail_path)
        button = QPushButton('Elegir imagen local…')
        button.clicked.connect(self._browse_thumbnail)
        row.addWidget(button)
        form.addRow('Archivo de miniatura:', row)

    def _browse_videos(self):
        path = QFileDialog.getExistingDirectory(self, 'Carpeta de videos', self.videos_folder.text())
        if path:
            self.video_source.setCurrentIndex(0)
            self.videos_folder.setText(path)

    def _browse_thumbnail(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Miniatura', self.thumbnail_path.text(),
                                             'Imágenes (*.png *.jpg *.jpeg *.webp)')
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
