"""Beat que no se puede usar (sin audio): otro beat toma su horario.

Si un beat falla al preparar el video por un motivo propio del beat (BeatStars no da la
vista previa y no hay audio asociado en Dropbox, el archivo no sirve, etc.), dejar su
trabajo pendiente lo haría fallar todos los días hasta que venza el horario. En cambio:

- el trabajo pasa a ``cancelled`` con ``swapped: True`` (libera el horario, como ``lost``);
- el planificador no vuelve a elegir ese beat en ese canal por ``REST_DAYS`` días;
- en la misma corrida se replanifica el canal y el beat nuevo entra en la cola.

Solo pasa antes de reservar intento de subida, así que nunca gasta cupo.
"""
from datetime import timedelta

from core.beat_schema import instant

# Motivos propios del beat que aparecen al bajar su audio (core.beat_download).
UNUSABLE = frozenset({'explicit_audio_association_required', 'audio_type_rejected',
                      'duration_mismatch', 'download_limit'})
REST_DAYS = 30
MAX_PER_RUN = 3  # tope de reemplazos por corrida y canal


def unusable_tracks(state, now):
    """``{(canal, track_id)}`` de beats reemplazados en los últimos ``REST_DAYS`` días."""
    cutoff = instant(now) - timedelta(days=REST_DAYS)
    return {(job['channel'], job['track_id']) for job in state['jobs'].values()
            if job.get('swapped') and instant(job['swapped_at']) >= cutoff}


def mark(state, job_id, now):
    """Cancela ``job_id`` como reemplazado si sigue pendiente y sin intento. Devuelve True si lo hizo."""
    job = state['jobs'].get(job_id)
    attempted = {entry['job_id'] for entries in state['attempts'].values()
                 for entry in entries.values()}
    if not job or job['status'] not in ('planned', 'failed') or job_id in attempted:
        return False
    job.update(status='cancelled', swapped=True, swapped_at=instant(now).isoformat())
    return True
