"""Desktop Beats remote actions: Dropbox is the only persistence (no app_config.json)."""
from copy import deepcopy
from PyQt5.QtWidgets import QDialog, QInputDialog
from core import beat_settings
from core.beat_cloud import CloudError
from core.beat_tasks import Cancelled
from core.cloud_merge import MergeConflict
from core.beat_panel_cloud import PanelCloud
from core.beat_dropbox_picker import DropboxPicker, start_folder


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
        current = {'videos': self.videos_folder.text(), 'thumbnail': self.thumbnail_path.text()}.get(target, '')
        picker = DropboxPicker(self, file=target == 'thumbnail', provider=self.cloud_provider,
                               start=start_folder(current, file=target == 'thumbnail'))
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
        """Lee config de Beats, registro de canales y ajustes de Dropbox (en un hilo)."""
        self.cloud_loaded = False

        def read(event, progress):
            data = PanelCloud(self.cloud_provider()).read_all(event)
            try:
                # Plantillas del registro compiladas; sin tocar carpetas locales en la UI.
                data['compiled'] = beat_settings.settings(data['config'], data['registry'])
            except ValueError:
                data['compiled'] = None
            return data

        self._start(read, self._cloud_config_loaded)

    def _cloud_config_loaded(self, data):
        self.cloud_base, self.cloud_rev = deepcopy(data['config']), data['rev']
        self.registry, self.registry_rev = deepcopy(data['registry']), data['registry_rev']
        self.registry_base = deepcopy(data['registry'])
        self.ajustes = data['ajustes']
        self.cloud_loaded = True
        if data['compiled'] is None:
            self.config_readable = False
            self._set_editable(False)
            self.status.setText('La configuración de Dropbox tiene valores inválidos. '
                                'No se sobrescribirá: corregila y recargá.')
            return
        self.config = data['compiled']
        self.config_readable = True
        self._fill_channels()
        profile = self.config.get('beatstars_profile_url') or (
            (self.ajustes.get('beatstars') or {}).get('profile_url') or '')
        self.selected = -1
        self.profile.setText(profile)
        self._refresh_list()
        self._set_editable(True)
        if self.registry_rev is None:
            self.status.setText('No existe /automatizacion/canales.json en Dropbox: falta la '
                                'migración (scripts/migrate_to_cloud.py --apply).')
        elif self.cloud_rev is None:
            self.status.setText('No existe config remota. «Publicar al robot» la crea sin estado.')
        else:
            self.status.setText('Configuración cargada de Dropbox.')
        self.refresh_publish_readiness()

    def save_cloud_config(self):
        if not self.cloud_loaded or not self.config_readable:
            self.status.setText('Recargá la configuración de Dropbox antes de publicar.')
            self.wizard_notify(False, 'Recargá la configuración de Dropbox antes de publicar.')
            return False
        try:
            config = self.draft()
        except Exception as exc:
            text = (f'No se publicó: {exc}' if isinstance(exc, ValueError)
                    else 'Revisá la configuración antes de publicar.')
            self.status.setText(text)
            self.wizard_notify(False, text)
            return False
        registry, registry_base, registry_rev = (deepcopy(self.registry), self.registry_base,
                                                 self.registry_rev)
        base, rev = self.cloud_base, self.cloud_rev

        def write(event, progress):
            service = PanelCloud(self.cloud_provider())
            try:
                if registry != registry_base:
                    progress('Guardando el registro de canales…')
                    reg_doc, reg_rev = service.save_registry(registry, registry_base,
                                                             registry_rev, event)
                else:
                    reg_doc, reg_rev = registry_base, registry_rev
                progress('Publicando /type-beats/config.json…')
                doc, new_rev = service.save_config_merged(config, base, rev, reg_doc, event)
            except MergeConflict as exc:
                routes = ', '.join(c['ruta'] for c in exc.choques[:5])
                raise CloudError('Conflicto: otra PC cambió los mismos campos '
                                 f'({routes}). Recargá; el borrador se conserva.') from None
            except Cancelled:
                raise
            except CloudError:
                # Mensajes del transporte: nunca a la UI (pueden traer datos de Dropbox).
                raise CloudError('No se confirmó el guardado en Dropbox. '
                                 'Recargá antes de reintentar.') from None
            except ValueError as exc:
                raise CloudError(f'No se publicó: {exc}') from None
            except Exception:
                raise CloudError('No se confirmó el guardado en Dropbox. '
                                 'Recargá antes de reintentar.') from None
            return dict(config=doc, rev=new_rev, registry=reg_doc, registry_rev=reg_rev,
                        draft=config)

        # A canceled/lost response may already have committed: require reload on any failure.
        self.cloud_loaded = False
        self._start(write, self._cloud_config_saved)
        return True

    def _cloud_config_saved(self, result):
        self.cloud_base, self.cloud_rev = deepcopy(result['config']), result['rev']
        self.registry_base, self.registry_rev = deepcopy(result['registry']), result['registry_rev']
        self.registry = deepcopy(result['registry'])
        self.cloud_loaded = True
        if result['config'] != result['draft']:
            # Se fusionaron cambios de otra PC: mostrar el documento publicado.
            row = self.selected
            self.config = deepcopy(result['config'])
            self.selected = -1
            self._fill_channels()
            self._refresh_list(max(0, min(row, len(self.config['channels']) - 1)))
        # Flag del asistente de alta: la config (de todos los canales) ya está en Dropbox.
        for ch in self.config.get('channels', []):
            self.pilot_flag_set(ch['id'], 'config')
        self.status.setText('Publicado en /type-beats/config.json y en el registro de canales. '
                            'Estado remoto sin cambios.')
        self.wizard_notify(True)
