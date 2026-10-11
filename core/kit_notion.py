# -*- coding: utf-8 -*-
"""Lectura de la página de Notion con el informe semanal de tendencias (solo lectura).

La clave solo viaja a ``api.notion.com`` (URL fija, id de página validado) y no sigue
redirecciones a otro host. Ningún error lleva la URL, las cabeceras ni el contenido: solo un
``code`` fijo. El informe y su validación están en ``kit_trends``.
"""
import json
import re
import urllib.parse
import urllib.request

from core import kit_cloud

ENV_TOKEN = 'KIT_NOTION_TOKEN'
ENV_PAGE = 'KIT_NOTION_PAGE_ID'

_API = 'https://api.notion.com/v1'
_VERSION = '2022-06-28'
_MAX_BYTES = 2_000_000    # respuesta de Notion
_MAX_CHARS = 200_000      # texto del informe
_MAX_PAGES = 10           # páginas de bloques (100 bloques cada una)
_ID = re.compile(r'([0-9a-f]{32})(?:[?#].*)?\Z', re.IGNORECASE)


class NotionError(Exception):
    """Problema al leer el informe. ``code`` es una palabra fija: el mensaje no lleva datos."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code


def page_id(value):
    """Los 32 hex del final de un id o de una URL de página; None si no hay."""
    found = _ID.search(str(value or '').strip().replace('-', ''))
    return found.group(1).lower() if found else None


def configured(env=None):
    """True si están los dos secretos de Notion (la función es opcional)."""
    return bool(kit_cloud.secret(ENV_TOKEN, env) and page_id(kit_cloud.secret(ENV_PAGE, env)))


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # la clave no sigue a otro host
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _get(url, token, timeout):
    req = urllib.request.Request(url, headers={
        'Authorization': f'Bearer {token}', 'Notion-Version': _VERSION})
    try:
        with _OPENER.open(req, timeout=timeout) as resp:
            return json.loads(resp.read(_MAX_BYTES).decode('utf-8'))
    except Exception:
        # Sin el motivo: el texto del error puede traer la URL o cabeceras.
        raise NotionError('notion') from None


def fetch_report_text(timeout=30, env=None):
    """Texto del último bloque de código ``json`` con contenido de la página del informe."""
    token = kit_cloud.secret(ENV_TOKEN, env)
    page = page_id(kit_cloud.secret(ENV_PAGE, env))
    if not token or not page:
        raise NotionError('sin_notion')
    cursor, text = None, None
    for _ in range(_MAX_PAGES):
        url = f'{_API}/blocks/{page}/children?page_size=100'
        if cursor:
            url += '&start_cursor=' + urllib.parse.quote(str(cursor), safe='')
        data = _get(url, token, timeout)
        for block in data.get('results') or []:
            if not isinstance(block, dict) or block.get('type') != 'code':
                continue
            code = block.get('code')
            if isinstance(code, dict) and code.get('language') == 'json':
                parts = code.get('rich_text') or []
                found = ''.join(p.get('plain_text', '') for p in parts if isinstance(p, dict))
                if found.strip():  # un bloque vacío no tapa al informe
                    text = found
        if not data.get('has_more') or not data.get('next_cursor'):
            break
        cursor = data['next_cursor']
    if not text:
        raise NotionError('sin_bloque')
    return text[:_MAX_CHARS]
