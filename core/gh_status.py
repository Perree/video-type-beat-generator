# -*- coding: utf-8 -*-
"""Estado y escritura de GitHub Secrets/Variables con la sesión de ``gh auth login``. Sin Qt.

Lectura: solo nombres y fechas (``gh secret list --json name,updatedAt``) y el valor de
variables públicas (``gh variable get``); GitHub nunca devuelve el valor de un secreto.
Escritura: el valor viaja siempre por stdin; nunca va en un argumento ni se imprime.
Las lecturas se guardan en memoria unos 60 s (los fallos, 5 s); cualquier escritura vacía la
caché. Con ``enable_background`` (lo activa la UI), un dato que falta en el hilo principal se
carga en un hilo aparte y se avisa a los oyentes: la ventana nunca espera a ``gh``.
"""
import json
import os
import re
import subprocess
import threading
import time

from core.beat_actions import TRUSTED_REPOSITORY

OK, MISSING, UNKNOWN = 'ok', 'missing', 'unknown'
ENV = 'kit-weekly'
REPO = None  # «sin Environment»: secretos del repo, que ven todos los Environments
TTL = 60
FAIL_TTL = 5  # un fallo (sin sesión, red) se reintenta pronto: p. ej. tras «gh auth login»
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_NAME = re.compile('[A-Z][A-Z0-9_]{0,99}')
_ENV = re.compile('kit-weekly(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?')
_TIMEOUT = 30


class GhError(Exception):
    """Mensaje apto para la UI: nunca incluye valores."""


def _run(args, stdin=None):
    """``(código, stdout)`` de ``gh``; 127 si no está instalada. Sin shell ni consola."""
    try:
        result = subprocess.run(
            ['gh', *args], cwd=ROOT, capture_output=True, timeout=_TIMEOUT,
            input=None if stdin is None else stdin.encode('utf-8'),
            stdin=subprocess.DEVNULL if stdin is None else None,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError):
        return 127, ''
    return result.returncode, result.stdout.decode('utf-8', 'replace')


def check_env(env):
    if not isinstance(env, str) or not _ENV.fullmatch(env) or len(env) > 60:
        raise GhError('Environment de GitHub inválido.')
    return env


def _scope(env):
    """Argumentos de ``gh secret`` para un Environment, o ninguno para el repo (``REPO``)."""
    return [] if env is REPO else ['--env', check_env(env)]


def check_name(name):
    if not isinstance(name, str) or not _NAME.fullmatch(name):
        raise GhError('Nombre de secreto o variable inválido.')
    return name


def day(updated_at):
    """``2026-10-13`` de un ``updatedAt`` ISO; vacío si no sirve."""
    return updated_at[:10] if isinstance(updated_at, str) and len(updated_at) >= 10 else ''


class GhStatus:
    """Cliente chico de ``gh`` con caché en memoria. ``run(args, stdin) -> (code, out)``."""

    def __init__(self, run=None, ttl=TTL, clock=time.monotonic, repo=None,
                 allow_background=False):
        self._run = run or _run
        self.ttl, self._clock, self.repo = ttl, clock, repo
        self._cache = {}
        self._lock = threading.Lock()
        self._generation = 0          # sube con cada invalidate: descarta cargas viejas
        self._loading = set()
        self._allow_background = allow_background
        self._listeners = []

    def _repo(self):
        return ['--repo', self.repo] if self.repo else []

    def enable_background(self, listener):
        """Carga en segundo plano lo que pida el hilo principal; ``listener()`` al terminar.

        Solo en clientes creados con ``allow_background`` (el real); los dobles siguen síncronos.
        """
        if self._allow_background and listener not in self._listeners:
            self._listeners.append(listener)

    def pending(self):
        """True mientras haya lecturas en segundo plano sin terminar."""
        with self._lock:
            return bool(self._loading)

    def _store(self, key, value, good, generation):
        with self._lock:
            if generation == self._generation:
                self._cache[key] = (self._clock(), value, self.ttl if good(value) else FAIL_TTL)

    def _cached(self, key, load, good=lambda v: v is not None, pending=None):
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and self._clock() - hit[0] < hit[2]:
                return hit[1]
            generation = self._generation
            background = (self._listeners and
                          threading.current_thread() is threading.main_thread())
            if background:
                if key in self._loading:
                    return pending
                self._loading.add(key)
        if not background:
            value = load()
            self._store(key, value, good, generation)
            return value

        def work():
            try:
                self._store(key, load(), good, generation)
            finally:
                with self._lock:
                    self._loading.discard(key)
                for listener in list(self._listeners):
                    listener()
        threading.Thread(target=work, name='gh-status', daemon=True).start()
        return pending

    def invalidate(self):
        with self._lock:
            self._cache.clear()
            self._generation += 1

    def auth(self):
        """``ok`` si hay sesión de ``gh auth login``; ``missing`` si no (o sin gh).

        Mientras se consulta en segundo plano devuelve ``unknown``.
        """
        return self._cached(('auth',), lambda: OK if self._run(['auth', 'status'])[0] == 0
                            else MISSING, good=lambda v: v == OK, pending=UNKNOWN)

    def secrets(self, env=ENV):
        """``{nombre: updatedAt}`` del Environment (``REPO``: del repo), o ``None`` si falló."""
        scope = _scope(env)

        def load():
            code, out = self._run(['secret', 'list', *scope, '--json', 'name,updatedAt',
                                   *self._repo()])
            if code != 0:
                return None
            try:
                rows = json.loads(out or '[]')
                return {row['name']: str(row.get('updatedAt') or '') for row in rows
                        if isinstance(row, dict) and isinstance(row.get('name'), str)}
            except (ValueError, TypeError):
                return None
        return self._cached(('secrets', env), load)

    def variable(self, name):
        """Valor de una variable del repo, o ``None`` si no existe o no se pudo leer."""
        check_name(name)

        def load():
            code, out = self._run(['variable', 'get', name, *self._repo()])
            return out.strip() if code == 0 else None
        return self._cached(('variable', name), load)

    def environments(self):
        """Nombres de Environments ``kit-weekly*`` del repo, o ``None`` si falló."""
        def load():
            repo = self.repo or '{owner}/{repo}'
            code, out = self._run(['api', f'repos/{repo}/environments',
                                   '--jq', '.environments[].name'])
            if code != 0:
                return None
            return [n for n in out.split() if _ENV.fullmatch(n)]
        return self._cached(('environments',), load)

    def read(self, args):
        """``(código, stdout)`` sin caché, para lecturas puntuales (p. ej. ``variable get``)."""
        return self._run(list(args))

    def runner(self, args, stdin=None):
        """Firma de ``scripts/kit_secrets_sync._gh``: devuelve solo el código de salida."""
        try:
            return self._run(list(args), stdin)[0]
        finally:
            self.invalidate()  # lo usan los sync scripts para escribir

    def set_secret(self, name, value, env=ENV):
        """Sube ``value`` por stdin (``env=REPO``: secreto del repo). True si gh terminó bien."""
        check_name(name)
        scope = _scope(env)
        if not isinstance(value, str) or not value:
            raise GhError('Valor de secreto vacío.')
        try:
            return self._run(['secret', 'set', name, *scope, *self._repo()], value)[0] == 0
        finally:
            self.invalidate()

    def set_variable(self, name, value):
        check_name(name)
        try:
            return self._run(['variable', 'set', name, *self._repo()], value)[0] == 0
        finally:
            self.invalidate()


# Repo fijo: los secretos nunca dependen de qué remotos tenga la carpeta (fork, upstream).
DEFAULT = GhStatus(allow_background=True, repo=TRUSTED_REPOSITORY)


def default():
    return DEFAULT


def set_default(client):
    """Reemplaza el cliente compartido (smokes y tests). Devuelve el anterior."""
    global DEFAULT
    previous, DEFAULT = DEFAULT, client
    return previous
