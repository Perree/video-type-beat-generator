"""Manual BeatStars acquisition service. No Qt, credentials, uploads or automation jobs."""
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from core.beat_download import download_hls, duration
from core.beat_http import BeatError, check_cancelled
from core.beat_preview import PreviewResolver
from core.beat_source import BeatStarsSource, Track
from core.manual_beatstars_media import ManualMediaTools
from core.manual_beatstars_store import (HistoryError, HistoryStore, LINK, SIDECAR, digest,
                                        identity, metadata_bytes, package_files, validate_metadata)


@dataclass(frozen=True)
class Candidate:
    track: Track
    downloaded: bool


@dataclass(frozen=True)
class SearchResult:
    profile_url: str
    member_id: str
    candidates: tuple


@dataclass
class BatchResult:
    downloads: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    skipped: list = field(default_factory=list)
    cancelled: bool = False


def filter_tags(tracks, tags, match='any'):
    if match not in ('any', 'all'):
        raise ValueError('invalid_tag_match')
    if isinstance(tags, str):
        tags = tags.split(',')
    if (not isinstance(tags, (list, tuple)) or len(tags) > 40
            or any(type(t) is not str or len(t) > 100 for t in tags)):
        raise ValueError('invalid_tags')
    wanted = {t.strip().casefold() for t in tags if t.strip()}
    for track in tracks:
        actual = {t.strip().casefold() for t in track.tags}
        if not wanted or (wanted <= actual if match == 'all' else wanted & actual):
            yield track


def _target(destination, track):
    # Prefix also avoids Windows device names; the ID survives title truncation.
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', '_', track.title).strip(' .')[:90]
    stem = f'{track.id} - {name or "Beat"}'
    target, n = destination / (stem + '.m4a'), 2
    while any(path.exists() for path in (target, Path(str(target) + SIDECAR), Path(str(target) + LINK))):
        target = destination / f'{stem} ({n}).m4a'
        n += 1
    return target


def _publish(source, target):
    """Atomic creation without replacing an existing destination, on the same volume."""
    if os.name == 'nt':
        os.rename(source, target)  # Windows rename fails if target already exists.
    else:
        os.link(source, target)
        source.unlink()


class ManualBeatStars:
    def __init__(self, store=None, source=None, resolver=None, http=None, tools=None,
                 cancelled=lambda: False):
        self.cancelled = cancelled
        self.store = store if store is not None else HistoryStore()
        self.source = source if source is not None else BeatStarsSource(cancelled=cancelled)
        self.resolver = resolver if resolver is not None else PreviewResolver(cancelled=cancelled)
        self.http = http
        self.tools = tools if tools is not None else ManualMediaTools(cancelled)

    def search(self, profile_url, tags=(), match='any', include_downloaded=False):
        # Refuse corrupt history before any network access. Also recover other channels.
        with self.store.locked():
            state = self.store.load()
            self.store.recover(state)
        check_cancelled(self.cancelled)
        # Validate input before scanning the remote catalogue.
        tuple(filter_tags((), tags, match))
        snapshot = self.source.scan(profile_url)
        check_cancelled(self.cancelled)
        with self.store.locked():
            state = self.store.load()
            self.store.recover(state)
            candidates = []
            for track in filter_tags(snapshot.tracks, tags, match):
                downloaded = identity(snapshot.member_id, track.id) in state['downloads']
                if include_downloaded or not downloaded:
                    candidates.append(Candidate(track, downloaded))
        return SearchResult(profile_url, snapshot.member_id, tuple(candidates))

    def download(self, search, track_ids, destination, include_downloaded=False,
                 progress=lambda done, total, track_id: None):
        if (not isinstance(track_ids, (list, tuple)) or not 1 <= len(track_ids) <= 100
                or any(type(t) is not str for t in track_ids)
                or len(set(track_ids)) != len(track_ids)):
            raise ValueError('invalid_track_selection')
        available = {item.track.id: item.track for item in search.candidates}
        if any(tid not in available for tid in track_ids):
            raise ValueError('unknown_track')
        result = BatchResult()
        try:
            with self.store.locked():
                state = self.store.load()
                self.store.recover(state)
                check_cancelled(self.cancelled)
                destination = Path(destination).resolve()
                destination.mkdir(parents=True, exist_ok=True)
                for index, tid in enumerate(track_ids):
                    check_cancelled(self.cancelled)
                    progress(index, len(track_ids), tid)
                    if not include_downloaded and identity(search.member_id, tid) in state['downloads']:
                        result.skipped.append(tid)
                        continue
                    try:
                        path = self._download_one(search, available[tid], destination, state)
                        result.downloads.append(path)
                    except HistoryError:
                        raise
                    except BeatError as exc:
                        if str(exc) == 'cancelled':
                            raise
                        result.errors.append((tid, str(exc)))
                    except OSError:
                        result.errors.append((tid, 'local_write_failed'))
                progress(len(track_ids), len(track_ids), '')
        except HistoryError as exc:
            exc.result = result  # UI can retain the successes before the fatal error.
            raise
        except BeatError as exc:
            if str(exc) != 'cancelled':
                raise
            result.cancelled = True
        return result

    def _download_one(self, search, track, destination, state):
        check_cancelled(self.cancelled)
        url, expected = self.resolver.resolve(track.payload(), search.profile_url)
        check_cancelled(self.cancelled)
        if expected is not None:
            duration(expected)
        # All staging files end in .part, so folder scans cannot import them.
        with tempfile.TemporaryDirectory(prefix='.beatstars-', dir=destination) as temp:
            temp = Path(temp)
            source, prepared = temp / 'preview.part', temp / 'audio.part'
            total = download_hls(url, source, self.http, self.cancelled)
            for reference in (expected, track.duration):
                if reference is not None and abs(total - reference) > max(3, reference * .03):
                    raise BeatError('duration_mismatch')
            self.tools.prepare(source, prepared, total)
            check_cancelled(self.cancelled)
            metadata = validate_metadata({
                'version': 1, 'member_id': search.member_id, 'track_id': track.id,
                'title': track.title, 'tags': list(track.tags), 'url': track.url,
                'downloaded_at': datetime.now(timezone.utc).isoformat(),
                'size': prepared.stat().st_size, 'sha256': digest(prepared),
            })
            sidecar, link = temp / 'metadata.part', temp / 'link.part'
            sidecar.write_bytes(metadata_bytes(metadata))
            link.write_text(track.url + '\n', encoding='utf-8', newline='')
            target = _target(destination, track)
            # Flush all payloads before recording the durable publication intent.
            for path in (prepared, sidecar, link):
                with path.open('r+b') as stream:
                    os.fsync(stream.fileno())
            check_cancelled(self.cancelled)
            state['pending'] = {'audio': str(target), 'metadata': metadata}
            self.store.save(state)
            published = []
            try:
                # Audio last: an input-folder scan only sees complete packages.
                for staged, final in ((sidecar, Path(str(target) + SIDECAR)),
                                      (link, Path(str(target) + LINK)), (prepared, target)):
                    _publish(staged, final)
                    published.append(final)
            except OSError:
                # Remove only files created by this attempt, never an external collision.
                try:
                    for path in published:
                        path.unlink()
                except OSError:
                    raise HistoryError('package_rollback_failed') from None
                state['pending'] = None
                self.store.save(state)
                raise
            state['downloads'][identity(search.member_id, track.id)] = metadata
            state['pending'] = None
            self.store.save(state)  # Failure leaves a complete journaled package for recovery.
            return target
