"""Offline full daily pipeline: public catalog, Dropbox, HLS, FFmpeg, YouTube."""
import sys
import unittest
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
# Choque de calendario: un lunes ya ocupado en YouTube (fila falsa) debe mover el trabajo
# nuevo al jueves y cancelar el lunes planificado sin reservar intento.
COLLISION = ('test_taken_monday_moves_new_job_to_thursday',
             'test_planned_monday_job_cancelled_without_reserving_attempt',
             'test_second_read_blocks_upload_first_read_allowed')


def _ids(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _ids(item)
        else:
            yield item.id()


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover(str(root / 'tests'), pattern='test_beat_daily.py')
    names = {name.rsplit('.', 1)[-1] for name in _ids(suite)}
    missing = [name for name in COLLISION if name not in names]
    if missing:
        print('FAIL: faltan los smokes de calendario:', ', '.join(missing))
        raise SystemExit(1)
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
