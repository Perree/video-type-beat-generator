# -*- coding: utf-8 -*-
"""Subida a YouTube (Data API v3) con un token OAuth por canal de la app.

Cada canal de la app (config/app_config.json) se conecta a una cuenta de Google distinta;
el token queda en tokens/<canal>.json (no versionado). Las credenciales OAuth "Escritorio"
del proyecto de Google Cloud van en config/client_secret.json (no versionado).

Cuota (por defecto 10.000 unidades/día por proyecto): videos.insert ~1600, thumbnails.set 50,
channels.list 1. Mientras la app no pase la auditoría de la API, YouTube fuerza los videos
subidos a privado.
"""
import os
import re

CLIENT_SECRET_FILE = os.path.join('config', 'client_secret.json')
TOKENS_DIR = 'tokens'
SCOPES = ['https://www.googleapis.com/auth/youtube.upload',
          'https://www.googleapis.com/auth/youtube.readonly']
PRIVACY_OPTIONS = ('private', 'unlisted', 'public')
CATEGORY_MUSIC = '10'


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
           privacy='private', publish_at=None, progress=None, tokens_dir=None):
    """Sube un video y devuelve {'youtube_id', 'url', 'privacy', 'thumbnail_error'}.

    publish_at: ISO 8601 UTC (ej. '2026-10-05T18:00:00Z'); obliga privacy='private'.
    progress: callback opcional progress(porcentaje:int).
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
            'categoryId': CATEGORY_MUSIC,
        },
        'status': status,
    }
    yt = _service(_load_credentials(channel, tokens_dir))
    media = MediaFileUpload(video_path, chunksize=8 * 1024 * 1024, resumable=True,
                            mimetype='video/mp4')
    request = yt.videos().insert(part='snippet,status', body=body, media_body=media)
    response = None
    retries = 0
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
    video_id = response['id']
    if progress:
        progress(100)

    thumb_error = ''
    if thumbnail and os.path.exists(thumbnail):
        try:
            yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(thumbnail)).execute()
        except HttpError as e:
            # Común: la cuenta no está verificada por teléfono (no permite miniaturas)
            thumb_error = str(e)
    return {
        'youtube_id': video_id,
        'url': f"https://youtu.be/{video_id}",
        'privacy': response.get('status', {}).get('privacyStatus', status['privacyStatus']),
        'thumbnail_error': thumb_error,
    }


def list_channel_videos(channel, tokens_dir=None, max_videos=2000):
    """Videos ya publicados en el canal: [{'youtube_id','title','published_at','privacy'}].

    Usa la playlist de uploads (1 unidad por 50 ids) y videos.list (1 unidad por 50 videos).
    """
    yt = _service(_load_credentials(channel, tokens_dir))
    resp = yt.channels().list(part='contentDetails', mine=True).execute()
    items = resp.get('items') or []
    if not items:
        raise YouTubeError(f"No se encontró el canal de YouTube de '{channel}'.")
    playlist = items[0]['contentDetails']['relatedPlaylists']['uploads']
    ids, token = [], None
    while len(ids) < max_videos:
        r = yt.playlistItems().list(part='contentDetails', playlistId=playlist,
                                    maxResults=50, pageToken=token).execute()
        ids += [i['contentDetails']['videoId'] for i in r.get('items', [])]
        token = r.get('nextPageToken')
        if not token:
            break
    videos = []
    for i in range(0, len(ids), 50):
        r = yt.videos().list(part='snippet,status', id=','.join(ids[i:i + 50])).execute()
        for v in r.get('items', []):
            videos.append({'youtube_id': v['id'],
                           'title': v['snippet']['title'],
                           'published_at': v['snippet'].get('publishedAt', ''),
                           'privacy': v.get('status', {}).get('privacyStatus', '')})
    return videos
