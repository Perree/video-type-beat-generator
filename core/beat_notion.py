"""Read one JSON code block, with separate Beats credentials and fixed HTTPS host."""
import os
import re
import time
import urllib.parse
import urllib.request
from core.beat_cloud import decode_document
from core.beat_seo_report import MAX_BYTES


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _read_response(response, deadline, clock):
    """read1 performs at most one underlying read; check budget between chunks."""
    chunks, size = [], 0
    while True:
        if clock() >= deadline:
            raise ValueError()
        chunk = response.read1(min(64 * 1024, 2_000_001 - size))
        if type(chunk) is not bytes:
            raise ValueError()
        size += len(chunk)
        if size > 2_000_000 or clock() >= deadline:
            raise ValueError()
        if not chunk:
            return b''.join(chunks)
        chunks.append(chunk)


def read_report_file(path):
    try:
        with open(path, 'rb') as stream:
            payload = stream.read(MAX_BYTES + 1)
        if len(payload) > MAX_BYTES:
            raise ValueError()
        return payload
    except Exception:
        raise ValueError('seo_report_file_rejected') from None


def fetch_report(env=None, *, opener=None, clock=time.monotonic):
    """Direct page children only, at most 10 pages/2 MB each/60 s total.

    A report is a single json code block. Never concatenate multiple reports,
    follow links, execute blocks, retrieve attachments, or truncate oversized JSON.
    """
    env = os.environ if env is None else env
    token, page = env.get('BEAT_NOTION_TOKEN'), env.get('BEAT_NOTION_PAGE_ID')
    if (type(token) is not str or not token or len(token) > 512
            or any(ord(c) < 33 or ord(c) > 126 for c in token)
            or type(page) is not str or not re.fullmatch(
                r'(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})', page)):
        raise ValueError('seo_notion_unconfigured')
    opener = opener or urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    deadline, cursor, payload = clock() + 60, None, None
    seen = set()
    try:
        for _ in range(10):
            remaining = deadline - clock()
            if remaining <= 0:
                raise ValueError()
            url = 'https://api.notion.com/v1/blocks/' + page.replace('-', '') + '/children?page_size=100'
            if cursor:
                url += '&start_cursor=' + urllib.parse.quote(cursor, safe='')
            req = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + token,
                'Notion-Version': '2022-06-28'})
            with opener.open(req, timeout=min(15, remaining)) as response:
                if response.status != 200 or response.geturl() != url:
                    raise ValueError()
                if response.headers.get_content_type() != 'application/json':
                    raise ValueError()
                data = _read_response(response, deadline, clock)
            if len(data) > 2_000_000 or clock() > deadline:
                raise ValueError()
            data = decode_document(data.decode('utf-8'))
            rows = data['results']
            if type(rows) is not list or len(rows) > 100 or type(data['has_more']) is not bool:
                raise ValueError()
            for block in rows:
                if type(block) is not dict:
                    raise ValueError()
                if block.get('type') != 'code':
                    continue
                code = block['code']
                if code.get('language') != 'json':
                    continue
                parts = code['rich_text']
                if type(parts) is not list or len(parts) > 100:
                    raise ValueError()
                pieces = []
                size = 0
                for part in parts:
                    value = part['plain_text']
                    if type(value) is not str:
                        raise ValueError()
                    encoded = value.encode('utf-8')
                    size += len(encoded)
                    if size > MAX_BYTES:
                        raise ValueError()
                    pieces.append(encoded)
                found = b''.join(pieces)
                if found.strip():
                    if payload is not None:
                        raise ValueError()  # ambiguous report: fail closed
                    payload = found
            if not data['has_more']:
                if payload is None:
                    raise ValueError()
                return payload
            cursor = data['next_cursor']
            if (type(cursor) is not str or not re.fullmatch(r'[A-Za-z0-9-]{1,100}', cursor)
                    or cursor in seen):
                raise ValueError()
            seen.add(cursor)
        raise ValueError()
    except Exception:
        raise ValueError('seo_notion_rejected') from None
