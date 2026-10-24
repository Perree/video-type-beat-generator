# -*- coding: utf-8 -*-
"""Calendario de ocupación de YouTube, común a todos los canales automatizados.

Un video agendado a mano en YouTube Studio es invisible para el estado de los workers;
este módulo convierte la lista de videos del canal en el conjunto de días (Buenos Aires)
que ya están ocupados. Las fases siguientes saltan un día de cron si está en ese conjunto.
"""
from datetime import datetime, date, timedelta

from core.beat_schema import BA, instant

_PRIVACIES = ('private', 'public', 'unlisted')


def _day(value, code):
    """Día de Buenos Aires de un timestamp ISO.

    Parámetros: value (str ISO, admite sufijo 'Z'); code (código estable si falla).
    Devuelve: datetime.date. Lanza ValueError(code) si está vacío o no se puede interpretar.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError(code)
    text = value.strip()
    if text.endswith(('Z', 'z')):
        text = text[:-1] + '+00:00'  # fromisoformat de Python < 3.11 no acepta 'Z'
    try:
        return instant(text).date()
    except ValueError:
        raise ValueError(code) from None


def occupied_days(videos, now):
    """Días de calendario (zona Buenos Aires) ocupados por los videos del canal.

    Parámetros:
        videos: iterable de dicts con privacy (str), published_at (ISO o "") y
            publish_at (ISO o "").
        now: datetime con zona horaria; se valida pero no filtra (el llamador recorta
            la ventana de planificación).
    Devuelve: set[datetime.date]. Un mismo día con distinta hora cuenta una sola vez.
    Lanza ValueError con código estable: aware_datetime_required, calendar_privacy_invalid,
    calendar_publish_at_invalid, calendar_published_at_invalid.
    """
    if not isinstance(now, datetime):
        raise ValueError('aware_datetime_required')
    instant(now)
    days = set()
    for video in videos:
        privacy = video.get('privacy')
        if privacy not in _PRIVACIES:
            raise ValueError('calendar_privacy_invalid')
        publish_at = video.get('publish_at') or ''
        # publishAt es la fecha de decisión: un video agendado es private con publishAt;
        # snippet.publishedAt es la fecha de subida y no dice cuándo sale al aire.
        if publish_at:
            days.add(_day(publish_at, 'calendar_publish_at_invalid'))
        elif privacy != 'private':
            days.add(_day(video.get('published_at') or '', 'calendar_published_at_invalid'))
        # private sin publishAt: borrador o piloto privado, no ocupa nada
    return days


def slot_day(value, tz=None):
    """Día de Buenos Aires de un slot.

    Parámetros: value (datetime; si es naive se interpreta en ``tz``); tz (zona de los
    datetimes naive; por defecto Buenos Aires).
    Devuelve: datetime.date en Buenos Aires, comparable con ``occupied_days``.
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=tz or BA)
    return instant(value).date()


def next_free_slots(slots, now, occupied_days, count, horizon_days, *, tz=None):
    """Próximos slots de cron cuyo día (Buenos Aires) no está ocupado en YouTube.

    Es el helper que debe usar todo worker automático que elige su propia fecha
    (Loopkits semanal y preview, y cualquier programador futuro). Type Beats no lo usa:
    planifica su búfer de 14 días con ``beat_schedule.plan``.

    Parámetros:
        slots: lista de ``{weekday, hour, minute}`` (weekday 0 = lunes).
        now: datetime de referencia (naive en ``tz`` o con zona); los slots son
            estrictamente posteriores.
        occupied_days: conjunto de datetime.date de ``occupied_days``.
        count: máximo de slots a devolver (int >= 0).
        horizon_days: tope del recorrido; solo slots en ``(now, now + horizon_days]``.
        tz: zona de los datetimes naive (por defecto Buenos Aires).
    Devuelve: lista de hasta ``count`` datetimes con la misma tzinfo que ``now``, en
    orden. Puede traer menos si el horizonte se corta antes.
    """
    # Import diferido: Type Beats importa este módulo y no debe cargar módulos de kits.
    from core.kit_publish import next_slot

    if type(count) is not int or count < 0:
        raise ValueError('invalid_slot_count')
    if type(horizon_days) is not int or horizon_days < 1:
        raise ValueError('invalid_horizon_days')
    taken = set(occupied_days)
    end = now + timedelta(days=horizon_days)
    found, cur = [], now
    while len(found) < count:
        cur = next_slot(cur, slots)
        # El horizonte acota el recorrido: con todos los días ocupados no gira para siempre.
        if cur > end:
            break
        if slot_day(cur, tz) not in taken:
            found.append(cur)
    return found
