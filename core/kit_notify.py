# -*- coding: utf-8 -*-
"""Avisos del worker semanal por Telegram (urllib, sin dependencias nuevas).

Token y chat id salen del entorno. El token viaja solo en la URL de la API y nunca se
imprime ni aparece en un mensaje de error.
"""
import json
import os
import urllib.request
import uuid

from core import kit_cloud, kit_http

ENV_TOKEN = 'KIT_TELEGRAM_TOKEN'
ENV_CHAT = 'KIT_TELEGRAM_CHAT_ID'
STUDIO_URL = 'https://studio.youtube.com/video/{}/edit'
_API = 'https://api.telegram.org/bot{}/{}'
_TIMEOUT = 30


class KitNotifyError(Exception):
    pass


def _credentials(env):
    token = kit_cloud.secret(ENV_TOKEN, env)
    chat = kit_cloud.secret(ENV_CHAT, env)
    if not token or not chat:
        raise KitNotifyError(f"Faltan {ENV_TOKEN} / {ENV_CHAT} en el entorno.")
    return token, chat


def _post(token, method, body, content_type):
    req = urllib.request.Request(
        _API.format(token, method), data=body, headers={'Content-Type': content_type})
    try:
        with kit_http.open_request(req, timeout=_TIMEOUT) as resp:
            ok = json.loads(kit_http.read_response(resp, 65536).decode('utf-8')).get('ok')
    except Exception as e:
        # Solo el tipo: el texto del error puede traer la URL con el token.
        from core.telegram_errors import message
        raise KitNotifyError(message(e)) from None
    if not ok:
        raise KitNotifyError("Telegram rechazó el mensaje.")


def _multipart(fields, photo_path):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            .encode('utf-8'))
    with open(photo_path, 'rb') as f:
        data = f.read()
    parts.append(
        (f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; '
         f'filename="photo{os.path.splitext(photo_path)[1] or ".jpg"}"\r\n'
         'Content-Type: application/octet-stream\r\n\r\n').encode('utf-8') + data + b'\r\n')
    parts.append(f'--{boundary}--\r\n'.encode('utf-8'))
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def send(text, photo=None, env=None):
    """Manda ``text`` al chat configurado; con ``photo`` (ruta) va como pie de foto."""
    token, chat = _credentials(env)
    if photo:
        body, ctype = _multipart({'chat_id': chat, 'caption': text[:1024]}, photo)
        _post(token, 'sendPhoto', body, ctype)
    else:
        body = json.dumps({'chat_id': chat, 'text': text[:4096],
                           'disable_web_page_preview': True}).encode('utf-8')
        _post(token, 'sendMessage', body, 'application/json')


def summary(videos):
    """Texto con un link de YouTube Studio por video.

    Args:
        videos: dicts con ``youtube_id`` y opcionales ``title`` y ``slot`` (datetime o str).
    """
    if not videos:
        return "Loop kits: esta semana no se subió ningún video."
    lines = [f"Loop kits: {len(videos)} video(s) subidos en privado. "
             "Programalos en YouTube Studio:"]
    for i, v in enumerate(videos, 1):
        slot = v.get('slot')
        when = slot.strftime('%a %d/%m %H:%M') if hasattr(slot, 'strftime') else (slot or '')
        head = f"{i}. {when}".strip()
        lines.append(f"{head} - {v.get('title') or 'sin titulo'}")
        lines.append(STUDIO_URL.format(v['youtube_id']))
    return '\n'.join(lines)


_YOUTUBE_CODES = (('no está conectado', 'not_connected'), ('no es válido', 'token_invalid'),
                  ('No existe el video', 'video_missing'),
                  ('No se encontró el canal', 'channel_not_found'))


def error_kind(error):
    """Tipo del error para logs y alertas, sin mensaje (puede traer datos).

    Si es un error de YouTube que viene de una respuesta HTTP, suma el código y la razón que
    devuelve la API (por ejemplo ``HTTP 403 quotaExceeded``): son valores fijos, sin datos privados.
    """
    if isinstance(error, str):
        return error
    kind = type(error).__name__
    cause = getattr(error, '__cause__', None)
    status = getattr(getattr(cause, 'resp', None), 'status', None)
    if not isinstance(status, int):
        if kind == 'YouTubeError':
            # Motivos propios de core.youtube (el mensaje lleva el nombre del canal: no se copia).
            for needle, code in _YOUTUBE_CODES:
                if needle in str(error):
                    return f"{kind} {code}"
        return kind
    reason = ''
    try:
        items = json.loads(cause.content.decode('utf-8'))['error'].get('errors') or []
        reason = ''.join(c for c in str(items[0].get('reason') or '') if c.isalnum())[:40]
    except Exception:
        pass
    return f"{kind} HTTP {status}" + (f" {reason}" if reason else '')


def _action(error):
    """Bloque «ACCIÓN NECESARIA» si el error pide reconectar YouTube, o ''."""
    from core import beat_reasons
    if isinstance(error, str):
        return ''
    try:
        code = beat_reasons.classify(error)
    except Exception:
        return ''
    if type(error).__name__ == 'YouTubeError' and code.startswith('error_'):
        # Motivos propios de core.youtube: canal sin conectar o token inválido.
        kind = error_kind(error)
        code = 'youtube_token_invalid' if kind.endswith(('token_invalid', 'not_connected')) else code
    return '\n'.join(beat_reasons.action_lines([code], panel='Loop kits'))


def alert(error, step=None):
    """Texto de alerta: paso que falló y tipo de error, sin mensaje (puede traer datos).

    Si el error pide reconectar YouTube, el aviso empieza con los pasos para hacerlo.
    """
    kind = error_kind(error)
    where = f" en el paso '{step}'" if step else ''
    text = f"Loop kits: fallo el worker semanal{where} ({kind}). Revisar el log de Actions."
    action = _action(error)
    return f"{action}\n\n{text}" if action else text
