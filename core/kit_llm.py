# -*- coding: utf-8 -*-
"""Llamada mínima a un LLM por HTTP (urllib, API estilo chat/completions).

``cfg`` trae ``base_url``, ``model`` y ``key_file`` (ruta a un archivo con la clave);
opcionales ``max_tokens``, ``temperature`` y ``timeout``. La clave solo viaja en el
header Authorization: nunca se imprime ni aparece en un mensaje de error.

La config puede venir de Dropbox, así que no decide a dónde va la clave ni de qué archivo
sale: ``base_url`` tiene que apuntar a un host de ``ALLOWED_HOSTS`` (ampliable solo con la
variable de entorno ``KIT_API_HOSTS``) y, con credenciales ``KIT_*`` en el entorno,
``key_file`` no se lee.
"""
import json
import os
import urllib.parse
import urllib.request

from core import kit_cloud

ENV_HOSTS = 'KIT_API_HOSTS'
ALLOWED_HOSTS = ('api.openai.com',)
_DEFAULT_TIMEOUT = 60
_DEFAULT_MAX_TOKENS = 300


class KitLlmError(Exception):
    pass


def allowed_hosts(env=None):
    """Hosts a los que se puede mandar una clave: los fijos más ``KIT_API_HOSTS`` (por comas)."""
    env = os.environ if env is None else env
    extra = (h.strip().lower() for h in (env.get(ENV_HOSTS) or '').split(','))
    return set(ALLOWED_HOSTS) | {h for h in extra if h}


def check_base_url(base_url, what='del LLM', env=None):
    """Devuelve ``base_url`` sin barra final si es https y su host está permitido.

    Raises:
        KitLlmError: no es https, lleva usuario o un puerto distinto de 443, o el host no
            está en ``allowed_hosts``. El mensaje no repite la URL.
    """
    url = str(base_url or '').strip().rstrip('/')
    try:
        parts = urllib.parse.urlsplit(url)
        host, port = (parts.hostname or '').lower(), parts.port
    except ValueError:
        parts = None
    if parts is None or parts.scheme != 'https' or not host:
        raise KitLlmError(f"base_url {what} debe ser https.")
    odd = chr(92) in url or any(c.isspace() or ord(c) < 32 for c in url)
    if (odd or parts.username or parts.password or port not in (None, 443)
            or host not in allowed_hosts(env)):
        raise KitLlmError(f"base_url {what} no apunta a un host permitido "
                          f"(se amplía con la variable de entorno {ENV_HOSTS}).")
    return url


def read_key(cfg):
    """Lee la clave del archivo ``cfg['key_file']`` (primera línea, sin espacios).

    Con credenciales ``KIT_*`` en el entorno (worker en la nube) no se lee ningún archivo:
    la clave tiene que venir en su variable de entorno.
    """
    if kit_cloud.in_cloud():
        raise KitLlmError("En la nube la clave va en su variable de entorno; key_file no se usa.")
    path = (cfg or {}).get('key_file')
    if not path:
        raise KitLlmError("Falta key_file en la config del LLM.")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            key = f.readline().strip()
    except OSError:
        raise KitLlmError("No se pudo leer el archivo de clave del LLM.") from None
    if not key:
        raise KitLlmError("El archivo de clave del LLM está vacío.")
    return key


def call(system, user, cfg, key=None):
    """Devuelve el texto de la respuesta. Sin ``key`` la lee de ``cfg['key_file']``."""
    cfg = cfg or {}
    base_url = (cfg.get('base_url') or '').strip()
    model = (cfg.get('model') or '').strip()
    if not base_url or not model:
        raise KitLlmError("Faltan base_url y model en la config del LLM.")
    base_url = check_base_url(base_url)
    key = key or read_key(cfg)
    body = json.dumps({
        'model': model,
        'messages': [{'role': 'system', 'content': system},
                     {'role': 'user', 'content': user}],
        'max_tokens': int(cfg.get('max_tokens') or _DEFAULT_MAX_TOKENS),
        'temperature': float(cfg.get('temperature', 0.9)),
    }).encode('utf-8')
    req = urllib.request.Request(
        base_url + '/chat/completions', data=body,
        headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {key}'})
    try:
        with urllib.request.urlopen(req, timeout=cfg.get('timeout') or _DEFAULT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode('utf-8'))
        text = data['choices'][0]['message']['content']
    except Exception as e:
        # Solo el tipo: el texto del error puede incluir la URL o cabeceras.
        raise KitLlmError(f"El LLM no respondió ({type(e).__name__}).") from None
    if not isinstance(text, str):
        raise KitLlmError("Respuesta del LLM sin texto.")
    return text
