# -*- coding: utf-8 -*-
"""Subidas escalonadas: cada video se sube unos días antes de su fecha, no todos juntos.

El cronograma de publicación no cambia. Lo que cambia es *cuándo* se hace la subida a
YouTube: en vez de subir de una vez todo el búfer de 14 días, cada trabajo espera hasta
quedar a ``lead_days`` de su horario. ``lead_days`` sale de un hash del id del trabajo
(estable entre corridas) y va de ``min_days`` a ``max_days``, así las subidas caen en
días distintos.

Config por canal: ``upload_spread`` = ``{"min_days": 2, "max_days": 4}``, ``false`` para
subir todo el búfer como antes, o ausente para usar ``DEFAULT``.
"""
import hashlib
from datetime import timedelta

# min_days 2: si una corrida diaria falla, queda al menos otra antes de que el horario venza.
DEFAULT = {'min_days': 2, 'max_days': 4}


def settings(value):
    """Normaliza la config a ``{min_days, max_days}``, o None si está apagada."""
    if value is False:
        return None
    if value is None or value is True:
        value = DEFAULT
    if not isinstance(value, dict):
        raise ValueError('invalid_upload_spread')
    low = value.get('min_days', DEFAULT['min_days'])
    high = value.get('max_days', DEFAULT['max_days'])
    if type(low) is not int or type(high) is not int or not 1 <= low <= high <= 14:
        raise ValueError('invalid_upload_spread')
    return {'min_days': low, 'max_days': high}


def lead_days(job_id, cfg):
    """Días antes del horario en que se sube este trabajo (estable por id)."""
    span = cfg['max_days'] - cfg['min_days'] + 1
    digest = hashlib.sha256(str(job_id).encode()).digest()
    return cfg['min_days'] + digest[0] % span


def too_early(job, slot, now, value):
    """True si todavía no toca subir ``job`` (``slot`` y ``now`` con zona horaria)."""
    cfg = settings(value)
    if cfg is None:
        return False
    return slot > now + timedelta(days=lead_days(job['id'], cfg))
