"""Local Beats settings and read-only simulation using the Phase 2 planner."""
from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile

from core.beat_schema import BA, instant, migrate
from core.beat_schedule import plan
from core.beat_source import profile_username
from core.sections import SECTION_BEATS, channel_names_for_section
from core.beat_cloud import decode_document
from core.beat_visual import options
from core.beat_download import dropbox_path


def read_app(path):
    path = Path(path)
    app = decode_document(path.read_text(encoding="utf-8")) if path.exists() else {}
    if not isinstance(app, dict):
        raise ValueError("La configuración debe ser un objeto JSON.")
    return app


def settings(app):
    result = migrate(app.get("beat_automation", {}), "config")
    for channel in result["channels"]:
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


def validate(config, app):
    result = migrate(config, "config")
    profile_username(result.get("beatstars_profile_url", ""))
    available = channel_names_for_section(app.get("channels", {}), SECTION_BEATS)
    for channel in result["channels"]:
        if channel["id"] not in available:
            raise ValueError("Elegí un canal de la sección Beats.")
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


def save(path, config):
    """Re-read the app and replace only beat_automation, atomically."""
    path = Path(path)
    app = read_app(path)
    app["beat_automation"] = validate(config, app)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(app, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return app["beat_automation"]


def simulate(config, tracks, state=None, now=None):
    """No mutations, locks, reservations or cloud writes."""
    state = migrate({} if state is None else state, "state")
    now = instant(now if now is not None else datetime.now(BA))
    return {"as_of": now.isoformat(), "jobs": plan(config, state, tracks, now),
            "remaining": 6 - len(state["attempts"].get(now.date().isoformat(), {})),
            "state": deepcopy(state)}
