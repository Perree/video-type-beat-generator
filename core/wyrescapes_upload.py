# -*- coding: utf-8 -*-
"""WyreScapes: subida programada a YouTube (AllusionBeatz) de la mixtape del día.

- Canal fijo ``UCrC-LCmo-lccKZaTOmGI4ig``: antes de subir se verifica que el token sea de
  ese canal (nunca subir a otro).
- Programado a las 12:00 de Argentina (UTC−3, sin horario de verano), privado hasta esa hora.
- Descripción: el link de Spotify siempre en la primera línea.
- Miniatura = la imagen del video, a 1280×720 (recorte central) y < 2 MB.
- El comentario fijado no se puede por API: queda en un ``.txt`` al lado del video.
- Registro local de lo subido: evita subir dos veces el mismo video y guarda los títulos
  (la Fase 4 los usa para no repetirlos).

Token en ``tokens/wyrescapes.json`` (git-ignored); la llave OAuth sale del llavero.
"""
import json
import os
import subprocess
from datetime import datetime, timedelta, timezone

from core import youtube
from core.ffmpeg_util import resolve_tool

CHANNEL_ID = 'UCrC-LCmo-lccKZaTOmGI4ig'
TOKEN_NAME = 'wyrescapes'
SPOTIFY_URL = 'https://open.spotify.com/playlist/1GqQd4yh4r79yH0zrkib6p'
ARGENTINA = timezone(timedelta(hours=-3), 'ART')
PUBLISH_HOUR = 12
MIN_LEAD = timedelta(minutes=45)  # margen para subir y procesar antes de publicar
THUMB_MAX_BYTES = 2 * 1024 * 1024 - 1
DEFAULT_LOG_PATH = os.path.join('config', 'wyrescapes_published.json')


class UploadError(RuntimeError):
    pass


def next_publish_time(now=None, hour=PUBLISH_HOUR, lead=MIN_LEAD):
    """Próximo ``hour``:00 de Argentina con al menos ``lead`` de margen (datetime AR)."""
    now = (now or datetime.now(timezone.utc)).astimezone(ARGENTINA)
    slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if slot - now < lead:
        slot += timedelta(days=1)
    return slot


def publish_at_utc(slot):
    """``2026-11-22T15:00:00Z`` para la API."""
    return slot.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def build_description(text):
    """El link de Spotify en la primera línea (sin duplicarlo si ya viene en el texto)."""
    lines = [ln for ln in (text or '').strip().splitlines()]
    lines = [ln for ln in lines if ln.strip() != SPOTIFY_URL]
    body = '\n'.join(lines).strip()
    return f'{SPOTIFY_URL}\n\n{body}' if body else SPOTIFY_URL


def validate_meta(meta):
    """Chequea y normaliza ``{title, description, tags, pinned_comment}``."""
    if not isinstance(meta, dict):
        raise UploadError('La metadata tiene que ser un objeto JSON')
    title = str(meta.get('title') or '').strip()
    if not title:
        raise UploadError('Falta el título')
    if len(title) > 100 or '<' in title or '>' in title:
        raise UploadError('El título debe tener ≤100 caracteres y sin < >')
    tags = meta.get('tags') or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    return {'title': title,
            'description': build_description(meta.get('description')),
            'tags': [str(t).strip() for t in tags if str(t).strip()],
            'pinned_comment': str(meta.get('pinned_comment') or '').strip()}


def make_thumbnail(image, out_path, ffmpeg=None):
    """JPEG 1280×720 (cover) de la imagen, bajando calidad hasta quedar < 2 MB."""
    ffmpeg = ffmpeg or resolve_tool('ffmpeg')
    if not ffmpeg:
        raise UploadError('No está ffmpeg para armar la miniatura')
    for quality in (2, 4, 7, 10, 15):
        cmd = [ffmpeg, '-y', '-v', 'error', '-i', image, '-frames:v', '1',
               '-vf', 'scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,setsar=1',
               '-q:v', str(quality), out_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                errors='replace', stdin=subprocess.DEVNULL, timeout=120,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0 or not os.path.isfile(out_path):
            raise UploadError(f'No se pudo armar la miniatura: {(result.stderr or "")[-300:]}')
        if os.path.getsize(out_path) <= THUMB_MAX_BYTES:
            return out_path
    raise UploadError('La miniatura no baja de 2 MB')


def write_pinned_comment(video_path, text):
    """``<video>.comentario.txt`` con el comentario para fijar a mano. Devuelve la ruta."""
    path = os.path.splitext(video_path)[0] + '.comentario.txt'
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write((text or '').strip() + '\n')
    return path


def load_log(path=DEFAULT_LOG_PATH):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def append_log(entry, path=DEFAULT_LOG_PATH):
    entries = load_log(path) + [entry]
    folder = os.path.dirname(path)
    if folder:
        os.makedirs(folder, exist_ok=True)
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        json.dump(entries, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return entries


def already_uploaded(video_path, log):
    name = os.path.basename(video_path)
    return next((e for e in log if e.get('video') == name and e.get('youtube_id')), None)


def connect(tokens_dir=None, authorize=youtube.authorize):
    """OAuth (navegador) y guarda el token solo si la cuenta es AllusionBeatz."""
    token_json, title, channel_id = authorize()
    if channel_id != CHANNEL_ID:
        raise UploadError(f'La cuenta autorizada es «{title or "?"}» ({channel_id or "sin id"}), '
                          f'no AllusionBeatz ({CHANNEL_ID}). No se guardó nada.')
    path = youtube._token_path(TOKEN_NAME, tokens_dir)
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(token_json)
    return title


def token_channel_id(tokens_dir=None):
    """Id del canal del token guardado (1 unidad de cuota)."""
    creds = youtube._load_credentials(TOKEN_NAME, tokens_dir)
    items = youtube._service(creds).channels().list(part='id', mine=True).execute().get(
        'items') or []
    return items[0].get('id', '') if items else ''


def upload_scheduled(video_path, meta, image, slot, tokens_dir=None, log_path=DEFAULT_LOG_PATH,
                     uploader=youtube.upload, channel_check=token_channel_id,
                     thumb_maker=make_thumbnail, progress=None):
    """Sube el video privado, programado para ``slot`` (datetime AR). Devuelve la entrada del log.

    Raises UploadError si ya se subió, si el token es de otro canal o si falla la subida.
    """
    if not os.path.isfile(video_path):
        raise UploadError(f'No existe el video: {video_path}')
    meta = validate_meta(meta)
    previous = already_uploaded(video_path, load_log(log_path))
    if previous:
        raise UploadError(f'Ese video ya se subió: {previous.get("url")}')
    if not youtube.is_connected(TOKEN_NAME, tokens_dir):
        raise UploadError('AllusionBeatz no está conectado: correr wyrescapes_upload.py --connect')
    found = channel_check(tokens_dir)
    if found != CHANNEL_ID:
        raise UploadError(f'El token es del canal {found or "?"}, no de AllusionBeatz. No se subió.')

    thumb = None
    if image and os.path.isfile(image):
        thumb = thumb_maker(image, os.path.splitext(video_path)[0] + '.miniatura.jpg')
    comment_txt = write_pinned_comment(video_path, meta['pinned_comment']) \
        if meta['pinned_comment'] else None
    try:
        result = uploader(TOKEN_NAME, video_path, meta['title'], meta['description'],
                          tags=meta['tags'], thumbnail=thumb, privacy='private',
                          publish_at=publish_at_utc(slot), progress=progress,
                          tokens_dir=tokens_dir)
    except youtube.YouTubeError as exc:
        raise UploadError(str(exc)) from exc
    entry = {'video': os.path.basename(video_path), 'title': meta['title'],
             'youtube_id': result['youtube_id'], 'url': result['url'],
             'publish_at': slot.isoformat(), 'image': os.path.basename(image or ''),
             'uploaded_at': datetime.now(ARGENTINA).isoformat(timespec='seconds'),
             'thumbnail_error': result.get('thumbnail_error', ''),
             'pinned_comment_file': comment_txt or ''}
    append_log(entry, log_path)
    return entry
