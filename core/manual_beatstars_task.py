"""Qt worker for manual acquisition; results are consumed only after thread exit."""
from threading import Event

from PyQt5.QtCore import QThread, pyqtSignal

from core.beat_http import BeatError
from core.manual_beatstars import BatchResult, ManualBeatStars
from core.manual_beatstars_store import HistoryError


def error_message(code):
    messages = {
        'cancelled': 'Operación cancelada.',
        'invalid_profile': 'Ingresá la URL de tu perfil de BeatStars.',
        'url_rejected': 'Usá una URL HTTPS de beatstars.com.',
        'invalid_tags': 'Usá hasta 40 tags de hasta 100 caracteres, separados por comas.',
        'history_busy': 'Otra descarga está usando el historial. Esperá y volvé a intentar.',
        'history_unavailable': 'No se pudo abrir el historial local. Revisá los permisos de config.',
        'history_unreadable': 'El historial local no se puede leer. Conservá el archivo y restaurá una copia válida.',
        'history_write_failed': 'No se pudo guardar el historial. Se detuvo la tanda; los paquetes completos se recuperan al reintentar.',
        'history_limit': 'El historial alcanzó su límite de tamaño. Se detuvo la tanda.',
        'package_recovery_conflict': 'Hay un paquete pendiente modificado. Revisá sus archivos antes de reintentar.',
        'package_recovery_failed': 'No se pudo recuperar una descarga pendiente. Revisá los archivos y permisos.',
        'package_rollback_failed': 'No se pudo limpiar una descarga incompleta. Se detuvo la tanda para recuperarla al reintentar.',
        'preview_unavailable': 'Este beat no tiene un preview público disponible.',
        'media_tool_missing': 'Falta FFmpeg o FFprobe. Revisá la instalación de la app.',
        'duration_mismatch': 'La duración del preview no coincide con el beat.',
        'local_write_failed': 'No se pudieron guardar los archivos. Revisá el espacio y los permisos de la carpeta.',
        'invalid_track_selection': 'Elegí entre 1 y 100 beats sin repetir.',
        'unknown_track': 'La selección cambió. Volvé a buscar los beats.',
        'unexpected_error': 'La operación no pudo completarse. Volvé a intentar.',
    }
    if code in messages:
        return messages[code]
    if code in {'request_failed', 'http_error', 'media_request_failed', 'preview_resolution_failed',
                'scan_timeout', 'download_timeout'}:
        return 'No se pudo consultar o descargar desde BeatStars. Revisá la conexión y volvé a intentar.'
    if code in {'audio_probe_failed', 'audio_type_rejected', 'audio_stream_rejected',
                'media_process_failed', 'media_validation_failed', 'media_timeout', 'converted_audio_rejected'}:
        return 'No se pudo validar o convertir el audio de este beat.'
    return 'BeatStars devolvió datos o medios que no se pudieron validar. Volvé a intentar.'


class ManualBeatStarsTask(QThread):
    progress = pyqtSignal(int, int, str)

    def __init__(self, action, parameters, parent=None, service_factory=ManualBeatStars):
        super().__init__(parent)
        self.action = action
        self.parameters = dict(parameters)
        self.service_factory = service_factory
        self.cancel_event = Event()
        self.value = None
        self.error = ''

    def cancel(self):
        self.cancel_event.set()
        self.requestInterruption()

    def run(self):
        try:
            if self.cancel_event.is_set():
                raise BeatError('cancelled')
            service = self.service_factory(cancelled=self.cancel_event.is_set)
            if self.action == 'search':
                self.value = service.search(**self.parameters)
                if self.cancel_event.is_set():
                    self.value = None
                    self.error = 'cancelled'
            else:
                self.value = service.download(**self.parameters, progress=self.progress.emit)
                if self.cancel_event.is_set():
                    self.value.cancelled = True
        except HistoryError as exc:
            self.value = getattr(exc, 'result', None)
            self.error = str(exc)
        except BeatError as exc:
            self.error = 'cancelled' if self.cancel_event.is_set() else str(exc)
        except ValueError as exc:
            code = str(exc)
            self.error = code if code in {'invalid_tags', 'invalid_track_selection', 'unknown_track'} else 'unexpected_error'
        except OSError:
            self.error = 'local_write_failed'
        except Exception:
            self.error = 'unexpected_error'
        if self.action == 'download' and self.value is None and self.error == 'cancelled':
            self.value = BatchResult(cancelled=True)
