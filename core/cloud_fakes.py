# -*- coding: utf-8 -*-
"""Dobles en memoria de ``gh`` y ``keyring`` para smokes y tests (sin red ni disco)."""
import json

_REPO = '(repo)'  # clave interna de los secretos del repo (``env=None``, sin ``--env``)


class FakeGhRun:
    """``run(args, stdin) -> (código, stdout)`` con secretos, variables y Environments en memoria.

    Registra cada llamada en ``calls`` como ``(args, stdin)`` para comprobar que los valores
    viajan por stdin y nunca como argumento.
    """

    def __init__(self, logged_in=True, environments=('kit-weekly',), variables=None):
        self.logged_in = logged_in
        self.envs = {name: {} for name in environments}
        self.envs[_REPO] = {}
        self.variables = dict(variables or {})
        self.calls = []
        self.fail_set = set()   # nombres de secretos cuyo «gh secret set» falla
        self.clock = 0

    def put(self, env, *names, updated='2026-10-13T04:27:38Z'):
        """Marca secretos como cargados (sin valor real)."""
        for name in names:
            self.envs.setdefault(_key(env), {})[name] = ('<fake>', updated)

    def drop(self, env, *names):
        for name in names:
            self.envs.get(_key(env), {}).pop(name, None)

    def value(self, env, name):
        """Valor en ``env`` (``None``: secreto del repo)."""
        return self.envs.get(_key(env), {}).get(name, (None,))[0]

    def __call__(self, args, stdin=None):
        args = list(args)
        self.calls.append((args, stdin))
        if args[:2] == ['auth', 'status']:
            return (0 if self.logged_in else 1), ''
        if not self.logged_in:
            return 1, ''
        if args[:2] == ['secret', 'list']:
            env = _scope(args)
            if env not in self.envs:
                return 1, ''
            rows = [{'name': n, 'updatedAt': d} for n, (_v, d) in sorted(self.envs[env].items())]
            return 0, json.dumps(rows)
        if args[:2] == ['secret', 'set']:
            name, env = args[2], _scope(args)
            if name in self.fail_set or env not in self.envs or stdin is None:
                return 1, ''
            self.clock += 1
            self.envs[env][name] = (stdin, f'2026-10-18T00:00:{self.clock:02d}Z')
            return 0, ''
        if args[:2] == ['variable', 'get']:
            value = self.variables.get(args[2])
            return (0, value + '\n') if value is not None else (1, '')
        if args[:2] == ['variable', 'set']:
            self.variables[args[2]] = stdin or ''
            return 0, ''
        if args[:1] == ['api']:
            return self._api(args)
        return 1, ''

    def _api(self, args):
        if '--method' in args:
            method = args[args.index('--method') + 1]
            path = args[args.index('--method') + 2]
            env = path.split('/environments/')[1].split('/')[0]
            if method == 'PUT':
                self.envs.setdefault(env, {})
            return 0, ''
        path = args[1]
        if path.endswith('/environments'):
            return 0, '\n'.join(sorted(e for e in self.envs if e != _REPO))
        if '/environments/' in path:
            return (0, '{}') if path.split('/environments/')[1] in self.envs else (1, '')
        return 1, ''


def _key(env):
    return _REPO if env is None else env


def _scope(args):
    return args[args.index('--env') + 1] if '--env' in args else _REPO


class MemoryKeyring:
    """Mismo API que el módulo ``keyring`` (get/set/delete_password)."""

    def __init__(self):
        self.store = {}

    def get_password(self, service, name):
        return self.store.get((service, name))

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def delete_password(self, service, name):
        if (service, name) not in self.store:
            raise KeyError('missing')
        del self.store[(service, name)]
