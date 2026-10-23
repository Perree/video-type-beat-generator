# -*- coding: utf-8 -*-
"""Subida a YouTube (Data API v3) con un token OAuth por canal de la app.

Cada canal de la app se conecta a una cuenta de Google distinta. En el escritorio,
``authorize`` obtiene el token en memoria y se sube directo a GitHub Secrets; las credenciales
OAuth "Escritorio" viven en el llavero (``core/cloud_login``). ``connect_channel`` y
``tokens/<canal>.json`` quedan para el runner y los scripts sueltos.

La cuota efectiva se consulta por proyecto en Google Cloud; el límite local de la app
es independiente. Ver docs/TYPE_BEATS_DISTRIBUTION.md y la referencia oficial vigente.
"""
import os
import re

CLIENT_SECRET_FILE = os.path.join('config', 'client_secret.json')
TOKENS_DIR = 'tokens'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']
PRIVACY_OPTIONS = ('private', 'unlisted', 'public')
CATEGORY_MUSIC = '10'
AUTH_TIMEOUT = 300  # segundos para completar el OAuth en el navegador


class YouTubeError(Exception):
    pass


def _token_path(channel, tokens_dir=None):
    safe = re.sub(r'[^\w\-. ]', '_', channel).strip() or 'canal'
    return os.path.join(tokens_dir or TOKENS_DIR, f"{safe}.json")


def is_connected(channel, tokens_dir=None):
    return os.path.exists(_token_path(channel, tokens_dir))


def disconnect_channel(channel, tokens_dir=None):
    path = _token_path(channel, tokens_dir)
    if os.path.exists(path):
        os.remove(path)


def _load_credentials(channel, tokens_dir=None):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    path = _token_path(channel, tokens_dir)
    if not os.path.exists(path):
        raise YouTubeError(f"El canal '{channel}' no está conectado a YouTube.")
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(path, 'w', encoding='utf-8') as f:
                f.write(creds.to_json())
        else:
            raise YouTubeError(f"El token de '{channel}' no es válido; volvé a conectar el canal.")
    return creds


def _service(creds):
    from googleapiclient.discovery import build
    return build('youtube', 'v3', credentials=creds, cache_discovery=False)


def connect_channel(channel, client_secret=None, tokens_dir=None):
    """Abre el navegador para autorizar una cuenta de Google y guarda tokens/<channel>.json.

    Devuelve el título del canal de YouTube autorizado (para confirmar que es la cuenta correcta).
    """
    from google_auth_oauthlib.flow import InstalledAppFlow

    secret = client_secret or CLIENT_SECRET_FILE
    if not os.path.exists(secret):
        raise YouTubeError(
            f"No se encontró {secret}. Descargá las credenciales OAuth (tipo 'Escritorio') "
            "desde Google Cloud y guardalas con ese nombre.")
    flow = InstalledAppFlow.from_client_secrets_file(secret, SCOPES)
    # prompt=select_account: permite elegir una cuenta distinta para cada canal
    creds = flow.run_local_server(port=0, prompt='consent select_account',
                                  authorization_prompt_message='', open_browser=True)
    path = _token_path(channel, tokens_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(creds.to_json())
    return channel_title(channel, tokens_dir)


def authorize(client_config=None):
    """OAuth «Escritorio» en memoria: no escribe ningún archivo.

    Devuelve ``(token_json, título, id del canal)``: el título y el id sirven para confirmar
    la cuenta antes de subir. ``client_config`` por defecto sale del llavero
    (``core/cloud_login.client_secret_config``). El token se sube con ``gh`` por stdin al
    secreto del canal; el llamador no debe guardarlo ni mostrarlo.
    """
    import logging
    from google_auth_oauthlib.flow import InstalledAppFlow

    # El servidor local registra la línea de pedido (``GET /?code=…``) en INFO: nunca a un log.
    logging.getLogger('google_auth_oauthlib.flow').setLevel(logging.WARNING)

    if client_config is None:
        from core import cloud_login
        try:
            client_config = cloud_login.client_secret_config()
        except cloud_login.LoginError as exc:
            raise YouTubeError(str(exc)) from None
    try:
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
        # Con tope: si se cierra la pestaña sin autorizar, el hilo no queda esperando para siempre.
        creds = flow.run_local_server(port=0, prompt='consent select_account',
                                      authorization_prompt_message='', open_browser=True,
                                      timeout_seconds=AUTH_TIMEOUT)
    except Exception:
        raise YouTubeError('No se completó la autorización de YouTube (¿se cerró el navegador '
                           'o pasaron 5 minutos?).') from None
    if not getattr(creds, 'refresh_token', None):
        raise YouTubeError('Google no devolvió un refresh token: revocá el acceso y reintentá.')
    try:
        items = _service(creds).channels().list(part='snippet', mine=True).execute().get(
            'items') or []
        title = items[0]['snippet']['title'] if items else ''
        channel_id = items[0].get('id', '') if items else ''
    except Exception:
        title, channel_id = '', ''  # sin datos la UI pide confirmar igual
    return creds.to_json(), title, channel_id


def channel_title(channel, tokens_dir=None):
    """Título del canal de YouTube asociado al token (1 unidad de cuota)."""
    resp = _service(_load_credentials(channel, tokens_dir)).channels().list(
        part='snippet', mine=True).execute()
    items = resp.get('items') or []
    return items[0]['snippet']['title'] if items else ''


def _split_tags(tags):
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(',')]
    out, total = [], 0
    for t in tags or []:
        t = t.strip()
        # YouTube limita el total de tags a ~500 caracteres
        if t and total + len(t) + 1 <= 480:
            out.append(t)
            total += len(t) + 1
    return out


def upload(channel, video_path, title, description='', tags=None, thumbnail=None,
           privacy='private', publish_at=None, progress=None, tokens_dir=None,
           category_id=None):
    """Sube un video y devuelve {'youtube_id', 'url', 'privacy', 'thumbnail_error'}.

    publish_at: ISO 8601 UTC (ej. '2026-10-05T18:00:00Z'); obliga privacy='private'.
    progress: callback opcional progress(porcentaje:int).
    category_id: categoría de YouTube. Si no se pasa, queda 10 (Música).
        Los Shorts usan 22 (People & Blogs); el default de beats no cambia.
    """
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    if not os.path.exists(video_path):
        raise YouTubeError(f"No existe el video: {video_path}")
    if privacy not in PRIVACY_OPTIONS:
        raise YouTubeError(f"privacy inválido: {privacy}")
    status = {'privacyStatus': 'private' if publish_at else privacy,
              'selfDeclaredMadeForKids': False}
    if publish_at:
        status['publishAt'] = publish_at
    body = {
        'snippet': {
            'title': (title or os.path.splitext(os.path.basename(video_path))[0])
                     .replace('<', '').replace('>', '')[:100],
            'description': (description or '')[:5000].replace('<', '').replace('>', ''),
            'tags': _split_tags(tags),
            'categoryId': str(category_id).strip() if category_id not in (None, '')
                          else CATEGORY_MUSIC,
        },
        'status': status,
    }
    yt = _service(_load_credentials(channel, tokens_dir))
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True,
                            mimetype='video/mp4')
    response = None
    retries = 0
    try:
        request = yt.videos().insert(part='snippet,status', body=body, media_body=media)
        while response is None:
            try:
                st, response = request.next_chunk()
                retries = 0
                if st and progress:
                    progress(int(st.progress() * 100))
            except HttpError as e:
                if e.resp.status in (500, 502, 503, 504) and retries < 5:
                    retries += 1
                    continue
                raise YouTubeError(f"Error de YouTube ({e.resp.status}): {e}") from e
    finally:
        # Release the video before the worker removes its temporary directory,
        # even if a request/traceback retains the media object on Windows.
        media.stream().close()
    video_id = response['id']
    if progress:
        progress(100)

    thumb_error = ''
    if thumbnail and os.path.exists(thumbnail):
        thumbnail_media = None
        try:
            thumbnail_media = MediaFileUpload(thumbnail)
            yt.thumbnails().set(videoId=video_id, media_body=thumbnail_media).execute()
        except Exception:
            # Común: la cuenta no está verificada por teléfono (no permite miniaturas)
            # An upload already succeeded: a timeout here must not trigger another insert.
            thumb_error = 'No se pudo confirmar la miniatura. El video ya está subido; no lo vuelvas a subir.'
        finally:
            if thumbnail_media is not None:
                thumbnail_media.stream().close()
    return {
        'youtube_id': video_id,
        'url': f"https://youtu.be/{video_id}",
        'privacy': response.get('status', {}).get('privacyStatus', status['privacyStatus']),
        'thumbnail_error': thumb_error,
    }


def _uploads_playlist_id(yt, channel_label):
    """Id de la playlist «uploads» del canal autenticado (1 unidad de cuota)."""
    resp = yt.channels().list(part='contentDetails', mine=True).execute()
    items = resp.get('items') or []
    if not items:
        raise YouTubeError(f"No se encontró el canal de YouTube de '{channel_label}'.")
    return items[0]['contentDetails']['relatedPlaylists']['uploads']


def _playlist_video_ids(yt, playlist_id, max_videos):
    """Ids de la playlist de uploads, hasta max_videos (1 unidad de cuota por cada 50)."""
    ids, token = [], None
    cap = max(1, int(max_videos))
    while len(ids) < cap:
        r = yt.playlistItems().list(
            part='contentDetails', playlistId=playlist_id,
            maxResults=min(50, cap - len(ids)), pageToken=token).execute()
        ids += [i['contentDetails']['videoId'] for i in r.get('items', [])]
        token = r.get('nextPageToken')
        if not token:
            break
    return ids[:cap]


def list_channel_videos(channel, tokens_dir=None, max_videos=2000):
    """Videos ya publicados en el canal: [{'youtube_id','title','published_at','privacy'}].

    Usa la playlist de uploads (1 unidad por 50 ids) y videos.list (1 unidad por 50 videos).
    """
    yt = _service(_load_credentials(channel, tokens_dir))
    playlist = _uploads_playlist_id(yt, channel)
    ids = _playlist_video_ids(yt, playlist, max_videos)
    videos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part='snippet,status', id=','.join(ids[i:i + 50])).execute()
        for v in r.get('items', []):
            videos.append({'youtube_id': v['id'],
                           'title': v['snippet']['title'],
                           'published_at': v['snippet'].get('publishedAt', ''),
                           'privacy': v.get('status', {}).get('privacyStatus', '')})
    return videos


def list_channel_video_stats(channel, tokens_dir=None, max_videos=30):
    """Título y views de los uploads más recientes del canal (tope 30).

    Cuota: channels.list (1) + playlistItems (1 por 50 ids) + videos.list statistics
    (1 por 50). Misma recolección de ids que list_channel_videos, con tope bajo.
    Devuelve [{'youtube_id','title','views'}] ordenados por views descendente.
    """
    cap = min(max(1, int(max_videos or 30)), 30)
    yt = _service(_load_credentials(channel, tokens_dir))
    playlist = _uploads_playlist_id(yt, channel)
    ids = _playlist_video_ids(yt, playlist, cap)
    rows = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(
            part='snippet,statistics', id=','.join(ids[i:i + 50])).execute()
        for v in r.get('items', []):
            stats = v.get('statistics') or {}
            try:
                views = int(stats.get('viewCount') or 0)
            except (TypeError, ValueError):
                views = 0
            rows.append({
                'youtube_id': v['id'],
                'title': v['snippet']['title'],
                'views': views,
            })
    rows.sort(key=lambda row: (-row['views'], row['title']))
    return rows
