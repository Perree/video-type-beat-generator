"""Beats settings validated against the Dropbox registry, and read-only simulation.

Source of truth: ``/type-beats/config.json`` (worker document) plus
``/automatizacion/canales.json`` (channel registry). Nothing here writes to disk.
"""
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from core.beat_schema import BA, instant, migrate
from core.beat_schedule import plan
from core.beat_source import profile_username
from core import channel_kind
from core.beat_cloud import decode_document
from core.beat_visual import options
from core.beat_download import dropbox_path
from core.beat_templates import apply_channel_templates


def read_app(path):
    """Read-only legacy ``app_config.json`` reader, kept for scripts/migrate_to_cloud.py."""
    path = Path(path)
    app = decode_document(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(app, dict):
        raise ValueError("La configuración debe ser un objeto JSON.")
    return app


def beat_channels(registry):
    """``{clave: ficha}`` of the Beats channels in the registry."""
    return {row["clave"]: row for row in channel_kind.channels_of(registry, channel_kind.BEATS)}


def _templates(registry, channel_id):
    row = beat_channels(registry).get(channel_id)
    return None if row is None else dict(row.get("plantillas") or {})


def settings(config, registry):
    result = migrate(config, "config")
    for channel in result["channels"]:
        apply_channel_templates(channel, _templates(registry, channel["id"]))
        _metadata(channel)
    return result


def _metadata(channel):
    from core.beat_seo import manual_profile
    manual_profile(channel)
    options(channel)
    folders = channel.get('dropbox_images', {})
    if not isinstance(folders, dict) or len(folders) > 40:
        raise ValueError('Carpetas Dropbox: una por género, con formato género=carpeta.')
    for genre, folder in folders.items():
        if not isinstance(genre, str) or not genre.strip() or len(genre) > 100:
            raise ValueError('Género de imágenes inválido.')
        try:
            dropbox_path(folder)
        except Exception:
            raise ValueError('Carpeta Dropbox inválida.') from None
    for key in ("tags", "genres"):
        values = channel.get(key, [])
        if (not isinstance(values, list) or len(values) > 40
                or any(not isinstance(v, str) or not v.strip() or len(v) > 100 for v in values)):
            raise ValueError("Tags y géneros: hasta 40 valores de 100 caracteres.")
    if not isinstance(channel.get("images_folder", ""), str):
        raise ValueError("La carpeta de imágenes debe ser texto.")


def validate(config, registry):
    result = migrate(config, "config")
    profile_username(result.get("beatstars_profile_url", ""))
    available = beat_channels(registry)
    for channel in result["channels"]:
        row = available.get(channel["id"])
        if row is None:
            raise ValueError("Elegí un canal de Beats del registro.")
        if "actions_slug" in channel and channel["actions_slug"] != row["slug"]:
            raise ValueError("El slug de Actions no coincide con el del registro de canales.")
        apply_channel_templates(channel, _templates(registry, channel["id"]))
        _metadata(channel)
        spec = options(channel)
        if spec['mode'] in ('video', 'alternate') and channel.get('active', True):
            folder = spec['videos_folder']
            if not folder or (spec['video_source'] == 'local' and not Path(folder).is_dir()):
                raise ValueError('Configurá una carpeta de videos existente o una ruta Dropbox.')
        if spec['thumbnail_source'] != 'auto':
            path = spec['thumbnail_path']
            if not path or (spec['thumbnail_source'] == 'local' and not Path(path).is_file()):
                raise ValueError('Configurá la imagen de miniatura.')
        folder = channel.get("images_folder", "")
        if not isinstance(folder, str) or (folder and not Path(folder).is_dir()):
            raise ValueError("La carpeta de imágenes debe existir o quedar vacía.")
    return result


def simulate(config, tracks, state=None, now=None):
    """No mutations, locks, reservations or cloud writes."""
    state = migrate({} if state is None else state, "state")
    now = instant(now if now is not None else datetime.now(BA))
    return {"as_of": now.isoformat(), "jobs": plan(config, state, tracks, now),
            "remaining": 6 - len(state["attempts"].get(now.date().isoformat(), {})),
            "state": deepcopy(state)}
