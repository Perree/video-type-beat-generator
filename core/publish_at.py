# -*- coding: utf-8 -*-
"""Convierte fecha/hora local a publishAt de YouTube (ISO 8601 UTC con sufijo Z)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def local_to_youtube_publish_at(
    schedule_enabled: bool,
    local_dt: Optional[datetime],
    *,
    tz=None,
) -> Optional[str]:
    """Devuelve publishAt en UTC para youtube.upload, o None si no hay programación.

    Args:
        schedule_enabled: True si el usuario activó «Programar».
        local_dt: Fecha/hora en hora local (naive = zona del sistema o `tz`).
        tz: Zona horaria explícita para datetimes naive (p. ej. en tests).

    Returns:
        Cadena tipo ``2026-10-05T18:00:00Z`` o None.
    """
    if not schedule_enabled or local_dt is None:
        return None
    if local_dt.tzinfo is None:
        if tz is None:
            tz = datetime.now().astimezone().tzinfo
        local_dt = local_dt.replace(tzinfo=tz)
    utc = local_dt.astimezone(timezone.utc).replace(microsecond=0)
    return utc.strftime('%Y-%m-%dT%H:%M:%SZ')


def publish_at_from_qdatetime(schedule_enabled: bool, qdatetime) -> Optional[str]:
    """Lee un QDateTime de Qt (hora local del widget) y devuelve publishAt o None."""
    if not schedule_enabled or qdatetime is None or not qdatetime.isValid():
        return None
    return local_to_youtube_publish_at(True, qdatetime.toPyDateTime())
