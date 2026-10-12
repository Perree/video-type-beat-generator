"""Beats-only authenticated HTTPS session without proxies or redirects."""
import requests
from core.beat_http import BeatError, check_url


class DropboxSession(requests.Session):
    def __init__(self):
        super().__init__()
        self.trust_env = False

    def send(self, request, **kwargs):
        check_url(request.url, {'api.dropboxapi.com', 'content.dropboxapi.com'})
        kwargs['allow_redirects'] = False
        response = super().send(request, **kwargs)
        if 300 <= response.status_code < 400:
            response.close()
            raise BeatError('redirect_rejected')
        return response
