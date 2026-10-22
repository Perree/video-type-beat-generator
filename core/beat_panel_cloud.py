"""Desktop-only Dropbox connection, bounded browsing and config-only CAS.

Never initializes cloud documents. Workers keep using DropboxTransport.from_env.
"""
import time

from core.beat_cloud import BeatCloud, CloudError, Conflict, DropboxTransport
from core.beat_download import dropbox_path
from core.beat_tasks import checkpoint, Cancelled

def _valid(value, limit):
    return (isinstance(value, str) and 1 <= len(value) <= limit
            and not any(c.isspace() or ord(c) < 32 for c in value))


def local_transport(credentials=None):
    """Transporte de Dropbox del escritorio: llavero de Windows; si no, ``BEAT_DROPBOX_*``.

    Nunca lee ``tokens/``. ``credentials`` (``{app_key, refresh_token}``) solo para tests.
    """
    try:
        if credentials is None:
            from core import cloud_login
            try:
                credentials = cloud_login.dropbox_credentials()
            except cloud_login.LoginError:
                credentials = None  # sin llavero: queda el entorno
        if credentials is None:
            return DropboxTransport.from_env()
        if not isinstance(credentials, dict) or not all(
                _valid(credentials.get(k), 4096) for k in ('app_key', 'refresh_token')):
            raise ValueError()
        import dropbox
        from core.beat_dropbox_http import DropboxSession
        return DropboxTransport(dropbox.Dropbox(
            app_key=credentials['app_key'], oauth2_refresh_token=credentials['refresh_token'],
            session=DropboxSession(), timeout=30, max_retries_on_error=0,
            max_retries_on_rate_limit=0))
    except Exception:
        raise CloudError('No se pudo conectar Dropbox. Conectalo en Conexiones '
                         '(o definí BEAT_DROPBOX_*).') from None


class PanelCloud:
    def __init__(self, transport):
        self.transport = transport

    def list_folder(self, path, event):
        """Only immediate children, at most 10 pages / 2000 entries / 120 s."""
        from dropbox.files import FolderMetadata, FileMetadata
        try:
            if path:
                dropbox_path(path)
            checkpoint(event)
            deadline = time.monotonic() + 120
            rows, cursor, count = [], None, 0
            for page in range(10):
                checkpoint(event)
                if time.monotonic() >= deadline:
                    raise ValueError()
                result = self.transport._call(
                    lambda: self.transport.client.files_list_folder_continue(cursor)
                    if cursor else self.transport.client.files_list_folder(
                        path, recursive=False, limit=200, include_deleted=False))
                checkpoint(event)
                count += len(result.entries)
                if time.monotonic() >= deadline or count > 2000:
                    raise ValueError()
                for entry in result.entries:
                    if not isinstance(entry, (FolderMetadata, FileMetadata)):
                        continue
                    child = dropbox_path(entry.path_display)
                    # Paths are relative to the app's visible root. Reject non-children.
                    if child.rsplit('/', 1)[0].casefold() != path.casefold():
                        raise ValueError()
                    rows.append(dict(path=child, name=entry.name,
                                     folder=isinstance(entry, FolderMetadata)))
                if not result.has_more:
                    return sorted(rows, key=lambda row: (not row['folder'], row['name'].casefold()))
                cursor = result.cursor
                if not isinstance(cursor, str) or not cursor:
                    raise ValueError()
            raise ValueError()
        except Cancelled:
            raise
        except Exception:
            raise CloudError('No se pudo listar Dropbox (autorización, carpeta o límite de navegación).') from None

    def read_config(self, event):
        try:
            checkpoint(event)
            result = BeatCloud(self.transport, retries=1).read('config')
            checkpoint(event)
            return result
        except Cancelled:
            raise
        except Exception:
            raise CloudError('No se pudo cargar la configuración de Dropbox.') from None

    def save_config(self, config, rev, event):
        try:
            checkpoint(event)
            # Single CAS attempt: no update(), initialize(), state write or conflict retry.
            return BeatCloud(self.transport, retries=1).write(
                'config', config, rev, before_write=lambda: checkpoint(event))
        except (Cancelled, Conflict):
            raise
        except Exception:
            raise CloudError('No se confirmó el guardado en Dropbox. Recargá antes de reintentar.') from None

    def read_all(self, event):
        """Config de Beats + registro de canales + ajustes, todo de Dropbox (sin escribir)."""
        from core.cloud_registry import CloudRegistry, RegistryError
        try:
            checkpoint(event)
            registry = CloudRegistry(self.transport)
            canales, canales_rev = registry.read('canales')
            checkpoint(event)
            ajustes, ajustes_rev = registry.read('ajustes')
            checkpoint(event)
            config, rev = BeatCloud(self.transport, retries=1).read('config')
            checkpoint(event)
            return dict(config=config, rev=rev, registry=canales, registry_rev=canales_rev,
                        ajustes=ajustes, ajustes_rev=ajustes_rev)
        except Cancelled:
            raise
        except RegistryError as exc:
            raise CloudError(f'Registro de canales inválido en Dropbox: {exc}') from None
        except Exception:
            raise CloudError('No se pudo cargar la configuración de Dropbox.') from None

    def save_registry(self, mine, base, rev, event):
        """``canales.json`` por CAS con merge por campo ante un conflicto de rev."""
        from core.cloud_registry import CloudRegistry
        checkpoint(event)
        return CloudRegistry(self.transport).save('canales', mine, base, rev)

    def save_config_merged(self, config, base, rev, registry, event):
        """``/type-beats/config.json`` por CAS; ante Conflict relee y fusiona con ``base``."""
        from core import beat_settings, cloud_merge
        cloud = BeatCloud(self.transport, retries=1)
        checkpoint(event)
        return cloud_merge.save_merged(
            lambda: cloud.read('config'),
            lambda doc, current: cloud.write('config', doc, current,
                                             before_write=lambda: checkpoint(event)),
            base, config, rev, (Conflict,),
            prepare=lambda doc: beat_settings.validate(doc, registry))
