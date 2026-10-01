# -*- coding: utf-8 -*-
"""
Helpers para nombres de archivo y filtros de FFmpeg.
"""


def _sanitize_filename(s):
    """Elimina caracteres no válidos para nombres de archivo."""
    for c in '\\/:*?"<>|':
        s = s.replace(c, '_')
    return s[:200].strip() or 'video'


def _escape_drawtext(s):
    """Escapa texto para drawtext de FFmpeg (comillas y dos puntos)."""
    if not s:
        return ''
    return s.replace('\\', '\\\\').replace("'", "\\'").replace(':', '\\:')


def _build_vf_with_overlays(base_vf, overlay_display=None, cta_text=None, audio_duration=None):
    """Añade overlay de título y CTA (último 15% del video) al filtro de video. Sin escape_text (no soportado en todas las builds de FFmpeg)."""
    vf = base_vf
    if overlay_display:
        vf += ",drawtext=text='{}':fontsize=32:fontcolor=white:bordercolor=black:borderw=2:x=(w-tw)/2:y=80".format(_escape_drawtext(overlay_display))
    if cta_text and audio_duration is not None and audio_duration > 0:
        t0 = audio_duration * 0.85
        t1 = audio_duration + 1
        vf += ",drawtext=text='{}':fontsize=24:fontcolor=white:bordercolor=black:borderw=1:x=(w-tw)/2:y=h-60:enable='between(t,{},{})'".format(_escape_drawtext(cta_text), t0, t1)
    return vf
