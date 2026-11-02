"""Actionable Telegram errors; never return remote text, URLs or credentials."""
import json
import ssl
from urllib.error import HTTPError, URLError


def message(error):
    if isinstance(error, HTTPError):
        try:
            payload = json.loads(error.read(4096))
            description = payload.get('description', '') if isinstance(payload, dict) else ''
            description = description.lower() if isinstance(description, str) else ''
        except Exception:
            description = ''
        finally:
            error.close()
        if error.code in (401, 404):
            return 'Telegram rechazó el token del bot. Copiá el token completo de API Token en @BotFather.'
        if error.code == 400 and 'chat not found' in description:
            return ('Telegram no encuentra ese chat. Abrí el bot correspondiente a este token, '
                    'enviá /start y revisá el chat ID del destinatario (no el ID del bot).')
        if error.code == 403 and 'blocked' in description:
            return 'El bot está bloqueado en Telegram. Desbloquealo, enviá /start y volvé a probar.'
        if error.code == 403:
            return ('El bot no tiene permiso para escribir en ese chat. En un chat privado enviá /start; '
                    'en un grupo o canal, agregá el bot y habilitá el envío de mensajes.')
        if error.code == 429:
            return 'Telegram limitó los mensajes. Esperá un momento y volvé a probar.'
        if error.code >= 500:
            return 'Telegram tiene un problema temporal. Volvé a probar en unos minutos.'
        return 'Telegram rechazó la solicitud. Revisá el token del bot y el chat ID del destinatario.'
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return 'No se pudo verificar el certificado HTTPS de Telegram. Revisá la fecha de Windows y los certificados.'
    if isinstance(reason, (TimeoutError, OSError)) or isinstance(error, URLError):
        return 'No se pudo conectar con Telegram. Revisá internet y si una VPN o firewall bloquea la conexión.'
    return 'No se pudo completar la respuesta de Telegram. Volvé a probar.'
