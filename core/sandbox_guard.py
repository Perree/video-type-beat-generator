# -*- coding: utf-8 -*-
"""¿Este proceso está corriendo tests? Entonces nada toca el llavero de Windows ni ``gh`` real.

Un test que se olvidó de poner dobles (``MemoryKeyring``, ``FakeGhRun``) llegó a pisar las
claves reales de Dropbox y Google de una PC al correr con ``python -m unittest`` (sin el
``conftest.py`` de pytest). Con esta guarda, ``cloud_login`` y ``gh_status`` usan solos un
llavero en memoria y un ``gh`` que no existe.

Se considera test: ``pytest`` cargado, o ``unittest`` cargado y el programa no es ``main.py``.
Un smoke que de verdad necesite las credenciales reales define ``TBVG_REAL_CREDENTIALS=1``.
"""
import os
import sys

APP_ENTRY = 'main.py'
OVERRIDE = 'TBVG_REAL_CREDENTIALS'


def running_tests(modules=None, main_file=None, environ=None):
    environ = os.environ if environ is None else environ
    if environ.get(OVERRIDE) == '1':
        return False
    modules = sys.modules if modules is None else modules
    if 'pytest' in modules:
        return True
    if 'unittest' not in modules:
        return False
    if main_file is None:
        main_file = getattr(modules.get('__main__'), '__file__', None) or ''
    return os.path.basename(main_file) != APP_ENTRY
