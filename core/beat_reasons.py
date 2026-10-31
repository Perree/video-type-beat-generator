"""Motivos legibles de los fallos de Beats, sin filtrar datos.

``classify(exc)`` convierte un error en un código fijo (``youtube_token_expired``,
``dropbox_error``, ...). Nunca usa el texto del error tal cual: solo códigos que el propio
proyecto lanza (``ValueError('beat_config_missing')``), motivos de una lista cerrada de la API
de YouTube y nombres de clase. ``note`` los cuenta en el resumen y ``lines`` arma el texto
para Telegram.
"""
import json
import re

KEY = 'reasons'
# Códigos del proyecto: palabras en minúscula unidas por guion bajo (al menos dos).
_CODE = re.compile(r'(?=.{5,60}$)[a-z][a-z0-9]*(?:_[a-z0-9]+)+')
_DEPTH = 6

# Motivos de la API de YouTube que se pueden mostrar (el resto queda como el código HTTP).
_YT_REASONS = {
    'quotaExceeded': 'youtube_quota',
    'dailyLimitExceeded': 'youtube_quota',
    'rateLimitExceeded': 'youtube_quota',
    'uploadLimitExceeded': 'youtube_upload_limit',
    'youtubeSignupRequired': 'youtube_channel_missing',
    'forbidden': 'youtube_forbidden',
    'insufficientPermissions': 'youtube_forbidden',
    'invalidPublishAt': 'youtube_invalid_publish_at',
}

TEXTS = {
    'youtube_token_expired': 'El permiso de YouTube venció o fue revocado. Reconectá el canal '
                             '(y revisá que la app de Google esté "En producción", no "Testing").',
    'youtube_token_invalid': 'El token de YouTube guardado en GitHub no es válido. Reconectá el canal.',
    'youtube_quota': 'Se agotó la cuota diaria de la API de YouTube. Se reintenta mañana.',
    'youtube_upload_limit': 'YouTube no deja subir más videos hoy en este canal (límite diario).',
    'youtube_channel_missing': 'La cuenta de Google conectada no tiene canal de YouTube.',
    'youtube_forbidden': 'YouTube rechazó el permiso (403). Reconectá el canal con la cuenta correcta.',
    'youtube_invalid_publish_at': 'YouTube rechazó la fecha de publicación del video.',
    'youtube_unavailable': 'YouTube no respondió (error del servidor). Se reintenta en otra corrida.',
    'youtube_deadline_exceeded': 'La subida a YouTube tardó demasiado y se cortó.',
    'youtube_owner_mismatch': 'El token conectado es de otro canal de YouTube. Reconectá el canal correcto.',
    'youtube_owner_unconfigured': 'Falta el ID del canal de YouTube en la config del canal.',
    'youtube_destination_changed': 'Cambió el canal de YouTube de destino en la config.',
    'calendar_read_failed': 'No se pudo leer el calendario de YouTube: hoy no se subió nada.',
    'dropbox_error': 'Falló Dropbox (estado del canal). Revisá la conexión de Dropbox.',
    'dropbox_api_error': 'Dropbox rechazó un pedido. Revisá la conexión de Dropbox.',
    'dropbox_busy': 'Dropbox estaba ocupado o limitado. Se reintenta en otra corrida.',
    'document_missing': 'Falta un archivo del canal en Dropbox (config o estado).',
    'missing_beat_dropbox_credentials': 'Faltan las credenciales de Dropbox en GitHub.',
    'beat_config_missing': 'No está la config de Beats en Dropbox.',
    'beat_state_missing': 'No está el estado de Beats en Dropbox.',
    'image_catalog_failed': 'No se pudieron listar las imágenes del canal en Dropbox.',
    'image_catalog_limit': 'La carpeta de imágenes del canal tiene demasiados archivos.',
    'download_limit': 'Un archivo de Dropbox superó el tamaño permitido.',
    'request_failed': 'BeatStars no respondió.',
    'scan_timeout': 'BeatStars tardó demasiado en responder.',
    'scan_incomplete': 'BeatStars devolvió el catálogo incompleto.',
    'remote_schema_error': 'BeatStars cambió el formato de su respuesta.',
    'invalid_profile': 'El link del perfil de BeatStars no es válido.',
    'render_failed': 'Falló el armado del video (FFmpeg).',
    'network_error': 'Falló la conexión a internet del runner.',
    'channel_missing_in_config': 'El canal no está en la config de Beats.',
    'missing_secret': 'Falta un secreto del canal en GitHub.',
    'thumbnail_rejected': 'YouTube no aceptó la miniatura (el canal tiene que estar verificado '
                          'por teléfono para usar miniaturas propias).',
    'slot_expired': 'El horario de un video pasó sin subirse (la corrida no llegó a tiempo).',
    'upload_reservation_day_changed': 'La subida cruzó la medianoche y se frenó por seguridad.',
}


def _chain(exc):
    seen = []
    while exc is not None and exc not in seen and len(seen) < _DEPTH:
        seen.append(exc)
        exc = exc.__cause__ or exc.__context__
    return seen


def _arg_code(exc):
    args = getattr(exc, 'args', ())
    if len(args) == 1 and isinstance(args[0], str) and _CODE.fullmatch(args[0]):
        return args[0]
    return None


def _http_code(exc):
    status = getattr(getattr(exc, 'resp', None), 'status', None)
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = 0
    try:
        body = json.loads((getattr(exc, 'content', b'') or b'').decode('utf-8', 'replace'))
        reasons = [e.get('reason') for e in body.get('error', {}).get('errors', [])]
    except Exception:
        reasons = []
    for reason in reasons:
        if reason in _YT_REASONS:
            return _YT_REASONS[reason]
    if status == 401:
        return 'youtube_token_expired'
    if status == 403:
        return 'youtube_forbidden'
    if status >= 500:
        return 'youtube_unavailable'
    return f'youtube_http_{status}' if status else 'youtube_error'


def _one(exc):
    name = type(exc).__name__
    names = {cls.__name__ for cls in type(exc).__mro__}
    if name == 'RefreshError':
        return 'youtube_token_expired'
    if name == 'HttpError':
        return _http_code(exc)
    if 'Transient' in names:
        return 'dropbox_busy'
    if 'CloudError' in names:
        return _arg_code(exc) or 'dropbox_error'
    if 'DropboxError' in names:
        return 'dropbox_error'
    if 'CalledProcessError' in names:
        return 'render_failed'
    if isinstance(exc, StopIteration):
        return 'channel_missing_in_config'
    if isinstance(exc, KeyError):
        arg = exc.args[0] if exc.args else ''
        return 'missing_secret' if isinstance(arg, str) and arg.startswith('BEAT_') else None
    code = _arg_code(exc)
    if code:
        return code
    if isinstance(exc, (ConnectionError, TimeoutError)) or name in ('URLError', 'timeout'):
        return 'network_error'
    return None


def classify(exc):
    """Código fijo para ``exc``; mira también las causas encadenadas."""
    chain = _chain(exc)
    for item in chain:
        code = _one(item)
        if code:
            return code
    # Último recurso: solo el nombre de la clase, nunca el mensaje.
    name = re.sub(r'[^A-Za-z]', '', type(exc).__name__)[:40] or 'Exception'
    return 'error_' + name.lower()


def note(summary, code_or_exc):
    """Suma un motivo al resumen (``summary['reasons'][código] += 1``). Nunca levanta."""
    try:
        code = code_or_exc if isinstance(code_or_exc, str) else classify(code_or_exc)
        if not _CODE.fullmatch(code):
            code = 'error_unknown'
        reasons = summary.setdefault(KEY, {})
        reasons[code] = reasons.get(code, 0) + 1
    except Exception:
        pass


def lines(summary):
    """Renglones para Telegram, uno por motivo. Ignora todo lo que no sea código + entero."""
    reasons = summary.get(KEY) if isinstance(summary, dict) else None
    if not isinstance(reasons, dict):
        return []
    out = []
    for code, count in sorted(reasons.items()):
        if not isinstance(code, str) or not _CODE.fullmatch(code) or type(count) is not int:
            continue
        text = TEXTS.get(code) or f'Error sin descripción ({code}).'
        out.append(f'- {text}' + (f' (x{count})' if count > 1 else ''))
    return out
