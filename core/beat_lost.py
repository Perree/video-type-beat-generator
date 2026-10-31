"""Subidas perdidas: intentos de subida que nunca llegaron a YouTube.

Una subida que falla con resultado desconocido queda como intento reservado y, para no
duplicar videos, nunca se reintenta. Pero así el día queda vacío y el beat bloqueado para
siempre. ``lost_jobs`` decide, con el calendario real de YouTube, cuáles se pueden liberar.

Solo se libera un trabajo si TODO se cumple (ante cualquier duda, no se toca):
- es del canal, sigue ``planned``/``failed`` y tiene intento reservado;
- su último intento tiene más de ``GRACE`` (un insert exitoso ya se vería en YouTube);
- el día del trabajo no está ocupado en el calendario de YouTube;
- ningún video del canal tiene el título que se iba a subir;
- la lista de YouTube cubre el momento del intento (no está cortada por el tope).
"""
from datetime import timedelta

from core.beat_schema import instant

GRACE = timedelta(hours=12)
MAX_ROWS = 200  # tope de youtube.list_channel_calendar


def _title(text):
    # Mismo recorte que BeatYouTube.upload aplica al título.
    return ' '.join(str(text or '').replace('<', '').replace('>', '')[:100].split()).casefold()


def _covered_since(rows, cap):
    """Desde cuándo la lista de YouTube está completa: None si no se sabe."""
    if len(rows) < cap:
        return 'all'
    dates = []
    for row in rows:
        try:
            dates.append(instant(row.get('published_at')))
        except Exception:
            return None
    return min(dates) if dates else None


def lost_jobs(state, channel_id, rows, now, taken, *, grace=GRACE, cap=MAX_ROWS):
    """Ids de trabajos de ``channel_id`` cuya subida se perdió y se pueden liberar.

    Args:
        state: estado de Beats (``jobs`` y ``attempts``).
        rows: videos del canal (``youtube.list_channel_calendar``), lista completa.
        now: instante actual con zona.
        taken: días ocupados en YouTube (``publish_calendar.occupied_days``).
    """
    rows = list(rows)
    titles = {_title(row.get('title')) for row in rows}
    covered = _covered_since(rows, cap)
    attempts = {}
    for entries in state.get('attempts', {}).values():
        for entry in entries.values():
            attempts.setdefault(entry['job_id'], []).append(instant(entry['reserved_at']))
    limit = instant(now) - grace
    lost = []
    for job in state.get('jobs', {}).values():
        reserved = attempts.get(job['id'])
        if (job['channel'] != channel_id or job['status'] not in ('planned', 'failed')
                or not reserved or max(reserved) > limit):
            continue
        if instant(job['slot']).date() in taken:
            continue
        if covered is None or (covered != 'all' and covered > min(reserved)):
            continue
        title = ((job.get('seo_snapshot') or {}).get('selected') or {}).get('title')
        if not title or _title(title) in titles:
            continue
        lost.append(job['id'])
    return sorted(lost)
