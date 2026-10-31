"""Telegram receives only fixed codes and integer counters, never exceptions."""
import json
import re
import urllib.request
from core.beat_notion import NoRedirect
from core.beat_reasons import lines

COUNTERS = ('planned', 'eligible', 'uploaded', 'orphan', 'unknown', 'failed',
            'blocked', 'budget', 'thumbnail_failed', 'expired', 'no_matching_tracks',
            'calendar_unavailable')


def message(summary):
    prefix = 'Type Beats DRY RUN' if summary.get('dry_run') else 'Type Beats daily'
    if summary.get('private_pilot') and not summary.get('dry_run'):
        prefix = 'Type Beats PRIVATE PILOT'
    text = prefix + '\n' + '\n'.join(f'{key}: {summary.get(key, 0)}'
        for key in COUNTERS if type(summary.get(key, 0)) is int)
    reasons = lines(summary)
    return text + ('\n\nMotivos:\n' + '\n'.join(reasons) if reasons else '')


class Telegram:
    def __init__(self, token, chat):
        if (not isinstance(token, str) or not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token)
                or not isinstance(chat, str) or not re.fullmatch(r'-?[0-9]+', chat)):
            raise ValueError('telegram_unconfigured')
        self.token, self.chat = token, chat

    def __call__(self, summary):
        payload = json.dumps({'chat_id': self.chat, 'text': message(summary)}).encode()
        request = urllib.request.Request('https://api.telegram.org/bot' + self.token + '/sendMessage',
            data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=15) as response:
            if response.status != 200 or json.loads(response.read(65537)).get('ok') is not True:
                raise ValueError('telegram_failed')
