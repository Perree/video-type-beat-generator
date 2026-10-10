#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: kit_names conectado a run_preview y al worker (LLM falso, sin red)."""

import os
import sys
import tempfile
from datetime import datetime

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, 'scripts')):
    if p not in sys.path:
        sys.path.insert(0, p)

from core import kit_names, kit_source, kit_state
from run_kit_preview import run_preview
import run_kit_weekly

NOW = datetime(2026, 10, 5, 10, 0)
PACK_PATH = '/kits/PackPreview'
FAILS = []


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


class MemStore:
    """Misma interfaz que CloudStore, en memoria."""

    def __init__(self, used=()):
        self.cycle = {'used_names': list(used)}
        self.runs = []

    def has_scheduled_run(self, publish_at, db_path=None):
        return False

    def selection_history(self, db_path=None):
        return {'last_used_by_path': {}, 'last_image_by_path': {}}

    def upsert_pack(self, path, nombre, db_path=None):
        return 1

    def get_cycle(self, path):
        return dict(self.cycle)

    def update_cycle(self, path, **fields):
        self.cycle.update(fields)

    def record_run(self, pack_id, db_path=None, **fields):
        self.runs.append(fields)
        return len(self.runs)


def _fake_download(paths, dest_dir, dbx=None):
    out = []
    for i, _ in enumerate(paths):
        dest = os.path.join(dest_dir, f"dl_{i}.wav")
        open(dest, 'wb').close()
        out.append(dest)
    return out


def _run(tmp, names_cfg, store, llm, link='https://shop.example/p'):
    bg = os.path.join(tmp, 'bg.png')
    Image.new('RGB', (900, 600), (120, 90, 60)).save(bg)
    pack = [{
        'name': 'PackPreview', 'dropbox_path': PACK_PATH,
        'loops': [{'name': 'L1.wav', 'path': '/kits/PackPreview/l1.wav'}],
        'named_previews': [{'name': 'Preview.wav', 'path': '/kits/PackPreview/Preview.wav'}],
        'images': [{'name': 'bg.png', 'path': bg, 'source': 'local'}],
    }]
    kit_cfg = {'dropbox_root': '/loop_kits', 'prefer_named_preview': True}
    if names_cfg is not None:
        kit_cfg['names'] = names_cfg
    seen = {}

    def render(image, wavs, out):
        return out

    def publish(channel, video, thumbnail, name, slots, templates, **kw):
        seen.update(name=name, link=templates.get('link'), kw=kw)
        store.record_run(1, **{k: v for k, v in kw.items() if k in ('video_name', 'tracking_id')})
        return {'youtube_id': 'x', 'title': name}

    cover_titles = []

    def cover(cfg, image, title, tmpdir):
        cover_titles.append(title)
        return image, None

    templates = {'title_template': '{name}', 'link': link}
    run_preview(
        app_config={'kit_preview': kit_cfg, 'channels': {'c': {'section': 'loop_kits'}}},
        channel='c', channel_templates=templates, now=NOW, seed=1, store=store,
        list_packs_fn=lambda *_a, **_k: pack, render_fn=render, publish_fn=publish,
        cover_fn=cover, llm_call=llm, output_dir=os.path.join(tmp, 'out'))
    seen['cover_title'] = cover_titles[0]
    return seen


def main():
    real = kit_source.download_pack_files
    kit_source.download_pack_files = _fake_download
    try:
        prompts = []

        def llm(system, user):
            prompts.append(user)
            return "1. Sol Dorado\n2. Brisa\n3. Nube"

        cfg = {'genre': 'soul', 'base_url': 'https://llm.example/v1', 'model': 'm'}
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            store = MemStore(used=['Sol Dorado'])
            seen = _run(tmp, cfg, store, llm)
            check(seen['name'] == 'Brisa', "el nombre usado en el ciclo no se evitó")
            check(seen['cover_title'] == 'Brisa', "la portada no usa el nombre del video")
            check('Sol Dorado' in prompts[0] and 'soul' in prompts[0], "el prompt no lleva género ni usados")
            tid = seen['kw'].get('tracking_id')
            check(tid and seen['kw'].get('video_name') == 'Brisa', "faltan video_name o tracking_id")
            check(seen['link'] == f"https://shop.example/p?utm_source=youtube&utm_content={tid}",
                  "el link no lleva el seguimiento del video")
            check(store.cycle['used_names'] == ['Sol Dorado', 'Brisa'], "el nombre no quedó en el ciclo")

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            # LLM roto: se usa el nombre del pack y la subida sigue.
            def boom(system, user):
                raise RuntimeError("sin red")
            store = MemStore()
            seen = _run(tmp, cfg, store, boom)
            check(seen['name'] == 'PackPreview', "sin LLM debía usarse el nombre del pack")
            check(store.cycle['used_names'] == [], "no debía guardarse un nombre inexistente")

        for label, ncfg in (('sin names', None), ('enabled false', dict(cfg, enabled=False)),
                            ('sin genre', {'base_url': 'https://llm.example/v1', 'model': 'm'})):
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
                prompts.clear()
                store = MemStore()
                seen = _run(tmp, ncfg, store, llm)
                check(seen['name'] == 'PackPreview' and not prompts, f"{label}: no debía llamar al LLM")
                if label != 'sin genre':
                    check(seen['link'] == 'https://shop.example/p' and not seen['kw'].get('tracking_id'),
                          f"{label}: no debía cambiar el link ni registrar tracking_id")

        # CloudStore delega el ciclo en kit_state.
        calls = []
        real_get, real_upd = kit_state.get_cycle, kit_state.update_cycle
        kit_state.get_cycle = lambda path, dbx=None, **k: calls.append(('get', path, dbx)) or {'used_names': []}
        kit_state.update_cycle = lambda path, dbx=None, **k: calls.append(('upd', path, k))
        try:
            cs = run_kit_weekly.CloudStore('DBX')
            cs.get_cycle('/p')
            cs.update_cycle('/p', used_names=['A'])
        finally:
            kit_state.get_cycle, kit_state.update_cycle = real_get, real_upd
        check(calls == [('get', '/p', 'DBX'), ('upd', '/p', {'used_names': ['A']})],
              "CloudStore no delega el ciclo en kit_state")
    finally:
        kit_source.download_pack_files = real

    if FAILS:
        for f in FAILS:
            print("FAIL:", f)
        return 1
    print("OK smoke_kit_names_wiring")
    return 0


if __name__ == '__main__':
    sys.exit(main())
