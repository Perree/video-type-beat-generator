# -*- coding: utf-8 -*-
"""Merge de 3 vías por campo para documentos JSON de Dropbox (sin Qt ni red).

base = lo último leído, mío = lo editado, nube = lo releído tras un conflicto de rev.
Un campo que cambió de un solo lado se toma de ese lado; si cambió distinto en los dos es un
choque. Las listas de objetos con identidad (``id``, ``slug``, ``clave`` o ``folder``) se
fusionan elemento por elemento; el resto de las listas cuenta como un valor entero.
"""
from copy import deepcopy

IDENTITY_KEYS = ('id', 'slug', 'clave', 'folder')
_MISSING = object()


class MergeConflict(Exception):
    """El mismo campo cambió distinto en los dos lados; ``choques`` dice cuáles."""

    def __init__(self, choques):
        super().__init__('Cambios en conflicto: ' + ', '.join(c['ruta'] for c in choques))
        self.choques = choques


def _identity(*lists):
    """Primera clave de identidad presente (texto, sin repetir) en todos los elementos."""
    items = [item for values in lists for item in values]
    if not items or not all(isinstance(item, dict) for item in items):
        return None
    for key in IDENTITY_KEYS:
        if all(isinstance(item.get(key), str) for item in items) and all(
                len({item[key] for item in values}) == len(values) for values in lists):
            return key
    return None


def _show(value):
    return None if value is _MISSING else deepcopy(value)


def _merge(base, mine, theirs, path, choques):
    if mine == theirs:
        return mine
    if mine == base:
        return theirs
    if theirs == base:
        return mine
    if isinstance(mine, dict) and isinstance(theirs, dict):
        return _merge_dict(base if isinstance(base, dict) else {}, mine, theirs, path, choques)
    if isinstance(mine, list) and isinstance(theirs, list):
        lists = [mine, theirs] + ([base] if isinstance(base, list) else [])
        key = _identity(*lists)
        if key is not None:
            return _merge_list(base if isinstance(base, list) else [], mine, theirs, key,
                               path, choques)
    choques.append({'ruta': path or '(documento)', 'base': _show(base), 'mio': _show(mine),
                    'nube': _show(theirs)})
    return theirs


def _merge_dict(base, mine, theirs, path, choques):
    out = {}
    keys = list(theirs) + [k for k in mine if k not in theirs] + [
        k for k in base if k not in theirs and k not in mine]
    for key in keys:
        value = _merge(base.get(key, _MISSING), mine.get(key, _MISSING),
                       theirs.get(key, _MISSING), f'{path}.{key}' if path else str(key), choques)
        if value is not _MISSING:
            out[key] = value
    return out


def _merge_list(base, mine, theirs, key, path, choques):
    index = lambda items: {item[key]: item for item in items}
    b, m, t = index(base), index(mine), index(theirs)
    order = [item[key] for item in theirs] + [item[key] for item in mine if item[key] not in t]
    out = []
    for ident in order:
        # Dos altas del mismo id se fusionan campo por campo contra una base vacía.
        value = _merge(b.get(ident, _MISSING if ident not in m or ident not in t else {}),
                       m.get(ident, _MISSING), t.get(ident, _MISSING),
                       f'{path}[{key}={ident}]', choques)
        if value is not _MISSING:
            out.append(value)
    return out


def merge3(base, mine, theirs):
    """Devuelve ``(documento_fusionado, choques)``. No modifica las entradas.

    ``base`` None equivale a un documento que no existía. En cada choque el fusionado queda
    con el valor de la nube; quien llama no debe escribirlo si hay choques.
    """
    choques = []
    merged = _merge({} if base is None else base, mine, theirs, '', choques)
    return deepcopy(merged), choques


def save_merged(read, write, base, mine, rev, conflicts, prepare=None, attempts=4):
    """Escribe ``mine`` por CAS; ante un conflicto relee, fusiona con ``base`` y reintenta.

    Args:
        read: ``() -> (doc_nube, rev)``.
        write: ``(doc, rev) -> rev_nuevo``; levanta una de ``conflicts`` si el rev cambió.
        prepare: valida/normaliza el documento antes de cada escritura (puede levantar).

    Returns:
        ``(doc_escrito, rev_nuevo)``. Levanta MergeConflict si hay choques: nada se escribe.
        Si el rev sigue cambiando tras ``attempts`` intentos, levanta ``conflicts[0]``.
    """
    document = prepare(mine) if prepare else mine
    for _ in range(attempts):
        try:
            return document, write(document, rev)
        except conflicts:
            theirs, rev = read()
            merged, choques = merge3(base, mine, theirs if theirs is not None else {})
            if choques:
                raise MergeConflict(choques) from None
            base, mine = theirs, merged
            document = prepare(merged) if prepare else merged
    raise conflicts[0]('revision_retry_exhausted')
