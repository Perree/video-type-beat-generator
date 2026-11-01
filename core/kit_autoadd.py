# -*- coding: utf-8 -*-
"""Kits nuevos de Dropbox que entran solos al catálogo (``kits.json``) del canal.

Cada canal revisa solo sus categorías (``kit_preview.scan_folders``), así que una carpeta
que aparece ahí y no está en el catálogo es un kit nuevo de ese canal. Entra con el link
del canal y con el género que se pueda deducir sin adivinar:

- el canal tiene un solo género: ese;
- tiene varios: el que se llama igual que la categoría (sin mayúsculas);
- si no, queda pendiente y se avisa (hay que completarlo en el panel).

No entran las carpetas que empiezan con ``_`` ni las copias (nombre terminado en " (N)").
Los kits que ya están en el catálogo, activos o no, no se tocan. Los avisos no llevan
nombres de kit (el log de Actions es público).
"""
from core import kit_catalog, kit_cloud
from core.kit_detect import is_copy

ATTEMPTS = 3


def _known(catalog):
    return {kit_catalog._norm(entry.get('folder')) for entry in catalog or []}


def pick_genre(category, genres):
    """Género de un kit nuevo de ``category``, '' si el canal no usa géneros, o None."""
    genres = [str(g).strip() for g in genres or [] if str(g).strip()]
    if not genres:
        return ''
    if len(genres) == 1:
        return genres[0]
    wanted = kit_catalog._norm(category)
    return next((g for g in genres if kit_catalog._norm(g) == wanted), None)


def new_entries(packs, catalog, genres, channel_link):
    """Entradas de catálogo para los kits de ``packs`` que el catálogo todavía no tiene.

    Args:
        packs: salida de ``kit_source.list_packs`` (``name``, ``dropbox_path``, ``category``).
        catalog: catálogo validado del canal.
        genres: géneros del canal (``kit_catalog.configured_genres``).
        channel_link: link del canal (``channels.<canal>.link``).

    Returns:
        ``(entradas, avisos)``.
    """
    known = _known(catalog)
    fresh = [p for p in packs or []
             if p.get('loops') and not p['name'].startswith('_') and not is_copy(p['name'])
             and kit_catalog._norm(p['name']) not in known
             and kit_catalog._norm(p['dropbox_path']) not in known]
    if not fresh:
        return [], []
    if not kit_catalog.is_valid_link(channel_link):
        return [], [f"{len(fresh)} kit(s) nuevo(s) en Dropbox no entran solos: el canal no "
                    "tiene link. Cargales el link en el panel."]
    counts = {}
    for pack in packs:
        key = kit_catalog._norm(pack['name'])
        counts[key] = counts.get(key, 0) + 1
    entries, pending = [], 0
    for pack in fresh:
        genre = pick_genre(pack.get('category'), genres)
        if genre is None:
            pending += 1
            continue
        unique = counts[kit_catalog._norm(pack['name'])] == 1
        entries.append({'folder': pack['name'] if unique else pack['dropbox_path'],
                        'name': pack['name'], 'payhip_url': channel_link.strip(),
                        'genre': genre, 'active': True})
    warnings = []
    if entries:
        warnings.append(f"{len(entries)} kit(s) nuevo(s) en Dropbox entraron solos a la rueda "
                        "con el link del canal.")
    if pending:
        warnings.append(f"{pending} kit(s) nuevo(s) en Dropbox no entran: no se sabe su género "
                        "(la categoría no se llama como ninguno). Completalos en el panel.")
    return entries, warnings


def persist(path, entries, genres=None, dbx=None, attempts=ATTEMPTS):
    """Suma ``entries`` al ``kits.json`` de ``path`` sin pisar ediciones del panel.

    Relee el archivo, agrega solo las entradas cuya carpeta no esté y escribe con el ``rev``
    leído; si otro lo cambió en el medio, vuelve a probar.

    Returns:
        Cantidad de entradas que se guardaron (0 si no había archivo o ya estaban).

    Raises:
        kit_cloud.KitCloudConflict: siguió cambiando en todos los intentos.
        kit_catalog.KitCatalogError: el resultado no sería un catálogo válido.
    """
    if not entries:
        return 0
    for attempt in range(attempts):
        data, rev = kit_cloud.read_json_rev(path, dbx=dbx)
        if not isinstance(data, list):
            return 0
        known = _known(data)
        missing = [e for e in entries if kit_catalog._norm(e['folder']) not in known]
        if not missing:
            return 0
        merged = data + missing
        kit_catalog.validate(merged, genres)
        try:
            kit_cloud.write_json(path, merged, rev=rev, dbx=dbx)
            return len(missing)
        except kit_cloud.KitCloudConflict:
            if attempt == attempts - 1:
                raise
    return 0
