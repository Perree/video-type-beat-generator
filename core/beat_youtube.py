"""Beats-only adapter: the insert result returns before thumbnail side effects."""
from core import youtube
import re
import time
from core.beat_google import service


class BeatYouTube:
    def __init__(self, tokens_dir):
        self.tokens_dir = tokens_dir

    def service(self, channel):
        return service(youtube._token_path(channel, self.tokens_dir))

    def check_owner(self, channel, expected_id):
        if not isinstance(expected_id, str) or not re.fullmatch(r'UC[A-Za-z0-9_-]{22}', expected_id):
            raise ValueError('youtube_owner_unconfigured')
        rows = self.service(channel).channels().list(part='id', mine=True).execute().get('items', [])
        if len(rows) != 1 or rows[0].get('id') != expected_id:
            raise ValueError('youtube_owner_mismatch')

    def calendar(self, channel, max_videos=200):
        """Videos del canal para el calendario (ver youtube.list_channel_calendar)."""
        return youtube.list_channel_calendar(channel, self.tokens_dir, max_videos)

    def upload(self, **kwargs):
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError
        # One resumable insert; never restart an insert after an ambiguous error.
        deadline = time.monotonic() + 1800
        client = self.service(kwargs['channel'])
        status = {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False}
        if kwargs.get('publish_at'):
            status['publishAt'] = kwargs['publish_at']
        body = {'snippet': {'title': kwargs['title'].replace('<', '').replace('>', '')[:100],
                'description': kwargs.get('description', '').replace('<', '').replace('>', '')[:5000],
                'tags': youtube._split_tags(kwargs.get('tags')), 'categoryId': youtube.CATEGORY_MUSIC},
                'status': status}
        media = MediaFileUpload(kwargs['video_path'], chunksize=8 * 1024 * 1024,
                                resumable=True, mimetype='video/mp4')
        try:
            request = client.videos().insert(part='snippet,status', body=body, media_body=media)
            response, retries = None, 0
            while response is None:
                if time.monotonic() >= deadline:
                    raise TimeoutError('youtube_deadline_exceeded')
                try:
                    _, response = request.next_chunk()
                    retries = 0
                except HttpError as exc:
                    if exc.resp.status not in (500, 502, 503, 504) or retries >= 5:
                        raise
                    delay = 2 ** retries
                    if time.monotonic() + delay >= deadline:
                        raise TimeoutError('youtube_deadline_exceeded') from None
                    time.sleep(delay)
                    retries += 1
            return {'youtube_id': response['id'], 'thumbnail_error': ''}
        finally:
            media.stream().close()

    def thumbnail(self, channel, video_id, path):
        from googleapiclient.http import MediaFileUpload
        client = self.service(channel)
        media = MediaFileUpload(str(path))
        try:
            client.thumbnails().set(videoId=video_id, media_body=media).execute()
        finally:
            media.stream().close()
