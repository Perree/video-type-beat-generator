#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Job ``plan`` del workflow: qué canales de loop kits corren en esta corrida.

Lee ``KIT_CHANNELS`` (variable del repo) y ``KIT_ONLY`` (canal elegido en una corrida manual)
del entorno y escribe ``matrix=<json>`` en la salida. Sin secretos y solo con la librería
estándar. No imprime el contenido de las variables.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import kit_channel

CRON_OFFSET = timedelta(hours=23)  # Igual al cron de .github/workflows/kit-weekly.yml.


def main(env=None, now=None):
    env = os.environ if env is None else env
    # Día del cron (23:00 UTC = 20:00 Buenos Aires), no de la hora real de arranque:
    # GitHub suele demorar el cron 3-4 h y cruzar la medianoche, lo que salteaba el
    # canal del día. Restar 23 h devuelve el día del disparo para demoras de hasta 24 h.
    today = (now or datetime.now(timezone.utc)) - CRON_OFFSET
    try:
        print('matrix=' + kit_channel.matrix_json(
            env.get('KIT_CHANNELS'), today.weekday(), env.get('KIT_ONLY')))
    except kit_channel.KitChannelError as exc:
        print(f"Plan inválido: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
