"""Beats-only adapter: the insert result returns before thumbnail side effects."""
from core import youtube


class BeatYouTube:
    def __init__(self, tokens_dir):
        self.tokens_dir = tokens_dir

    def upload(self, **kwargs):
        # Shared upload catches only HttpError for thumbnails. A timeout there
        # would otherwise hide an already-created video's ID from our journal.
        kwargs['thumbnail'] = None
        return youtube.upload(**kwargs, tokens_dir=self.tokens_dir)

    def thumbnail(self, channel, video_id, path):
        from googleapiclient.http import MediaFileUpload
        service = youtube._service(youtube._load_credentials(channel, self.tokens_dir))
        service.thumbnails().set(videoId=video_id,
            media_body=MediaFileUpload(str(path))).execute()
