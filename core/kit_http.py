"""Credential-bearing HTTP: HTTPS only, no redirects/proxies, bounded responses."""
import math
import os
import urllib.request
from urllib.parse import urlsplit

JSON_LIMIT = 32 * 1024 * 1024
IMAGE_LIMIT = 24 * 1024 * 1024
DOWNLOAD_HOSTS_ENV = 'KIT_IMAGE_DOWNLOAD_HOSTS'
DOWNLOAD_HOSTS = {'oaidalleapiprodscus.blob.core.windows.net', 'api.openai.com'}


class HttpRejected(ValueError):
    """Fixed codes only; never include requests, credentials or signed URLs."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HttpRejected('redirect_rejected')


def https_url(url):
    try:
        parts = urlsplit(url)
        if (not isinstance(url, str) or len(url) > 8192 or parts.scheme != 'https'
                or not parts.hostname or parts.port not in (None, 443)
                or parts.username or parts.password or parts.fragment
                or '\\' in url or any(ord(c) <= 32 for c in url)):
            raise ValueError()
    except (TypeError, ValueError, AttributeError):
        raise HttpRejected('url_rejected') from None
    return parts


def image_url(url, base_url):
    """Only a provider host or explicitly trusted CDN may supply image bytes."""
    parts = https_url(url)
    allowed = DOWNLOAD_HOSTS | {https_url(base_url).hostname}
    allowed.update(h.strip().lower() for h in os.environ.get(DOWNLOAD_HOSTS_ENV, '').split(',')
                   if h.strip())
    if parts.hostname not in allowed:
        raise HttpRejected('image_host_rejected')
    return url


def open_request(request, timeout=60):
    https_url(request.full_url)
    try:
        seconds = float(timeout)
        if isinstance(timeout, bool) or not math.isfinite(seconds) or not 0 < seconds <= 180:
            raise ValueError()
    except (TypeError, ValueError, OverflowError):
        raise HttpRejected('timeout_rejected') from None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    return opener.open(request, timeout=seconds)


def read_response(response, limit=JSON_LIMIT):
    length = getattr(response, 'headers', {}).get('Content-Length')
    if length is not None and (not str(length).isdecimal() or int(length) > limit):
        raise HttpRejected('response_limit')
    data = response.read(limit + 1)
    if len(data) > limit:
        raise HttpRejected('response_limit')
    return data
