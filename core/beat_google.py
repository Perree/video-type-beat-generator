"""Beats-only Google transport: fixed hosts, no proxy/redirect, bounded requests."""
import time
from core.beat_http import check_url

HOSTS = {'oauth2.googleapis.com', 'www.googleapis.com', 'youtube.googleapis.com'}


def service(token_path, *, clock=time.monotonic, seconds=1800):
    import httplib2
    from google.oauth2.credentials import Credentials
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build
    from core.youtube import SCOPES

    deadline = clock() + seconds

    class BoundedHttp(httplib2.Http):
        def request(self, uri, *args, **kwargs):
            check_url(uri, HOSTS)
            remaining = deadline - clock()
            if remaining <= 0:
                raise TimeoutError('youtube_deadline_exceeded')
            self.timeout = min(30, remaining)
            response, content = super().request(uri, *args, **kwargs)
            if clock() >= deadline:
                raise TimeoutError('youtube_deadline_exceeded')
            if 300 <= response.status < 400 and response.status != 308:
                raise ValueError('youtube_redirect_rejected')
            return response, content

    http = BoundedHttp(timeout=30, proxy_info=None)
    http.follow_redirects = False
    http.redirect_codes -= {308}
    creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    authorized = AuthorizedHttp(creds, http=http, max_refresh_attempts=1)
    return build('youtube', 'v3', http=authorized, cache_discovery=False, static_discovery=True)
