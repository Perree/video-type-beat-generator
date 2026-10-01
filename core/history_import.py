# -*- coding: utf-8 -*-
"""Importa el historial de videos ya publicados en YouTube a la tabla `uploads`.

Empareja cada título con un beat de la biblioteca por nombre; los videos sin beat
correspondiente se devuelven como "sin emparejar" y no se guardan.
"""
import re
import unicodedata
from datetime import datetime

from core import library, youtube

MIN_NAME_LEN = 3


def normalize(text):
    text = unicodedata.normalize('NFKD', text or '').encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]+', ' ', text.lower()).strip()


def match_beat(title, beats):
    """Beat cuyo nombre (normalizado) aparece en el título; gana el nombre más largo."""
    t = f" {normalize(title)} "
    best = None
    for b in beats:
        n = normalize(b['nombre'])
        if len(n) >= MIN_NAME_LEN and f" {n} " in t and (best is None or len(n) > best[0]):
            best = (len(n), b)
    return best[1] if best else None


def _to_local_iso(published_at):
    """'2025-03-01T12:00:00Z' (UTC) -> ISO local sin zona, como el resto de `uploads`."""
    dt = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
    return dt.astimezone().replace(tzinfo=None).isoformat(timespec='seconds')


def import_history(channel, videos, grupo='', db_path=None, kind=None):
    """Guarda en `uploads` los videos que emparejan con un beat.

    Args:
        kind: limitar el emparejamiento a beats o loop kits.

    Devuelve {'imported', 'skipped' (ya registrados), 'unmatched': [títulos]}.
    """
    if kind is None:
        kind = library.KIND_BEAT
    beats = library.list_beats(db_path=db_path, kind=kind)
    known = {u for b in beats for u in
             (x['youtube_id'] for x in library.youtube_uploads(b['id'], channel, db_path=db_path))}
    res = {'imported': 0, 'skipped': 0, 'unmatched': []}
    for v in videos:
        if v['youtube_id'] in known:
            res['skipped'] += 1
            continue
        beat = match_beat(v['title'], beats)
        if not beat:
            res['unmatched'].append(v['title'])
            continue
        library.record_upload(
            beat['id'], channel, grupo, v['youtube_id'], f"https://youtu.be/{v['youtube_id']}",
            v['title'], estado='importado', subido_en=_to_local_iso(v['published_at']),
            db_path=db_path)
        known.add(v['youtube_id'])
        res['imported'] += 1
    return res


def import_channel_history(channel, db_path=None, kind=None):
    """Descarga el historial del canal y lo empareja con la biblioteca del kind dado."""
    if kind is None:
        kind = library.KIND_BEAT
    return import_history(
        channel, youtube.list_channel_videos(channel), db_path=db_path, kind=kind)
