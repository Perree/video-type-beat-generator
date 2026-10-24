"""BeatStars metadata and package moves for manual renders. No Qt or network."""
import errno
import json
import os
import shutil
import tempfile
from pathlib import Path

from core.beat_http import BeatError
from core.manual_beatstars_store import LINK, SIDECAR, digest, validate_metadata


class MetadataError(ValueError):
    """A sidecar exists but cannot safely identify this audio."""


def read_metadata(audio, verify=False):
    """Bounded metadata read; verify the audio hash in the render worker, not in Qt."""
    audio = Path(audio)
    sidecar = Path(str(audio) + SIDECAR)
    try:
        if sidecar.is_symlink():
            raise ValueError('linked_metadata')
        with sidecar.open('rb') as stream:
            raw = stream.read(16 * 1024 + 1)
        if len(raw) > 16 * 1024:
            raise ValueError('metadata_limit')
        metadata = validate_metadata(json.loads(raw))
    except FileNotFoundError:
        if sidecar.exists() or Path(str(audio) + LINK).exists():
            raise MetadataError('Falta la metadata de BeatStars del audio. Restaurá su archivo .beatstars.json.') from None
        return None
    except (OSError, ValueError, KeyError, TypeError, RecursionError, BeatError):
        raise MetadataError('No se pudo leer la metadata de BeatStars del audio. Revisá su archivo .beatstars.json.') from None
    if verify:
        try:
            if audio.stat().st_size != metadata['size'] or digest(audio) != metadata['sha256']:
                raise ValueError('audio_changed')
        except (OSError, ValueError):
            raise MetadataError('El audio no coincide con su metadata de BeatStars. Restaurá el paquete original.') from None
    return metadata


def _move_same_volume(source, target):
    """Move on the same filesystem without replacing a concurrent destination."""
    if os.name == 'nt':
        os.rename(source, target)
    else:
        os.link(source, target)
        try:
            source.unlink()
        except OSError:
            target.unlink()
            raise


def _move_one(source, target):
    try:
        _move_same_volume(source, target)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV and getattr(exc, 'winerror', None) != 17:
            raise
    # Preserve the old shutil.move cross-volume capability without overwriting a collision.
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.part', delete=False) as stream:
        temp = Path(stream.name)
    try:
        shutil.copy2(source, temp)
        with temp.open('r+b') as stream:
            os.fsync(stream.fileno())
        _move_same_volume(temp, target)
        try:
            source.unlink()
        except OSError:
            target.unlink()
            raise
    finally:
        temp.unlink(missing_ok=True)


def move_package(audio, directory):
    """Move existing sidecars first and audio last; roll back if any move fails."""
    audio, directory = Path(audio), Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    suffixes = (SIDECAR, LINK, '')
    target, number = directory / audio.name, 2
    while any(os.path.lexists(str(target) + suffix) for suffix in suffixes):
        target = directory / f'{audio.stem} ({number}){audio.suffix}'
        number += 1
    moves = [(Path(str(audio) + suffix), Path(str(target) + suffix))
             for suffix in suffixes if not suffix or os.path.lexists(str(audio) + suffix)]
    moved = []
    try:
        for source, final in moves:
            _move_one(source, final)
            moved.append((source, final))
    except OSError:
        rollback_failed = False
        for source, final in reversed(moved):
            try:
                _move_one(final, source)
            except OSError:
                rollback_failed = True
        if rollback_failed:
            raise OSError('No se pudo completar ni revertir el movimiento a hechos. Revisá los archivos en entrada y hechos.') from None
        raise
    return str(target)
