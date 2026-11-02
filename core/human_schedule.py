# -*- coding: utf-8 -*-
"""Horarios con variación humana: cada publicación se corre unos minutos y a veces un día.

La variación es determinística (sale de un hash de la fecha base y del horario), así que
volver a planificar la misma semana da exactamente el mismo resultado: no se duplican
trabajos ni cambia un horario ya agendado.

Config por canal: ``human_schedule`` = ``{"minutes": 45, "days": 1}``, ``false`` para
apagarla, o ausente para usar ``DEFAULT``.
"""
import hashlib
from datetime import timedelta

DEFAULT = {'minutes': 45, 'days': 1}
# Probabilidad de mover el día cuando ``days`` > 0: la mayoría de las semanas queda igual.
DAY_SHIFT_PCT = 30
_KEYS = ('vary_minutes', 'vary_days')


def settings(value):
    """Normaliza la config del canal a ``{minutes, days}`` (ceros = apagada)."""
    if value is False:
        return {'minutes': 0, 'days': 0}
    if value is None or value is True:
        value = DEFAULT
    if not isinstance(value, dict):
        raise ValueError('invalid_human_schedule')
    out = {}
    for key, top in (('minutes', 180), ('days', 2)):
        n = value.get(key, DEFAULT[key])
        if type(n) is not int or not 0 <= n <= top:
            raise ValueError('invalid_human_schedule')
        out[key] = n
    return out


def annotate(slots, value):
    """Copia de ``slots`` con ``vary_minutes``/``vary_days`` según la config del canal."""
    cfg = settings(value)
    return [dict(s, vary_minutes=cfg['minutes'], vary_days=cfg['days']) for s in slots]


def spread(spec):
    """Cuánto puede alejarse un slot de su hora base (para buscar candidatos)."""
    return timedelta(days=int(spec.get('vary_days') or 0),
                     minutes=int(spec.get('vary_minutes') or 0))


def varies(spec):
    return any(spec.get(k) for k in _KEYS)


def vary(base, spec, salt=''):
    """Hora final de un slot cuya hora base es ``base`` (datetime, con o sin zona)."""
    minutes = int(spec.get('vary_minutes') or 0)
    days = int(spec.get('vary_days') or 0)
    if not minutes and not days:
        return base
    key = f"{salt}|{base.date().isoformat()}|{spec.get('weekday')}|{spec.get('hour')}|{spec.get('minute')}"
    digest = hashlib.sha256(key.encode()).digest()
    shift = 0
    if days and digest[0] % 100 < DAY_SHIFT_PCT:
        shift = 1 + digest[1] % days
        shift = -shift if digest[2] % 2 else shift
    offset = (int.from_bytes(digest[3:5], 'big') % (2 * minutes + 1)) - minutes if minutes else 0
    return base + timedelta(days=shift, minutes=offset)
