#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: secretos fuera del entorno de los procesos hijos, log público y token de Dropbox del worker."""

import contextlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
import warnings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for path in (ROOT, os.path.join(ROOT, 'scripts')):
    if path not in sys.path:
        sys.path.insert(0, path)

from core import kit_art, kit_cloud, kit_names, kit_notify

import kit_dropbox_auth
import run_kit_weekly

FAILS = []
S = {'yt': 'SMOKE-YT-REFRESH', 'cs': 'SMOKE-CLIENT-SECRET', 'dbx': 'SMOKE-DBX-REFRESH',
     'key': 'SMOKE-APP-KEY', 'llm': 'SMOKE-LLM-KEY', 'img': 'SMOKE-IMG-KEY',
     'tg': 'SMOKE-TG-TOKEN'}
ENV = {
    kit_cloud.ENV_YT_CHANNEL: 'smoke canal',
    kit_cloud.ENV_YT_TOKEN: json.dumps({'refresh_token': S['yt'], 'client_secret': S['cs']}),
    kit_cloud.ENV_DROPBOX_TOKEN: S['dbx'],
    kit_cloud.ENV_DROPBOX_APP_KEY: json.dumps({'app_key': S['key']}),
    kit_names.ENV_LLM_KEY: S['llm'],
    kit_art.ENV_KEY: S['img'],
    kit_notify.ENV_TOKEN: S['tg'],
    kit_notify.ENV_CHAT: '12345',
}
_ALL = kit_cloud.ENV_VARS + kit_cloud.RUNTIME_SECRETS


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _child_sees():
    """Variables KIT_* que hereda un proceso hijo (como ffmpeg)."""
    out = subprocess.run(
        [sys.executable, '-c',
         "import os; print(','.join(sorted(k for k in os.environ if k.startswith('KIT_'))))"],
        capture_output=True, text=True).stdout.strip()
    return [k for k in out.split(',') if k]


def _check_hidden_env():
    check('KIT_YT_CLIENT_SECRET_JSON' not in _ALL, "el client_secret sigue entre los secretos")
    os.environ.update(ENV)
    try:
        check(set(_child_sees()) >= set(ENV), "el hijo de control no hereda el entorno")
        with kit_cloud.credentials_dir() as run_dir:
            check(not [k for k in _ALL if k in os.environ], "los secretos siguen en os.environ")
            check(not [k for k in _child_sees() if k in _ALL], "un proceso hijo hereda secretos")
            # Siguen disponibles en memoria para quien los usa.
            check(kit_cloud.in_cloud(), "in_cloud se pierde al esconder los secretos")
            check(kit_cloud.secret(kit_names.ENV_LLM_KEY) == S['llm']
                  and kit_art._read_key({}) == S['img']
                  and kit_notify._credentials(None) == (S['tg'], '12345'),
                  "los secretos no se leen desde memoria")
            check(not os.path.exists(os.path.join(run_dir, 'config', 'client_secret.json')),
                  "se escribió client_secret.json")
        check(all(os.environ.get(k) == v for k, v in ENV.items()) and not kit_cloud._STASH,
              "el entorno no se restauró al salir")
    finally:
        for name in ENV:
            os.environ.pop(name, None)
    # Con un entorno explícito (smokes) no se toca os.environ.
    with kit_cloud.credentials_dir(ENV):
        check(not kit_cloud._STASH, "un env explícito escondió secretos")


def _check_public_log():
    nested = kit_cloud.nested_secrets(ENV)
    check(sorted(nested) == sorted([S['yt'], S['cs'], S['key']]), f"nested_secrets: {len(nested)}")
    check(kit_cloud.nested_secrets({kit_cloud.ENV_YT_TOKEN: 'no es json'}) == [], "json inválido")
    real_err = sys.stderr
    for actions in (True, False):
        os.environ.update(ENV)
        os.environ.pop('GITHUB_ACTIONS', None)
        if actions:
            os.environ['GITHUB_ACTIONS'] = 'true'
        out, err = io.StringIO(), io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                with warnings.catch_warnings(), run_kit_weekly._public_log():
                    warnings.warn('aviso con ' + S['dbx'])
                    logging.getLogger('smoke.lib').warning('log con %s', S['llm'])
                    print('traza con ' + S['tg'], file=sys.stderr)
        finally:
            for name in (*ENV, 'GITHUB_ACTIONS'):
                os.environ.pop(name, None)
        check(err.getvalue() == '', "stderr llegó al log en la nube")
        masks = [line for line in out.getvalue().splitlines() if line.startswith('::add-mask::')]
        if actions:
            check(sorted(m[len('::add-mask::'):] for m in masks) == sorted(nested)
                  and len(masks) == len(out.getvalue().splitlines()),
                  "en Actions no se registran las máscaras de los valores internos")
        else:
            check(out.getvalue() == '', "fuera de Actions se imprimió algo")
    check(sys.stderr is real_err, "stderr no se restauró")
    # En la PC (sin variables KIT_*) stderr queda como está.
    err = io.StringIO()
    with contextlib.redirect_stderr(err), run_kit_weekly._public_log():
        print('visible', file=sys.stderr)
    check(err.getvalue().strip() == 'visible', "en la PC se perdió stderr")


class _Flow:
    class _Result:
        refresh_token = S['dbx']

    def finish(self, code):
        return self._Result()


def _check_worker_token(tmp):
    path = os.path.join(tmp, 'tokens', 'dropbox_worker.json')
    check(kit_cloud.worker_token(path) is None, "token inexistente")
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        kit_dropbox_auth.save_token(S['key'], _Flow(), ' codigo ', path)
    check(kit_cloud.worker_token(path) == {'refresh_token': S['dbx'], 'app_key': S['key']},
          "save_token no dejó refresh_token y app_key")
    check(S['dbx'] not in out.getvalue() and S['key'] not in out.getvalue(),
          "save_token imprimió el token")
    for bad in ('{"refresh_token": "x"}', '[]', 'no es json'):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(bad)
        check(kit_cloud.worker_token(path) is None, f"token incompleto aceptado: {bad}")
    ignored = subprocess.run(['git', 'check-ignore', '-q', kit_cloud.WORKER_TOKEN_FILE],
                             cwd=ROOT).returncode
    check(ignored == 0, "tokens/dropbox_worker.json no está ignorado por git")
    with open(os.path.join(ROOT, '.github', 'workflows', 'kit-weekly.yml'), encoding='utf-8') as f:
        workflow = f.read()
    check('environment: kit-weekly' in workflow and "github.ref == 'refs/heads/master'" in workflow
          and 'KIT_YT_CLIENT_SECRET_JSON' not in workflow and 'pull_request' not in
          workflow.split('jobs:')[0].split('on:')[1].replace('Nunca pull_request', ''),
          "el workflow perdió el Environment, la rama o volvió a pedir el client_secret")


def main():
    saved = {name: os.environ.pop(name) for name in (*_ALL, 'GITHUB_ACTIONS') if name in os.environ}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            for fn, args in ((_check_hidden_env, ()), (_check_public_log, ()),
                             (_check_worker_token, (tmp,))):
                try:
                    fn(*args)
                except Exception as e:
                    FAILS.append(f"{fn.__name__} falló: {type(e).__name__}: {e}")
    finally:
        os.environ.update(saved)
    if FAILS:
        for msg in FAILS:
            print('FAIL:', msg)
        return 1
    print('OK: smoke_kit_hardening')
    return 0


if __name__ == '__main__':
    sys.exit(main())
