"""Shared automation upload budget; durable CAS reservations, never refunded."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from core import dropbox_layout
from core.beat_cloud import BeatCloud, CloudError, Conflict, decode_document

LIMIT = 10
PATH = dropbox_layout.REGISTRY_DIR + '/upload_budget.json'
PACIFIC = ZoneInfo('America/Los_Angeles')


class UploadDeferred(Exception):
    """No upload may start; leave outstanding work for a later run."""


class UploadBudget:
    def __init__(self, transport, clock=lambda: datetime.now(timezone.utc)):
        self.transport, self.clock = transport, clock
        self.cloud = BeatCloud(transport, retries=10)

    def read(self):
        data, rev = self.cloud._retry(lambda: self.transport.read(PATH))
        try:
            doc = decode_document(data)
            if (doc['version'] != 1 or doc['limit'] != LIMIT
                    or not isinstance(doc['days'], dict) or not isinstance(doc['blocked'], dict)):
                raise ValueError()
            for day, entries in doc['days'].items():
                datetime.strptime(day, '%Y-%m-%d')
                if (not isinstance(entries, dict) or len(entries) > LIMIT
                        or any(not isinstance(k, str) or not isinstance(v, str)
                               for k, v in entries.items())):
                    raise ValueError()
            for channel, until in doc['blocked'].items():
                if not isinstance(channel, str) or datetime.fromisoformat(until).tzinfo is None:
                    raise ValueError()
        except (ValueError, TypeError, KeyError):
            raise CloudError('invalid_upload_budget') from None
        return doc, rev

    def _update(self, mutate):
        for _ in range(10):
            doc, rev = self.read()  # Missing/corrupt ledger fails closed.
            result = mutate(doc)
            payload = json.dumps(doc, sort_keys=True).encode()
            try:
                self.cloud._retry(lambda: self.transport.write(PATH, payload, rev))
                return result
            except Conflict:
                continue
        raise Conflict('upload_budget_conflict')

    def reserve(self, channel):
        token = uuid4().hex
        day = self.clock().astimezone(PACIFIC).date().isoformat()

        def mutate(doc):
            now = self.clock()
            if now.astimezone(PACIFIC).date().isoformat() != day:
                raise UploadDeferred('upload_reservation_day_changed')
            until = doc['blocked'].get(channel)
            if until and now < datetime.fromisoformat(until):
                raise UploadDeferred('youtube_upload_limit')
            entries = doc['days'].setdefault(day, {})
            if token not in entries and len(entries) >= LIMIT:
                raise UploadDeferred('shared_upload_budget_exhausted')
            entries[token] = channel
            return day

        self._update(mutate)
        self.check_day(day)
        return day

    def check_day(self, day):
        if self.clock().astimezone(PACIFIC).date().isoformat() != day:
            raise UploadDeferred('upload_reservation_day_changed')

    def rejected(self, channel, exc):
        from core.beat_reasons import classify
        if classify(exc) != 'youtube_upload_limit':
            return False
        until = (self.clock() + timedelta(hours=24)).isoformat()
        def mutate(doc):
            old = doc['blocked'].get(channel)
            if not old or datetime.fromisoformat(old) < datetime.fromisoformat(until):
                doc['blocked'][channel] = until
        try:
            self._update(mutate)
        except CloudError as exc:
            raise UploadDeferred('upload_budget_unavailable') from exc
        return True

    def call(self, channel, upload):
        self.reserve(channel)
        try:
            return upload()
        except Exception as exc:
            if self.rejected(channel, exc):
                raise UploadDeferred('youtube_upload_limit') from exc
            raise


def initialize(transport, now=None):
    """Explicit first deployment only. Reserve activation day for legacy uploads.

    Never overwrite an existing ledger. Ten fresh slots become available at the
    next Pacific midnight; uploads made before deployment cannot be undercounted.
    """
    now = now or datetime.now(timezone.utc)
    day = now.astimezone(PACIFIC).date().isoformat()
    doc = {'version': 1, 'limit': LIMIT, 'days': {
        day: {f'activation-{i}': 'legacy' for i in range(LIMIT)}}, 'blocked': {}}
    return transport.write(PATH, json.dumps(doc).encode(), None)
