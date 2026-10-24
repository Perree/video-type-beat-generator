"""Local manual-download history and recoverable publication. No automation state."""
import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from pathlib import Path

from core.beat_http import BeatError, PROFILE_HOSTS, check_url

HISTORY_FILE = Path(__file__).resolve().parents[1] / 'config/manual_beatstars_history.json'
SIDECAR = '.beatstars.json'
LINK = '.beatstars.txt'


class HistoryError(BeatError):
    """Fatal to a batch: do not continue after persistence failures."""


def identity(member_id, track_id):
    if (not isinstance(member_id, str) or not re.fullmatch(r'MR[0-9]{1,20}', member_id)
            or not isinstance(track_id, str) or not re.fullmatch(r'TK[0-9]{1,20}', track_id)):
        raise ValueError('invalid_identity')
    return member_id + ':' + track_id


def validate_metadata(data):
    if (not isinstance(data, dict) or type(data.get('version')) is not int
            or data['version'] != 1):
        raise ValueError('invalid_metadata')
    identity(data['member_id'], data['track_id'])
    url = check_url(data['url'], PROFILE_HOSTS)
    if (url.query or not re.fullmatch(r'/beat/[A-Za-z0-9_-]{1,400}', url.path)
            or not url.path.endswith('-' + data['track_id'][2:])):
        raise ValueError('invalid_track_url')
    if (not isinstance(data['title'], str) or not 1 <= len(data['title']) <= 500
            or type(data['tags']) is not list or len(data['tags']) > 40
            or any(type(t) is not str or not 1 <= len(t) <= 100 for t in data['tags'])
            or not isinstance(data['downloaded_at'], str)
            or not re.fullmatch(r'[a-f0-9]{64}', data['sha256'])
            or type(data['size']) is not int or not 0 < data['size'] <= 80 * 1024 * 1024):
        raise ValueError('invalid_metadata')
    return data


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def metadata_bytes(metadata):
    return (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def package_files(audio, metadata):
    audio = Path(audio)
    return ((audio, metadata['sha256']),
            (Path(str(audio) + SIDECAR), hashlib.sha256(metadata_bytes(metadata)).hexdigest()),
            (Path(str(audio) + LINK), hashlib.sha256((metadata['url'] + '\n').encode()).hexdigest()))


def _complete_in_archive(audio, metadata):
    """A render may archive a complete package before a failed history write recovers."""
    audio = Path(audio)
    archive = audio.parent / 'hechos'
    pattern = re.compile(re.escape(audio.stem) + r'(?: \([0-9]+\))?' + re.escape(audio.suffix), re.I)
    try:
        entries = os.scandir(archive)
    except FileNotFoundError:
        return False
    with entries:
        for entry in entries:
            if not entry.name.endswith(SIDECAR) or not entry.is_file(follow_symlinks=False):
                continue
            name = entry.name[:-len(SIDECAR)]
            if not pattern.fullmatch(name):
                continue
            files = package_files(archive / name, metadata)
            if digest(entry.path) != files[1][1]:
                continue  # An older package with a colliding basename is unrelated.
            if not all(path.is_file() and not path.is_symlink() and digest(path) == expected
                       for path, expected in reversed(files)):
                raise HistoryError('package_recovery_conflict')
            return True
    return False


class HistoryStore:
    def __init__(self, path=HISTORY_FILE):
        self.path = Path(path).resolve()

    @contextmanager
    def locked(self):
        """Nonblocking OS lock: released even after a process crash."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lock = open(str(self.path) + '.lock', 'a+b')
        except OSError:
            raise HistoryError('history_unavailable') from None
        acquired = False
        try:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0, 2)
                if lock.tell() == 0:
                    lock.write(b'0')
                    lock.flush()
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError:
                    raise HistoryError('history_busy') from None
            else:
                import fcntl
                try:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError:
                    raise HistoryError('history_busy') from None
            acquired = True
            yield
        finally:
            if acquired:
                if os.name == 'nt':
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            lock.close()

    def load(self):
        try:
            with self.path.open('rb') as stream:
                raw = stream.read(16 * 1024 * 1024 + 1)
            if len(raw) > 16 * 1024 * 1024:
                raise ValueError('history_limit')
            data = json.loads(raw)
            if (type(data) is not dict or type(data.get('version')) is not int or data['version'] != 1
                    or type(data.get('downloads')) is not dict):
                raise ValueError('invalid_history')
            for key, value in data['downloads'].items():
                validate_metadata(value)
                if key != identity(value['member_id'], value['track_id']):
                    raise ValueError('identity_mismatch')
            pending = data.get('pending')
            if pending is not None:
                validate_metadata(pending['metadata'])
                audio = Path(pending['audio'])
                if not audio.is_absolute() or audio.suffix != '.m4a':
                    raise ValueError('invalid_pending')
            return data
        except FileNotFoundError:
            return {'version': 1, 'downloads': {}, 'pending': None}
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            raise HistoryError('history_unreadable') from None
        except BeatError:
            raise HistoryError('history_unreadable') from None

    def save(self, data):
        temp = None
        try:
            payload = metadata_bytes(data)
            if len(payload) > 16 * 1024 * 1024:
                raise HistoryError('history_limit')
            with tempfile.NamedTemporaryFile(dir=self.path.parent, suffix='.tmp', delete=False) as stream:
                temp = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
        except OSError:
            raise HistoryError('history_write_failed') from None
        finally:
            if temp is not None:
                try:
                    temp.unlink(missing_ok=True)
                except OSError:
                    # A locked temporary must never hide a fatal history error:
                    # the batch must stop rather than continue as a per-track failure.
                    pass

    def recover(self, data):
        """Complete journaled packages become history; incomplete packages roll back."""
        pending = data.get('pending')
        if pending is None:
            return
        metadata = pending['metadata']
        files = package_files(pending['audio'], metadata)
        try:
            existing = [path for path, expected in files if path.exists()]
            # Never delete or register a changed file.
            if any(path.is_symlink() or (path.exists() and digest(path) != expected)
                   for path, expected in files):
                raise HistoryError('package_recovery_conflict')
            archived = len(existing) < len(files) and _complete_in_archive(pending['audio'], metadata)
            if existing and archived:
                raise HistoryError('package_recovery_conflict')
            if len(existing) == len(files) or archived:
                data['downloads'][identity(metadata['member_id'], metadata['track_id'])] = metadata
            else:
                for path in existing:
                    path.unlink()
            data['pending'] = None
            self.save(data)
        except OSError:
            raise HistoryError('package_recovery_failed') from None
