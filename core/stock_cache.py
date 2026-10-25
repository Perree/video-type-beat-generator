# -*- coding: utf-8 -*-
"""Caché de videos stock ya convertidos a 1080p30 (fuera de Dropbox). Sin Qt.

Convertir un video stock 1440p en cada beat era lo más lento (≈64 s por beat de 3:24).
Con la caché se convierte una sola vez (≈47 s) y cada beat solo repite el video ya listo y
codifica el audio (≈6 s). La caché vive en ``%LOCALAPPDATA%\\TypeBeat\\cache`` (no en Dropbox:
cada PC arma la suya) y se reconoce por ruta + tamaño + fecha del archivo original.
"""
import hashlib
import os

VERSION = 1  # subir si cambia el formato de la caché (invalida lo anterior)
MAX_SECONDS = 600  # un video stock más largo se guarda recortado a 10 min (igual se repite)
DEFAULT_MAX_GB = 5
NORMALIZE = ('scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,'
             'setsar=1,fps=30,format=yuv420p')
# Encuadre «difuminado»: el video entero centrado sobre una copia agrandada y desenfocada.
NORMALIZE_BLUR = ('split[a][b];[a]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,'
                  'boxblur=24:2[bg];[b]scale=1920:1080:force_original_aspect_ratio=decrease[fg];'
                  '[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30,format=yuv420p')
FILTERS = {'recortar': NORMALIZE, 'difuminado': NORMALIZE_BLUR}


def video_filter(framing):
    """Filtro FFmpeg del encuadre. «barras:<%>:<hex>» recorta la foto al alto completo y la centra entre
    dos barras de ancho fijo (misma geometría que ``style.bars_geometry``)."""
    if framing.startswith('barras:'):
        from core import style
        _, percent, color = framing.split(':')
        bar, inner = style.bars_geometry(style.FRAME, int(percent))
        return (f'scale={inner}:1080:force_original_aspect_ratio=increase,crop={inner}:1080,'
                f'pad=1920:1080:{bar}:0:color=0x{color},setsar=1,fps=30,format=yuv420p')
    return FILTERS.get(framing, NORMALIZE)


def default_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), '.cache')
    return os.path.join(base, 'TypeBeat', 'cache')


class StockCache:
    def __init__(self, folder=None, max_bytes=DEFAULT_MAX_GB * 1024 ** 3):
        self.folder = folder or default_dir()
        self.max_bytes = max_bytes

    def key(self, source, framing='recortar'):
        info = os.stat(source)
        raw = f'{VERSION}|{os.path.normcase(os.path.abspath(source))}|{info.st_size}|{info.st_mtime_ns}'
        if framing != 'recortar':  # «recortar» conserva la clave de siempre (reusa la caché existente)
            raw += f'|{framing}'
        return hashlib.sha1(raw.encode('utf-8')).hexdigest()

    def path_for(self, source, framing='recortar'):
        return os.path.join(self.folder, self.key(source, framing) + '.mp4')

    def ensure(self, source, tools, cancelled=lambda: False, framing='recortar'):
        """Ruta del video convertido; lo crea si no existe. Errores de FFmpeg se propagan."""
        target = self.path_for(source, framing)
        if os.path.isfile(target) and os.path.getsize(target) > 0:
            os.utime(target)  # «usado hace poco»: lo último que se borra al limpiar
            return target
        os.makedirs(self.folder, exist_ok=True)
        partial = target + '.part'
        # Sin B-frames y con keyframe cada 2 s: se puede repetir y cortar sin recodificar.
        args = ['-y', '-i', source, '-t', str(MAX_SECONDS), '-map', '0:v:0', '-an', '-sn', '-dn',
                '-vf', video_filter(framing), '-c:v', tools.codec,
                '-preset', 'veryfast' if tools.codec == 'libx264' else 'fast',
                '-bf', '0', '-g', '60', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-f', 'mp4', partial]
        try:
            tools.run(args, cancelled)
            os.replace(partial, target)
        finally:
            if os.path.exists(partial):
                os.remove(partial)
        self.prune(keep={target})
        return target

    def entries(self):
        if not os.path.isdir(self.folder):
            return []
        rows = []
        for name in os.listdir(self.folder):
            path = os.path.join(self.folder, name)
            if name.endswith('.mp4') and os.path.isfile(path):
                info = os.stat(path)
                rows.append((info.st_mtime, info.st_size, path))
        return sorted(rows)

    def size(self):
        return sum(size for _, size, _ in self.entries())

    def prune(self, keep=()):
        """Borra lo menos usado hasta quedar bajo ``max_bytes`` (nunca lo que está en ``keep``)."""
        rows = self.entries()
        total = sum(size for _, size, _ in rows)
        removed = 0
        for _, size, path in rows:
            if total <= self.max_bytes:
                break
            if path in keep:
                continue
            try:
                os.remove(path)
            except OSError:
                continue
            total -= size
            removed += 1
        return removed

    def clear(self):
        removed = 0
        for _, _, path in self.entries():
            try:
                os.remove(path)
                removed += 1
            except OSError:
                pass
        return removed
