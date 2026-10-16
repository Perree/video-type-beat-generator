# -*- coding: utf-8 -*-
"""Estado de las conexiones de Beats y Loop kits. Sin Qt.

Solo devuelve códigos (``ok/missing/invalid/unknown``) y nunca valores de secretos:
la UI y los logs pueden mostrarlos sin riesgo. Notion Beats vive en
``tokens/beat_secrets.json``; los SHARED de kits en ``tokens/kit_secrets.json``.
``tokens/`` no se versiona.
"""
import json
import os
import re
import shutil

from core import kit_channel, kit_notion, youtube

OK, MISSING, INVALID, UNKNOWN = 'ok', 'missing', 'invalid', 'unknown'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS_DIR = os.path.join(ROOT, 'tokens')
BEAT_SECRETS_FILE = os.path.join(TOKENS_DIR, 'beat_secrets.json')
KIT_SECRETS_FILE = os.path.join(TOKENS_DIR, 'kit_secrets.json')
DROPBOX_FILE = os.path.join(TOKENS_DIR, 'dropbox_worker.json')
NOTION_KEYS = ('BEAT_NOTION_TOKEN', 'BEAT_NOTION_PAGE_ID')
KIT_NOTION_KEYS = ('KIT_NOTION_TOKEN', 'KIT_NOTION_PAGE_ID')
KIT_TELEGRAM_KEYS = ('KIT_TELEGRAM_TOKEN', 'KIT_TELEGRAM_CHAT_ID')
KIT_LLM_KEY = 'KIT_LLM_API_KEY'
KIT_IMAGE_KEY = 'KIT_IMAGE_API_KEY'
# Misma lista que scripts/kit_secrets_sync.SHARED: la UI no puede inventar nombres.
KIT_SHARED_KEYS = (
    'KIT_DROPBOX_REFRESH_TOKEN', 'KIT_DROPBOX_APP_KEY',
    KIT_LLM_KEY, KIT_IMAGE_KEY,
    *KIT_TELEGRAM_KEYS, *KIT_NOTION_KEYS,
)
_SLUG = re.compile('[a-z][a-z0-9-]{0,39}')
# Mismas reglas que core/beat_notion.fetch_report para que "ok" signifique "usable".
_PAGE_ID = re.compile(r'(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})')


class AutomationError(Exception):
    """Mensaje apto para la UI: nunca incluye valores ni rutas."""


def _load_json(path):
    """Dict del JSON o ``None`` si no existe; ``INVALID`` marcado con ``False``."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return False
    return data if isinstance(data, dict) else False


def _inside(path, base):
    """True si ``path`` queda dentro de ``base`` (evita path traversal por nombre de canal)."""
    base = os.path.realpath(base)
    return os.path.commonpath([os.path.realpath(path), base]) == base


def valid_notion(token, page_id):
    """True si el par token/página cumple las reglas del lector de Notion de Beats."""
    return (isinstance(token, str) and 0 < len(token) <= 512
            and all(32 < ord(c) < 127 for c in token)
            and isinstance(page_id, str) and bool(_PAGE_ID.fullmatch(page_id)))


def youtube_token_status(channel, tokens_dir=None):
    """Estado del token OAuth ``tokens/<canal>.json`` del canal."""
    if not isinstance(channel, str) or not channel.strip():
        return UNKNOWN
    base = tokens_dir or TOKENS_DIR
    path = youtube._token_path(channel, base)  # ya sanea el nombre del archivo
    if not _inside(path, base):
        return INVALID
    data = _load_json(path)
    if data is None:
        return MISSING
    return OK if data and data.get('refresh_token') else INVALID


def dropbox_worker_status(path=None):
    """Estado de ``tokens/dropbox_worker.json`` (refresh_token + app_key)."""
    data = _load_json(path or DROPBOX_FILE)
    if data is None:
        return MISSING
    return OK if data and data.get('refresh_token') and data.get('app_key') else INVALID


def read_beat_notion(path=None):
    """``{BEAT_NOTION_*: valor}`` válidos del archivo local, o ``{}``. Uso interno y del sync."""
    data = _load_json(path or BEAT_SECRETS_FILE)
    if not data:
        return {}
    token, page = (str(data.get(k) or '').strip() for k in NOTION_KEYS)
    return dict(zip(NOTION_KEYS, (token, page))) if valid_notion(token, page) else {}


def beat_notion_status(path=None):
    """Estado de las credenciales de Notion Beats en ``tokens/beat_secrets.json``."""
    data = _load_json(path or BEAT_SECRETS_FILE)
    if data is None or (data is not False and not any(data.get(k) for k in NOTION_KEYS)):
        return MISSING
    return OK if read_beat_notion(path) else INVALID


def save_beat_notion(token, page_id, path=None):
    """Guarda token y page id de Notion Beats conservando otras claves del archivo.

    Lanza ``AutomationError`` (mensaje sin valores) si no pasan la validación.
    """
    token, page_id = (token or '').strip(), (page_id or '').strip()
    if not valid_notion(token, page_id):
        raise AutomationError('Notion: token o page ID con formato inválido.')
    path = path or BEAT_SECRETS_FILE
    data = _load_json(path)
    data = data if isinstance(data, dict) else {}
    data.update(dict(zip(NOTION_KEYS, (token, page_id))))
    tmp = path + '.tmp'
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Escritura atómica: un corte no deja el archivo truncado.
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError:
        raise AutomationError('No se pudo guardar las credenciales de Notion.') from None


def gh_available(which=shutil.which):
    """``ok`` si la GitHub CLI está en el PATH (no valida la sesión: eso es ``gh auth``)."""
    return OK if which('gh') else MISSING


def valid_slug(slug):
    return isinstance(slug, str) and bool(_SLUG.fullmatch(slug))


def _printable(value, max_len=512):
    return (isinstance(value, str) and 0 < len(value) <= max_len
            and all(32 < ord(c) < 127 for c in value))


def _kit_file(path=None):
    """Dict de ``kit_secrets.json``, ``None`` si no existe, ``False`` si está corrupto."""
    return _load_json(path or KIT_SECRETS_FILE)


def read_kit_secrets(path=None):
    """``{KIT_*: valor}`` de claves SHARED presentes; vacío si el archivo no sirve."""
    data = _kit_file(path)
    if not data:
        return {}
    out = {}
    for key in KIT_SHARED_KEYS:
        value = str(data.get(key) or '').strip()
        if value:
            out[key] = value
    return out


def _kit_value(name, path=None, env=None):
    """Valor de un SHARED: archivo local primero, si no el entorno (sin imprimirlo)."""
    value = read_kit_secrets(path).get(name) or ''
    if value:
        return value
    env = os.environ if env is None else env
    return str(env.get(name) or '').strip()


def _presence(name, path=None, env=None):
    """``ok`` / ``missing`` / ``invalid`` para un secreto suelto (LLM, imagen)."""
    data = _kit_file(path)
    if data is False:
        return INVALID
    return OK if _kit_value(name, path, env) else MISSING


def save_kit_keys(updates, path=None):
    """Fusiona solo claves SHARED conocidas. Las vacías no se tocan.

    Lanza ``AutomationError`` (sin valores) si hay una clave ajena o un formato inválido.
    """
    if not isinstance(updates, dict):
        raise AutomationError('No se pudieron guardar las credenciales.')
    clean = {}
    for key, value in updates.items():
        if key not in KIT_SHARED_KEYS:
            raise AutomationError('Clave de secreto no permitida.')
        value = (value or '').strip()
        if not value:
            continue
        if key == 'KIT_NOTION_PAGE_ID':
            nid = kit_notion.page_id(value)
            if not nid:
                raise AutomationError('Notion: token o page ID con formato inválido.')
            value = nid
        elif not _printable(value, 4096 if 'TOKEN' in key or key.endswith('_KEY') else 128):
            raise AutomationError('Valor de secreto con formato inválido.')
        clean[key] = value
    if not clean:
        raise AutomationError('No hay valores nuevos para guardar.')
    path = path or KIT_SECRETS_FILE
    data = _load_json(path)
    data = data if isinstance(data, dict) else {}
    data.update(clean)
    tmp = path + '.tmp'
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except OSError:
        raise AutomationError('No se pudieron guardar las credenciales.') from None


def kit_notion_status(path=None, env=None):
    """Estado de Notion Kits (archivo o entorno)."""
    data = _kit_file(path)
    token = _kit_value('KIT_NOTION_TOKEN', path, env)
    page = _kit_value('KIT_NOTION_PAGE_ID', path, env)
    if data is False:
        return INVALID
    if not token and not page:
        return MISSING
    return OK if _printable(token) and kit_notion.page_id(page) else INVALID


def save_kit_notion(token, page_id, path=None):
    """Guarda el par Notion Kits; exige los dos valores juntos."""
    token, page_id = (token or '').strip(), (page_id or '').strip()
    if not _printable(token) or not kit_notion.page_id(page_id):
        raise AutomationError('Notion: token o page ID con formato inválido.')
    save_kit_keys({'KIT_NOTION_TOKEN': token, 'KIT_NOTION_PAGE_ID': page_id}, path)


def kit_telegram_status(path=None, env=None):
    """Estado de Telegram Kits: hacen falta token y chat id."""
    data = _kit_file(path)
    token = _kit_value('KIT_TELEGRAM_TOKEN', path, env)
    chat = _kit_value('KIT_TELEGRAM_CHAT_ID', path, env)
    if data is False:
        return INVALID
    if not token and not chat:
        return MISSING
    return OK if _printable(token, 4096) and _printable(chat, 128) else INVALID


def kit_llm_status(path=None, env=None):
    """``ok`` si hay clave LLM; no se valida contra la API."""
    return _presence(KIT_LLM_KEY, path, env)


def kit_image_status(path=None, env=None):
    """``ok`` si hay clave de imágenes; no se valida contra la API."""
    return _presence(KIT_IMAGE_KEY, path, env)


def kit_env_name(automation_slug):
    """``kit-weekly`` o ``kit-weekly-<slug>``; ``None`` si el slug no sirve."""
    try:
        return kit_channel.environment(automation_slug)
    except kit_channel.KitChannelError:
        return None


def readiness_kits(channel, automation_slug, tokens_dir=None, dropbox_file=None,
                   secrets_file=None, which=shutil.which, env=None):
    """Checklist ``[{id, ok, label}]`` del canal de Loop kits.

    Notion, LLM e imagen son opcionales: la UI los muestra pero no bloquean el sync.
    """
    env_name = kit_env_name(automation_slug)
    items = [
        ('env', bool(env_name), 'Environment kit-weekly (canal por defecto o slug válido)'),
        ('youtube', youtube_token_status(channel, tokens_dir) == OK, 'Token de YouTube del canal'),
        ('dropbox', dropbox_worker_status(dropbox_file) == OK, 'Credenciales de Dropbox del worker'),
        ('telegram', kit_telegram_status(secrets_file, env) == OK, 'Telegram (token y chat id)'),
        ('gh', gh_available(which) == OK, 'GitHub CLI (gh) instalada'),
        ('notion', kit_notion_status(secrets_file, env) == OK, 'Notion Kits (opcional, tendencias)'),
        ('llm', kit_llm_status(secrets_file, env) == OK, 'Clave LLM (opcional, nombres)'),
        ('image', kit_image_status(secrets_file, env) == OK, 'Clave de imágenes (opcional, portadas)'),
    ]
    return [{'id': i, 'ok': ok, 'label': label} for i, ok, label in items]


def kit_sync_blockers(channel, automation_slug, tokens_dir=None, dropbox_file=None,
                      secrets_file=None, which=shutil.which, env=None):
    """Etiquetas de requisitos que bloquean un sync desde la UI (sin Notion/LLM/imagen)."""
    required = ('env', 'youtube', 'dropbox', 'telegram', 'gh')
    return [i['label'] for i in readiness_kits(
        channel, automation_slug, tokens_dir, dropbox_file, secrets_file, which, env)
            if i['id'] in required and not i['ok']]


def readiness_beats(channel, slug, tokens_dir=None, dropbox_file=None, notion_file=None,
                    which=shutil.which):
    """Checklist ``[{id, ok, label}]`` para dejar el canal listo en Actions.

    Notion es opcional (solo SEO), por eso no bloquea ``ok`` global: lo decide la UI.
    """
    items = [
        ('slug', valid_slug(slug), 'Canal con slug de Actions válido (actions_slug)'),
        ('youtube', youtube_token_status(channel, tokens_dir) == OK, 'Token de YouTube del canal'),
        ('dropbox', dropbox_worker_status(dropbox_file) == OK, 'Credenciales de Dropbox del worker'),
        ('gh', gh_available(which) == OK, 'GitHub CLI (gh) instalada'),
        ('notion', beat_notion_status(notion_file) == OK, 'Notion Beats (opcional, solo SEO)'),
    ]
    return [{'id': i, 'ok': ok, 'label': label} for i, ok, label in items]
