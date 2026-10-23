"""Pure weekly recommendations. A local planning ceiling is not YouTube's quota."""
from copy import deepcopy
from itertools import combinations

from core.beat_schema import migrate


def _capacity(config, fixed, external, ceiling):
    config = migrate(config, 'config')
    if type(ceiling) is not int or not 1 <= ceiling <= 6:
        raise ValueError('El tope de planificación debe estar entre 1 y 6.')
    if (not isinstance(external, (list, tuple)) or len(external) != 7
            or any(type(n) is not int or not 0 <= n <= 6 for n in external)):
        raise ValueError('Indicá siete reservas diarias entre 0 y 6.')
    if not set(fixed) <= {ch['id'] for ch in config['channels']}:
        raise ValueError('La lista de canales fijos cambió; abrí el asistente nuevamente.')
    loads = list(external)
    movable = []
    for ch in config['channels']:
        if not ch['active']:
            continue
        if ch['id'] in fixed:
            for slot in ch['slots']:
                loads[slot['weekday']] += 1
        else:
            movable.append(ch)
    if max(loads) > ceiling:
        raise ValueError('Los horarios fijos y las reservas ya superan el tope de un día.')
    return config, movable, loads


def recommend_counts(config, fixed=(), external=(0,) * 7, ceiling=6):
    """Keep all active channels represented; promote the highest priority if it fits."""
    _, channels, loads = _capacity(config, fixed, external, ceiling)
    if not channels:
        return {}
    free = sum(ceiling - n for n in loads)
    baseline = min(2, free // len(channels))
    if baseline < 1:
        raise ValueError('No alcanza para una publicación semanal por canal: fijá menos horarios o pausá canales.')
    counts = {ch['id']: baseline for ch in channels}
    try:
        distribute(config, counts, fixed, external, ceiling)
    except ValueError:
        counts = {ch['id']: 1 for ch in channels}
        distribute(config, counts, fixed, external, ceiling)
        baseline = 1
    # A daily channel also needs room on every day, not just in the weekly total.
    if free >= baseline * (len(channels) - 1) + 7 and max(loads) < ceiling:
        first = min(channels, key=lambda ch: (-ch['priority'], ch['id']))
        promoted = dict(counts, **{first['id']: 7})
        try:
            distribute(config, promoted, fixed, external, ceiling)
        except ValueError:
            pass  # Keep the feasible baseline if fixed calendars prevent a daily channel.
        else:
            counts = promoted
    return counts


def distribute(config, counts, fixed=(), external=(0,) * 7, ceiling=6):
    """Balance requested weekly degrees, then prefer evenly spaced circular gaps.

    Highest demand first and largest residual day capacities implement bipartite
    Havel-Hakimi. Spacing breaks ties only, so it cannot sacrifice feasibility.
    Existing fixed/paused channels and all non-schedule metadata stay untouched.
    """
    result, channels, loads = _capacity(config, fixed, external, ceiling)
    if set(counts) != {ch['id'] for ch in channels}:
        raise ValueError('Elegí una frecuencia para cada canal activo no fijo.')
    if any(type(n) is not int or not 1 <= n <= 7 for n in counts.values()):
        raise ValueError('Elegí entre 1 y 7 publicaciones semanales por canal.')
    for ch in sorted(channels, key=lambda ch: (-counts[ch['id']], -ch['priority'], ch['id'])):
        count = counts[ch['id']]
        choices = combinations([d for d in range(7) if loads[d] < ceiling], count)

        def score(days):
            after = [loads[d] + (d in days) for d in range(7)]
            gaps = [((days[(i + 1) % count] - days[i]) % 7 or 7) for i in range(count)]
            return tuple(sorted(after, reverse=True)), sum(g * g for g in gaps), days

        days = min(choices, key=score, default=None)
        if days is None:
            raise ValueError('La distribución no cabe en el tope diario. Bajá frecuencias o revisá las reservas.')
        # One publication per day; retain the first existing time (Argentina).
        time = min(ch['slots'], key=lambda s: (s['weekday'], s['hour'], s['minute']))
        ch['slots'] = [dict(weekday=d, hour=time['hour'], minute=time['minute']) for d in days]
        for day in days:
            loads[day] += 1
    return deepcopy(result), loads
