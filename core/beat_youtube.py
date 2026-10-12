"""Beats-only adapter: the insert result returns before thumbnail side effects."""
from core import youtube
import re


class BeatYouTube:
    def __init__(self, tokens_dir):
        self.tokens_dir = tokens_dir

    def check_owner(self, channel, expected_id):
        if not isinstance(expected_id, str) or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', expected_id):
            raise ValueError('youtube_owner_unconfigured')
        service = youtube._service(youtube._load_credentials(channel, self.tokens_dir))
        rows = service.channels().list(part='id', mine=True).execute().get('items', [])
        if len(rows) != 1 or rows[0].get('id') != expected_id:
            raise ValueError('youtube_owner_mismatch')

    def upload(self, **kwargs):
        # Shared upload catches only HttpError for thumbnails. A timeout there
        # would otherwise hide an already-created video's ID from our journal.
        kwargs['thumbnail'] = None
        return youtube.upload(**kwargs, tokens_dir=self.tokens_dir)

    def thumbnail(self, channel, video_id, path):
        from googleapiclient.http import MediaFileUpload
        service = youtube._service(youtube._load_credentials(channel, self.tokens_dir))
        media = MediaFileUpload(str(path))
        try:
            service.thumbnails().set(videoId=video_id, media_body=media).execute()
        finally:
            media.stream().close()
