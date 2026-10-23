# -*- coding: utf-8 -*-
"""Gasto estimado de las llamadas pagas de IA (portadas y texto): contador por mes y topes (solo librería estándar).

El gasto vive en el estado del canal (``state['spend'][<YYYY-MM>]``), así que cada canal
lleva el suyo y un mes nuevo arranca en cero. Son estimaciones: el costo por imagen y por
verificación sale de la config, no de la factura. ``check`` se consulta antes de cada
llamada paga y ``record`` después. ``Budget`` junta las dos cosas para una corrida y suma el
máximo de imágenes por corrida.

Config en ``kit_preview.spend``: ``monthly_cap_usd``, ``max_images_per_run``,
``image_cost_usd``, ``verify_cost_usd`` y ``text_cost_usd`` (gancho de la descripción).
"""
from datetime import datetime
import math

DEFAULTS = {
    'monthly_cap_usd': 10.0,
    'max_images_per_run': 6,
    'image_cost_usd': 0.25,    # estimado para una edición 1024x1024 en calidad alta
    'verify_cost_usd': 0.01,   # estimado para leer el título con un modelo con visión
    'text_cost_usd': 0.01,     # estimado para una llamada corta de texto (gancho)
}
COUNTERS = ('images', 'verifications')
REASON_MONTH, REASON_RUN, REASON_STATE = 'month', 'run', 'state'
REASON_TEXT = {
    REASON_MONTH: 'se llegó al tope de gasto estimado del mes',
    REASON_RUN: 'se llegó al máximo de imágenes de la corrida',
    REASON_STATE: 'no se pudo leer o guardar el gasto en el estado',
}
_EPS = 1e-9


def _number(value, default, cast=float):
    try:
        number = cast(value)
        if not math.isfinite(number):
            return default
    except (TypeError, ValueError, OverflowError):
        return default
    return number if number >= 0 else default


def settings(kit_cfg=None):
    """Topes y costos de ``kit_preview.spend`` con sus defaults (valores inválidos = default)."""
    raw = (kit_cfg or {}).get('spend')
    raw = raw if isinstance(raw, dict) else {}
    return {key: _number(raw.get(key), default, int if isinstance(default, int) else float)
            for key, default in DEFAULTS.items()}


def month_key(now=None):
    """Clave del mes (``YYYY-MM``) de ``now``."""
    return (now or datetime.now()).strftime('%Y-%m')


def month_entry(state, month):
    """Gasto guardado del mes: ``{usd, images, verifications}`` (ceros si no hay nada)."""
    raw = ((state or {}).get('spend') or {}).get(month)
    raw = raw if isinstance(raw, dict) else {}
    return {'usd': _number(raw.get('usd'), 0.0),
            **{key: _number(raw.get(key), 0, int) for key in COUNTERS}}


def spent(state, month):
    """USD estimados ya gastados en el mes."""
    # Display normalization must not turn a corrupted persisted balance into a
    # fresh budget. The caller (Budget) blocks further paid requests on errors.
    table = (state or {}).get('spend', {})
    if not isinstance(table, dict):
        raise ValueError('invalid_spend')
    entry = table.get(month, {})
    if not isinstance(entry, dict):
        raise ValueError('invalid_spend')
    value = float(entry.get('usd', 0))
    if not math.isfinite(value) or value < 0:
        raise ValueError('invalid_spend')
    return month_entry(state, month)['usd']


def check(spent_usd, cap, cost=0.0):
    """True si después de gastar ``cost`` el mes sigue dentro del tope."""
    try:
        values = [float(v) for v in (spent_usd, cap, cost)]
        return (all(math.isfinite(v) and v >= 0 for v in values)
                and values[0] + values[2] <= values[1] + _EPS)
    except (TypeError, ValueError, OverflowError):
        return False


def record(state, month, usd, images=0, verifications=0):
    """Suma un gasto al mes dentro de ``state`` (lo modifica) y devuelve la entrada del mes."""
    entry = month_entry(state, month)
    entry['usd'] = round(entry['usd'] + max(0.0, float(usd)), 4)
    entry['images'] += max(0, int(images))
    entry['verifications'] += max(0, int(verifications))
    table = state.get('spend')
    if not isinstance(table, dict):
        table = state['spend'] = {}
    table[month] = entry
    return entry


def summary_line(state, now=None, cap=None):
    """Línea para "Ver último estado": gasto estimado del mes, sin datos privados."""
    month = month_key(now)
    entry = month_entry(state, month)
    cap_text = '' if cap is None else f" de {float(cap):.2f}"
    return (f"Gasto estimado de portadas en {month}: USD {entry['usd']:.2f}{cap_text} "
            f"({entry['images']} imagen(es), {entry['verifications']} verificación(es)).")


class Budget:
    """Tope de gasto de una corrida.

    ``store`` guarda el gasto si tiene ``spend_month(month)`` y ``add_spend(month, usd,
    images=, verifications=)`` (el estado en la nube). Sin eso solo cuenta lo de esta
    corrida. Si el gasto no se puede leer o guardar, no autoriza más llamadas pagas.
    """

    def __init__(self, cfg=None, store=None, now=None):
        self.cfg = settings({'spend': cfg or {}})
        self.month = month_key(now)
        self._read = getattr(store, 'spend_month', None)
        self._write = getattr(store, 'add_spend', None)
        self._base = None if self._read else 0.0   # gasto del mes leído del estado
        self._own = 0.0                            # gastado en esta corrida
        self.images = 0
        self.broken = False
        self.notified = set()                      # motivos ya avisados (uno por corrida)

    def month_spent(self):
        """USD estimados del mes (estado + esta corrida), o None si no se pudo leer."""
        if self._base is None:
            try:
                self._base = float(self._read(self.month))
                if not math.isfinite(self._base) or self._base < 0:
                    raise ValueError('invalid_spend')
            except Exception:
                self.broken = True
                return None
        return self._base + self._own

    def blocked(self, cost, images=0):
        """Motivo por el que no se puede gastar ``cost`` (ver ``REASON_*``), o None."""
        total = self.month_spent()
        if self.broken or total is None:
            return REASON_STATE
        if images and self.images + images > int(self.cfg['max_images_per_run']):
            return REASON_RUN
        if not check(total, self.cfg['monthly_cap_usd'], cost):
            return REASON_MONTH
        return None

    def image_cost(self, count=1):
        return float(self.cfg['image_cost_usd']) * max(1, int(count))

    def verify_cost(self):
        return float(self.cfg['verify_cost_usd'])

    def text_cost(self):
        return float(self.cfg['text_cost_usd'])

    def charge(self, usd, images=0, verifications=0):
        """Anota un gasto ya hecho. Si no se puede guardar, corta las próximas llamadas."""
        self.month_spent()  # lee el mes antes de sumar, para no contar este gasto dos veces
        self._own += max(0.0, float(usd))
        self.images += max(0, int(images))
        if self._write is None:
            return
        try:
            self._write(self.month, usd, images=images, verifications=verifications)
        except Exception:
            self.broken = True
