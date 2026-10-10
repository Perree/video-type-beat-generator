#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del recorrido de la tienda: categorías, carpetas de loops y detección de kits.

Dropbox falso con la misma forma que la carpeta real (categorías, LOOPS/ y Loops/, drum
kits, MIDIS, TAG y preview, mp3+wav del mismo loop). Sin red; nombres ficticios.
"""
import os
import random
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_cycle, kit_detect, kit_source, kit_week
from core.kit_audio import plan_audio

STORE = '/store'
NOW = datetime(2026, 10, 4, 20, 0)
_failed = []


def check(cond, msg):
    if not cond:
        _failed.append(msg)
        print('FAIL:', msg)


class _Result:
    def __init__(self, entries):
        self.entries = entries
        self.has_more = False
        self.cursor = None


class _Entry:
    def __init__(self, name, path, is_folder):
        self.name = name
        self.path_lower = path
        self.is_folder = is_folder
        self.size = 0 if is_folder else 10


class FakeStore:
    """Árbol en memoria. Listar una carpeta que no está en el árbol es un fallo del smoke."""

    def __init__(self, tree):
        self.by_path = {}
        self.listed = []
        self._add(STORE, tree)

    def _add(self, path, node):
        entries = []
        for name, child in node.items():
            child_path = f'{path}/{name}'.lower()
            is_folder = isinstance(child, dict)
            entries.append(_Entry(name, child_path, is_folder))
            # None marca una carpeta que existe pero no se debe abrir nunca.
            if is_folder:
                self._add(child_path, child)
            elif child is None:
                entries[-1].is_folder = True
        self.by_path[path] = entries

    def files_list_folder(self, path):
        if path not in self.by_path:
            raise KeyError(f'listado inesperado: {path!r}')
        self.listed.append(path)
        return _Result(self.by_path[path])

    def files_list_folder_continue(self, cursor):
        raise AssertionError('paginado no usado en este smoke')

    def files_download(self, path):
        raise LookupError('path/not_found/')


def _audio(*names):
    return {name: 'file' for name in names}


def _tree():
    wav = lambda n: [f'Loop_{i:02d}.wav' for i in range(1, n + 1)]  # noqa: E731
    return {
        'Individual Kits': {
            'Smoke Alpha': {
                'LOOPS': _audio('Loop_01.wav', 'Loop_01.mp3', 'Loop_02.mp3', 'Loop_03.wav',
                                'Loop_04.wav', 'Vintage Stage 120.wav', 'Smoke Alpha TAG.wav',
                                'smoke_alpha_preview.mp3', 'Tag2.wav'),
                'DRUM KIT': None, 'MIDIS': None, 'STARTERS': None,
                'images': {'a.jpg': 'file'},
                'Smoke Alpha Demo.mp3': 'file',
            },
            'Smoke Alpha (1)': {'Loops': _audio(*wav(5))},
            'Smoke Beta': {'Loops': _audio(*wav(6)), 'Stems': None},
            'Smoke Drum Kit': {'Drum Loops': None, 'Kicks': _audio('Kick_01.wav', 'Kick_02.wav')},
            'Smoke Root': {**_audio(*wav(4), 'PREVIEW.wav'), 'Vocals': None, 'Phrases': None,
                           'stems': None, 'layers': None},
        },
        'Production Suites': {
            'Smoke Suite': {'LOOPS': _audio(*wav(8), *[n.replace('.wav', '.mp3') for n in wav(8)]),
                            'Drum Kit': None, 'Midis': None},
        },
        'Genre Bundles': {
            'Smoke Bundle': {
                'Smoke Gamma': {'Loops': _audio(*wav(7))},
                'Smoke Loose': _audio('Shot_01.wav', 'Shot_02.wav'),
            },
        },
        'STASH KITS': None,
        'free kits': {'Smoke Free': {'loops': _audio(*wav(3))}},
        '_automation': None,
    }


def _names(packs):
    return [p['name'] for p in packs]


def _check_scan(dbx):
    packs = kit_source.list_packs(STORE, dbx=dbx)
    check(_names(packs) == ['Smoke Alpha', 'Smoke Alpha (1)', 'Smoke Beta', 'Smoke Root',
                            'Smoke Suite', 'Smoke Gamma', 'Smoke Free'],
          f'kits en orden de categorías: {_names(packs)}')
    by = {p['name']: p for p in packs}
    check([p['category'] for p in packs] == ['Individual Kits'] * 4 + [
        'Production Suites', 'Genre Bundles', 'free kits'], 'categoría de cada kit')

    alpha = [loop['name'] for loop in by['Smoke Alpha']['loops']]
    check(alpha == ['Loop_01.wav', 'Loop_02.mp3', 'Loop_03.wav', 'Loop_04.wav',
                    'Vintage Stage 120.wav'],
          f'LOOPS/: TAG y preview afuera, mp3+wav una vez, "Vintage" adentro: {alpha}')
    check(all('/loops/' in loop['path'] for loop in by['Smoke Alpha']['loops']),
          'con LOOPS/ no se toman los audios de la raíz del kit')
    check(len(by['Smoke Beta']['loops']) == 6, 'loops en Loops/ (otra mayúscula)')
    check([loop['name'] for loop in by['Smoke Root']['loops']] ==
          [f'Loop_{i:02d}.wav' for i in range(1, 5)], 'kit con loops en la raíz, sin PREVIEW')
    suite = by['Smoke Suite']['loops']
    check(len(suite) == 8 and all(loop['name'].endswith('.wav') for loop in suite),
          f'mp3 y wav del mismo loop cuentan una vez y queda el wav: {len(suite)}')
    check('Smoke Drum Kit' not in by and 'Kicks' not in by and 'Smoke Loose' not in by,
          'un drum kit con "Drum Loops" o muestras sueltas no es un kit')
    check(by['Smoke Alpha']['images'] and not by['Smoke Beta']['images'], 'imágenes solo de images/')
    check(not any('named_previews' in p for p in packs), 'sin named_previews')
    check(not any('stash' in path or '_automation' in path for path in dbx.listed),
          'STASH KITS y _automation no se recorren')

    # Categorías elegidas, en el orden pedido; una que no existe se saltea.
    scan = kit_source.scan_settings({'scan_folders': ['free kits', 'No Existe', 'production suites']})
    check(_names(kit_source.list_packs(STORE, dbx=dbx, scan=scan)) == ['Smoke Free', 'Smoke Suite'],
          'scan_folders manda el orden')
    # Profundidad 1: no se entra al bundle.
    shallow = kit_source.scan_settings({'scan_folders': ['Genre Bundles'], 'scan_max_depth': 1})
    check(kit_source.list_packs(STORE, dbx=dbx, scan=shallow) == [], 'scan_max_depth corta el recorrido')
    # Palabras a ignorar configurables: sin lista entran TAG y preview.
    loose = kit_source.scan_settings({'scan_folders': ['Individual Kits'], 'ignore_names': []})
    loose_alpha = kit_source.list_packs(STORE, dbx=dbx, scan=loose)[0]['loops']
    check(len(loose_alpha) == 8, f'ignore_names vacío: {len(loose_alpha)} loops')
    return packs


def _check_detect(dbx):
    cats = kit_detect.categories(STORE, dbx=dbx)
    check(cats == ['free kits', 'Genre Bundles', 'Individual Kits', 'Production Suites',
                   'STASH KITS'], f'categorías para las casillas: {cats}')
    rows = kit_detect.detect(STORE, dbx=dbx)
    by = {row['folder']: row for row in rows}
    check(len(rows) == 7 and all(not row['payhip_url'] and not row['genre'] for row in rows),
          'detectar kits no inventa links ni géneros')
    check(by['Smoke Alpha (1)']['active'] is False, 'la carpeta duplicada "(1)" queda inactiva')
    check(all(row['active'] for name, row in by.items() if name != 'Smoke Alpha (1)'),
          'el resto queda activo')
    existing = [{'folder': 'smoke beta', 'name': 'Beta', 'payhip_url': 'https://example.com/b',
                 'genre': 'g', 'active': False}]
    merged, added = kit_detect.merge(existing, rows)
    check(added == 6 and merged[0] == existing[0] and len(merged) == 7,
          f'merge conserva lo cargado y suma lo nuevo: {added}')
    check(all('loops' not in row for row in merged), 'las filas de la tabla no llevan campos de más')
    twins = kit_detect.rows_from_packs([
        {'name': 'Same', 'dropbox_path': '/store/a/same', 'loops': []},
        {'name': 'same', 'dropbox_path': '/store/b/same', 'loops': []}])
    check([row['folder'] for row in twins] == ['/store/a/same', '/store/b/same'],
          'dos kits con el mismo nombre se distinguen por la ruta')


def _check_week(dbx, packs):
    def week(cover_mode):
        cfg = {'kit_preview': {'dropbox_root': STORE, 'cover_mode': cover_mode,
                               'art': {'refs_root': '/refs'}}}
        return kit_week.open_week(cfg, {'packs': {}, 'runs': []}, {}, NOW, random.Random(1),
                                  dbx=dbx)

    auto = week('auto')
    check([s['pack']['name'] for s in auto['queue']] == _names(packs),
          f"portada auto: entran los kits sin imágenes, en orden: "
          f"{[s['pack']['name'] for s in auto['queue']]}")
    check(all(s['image'] is None for s in auto['queue'][1:]) and auto['queue'][0]['image'],
          'sin imágenes la selección sale sin imagen')
    manual = week('manual')
    check([s['pack']['name'] for s in manual['queue']] == ['Smoke Alpha'],
          'portada manual: solo los kits con imágenes')
    check(any('sin imágenes' in w for w in manual['warnings']), 'manual avisa los kits que quedan afuera')

    # Mínimo de loops: 3 no arman video; 5 dan uno corto, sin repetir.
    by = {p['name']: p for p in packs}
    end = lambda path, **_k: 20.0  # noqa: E731
    free = plan_audio(by['Smoke Free'], [], random.Random(1), end_fn=end)
    check(free['ok'] is False, 'un kit con 3 loops se saltea')
    short = plan_audio(by['Smoke Alpha'], [], random.Random(1), end_fn=end)
    paths = [seg['path'] for seg in short['segments']]
    check(short['ok'] and short['short'] and short['duration'] == 100.0
          and len(set(paths)) == 5 and short['warnings'],
          f'5 loops: video corto con aviso y sin repetir: {short}')
    again = plan_audio(by['Smoke Alpha'], [short], random.Random(2), end_fn=end)
    check(again['ok'] is False, 'los loops ya usados no vuelven a salir en el ciclo')
    cfg = kit_cycle.settings()
    check(kit_cycle.advance({}, NOW, cfg, close=short['short'] or short['exhausted'])['rest_until'],
          'el video corto cierra el ciclo del kit')


def main() -> int:
    dbx = FakeStore(_tree())
    packs = _check_scan(dbx)
    _check_detect(dbx)
    _check_week(dbx, packs)
    if _failed:
        print(f'{len(_failed)} chequeo(s) fallaron.')
        return 1
    print('OK smoke_kit_scan')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
