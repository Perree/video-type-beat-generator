"""Read-only Beats Dropbox assets and deterministic per-channel/genre rotation."""
import os
import time
from pathlib import PurePosixPath
from core.beat_download import dropbox_path
from core.beat_http import BeatError
from core.beat_rotation import changed_image

IMAGE_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp'}


class DropboxAssets:
    def __init__(self, client):
        self.client = client

    @classmethod
    def from_env(cls):
        import dropbox
        from core.beat_dropbox_http import DropboxSession

        key, token = (os.environ.get(k) for k in ('BEAT_DROPBOX_APP_KEY', 'BEAT_DROPBOX_REFRESH_TOKEN'))
        if not key or not token:
            raise BeatError('missing_beat_dropbox_credentials')
        session = DropboxSession()
        return cls(dropbox.Dropbox(app_key=key, oauth2_refresh_token=token,
                                  session=session, timeout=15, max_retries_on_error=0,
                                  max_retries_on_rate_limit=0))

    def list_images(self, folder):
        return self._list_assets(folder, IMAGE_SUFFIXES, 20 * 1024 * 1024)

    def list_videos(self, folder):
        return self._list_assets(folder, {'.mp4', '.mov', '.mkv', '.webm'}, 150 * 1024 * 1024)

    def _list_assets(self, folder, suffixes, max_bytes):
        folder = dropbox_path(folder)
        try:
            page = self.client.files_list_folder(folder, recursive=False, limit=1000)
            result = []
            for _ in range(10):
                for entry in page.entries:
                    path = getattr(entry, 'path_lower', None)
                    size = getattr(entry, 'size', None)
                    if path and type(size) is int and 0 < size <= max_bytes:
                        dropbox_path(path)
                        if (PurePosixPath(path).parent == PurePosixPath(folder.lower())
                                and PurePosixPath(path).suffix in suffixes):
                            result.append({'path': path, 'rev': entry.rev, 'size': size})
                if len(result) > 5000:
                    raise BeatError('image_catalog_limit')
                if not page.has_more:
                    return sorted(result, key=lambda v: v['path'])
                page = self.client.files_list_folder_continue(page.cursor)
            raise BeatError('image_catalog_limit')
        except BeatError:
            raise
        except Exception:
            raise BeatError('image_catalog_failed') from None

    def download(self, path, target, limit, rev=None):
        dropbox_path(path)
        deadline = time.monotonic() + 180
        response = None
        try:
            metadata = self.client.files_get_metadata(path)
            if type(metadata.size) is not int or not 0 < metadata.size <= limit:
                raise BeatError('download_limit')
            if rev is not None and metadata.rev != rev:
                raise BeatError('asset_changed')
            meta, response = self.client.files_download(path, rev=metadata.rev)
            if meta.rev != metadata.rev or meta.size != metadata.size:
                raise BeatError('asset_changed')
            size = 0
            with target.open('wb') as stream:
                for chunk in response.iter_content(65536):
                    if time.monotonic() >= deadline:
                        raise BeatError('download_timeout')
                    size += len(chunk)
                    if size > limit:
                        raise BeatError('download_limit')
                    stream.write(chunk)
            if size != metadata.size:
                raise BeatError('download_incomplete')
        except BeatError:
            raise
        except Exception:
            raise BeatError('asset_download_failed') from None
        finally:
            if response is not None:
                response.close()


def select_image(channel, genre, state, job, dropbox):
    folders = channel.get('dropbox_images', {})
    if not isinstance(folders, dict) or genre not in channel.get('genres', []):
        raise BeatError('image_genre_unconfigured')
    folder = dropbox_path(folders.get(genre))
    catalog = dropbox.list_images(folder)
    if not catalog:
        raise BeatError('image_catalog_empty')
    history = state.get('image_rotation', {}).get(channel['id'], {}).get(genre, [])
    if not isinstance(history, list):
        raise BeatError('invalid_image_history')
    previous = next((row for row in history if row.get('job_id') == job['id']), None)
    if previous:
        selected = next((row for row in catalog if row['path'] == previous['path']), None)
        if selected is None:
            raise BeatError('reserved_image_missing')
        if selected['rev'] != previous.get('rev'):
            raise BeatError('asset_changed')
        return selected
    catalog = changed_image(catalog, state, job)
    used = {row['path']: i for i, row in enumerate(history)}
    return min(catalog, key=lambda row: (used.get(row['path'], -1), row['path']))
