"""Resolve only the reserved public track; no temporary URLs in state/logs."""
import re
import time
from core.beat_http import BeatError, PublicTransport
from core.beat_queries import PROFILE_QUERY, PREVIEWS_QUERY
from core.beat_source import profile_username


class PreviewResolver:
    def __init__(self, transport=None):
        self.transport = transport or PublicTransport()

    def resolve(self, track, profile_url):
        tid = track.get('id')
        ref = track.get('preview_ref', {})
        if (not isinstance(tid, str) or not re.fullmatch(r'TK[0-9]{1,20}', tid)
                or ref.get('provider') != 'beatstars' or ref.get('track_id') != tid
                or ref.get('v2_id') != tid[2:]):
            raise BeatError('invalid_preview_reference')
        deadline = time.monotonic() + 120
        try:
            profile = self.transport.query(PROFILE_QUERY, {
                'username': profile_username(profile_url)}, deadline)['profileByUsername']
            member = profile['memberId']
            if (not re.fullmatch(r'MR[0-9]{1,20}', member)
                    or profile['username'].casefold() != profile_username(profile_url).casefold()):
                raise BeatError('profile_mismatch')
            for page in range(100):
                data = self.transport.query(PREVIEWS_QUERY, {
                    'memberId': member, 'page': page, 'size': 50}, deadline)['profileTracks']
                if (data['number'] != page or type(data['last']) is not bool
                        or not isinstance(data['content'], list) or len(data['content']) > 50):
                    raise BeatError('pagination_rejected')
                for raw in data['content']:
                    if raw['id'] == tid:
                        if raw['profile']['memberId'] != member:
                            raise BeatError('owner_mismatch')
                        hls = (raw.get('bundle') or {}).get('hls') or {}
                        if not hls.get('url'):
                            raise BeatError('preview_unavailable')
                        return hls['url'], hls.get('duration')
                if data['last']:
                    break
        except BeatError:
            raise
        except Exception:
            raise BeatError('preview_resolution_failed') from None
        raise BeatError('preview_unavailable')
