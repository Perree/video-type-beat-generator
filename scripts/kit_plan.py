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


def main(env=None, now=None):
    env = os.environ if env is None else env
    # Día de la semana en Buenos Aires (UTC-3 fijo), igual que los horarios del worker.
    today = (now or datetime.now(timezone.utc)) - timedelta(hours=3)
    try:
        print('matrix=' + kit_channel.matrix_json(
            env.get('KIT_CHANNELS'), today.weekday(), env.get('KIT_ONLY')))
    except kit_channel.KitChannelError as exc:
        print(f"Plan inválido: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
