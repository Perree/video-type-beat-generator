"""Desktop Beats remote actions, separate from local persistence."""
from copy import deepcopy
from PyQt5.QtWidgets import QDialog, QInputDialog
from core import beat_settings
from core.beat_cloud import Conflict, CloudError
from core.beat_panel_cloud import PanelCloud
from core.beat_dropbox_picker import DropboxPicker


class BeatRemoteForm:
    def browse_remote(self, target):
        if self.task is not None:
            return
        genre = None
        if target == 'images':
            genre, ok = QInputDialog.getText(self, 'Imágenes Dropbox', 'Género de esta carpeta:')
            genre = genre.strip()
            if not ok or not genre:
                return
            if len(genre) > 100 or any(c in genre for c in '=\r\n'):
                self.status.setText('Género inválido.')
                return
        picker = DropboxPicker(self, file=target == 'thumbnail', provider=self.cloud_provider)
        if picker.exec_() == QDialog.Accepted:
            self._apply_remote_selection(target, picker.selected_path, genre)
        picker.deleteLater()

    def _apply_remote_selection(self, target, path, genre=None):
        if target == 'videos':
            self.video_source.setCurrentIndex(self.video_source.findData('dropbox'))
            self.videos_folder.setText(path)
        elif target == 'thumbnail':
            self.thumbnail_source.setCurrentIndex(self.thumbnail_source.findData('dropbox'))
            self.thumbnail_path.setText(path)
        else:
            lines = self.dropbox_images.toPlainText().splitlines()
            lines = [line for line in lines if line.partition('=')[0].strip() != genre]
            lines.append(f'{genre}={path}')
            self.dropbox_images.setPlainText('\n'.join(lines))

    def reload_cloud_config(self):
        self.cloud_loaded = False
        app = None
        try:
            app = beat_settings.read_app(self.config_path)
        except Exception:
            self.status.setText('No se pudo leer la configuración local.')
            return

        def read(event, progress):
            config, rev = PanelCloud(self.cloud_provider()).read_config(event)
            if rev is not None:
                # Validate without accessing local folders in the UI thread.
                config = beat_settings.validate(config, app)
            return config, rev

        self._start(read, self._cloud_config_loaded)

    def _cloud_config_loaded(self, result):
        config, self.cloud_rev = result
        if self.cloud_rev is not None:
            self.config = deepcopy(config)
            self.selected = -1
            self.profile.setText(config.get('beatstars_profile_url', ''))
            self._refresh_list()
        self.cloud_loaded = True
        self.status.setText('Configuración remota cargada; editá y guardá por separado.' if self.cloud_rev else
                            'No existe config remota. Podés publicar el borrador local sin crear estado.')

    def save_cloud_config(self):
        if not self.cloud_loaded:
            self.status.setText('Recargá la configuración de Dropbox antes de publicar.')
            self.wizard_notify(False, 'Recargá la configuración de Dropbox antes de publicar.')
            return
        try:
            config, rev = self.draft(), self.cloud_rev
        except Exception:
            self.status.setText('Revisá la configuración antes de publicar.')
            self.wizard_notify(False, 'Revisá la configuración antes de publicar.')
            return

        def write(event, progress):
            try:
                return PanelCloud(self.cloud_provider()).save_config(config, rev, event)
            except Conflict:
                raise CloudError('Conflicto de revisión: recargá la configuración de Dropbox. El borrador se conserva.') from None

        # A canceled/lost response may already have committed: require reload on any failure.
        self.cloud_loaded = False
        self._start(write, self._cloud_config_saved)

    def _cloud_config_saved(self, rev):
        self.cloud_rev, self.cloud_loaded = rev, True
        # Flag del asistente de alta: la config (de todos los canales) ya está en Dropbox.
        for ch in self.config.get('channels', []):
            self.pilot_flag_set(ch['id'], 'config')
        self.status.setText('Configuración guardada en /type-beats/config.json. Estado remoto sin cambios.')
        self.wizard_notify(True)
