#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Conecta la app de Dropbox del worker de loop kits (tipo "App folder").

Uso: ``py -3 scripts/kit_dropbox_auth.py --app-key <app key>``. Guarda el refresh token y el
app key en ``tokens/dropbox_worker.json`` (fuera de git) y no los imprime. Ver docs/KIT_WEEKLY.md.
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import dropbox_client, kit_cloud


def save_token(app_key, flow, code, path=None):
    """Canjea el código y deja ``{refresh_token, app_key}`` en ``path``."""
    path = path or kit_cloud.WORKER_TOKEN_FILE
    dropbox_client.finish_auth(flow, code, token_file=path)
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    data['app_key'] = app_key
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--app-key', required=True, help='App key de la app "App folder".')
    args = parser.parse_args(argv)
    app_key = args.app_key.strip()

    flow, url = dropbox_client.start_auth(app_key)
    print("Abrí este link, autorizá la app y pegá el código:")
    print(url)
    try:
        save_token(app_key, flow, input("Código: "))
    except dropbox_client.DropboxError:
        print("Código inválido o vencido.")
        return 1
    print("Listo: tokens/dropbox_worker.json. Copiá sus dos valores a los secretos de GitHub "
          "KIT_DROPBOX_REFRESH_TOKEN y KIT_DROPBOX_APP_KEY.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
