# -*- coding: utf-8 -*-
"""Estado de las conexiones de Beats y Loop kits. Sin Qt.

Solo devuelve códigos (``ok/missing/invalid/unknown``) y nunca valores de secretos:
la UI y los logs pueden mostrarlos sin riesgo. El estado «ok» sale de GitHub
(``gh secret list --env <env> --json name,updatedAt`` y ``gh variable get``, con caché
en memoria, ver ``core/gh_status``) y Dropbox de esta PC del llavero (``core/cloud_login``).
Ya no se lee ``tokens/``: los secretos se escriben directo a GitHub Secrets por stdin.
"""
import os
import re
import shutil

from core import cloud_login, gh_status, kit_channel, kit_notion
from core.beat_actions import secret_names

OK, MISSING, INVALID, UNKNOWN = 'ok', 'missing', 'invalid', 'unknown'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKENS_DIR = os.path.join(ROOT, 'tokens')  # solo informes SEO locales (seo_report_status)
ENV = gh_status.ENV
REPO = gh_status.REPO  # secretos del repo: los ve el Environment de cada canal sin copiarlos
NOTION_KEYS = ('BEAT_NOTION_TOKEN', 'BEAT_NOTION_PAGE_ID')
KIT_NOTION_KEYS = ('KIT_NOTION_TOKEN', 'KIT_NOTION_PAGE_ID')
KIT_TELEGRAM_KEYS = ('KIT_TELEGRAM_TOKEN', 'KIT_TELEGRAM_CHAT_ID')
GLOBAL_TELEGRAM_KEYS = ('AUTOMATION_TELEGRAM_TOKEN', 'AUTOMATION_TELEGRAM_CHAT_ID')
KIT_DROPBOX_KEYS = ('KIT_DROPBOX_REFRESH_TOKEN', 'KIT_DROPBOX_APP_KEY')
KIT_YT_KEYS = ('KIT_YT_CHANNEL', 'KIT_YT_TOKEN_JSON')
KIT_LLM_KEY = 'KIT_LLM_API_KEY'
KIT_IMAGE_KEY = 'KIT_IMAGE_API_KEY'
# Misma lista que scripts/kit_secrets_sync.SHARED: la UI no puede inventar nombres.
# Son de todos los canales (Beats y Loop kits): se guardan una vez en el repo. Por canal solo va YouTube.
KIT_SHARED_KEYS = (
    *KIT_DROPBOX_KEYS,
    KIT_LLM_KEY, KIT_IMAGE_KEY,
    *KIT_TELEGRAM_KEYS, *KIT_NOTION_KEYS,
)
_SLUG = re.compile('[a-z][a-z0-9-]{0,39}')
# Mismas reglas que core/beat_notion.fetch_report para que "ok" signifique "usable".
_PAGE_ID = re.compile(r'(?:[0-9a-fA-F]{32}|[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12})')


class AutomationError(Exception):
    """Mensaje apto para la UI: nunca incluye valores ni rutas."""


def _gh(gh):
    return gh or gh_status.default()


def _inside(path, base):
    """True si ``path`` queda dentro de ``base`` (evita path traversal por nombre de canal)."""
    base = os.path.realpath(base)
    return os.path.commonpath([os.path.realpath(path), base]) == base


def valid_notion(token, page_id):
    """True si el par token/página cumple las reglas del lector de Notion de Beats."""
    return (isinstance(token, str) and 0 < len(token) <= 512
            and all(32 < ord(c) < 127 for c in token)
            and isinstance(page_id, str) and bool(_PAGE_ID.fullmatch(page_id)))


def valid_slug(slug):
    return isinstance(slug, str) and bool(_SLUG.fullmatch(slug))


_printable = cloud_login.printable


# --- Lectura (solo nombres y fechas) ---

def _list(environment, gh):
    try:
        return _gh(gh).secrets(environment)
    except gh_status.GhError:
        return None


def _listed(names, environment, gh, shared):
    """``{nombre: fecha}`` visibles para ``environment``; ``None`` si no se pudo saber.

    ``shared``: también cuentan los del repo (GitHub los hereda a cada Environment; uno del
    Environment con el mismo nombre tiene prioridad).
    """
    if set(names) == set(KIT_TELEGRAM_KEYS):
        repo = _list(REPO, gh)
        if repo and all(k in repo for k in GLOBAL_TELEGRAM_KEYS):
            return {old: repo[new] for old, new in zip(KIT_TELEGRAM_KEYS, GLOBAL_TELEGRAM_KEYS)}
    own = _list(environment, gh)
    if not shared or environment is REPO:
        return own
    repo = _list(REPO, gh)
    if own is None and repo is None:
        return None
    merged = dict(repo or {})
    merged.update(own or {})
    if (own is None or repo is None) and not all(n in merged for n in names):
        return None  # falta una de las dos listas: no se puede decir «falta»
    return merged


def secrets_state(names, environment=ENV, gh=None, shared=False):
    """``ok`` si están todos, ``missing`` si ninguno, ``invalid`` si a medias.

    ``unknown`` si no se pudo listar (sin ``gh`` o sin sesión). Nunca lee valores.
    """
    listed = _listed(names, environment, gh, shared)
    if listed is None:
        return UNKNOWN
    present = [n in listed for n in names]
    if all(present):
        return OK
    return INVALID if any(present) else MISSING


def secrets_date(names, environment=ENV, gh=None, shared=False):
    """Fecha (``AAAA-MM-DD``) de la última actualización entre ``names``, o ``''``."""
    listed = _listed(names, environment, gh, shared) or {}
    days = [gh_status.day(listed[n]) for n in names if n in listed]
    return max(days) if days else ''


def secrets_badge(names, environment=ENV, gh=None, shared=False):
    """``(código, texto)`` para la UI: «cargado ✓ (fecha)» en lugar del valor."""
    code = secrets_state(names, environment, gh, shared)
    if code == OK:
        date = secrets_date(names, environment, gh, shared)
        return code, f'cargado ✓ ({date})' if date else 'cargado ✓'
    if code == UNKNOWN and _gh(gh).pending():
        return code, 'Consultando GitHub…'
    return code, {MISSING: 'Falta', INVALID: 'Incompleto',
                  UNKNOWN: 'Sin acceso a GitHub (gh auth login)'}[code]


def gh_auth_status(gh=None):
    """``ok`` si ``gh auth status`` tiene sesión (no solo el binario)."""
    return _gh(gh).auth()


def gh_available(which=shutil.which):
    """``ok`` si la GitHub CLI está en el PATH (la sesión la mide ``gh_auth_status``)."""
    return OK if which('gh') else MISSING


def dropbox_desktop_status():
    """Dropbox de esta PC (llavero de Windows)."""
    return cloud_login.dropbox_status()


def beat_secret_names(slug):
    """``(BEAT_CHANNEL_ID_<SLUG>, BEAT_YT_TOKEN_JSON_<SLUG>)`` o ``None`` si el slug no sirve."""
    if not valid_slug(slug):
        return None
    try:
        names = secret_names(slug)
    except ValueError:
        return None
    return names['channel_secret'], names['youtube_secret']


def beat_youtube_status(slug, gh=None):
    """Token de YouTube del canal de Beats (``BEAT_YT_TOKEN_JSON_<SLUG>``) en ``kit-weekly``."""
    names = beat_secret_names(slug)
    return secrets_state(names[1:], ENV, gh) if names else UNKNOWN


def beat_listed_status(slug, gh=None):
    """``ok`` si el slug está en la variable ``BEAT_CHANNELS``."""
    if not valid_slug(slug):
        return UNKNOWN
    import json
    raw = _gh(gh).variable('BEAT_CHANNELS')
    if raw is None:
        return UNKNOWN if gh_auth_status(gh) != OK else MISSING
    try:
        return OK if slug in json.loads(raw) else MISSING
    except (ValueError, TypeError):
        return INVALID


def kit_youtube_status(environment, gh=None):
    """``KIT_YT_CHANNEL`` + ``KIT_YT_TOKEN_JSON`` en el Environment del canal de kits."""
    return secrets_state(KIT_YT_KEYS, environment, gh) if environment else UNKNOWN


def shared_badge(names, environment=REPO, gh=None):
    """Badge de una clave compartida: la del repo (o la que ve el Environment de un canal)."""
    return secrets_badge(names, environment, gh, shared=True)


def dropbox_worker_status(environment=REPO, gh=None):
    """Credenciales de Dropbox del worker (``KIT_DROPBOX_*``): en el repo o en el Environment."""
    return secrets_state(KIT_DROPBOX_KEYS, environment, gh, shared=True)


def beat_notion_status(gh=None):
    """Notion Beats (``BEAT_NOTION_*``) en ``kit-weekly``."""
    return secrets_state(NOTION_KEYS, ENV, gh)


def _env_values(names, env):
    return [str(env.get(n) or '').strip() for n in names]


def kit_notion_status(environment=REPO, gh=None, env=None):
    """Notion Kits. ``env`` (dict) evalúa valores en memoria, p. ej. en el runner."""
    if env is not None:
        token, page = _env_values(KIT_NOTION_KEYS, env)
        if not token and not page:
            return MISSING
        return OK if _printable(token) and kit_notion.page_id(page) else INVALID
    return secrets_state(KIT_NOTION_KEYS, environment, gh, shared=True)


def kit_telegram_status(environment=REPO, gh=None, env=None):
    """Telegram (avisos de todos los canales, Beats y Loop kits): hacen falta token y chat id."""
    if env is not None:
        token, chat = _env_values(KIT_TELEGRAM_KEYS, env)
        if not token and not chat:
            return MISSING
        return OK if _printable(token, 4096) and _printable(chat, 128) else INVALID
    return secrets_state(KIT_TELEGRAM_KEYS, environment, gh, shared=True)


def kit_llm_status(environment=REPO, gh=None, env=None):
    """``ok`` si hay clave LLM; no se valida contra la API."""
    if env is not None:
        return OK if _env_values((KIT_LLM_KEY,), env)[0] else MISSING
    return secrets_state((KIT_LLM_KEY,), environment, gh, shared=True)


def kit_image_status(environment=REPO, gh=None, env=None):
    """``ok`` si hay clave de imágenes; no se valida contra la API."""
    if env is not None:
        return OK if _env_values((KIT_IMAGE_KEY,), env)[0] else MISSING
    return secrets_state((KIT_IMAGE_KEY,), environment, gh, shared=True)


def kit_env_name(automation_slug):
    """``kit-weekly`` o ``kit-weekly-<slug>``; ``None`` si el slug no sirve."""
    try:
        return kit_channel.environment(automation_slug)
    except kit_channel.KitChannelError:
        return None


def kit_environments(gh=None):
    """Destino de los compartidos: el repo (lo heredan los canales nuevos), ``kit-weekly`` y los
    ``kit-weekly-<slug>`` que existan (una copia vieja en un Environment taparía la del repo).

    Si no se pudo listar, AutomationError: escribir solo en ``kit-weekly`` dejaría a los
    canales con Environment propio con un valor viejo sin avisar.
    """
    found = _gh(gh).environments()
    if found is None:
        raise AutomationError('No se pudieron listar los Environments de GitHub; no se '
                              'guardó nada. Reintentá.')
    return [REPO, ENV] + sorted(e for e in found if e != ENV)


# --- Escritura (directo a GitHub Secrets por stdin) ---

def _write(values, environments, gh=None):
    """Sube cada valor a cada Environment. AutomationError (sin valores) si algo falló."""
    client = _gh(gh)
    if client.auth() != OK:
        raise AutomationError('GitHub no está conectado: corré «gh auth login» y reintentá.')
    failed = []
    for environment in environments:
        for name, value in values.items():
            try:
                ok = client.set_secret(name, value, environment)
            except gh_status.GhError:
                ok = False
            if not ok:
                failed.append(f'{name} ({environment or "repo"})')
    if failed:
        raise AutomationError('No se cargaron en GitHub: ' + ', '.join(failed) + '.')
    return list(environments)


def save_beat_notion(token, page_id, gh=None):
    """Sube token y page id de Notion Beats a ``kit-weekly``.

    Lanza ``AutomationError`` (mensaje sin valores) si no pasan la validación.
    """
    token, page_id = (token or '').strip(), (page_id or '').strip()
    if not valid_notion(token, page_id):
        raise AutomationError('Notion: token o page ID con formato inválido.')
    _write(dict(zip(NOTION_KEYS, (token, page_id))), [ENV], gh)


def clean_kit_keys(updates):
    """Valida solo claves SHARED conocidas; las vacías se omiten. Devuelve el dict limpio."""
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
    return clean


def save_kit_keys(updates, gh=None, environments=None):
    """Telegram vive solo en el repo; las demás claves se sincronizan a los Environments.

    Devuelve los Environments escritos. Los valores nunca tocan el disco.
    """
    clean = clean_kit_keys(updates)
    telegram = {k: clean.pop(k) for k in KIT_TELEGRAM_KEYS if k in clean}
    written = _write({GLOBAL_TELEGRAM_KEYS[KIT_TELEGRAM_KEYS.index(k)]: v
                      for k, v in telegram.items()}, [REPO], gh) if telegram else []
    if clean:
        written += _write(clean, environments or kit_environments(gh), gh)
    return list(dict.fromkeys(written))


def save_kit_notion(token, page_id, gh=None, environments=None):
    """Sube el par Notion Kits; exige los dos valores juntos."""
    token, page_id = (token or '').strip(), (page_id or '').strip()
    if not _printable(token) or not kit_notion.page_id(page_id):
        raise AutomationError('Notion: token o page ID con formato inválido.')
    return save_kit_keys({'KIT_NOTION_TOKEN': token, 'KIT_NOTION_PAGE_ID': page_id},
                         gh, environments)


def save_worker_dropbox(credentials, gh=None, environments=None):
    """Sube ``KIT_DROPBOX_*`` de una autorización **propia del worker** a todos los Environments.

    ``credentials`` sale de ``cloud_login.dropbox_exchange`` (en memoria, nunca del llavero):
    el token del worker es distinto del de esta PC, así cada uno se revoca por separado.
    """
    if (not isinstance(credentials, dict)
            or not _printable(credentials.get('refresh_token'), cloud_login.MAX_VALUE)
            or not _printable(credentials.get('app_key'), 128)):
        raise AutomationError('Dropbox no devolvió credenciales válidas para el worker.')
    values = {'KIT_DROPBOX_REFRESH_TOKEN': credentials['refresh_token'],
              'KIT_DROPBOX_APP_KEY': credentials['app_key']}
    return _write(values, environments or kit_environments(gh), gh)


# --- A qué canal van los secretos ---

def beat_slug_error(channel, slug, config_channels=(), registry=None):
    """Mensaje si subir secretos de ``slug`` para ``channel`` pisaría a otro canal; si no, None.

    ``BEAT_*_<SLUG>`` es de un solo canal: el slug tiene que ser el del registro para esa
    clave y no puede estar en otra fila del config ni del registro (de cualquier tipo).
    """
    if not channel or not valid_slug(slug):
        return 'El canal necesita un actions_slug válido.'
    for row in config_channels or ():
        if row.get('id') != channel and row.get('actions_slug') == slug:
            return f'El slug {slug} ya es del canal «{row.get("id")}»: no se tocaron sus secretos.'
    for row in (registry or {}).get('canales') or ():
        if not isinstance(row, dict):
            continue
        if row.get('slug') == slug and row.get('clave') != channel:
            return (f'El slug {slug} es del canal «{row.get("clave")}» en el registro: '
                    'no se tocaron sus secretos.')
        if row.get('clave') == channel and row.get('slug') != slug:
            return f'En el registro el slug de este canal es {row.get("slug")}, no {slug}.'
    return None


def kit_default_channel(registry=None, base_config=None):
    """Canal dueño de ``kit-weekly``: el ``legacy_default`` del registro o el del config guardado."""
    for row in (registry or {}).get('canales') or ():
        if isinstance(row, dict) and row.get('tipo') == 'loops' and row.get('legacy_default'):
            return row.get('clave') or None
    kit = (base_config or {}).get('kit_preview') if isinstance(base_config, dict) else None
    name = kit.get('channel') if isinstance(kit, dict) else None
    return name.strip() if isinstance(name, str) and name.strip() else None


def youtube_identity_error(expected_id, got_id):
    """Mensaje si la cuenta autorizada no es el canal esperado (cuando se conoce el id)."""
    if expected_id and got_id != expected_id:
        return ('La cuenta de Google autorizada es de otro canal de YouTube: no se subió nada. '
                'Volvé a conectar y elegí la cuenta correcta.')
    return None


# --- Checklists ---

def readiness_kits(channel, automation_slug, gh=None):
    """Checklist ``[{id, ok, label}]`` del canal de Loop kits.

    Notion, LLM e imagen son opcionales: la UI los muestra pero no bloquean el sync.
    """
    env_name = kit_env_name(automation_slug)
    target = env_name or ENV
    items = [
        ('env', bool(env_name), 'Environment kit-weekly (canal por defecto o slug válido)'),
        ('youtube', bool(channel) and kit_youtube_status(env_name, gh) == OK,
         'Token de YouTube del canal (en GitHub)'),
        ('dropbox', dropbox_worker_status(target, gh) == OK, 'Credenciales de Dropbox del worker'),
        ('telegram', kit_telegram_status(target, gh) == OK, 'Telegram (token y chat id)'),
        ('gh', gh_auth_status(gh) == OK, 'GitHub conectado (gh auth login)'),
        ('notion', kit_notion_status(target, gh) == OK, 'Notion Kits (opcional, tendencias)'),
        ('llm', kit_llm_status(target, gh) == OK, 'Clave LLM (opcional, nombres)'),
        ('image', kit_image_status(target, gh) == OK, 'Clave de imágenes (opcional, portadas)'),
    ]
    return [{'id': i, 'ok': ok, 'label': label} for i, ok, label in items]


def kit_sync_blockers(channel, automation_slug, gh=None):
    """Etiquetas de requisitos que bloquean preparar el Environment desde la UI."""
    out = []
    if not (channel or '').strip():
        out.append('Elegí el canal de YouTube')
    if not kit_env_name(automation_slug):
        out.append('Environment kit-weekly (canal por defecto o slug válido)')
    if gh_auth_status(gh) != OK:
        out.append('GitHub conectado (gh auth login)')
    return out


def readiness_beats(channel, slug, gh=None):
    """Checklist ``[{id, ok, label}]`` para dejar el canal listo en Actions.

    Notion es opcional (solo SEO), por eso no bloquea ``ok`` global: lo decide la UI.
    """
    items = [
        ('slug', valid_slug(slug), 'Canal con slug de Actions válido (actions_slug)'),
        ('youtube', bool(channel) and beat_youtube_status(slug, gh) == OK,
         'Token de YouTube del canal (en GitHub)'),
        ('dropbox', dropbox_worker_status(ENV, gh) == OK, 'Credenciales de Dropbox del worker'),
        ('gh', gh_auth_status(gh) == OK, 'GitHub conectado (gh auth login)'),
        ('notion', beat_notion_status(gh) == OK, 'Notion Beats (opcional, solo SEO)'),
    ]
    return [{'id': i, 'ok': ok, 'label': label} for i, ok, label in items]
