"""Public BeatStars short links (https://bsta.rs/...) for the description; read-only and best effort."""
import re
import time
from core.beat_http import PublicTransport
from core.beat_queries import PROFILE_QUERY, SHARE_QUERY
from core.beat_source import profile_username

SHORT_LINK = re.compile(r'https://bsta\.rs/[A-Za-z0-9]{4,20}')


class ShareLinks:
    """Lazily maps track ID -> short link for one profile. Never raises: callers fall back to the page URL."""

    def __init__(self, transport=None):
        self.transport = transport or PublicTransport()
        self._links = {}
        self._loaded = False

    def _load(self, profile_url):
        self._loaded = True
        deadline = time.monotonic() + 120
        try:
            username = profile_username(profile_url)
            profile = self.transport.query(PROFILE_QUERY, {'username': username}, deadline)['profileByUsername']
            member = profile['memberId']
            if (not re.fullmatch(r'MR[0-9]{1,20}', member)
                    or profile['username'].casefold() != username.casefold()):
                return
            for page in range(100):
                data = self.transport.query(SHARE_QUERY, {
                    'memberId': member, 'page': page, 'size': 50}, deadline)['profileTracks']
                if data['number'] != page or not isinstance(data['content'], list) or len(data['content']) > 50:
                    return
                for raw in data['content']:
                    link = raw.get('shareUrl')
                    if (isinstance(raw.get('id'), str) and isinstance(link, str)
                            and SHORT_LINK.fullmatch(link) and raw['profile']['memberId'] == member):
                        self._links[raw['id']] = link
                if data['last']:
                    return
        except Exception:
            return

    def get(self, track_id, profile_url):
        if not self._loaded:
            self._load(profile_url)
        return self._links.get(track_id)
