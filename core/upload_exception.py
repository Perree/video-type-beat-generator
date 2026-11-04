"""Explicit, one-use private-pilot grants, separate from the normal daily ledger."""
import json
import re
from datetime import datetime
from uuid import uuid4

from core import dropbox_layout
from core.beat_cloud import CloudError, Conflict, Missing, decode_document
from core.upload_budget import UploadBudget, UploadDeferred, PACIFIC


def grant_path(run_id):
    if not isinstance(run_id, str) or not re.fullmatch(r'[0-9]{1,30}', run_id):
        raise ValueError('invalid_upload_exception_run')
    return dropbox_layout.REGISTRY_DIR + '/upload_exceptions/' + run_id + '.json'


class PrivatePilotBudget(UploadBudget):
    def __init__(self, transport, run_id, **kwargs):
        super().__init__(transport, **kwargs)
        self.path, self.run_id = grant_path(run_id), run_id

    def reserve(self, channel):
        try:
            return super().reserve(channel)
        except UploadDeferred as exc:
            if str(exc) != 'shared_upload_budget_exhausted':
                raise
        day = self.clock().astimezone(PACIFIC).date().isoformat()
        token = uuid4().hex
        for _ in range(10):
            try:
                raw, rev = self.cloud._retry(lambda: self.transport.read(self.path))
            except Missing:
                raise UploadDeferred('shared_upload_budget_exhausted') from None
            grant = decode_document(raw)
            if (not isinstance(grant, dict) or grant.get('version') != 1
                    or grant.get('run_id') != self.run_id or grant.get('channel') != channel
                    or grant.get('quota_day') != day or grant.get('private_pilot') is not True
                    or grant.get('consumed_by') not in (None, token)):
                raise UploadDeferred('shared_upload_budget_exhausted')
            self.check_day(day)
            # Recheck the normal ledger's real YouTube cooldown immediately before consumption.
            ledger, _ = self.read()
            until = ledger['blocked'].get(channel)
            if until and self.clock() < datetime.fromisoformat(until):
                raise UploadDeferred('youtube_upload_limit')
            grant['consumed_by'] = token
            try:
                self.cloud._retry(lambda: self.transport.write(
                    self.path, json.dumps(grant, sort_keys=True).encode(), rev))
                self.check_day(day)
                return day
            except Conflict:
                continue
        raise CloudError('upload_exception_conflict')
