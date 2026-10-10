#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke: inventario de packs sin red (fake dbx). SMOKE_LIVE_DROPBOX=1 queda fuera."""

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import dropbox_client, kit_source


class _FakeResult:
    def __init__(self, entries, has_more=False, cursor=None):
        self.entries = entries
        self.has_more = has_more
        self.cursor = cursor


class _FakeEntry:
    """Duck-type de FolderMetadata/FileMetadata para no pegarle a la red ni al SDK."""

    def __init__(self, name, path, is_folder=False, size=1):
        self.name = name
        self.path_lower = path
        self.path = path
        self.is_folder = is_folder
        self.size = 0 if is_folder else size


class FakeDbx:
    """files_list_folder en memoria. Falla si se lista stems/ o layers/."""

    def __init__(self, by_path):
        self.by_path = by_path

    def files_list_folder(self, path):
        key = path or ''
        if key not in self.by_path:
            raise KeyError(f"listado inesperado: {key!r}")
        return _FakeResult(self.by_path[key])

    def files_list_folder_continue(self, cursor):
        raise AssertionError("paginado no usado en este smoke")


def _folder(name, path):
    return _FakeEntry(name, path, is_folder=True)


def _file(name, path):
    return _FakeEntry(name, path, is_folder=False, size=10)


def main() -> int:
    # Pack A: 3 loops + Preview.wav + 2 jpg en images/ (+ stems/ que no debe listarse).
    # Pack B: sin images/; 1 loop; 1 png local.
    tree = {
        '/kits': [
            _folder('Pack A', '/kits/pack a'),
            _folder('Pack B', '/kits/pack b'),
            _file('readme.txt', '/kits/readme.txt'),
        ],
        '/kits/pack a': [
            _file('Loop_01.wav', '/kits/pack a/loop_01.wav'),
            _file('Loop_02.wav', '/kits/pack a/loop_02.wav'),
            _file('Loop_03.wav', '/kits/pack a/loop_03.wav'),
            _file('Preview.wav', '/kits/pack a/preview.wav'),
            _folder('images', '/kits/pack a/images'),
            _folder('stems', '/kits/pack a/stems'),
            _folder('layers', '/kits/pack a/layers'),
            _file('cover.jpg', '/kits/pack a/cover.jpg'),
        ],
        '/kits/pack a/images': [
            _file('a.jpg', '/kits/pack a/images/a.jpg'),
            _file('b.jpg', '/kits/pack a/images/b.jpg'),
            _file('notes.txt', '/kits/pack a/images/notes.txt'),
        ],
        '/kits/pack b': [
            _file('OnlyLoop.mp3', '/kits/pack b/onlyloop.mp3'),
        ],
    }
    dbx = FakeDbx(tree)

    local_root = tempfile.mkdtemp()
    pack_b_imgs = os.path.join(local_root, 'Pack B')
    os.makedirs(pack_b_imgs)
    local_png = os.path.join(pack_b_imgs, 'art.png')
    with open(local_png, 'wb') as f:
        f.write(b'\x89PNG')

    packs = kit_source.list_packs('/kits', local_images_root=local_root, dbx=dbx)
    by_name = {p['name']: p for p in packs}
    if set(by_name) != {'Pack A', 'Pack B'}:
        print('FAIL: packs', list(by_name))
        return 1

    pack_a = by_name['Pack A']
    loop_names = [x['name'] for x in pack_a['loops']]
    preview_names = [x['name'] for x in pack_a['named_previews']]
    if loop_names != ['Loop_01.wav', 'Loop_02.wav', 'Loop_03.wav']:
        print('FAIL: loops Pack A', loop_names)
        return 1
    if preview_names != ['Preview.wav']:
        print('FAIL: named_previews Pack A', preview_names)
        return 1
    if 'Preview.wav' in loop_names:
        print('FAIL: Preview.wav no debe estar en loops')
        return 1
    img_a = pack_a['images']
    if sorted(i['name'] for i in img_a) != ['a.jpg', 'b.jpg']:
        print('FAIL: images Pack A', img_a)
        return 1
    if any(i['source'] != 'dropbox' for i in img_a):
        print('FAIL: source Pack A', img_a)
        return 1
    if any('stems' in i['path'] or 'layers' in i['path'] for i in pack_a['loops']):
        print('FAIL: se recorrió stems/ o layers/')
        return 1

    pack_b = by_name['Pack B']
    if [x['name'] for x in pack_b['loops']] != ['OnlyLoop.mp3']:
        print('FAIL: loops Pack B', pack_b['loops'])
        return 1
    if pack_b['named_previews']:
        print('FAIL: named_previews Pack B', pack_b['named_previews'])
        return 1
    if len(pack_b['images']) != 1:
        print('FAIL: Pack B debe tomar 1 png local', pack_b['images'])
        return 1
    local_img = pack_b['images'][0]
    if local_img['name'] != 'art.png' or local_img['source'] != 'local':
        print('FAIL: imagen local Pack B', local_img)
        return 1
    if local_img['path'] != local_png:
        print('FAIL: path local', local_img['path'])
        return 1

    # El browser de beats no debe ver jpg.
    browser = dropbox_client.list_folder('/kits/pack a', dbx=dbx)
    names = [i['name'] for i in browser]
    if any(n.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')) for n in names):
        print('FAIL: list_folder devolvió imagen', names)
        return 1
    if 'Preview.wav' not in names or 'Loop_01.wav' not in names:
        print('FAIL: list_folder audio', names)
        return 1
    if 'cover.jpg' in names:
        print('FAIL: jpg en list_folder')
        return 1

    entries = dropbox_client.list_folder_entries('/kits/pack a', dbx=dbx)
    entry_names = [i['name'] for i in entries]
    if 'cover.jpg' not in entry_names:
        print('FAIL: list_folder_entries debe incluir jpg', entry_names)
        return 1

    print('OK smoke_kit_source')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
