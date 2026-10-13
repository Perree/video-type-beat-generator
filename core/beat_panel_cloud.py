"""Desktop-only Dropbox connection, bounded browsing and config-only CAS.

Never initializes cloud documents. Workers keep using DropboxTransport.from_env.
"""
from pathlib import Path
import time

from core.beat_cloud import BeatCloud, CloudError, Conflict, DropboxTransport, decode_document
from core.beat_download import dropbox_path
from core.beat_tasks import checkpoint, Cancelled

TOKEN_FILE = Path(__file__).resolve().parents[1] / 'tokens/dropbox_worker.json'


def local_transport(token_path=None):
    path = Path(token_path) if token_path is not None else TOKEN_FILE
    try:
        if not path.exists():
            return DropboxTransport.from_env()
        with path.open('rb') as stream:
            raw = stream.read(16385)
        if len(raw) > 16384:
            raise ValueError()
        data = decode_document(raw)
        if not isinstance(data, dict):
            raise ValueError()
        for field in ('app_key', 'refresh_token'):
            value = data.get(field)
            if (not isinstance(value, str) or not 1 <= len(value) <= 4096
                    or any(c.isspace() or ord(c) < 32 for c in value)):
                raise ValueError()
        import dropbox
        from core.beat_dropbox_http import DropboxSession
        return DropboxTransport(dropbox.Dropbox(
            app_key=data['app_key'], oauth2_refresh_token=data['refresh_token'],
            session=DropboxSession(), timeout=30, max_retries_on_error=0,
            max_retries_on_rate_limit=0))
    except Exception:
        raise CloudError('No se pudo conectar Dropbox. Revisá la autorización local o BEAT_DROPBOX_*.') from None


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
