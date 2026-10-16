# -*- coding: utf-8 -*-
"""Puente Claude Code -> informe -> worker: estado, validación e import local. Sin Qt ni red.

El informe es un dato externo no confiable. Este módulo NO cambia la semántica de SEO: reusa los
validadores existentes (``beat_seo_report`` para Beats, ``kit_trends`` para Loop kits) y solo
informa. Nunca devuelve texto libre del informe en mensajes: los errores son códigos fijos.
La copia local vive en ``tokens/seo_reports/`` (``tokens/`` no se versiona).
"""
import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime, timezone

from core import automation_status as status
from core import beat_seo_report, kit_seo, kit_trends
from core.beat_cloud import decode_document

BEATS, KITS = 'beats', 'kits'
REPORTS_DIR = os.path.join(status.TOKENS_DIR, 'seo_reports')
BEAT_MAX_AGE_DAYS = 14          # mismo tope que beat_seo_report.validate_report
MAX_KIT_BYTES = 256 * 1024      # kit_trends no limita el tamaño: el import local sí
EXPIRED = 'expired'

# Código fijo -> mensaje para la UI. Ningún mensaje lleva datos del informe.
ERROR_LABELS = {
    'file': 'No se pudo leer el archivo.',
    'size': 'El archivo es demasiado grande.',
    'json': 'No es un JSON UTF-8 válido (sin claves repetidas ni NaN).',
    'schema': 'Faltan campos o hay campos de más respecto del schema.',
    'version': 'Versión de schema no soportada.',
    'channel': 'El channel_id no coincide con el ID interno del canal.',
    'expired': 'La fecha del informe está vencida o es futura.',
    'date': 'La fecha generated_at es inválida (necesita zona horaria).',
    'sources': 'Las fuentes declaradas no son las esperadas.',
    'keywords': 'La lista de keywords es inválida.',
    'metric': 'Una métrica está fuera de rango.',
    'text': 'Un texto tiene formato no permitido.',
    'duplicate': 'Hay tags repetidos.',
    'key': 'Canal o automatización inválidos.',
    'write': 'No se pudo guardar la copia local.',
}
# Mensajes de ValueError de beat_seo_report -> código de UI.
_BEAT_CODES = {
    'seo_schema_invalid': 'schema', 'seo_version_invalid': 'version',
    'seo_channel_mismatch': 'channel', 'seo_report_expired': 'expired',
    'seo_sources_invalid': 'sources', 'seo_keywords_invalid': 'keywords',
    'seo_metric_invalid': 'metric', 'seo_date_invalid': 'date',
    'seo_text_invalid': 'text', 'seo_list_invalid': 'text', 'seo_duplicate': 'duplicate',
}
_KIT_CODES = {'json': 'json', 'version': 'version', 'fecha': 'date', 'viejo': 'expired'}


class SeoReportError(Exception):
    """Error de informe. ``code`` es una clave de ``ERROR_LABELS``; no lleva datos."""

    def __init__(self, code):
        super().__init__(code)
        self.code = code if code in ERROR_LABELS else 'schema'


def label(code):
    """Mensaje fijo para un código (desconocido -> schema)."""
    return ERROR_LABELS.get(code, ERROR_LABELS['schema'])


def _now(now):
    return now or datetime.now(timezone.utc)


def _filename(kind, key):
    """Nombre seguro y estable: slug acotado + hash, así dos IDs parecidos no colisionan."""
    key = key if isinstance(key, str) else ''
    if kind == BEATS and not key.strip():
        raise SeoReportError('key')
    slug = re.sub(r'[^a-z0-9]+', '-', key.casefold()).strip('-')[:30] or 'default'
    digest = hashlib.sha1(key.encode('utf-8')).hexdigest()[:8]
    return f'{kind}-{slug}-{digest}.json'


def report_path(kind, key, base=None):
    """Ruta de la copia local del informe; siempre dentro de ``tokens/seo_reports``."""
    if kind not in (BEATS, KITS):
        raise SeoReportError('key')
    base = base or REPORTS_DIR
    path = os.path.join(base, _filename(kind, key))
    if not status._inside(path, base):
        raise SeoReportError('key')
    return path


# --- Validación ---

def _beat_report(raw, channel_id, now):
    """Informe de Beats validado con las reglas del worker (UTF-8 estricto)."""
    try:
        data = decode_document(raw.decode('utf-8'))
    except Exception:
        raise SeoReportError('json') from None
    try:
        return beat_seo_report.validate_report(data, channel_id, now.isoformat())
    except ValueError as exc:
        raise SeoReportError(_BEAT_CODES.get(str(exc), 'schema')) from None
    except Exception:
        raise SeoReportError('schema') from None


def _kit_report(raw, now, max_age_days):
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise SeoReportError('json') from None
    try:
        report = kit_trends.parse_report(text, now, max_age_days)
    except kit_trends.KitTrendsError as exc:
        raise SeoReportError(_KIT_CODES.get(exc.code, 'schema')) from None
    except Exception:
        raise SeoReportError('schema') from None
    # Un informe sin keywords útiles es válido: el worker lo acepta y sigue con la ficha manual.
    return report


def _validate(kind, raw, key, now, max_age_days):
    """``(info, informe)``; lanza ``SeoReportError``. ``info`` no lleva texto del informe."""
    if kind == BEATS:
        report = _beat_report(raw, key, now)
        made, count = beat_seo_report.moment(report['generated_at']), len(report['keywords'])
    else:
        report = _kit_report(raw, now, max_age_days)
        made = datetime.fromisoformat(report['generated_at'])
        count = sum(len(v) for v in report['genres'].values())
    age = max((now - made).total_seconds(), 0) / 86400
    return {'generated_at': made.isoformat(), 'age_days': round(age, 1), 'keywords': count}, report


def _read_file(path, limit):
    try:
        with open(path, 'rb') as f:
            raw = f.read(limit + 1)
    except OSError:
        raise SeoReportError('file') from None
    if len(raw) > limit:
        raise SeoReportError('size')
    return raw


def _limit(kind):
    return beat_seo_report.MAX_BYTES if kind == BEATS else MAX_KIT_BYTES


# --- Import y estado local ---

def import_report(kind, source, key, now=None, base=None, max_age_days=None):
    """Valida el archivo ``source`` y, solo si sirve, lo copia a la ruta local del canal.

    Args:
        kind: ``'beats'`` (``key`` = id interno del canal) o ``'kits'`` (``key`` = slug o '').
    Returns:
        ``info`` con ``generated_at``, ``age_days`` y ``keywords``.
    Raises:
        SeoReportError: con código fijo; no se escribe nada ante un error.
    """
    now = _now(now)
    max_age = max_age_days or kit_trends.DEFAULTS['max_age_days']
    dest = report_path(kind, key, base)
    raw = _read_file(source, _limit(kind))
    info, _ = _validate(kind, raw, key, now, max_age)
    tmp = dest + '.tmp'
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(tmp, 'wb') as f:  # atómico: un corte no deja un informe truncado
            f.write(raw)
        os.replace(tmp, dest)
    except OSError:
        raise SeoReportError('write') from None
    return info


def local_status(kind, key, now=None, base=None, max_age_days=None, notion_state=None):
    """Estado del informe para la UI: ``{state, origin, code, ...info}``.

    ``state``: ``ok`` / ``missing`` / ``invalid`` / ``expired`` / ``unknown``.
    ``origin``: ``local`` (copia importada), ``notion`` (sin copia pero Notion configurado: lo
    lee el worker, acá no hay red) o ``none``.
    """
    now = _now(now)
    max_age = max_age_days or kit_trends.DEFAULTS['max_age_days']
    try:
        path = report_path(kind, key, base)
    except SeoReportError as exc:
        return {'state': status.UNKNOWN if kind == BEATS and not key else status.INVALID,
                'origin': 'none', 'code': exc.code}
    if not os.path.isfile(path):
        if notion_state == status.OK:
            return {'state': status.UNKNOWN, 'origin': 'notion', 'code': None}
        return {'state': status.MISSING, 'origin': 'none', 'code': None}
    try:
        info, _ = _validate(kind, _read_file(path, _limit(kind)), key, now, max_age)
    except SeoReportError as exc:
        state = EXPIRED if exc.code == 'expired' else status.INVALID
        return {'state': state, 'origin': 'local', 'code': exc.code}
    return {'state': status.OK, 'origin': 'local', 'code': None, **info}


def describe(info):
    """Texto de una línea para la UI a partir de ``local_status`` (solo códigos y números)."""
    origin = {'local': 'copia local', 'notion': 'Notion (lo lee el worker)', 'none': 'ninguno'}[info['origin']]
    state = info['state']
    if state == status.OK:
        return f"Informe vigente · origen: {origin} · {info['age_days']} días · {info['keywords']} keywords."
    if state == status.UNKNOWN and info['origin'] == 'none':
        return 'Elegí un canal para ver el estado de su informe.'
    if state == status.UNKNOWN:
        return f'Sin copia local · origen: {origin}. Importá un JSON para validarlo acá.'
    if state == status.MISSING:
        return 'Sin informe: el SEO usa la ficha manual del panel.'
    return f"Informe {'vencido' if state == EXPIRED else 'inválido'} ({origin}): {label(info['code'])}"


# --- Schema y sugerencias (solo lectura) ---

def schema_text(kind, key, names=(), now=None):
    """JSON de ejemplo listo para pegar en Claude Code.

    Args:
        names: tags manuales (Beats) o géneros del panel (Kits) para precargar el ejemplo.
    """
    stamp = _now(now).replace(microsecond=0).isoformat()
    names = [n for n in names if isinstance(n, str) and n.strip()]
    if kind == BEATS:
        doc = {'schema_version': 1, 'generated_at': stamp, 'channel_id': key,
               'sources': ['claude_code', 'vidiq', 'youtube_analytics'],
               'keywords': [{'tag': t, 'score': 50, 'views': 0, 'ctr': 0, 'average_view_percentage': 0}
                            for t in (names[:3] or ['trap'])]}
    else:
        entry = {'keyword': 'example loop kit', 'monthly_searches': 1000,
                 'competition': 20, 'growth_pct': 0}
        doc = {'version': 1, 'generated_at': stamp, 'channel': {'top_videos': []},
               'genres': {g: {'keywords': [dict(entry)]} for g in (names[:5] or ['guitarras'])}}
    return json.dumps(doc, indent=2, ensure_ascii=False)


_MANUAL_THUMBNAILS = (
    'Las miniaturas se configuran a mano en el panel (pestaña Canal). '
    'El robot no aplica sugerencias del informe.'
)


def _thumbnail_line(value):
    """Una línea informativa del informe; descarta texto sospechoso."""
    if type(value) is not str or not value.strip() or len(value) > 120:
        return None
    text = value.strip()
    if any(unicodedata.category(c).startswith('C') for c in text) or any(c in text for c in '<>{}'):
        return None
    if re.search(r'https?:|www\.', text, re.IGNORECASE):
        return None
    return text


def thumbnail_recommendations(kind, key, now=None, base=None, max_age_days=None):
    """Texto de solo lectura para miniaturas: ``thumbnail_suggestions`` del informe local o nota fija.

    No altera render ni títulos; el worker de Beats no lee este campo (solo UI / kits con JSON laxo).
    """
    now = _now(now)
    max_age = max_age_days or kit_trends.DEFAULTS['max_age_days']
    info = local_status(kind, key, now, base, max_age)
    if info['state'] != status.OK:
        return [_MANUAL_THUMBNAILS]
    try:
        raw = _read_file(report_path(kind, key, base), _limit(kind))
        doc = decode_document(raw.decode('utf-8'))
    except (SeoReportError, OSError, Exception):
        return [_MANUAL_THUMBNAILS]
    if not isinstance(doc, dict):
        return [_MANUAL_THUMBNAILS]
    lines = []
    for item in (doc.get('thumbnail_suggestions') if isinstance(doc.get('thumbnail_suggestions'), list)
                 else []):
        text = _thumbnail_line(item)
        if text and text not in lines:
            lines.append(f'• {text}')
    if not lines and kind == KITS and isinstance(doc.get('suggestions'), list):
        for item in doc['suggestions']:
            text = _thumbnail_line(item)
            if text and text not in lines:
                lines.append(f'• {text}')
    if not lines:
        return [_MANUAL_THUMBNAILS]
    return ['Sugerencias del informe (solo lectura; no se aplican solas):', *lines[:8]]


def suggestions(kind, key, names=(), now=None, base=None, max_age_days=None):
    """Líneas de sugerencia de solo lectura (nada se escribe en la ficha ni en títulos).

    Beats: tags del informe que coinciden con la ficha, sin afirmar que el worker los use
    (también tienen que estar en el beat y caber en el título). Kits: top de búsquedas por género.
    """
    now = _now(now)
    max_age = max_age_days or kit_trends.DEFAULTS['max_age_days']
    try:
        raw = _read_file(report_path(kind, key, base), _limit(kind))
        _, report = _validate(kind, raw, key, now, max_age)
    except SeoReportError:
        return []
    if kind == BEATS:
        manual = {n.casefold() for n in names}
        ranked = sorted(report['keywords'], key=lambda r: (-r['score'], r['tag'].casefold()))
        usable = [r['tag'] for r in ranked if r['tag'].casefold() in manual]
        missing = [r['tag'] for r in ranked if r['tag'].casefold() not in manual][:5]
        # candidates() además exige el tag en el beat y un título de hasta 100 caracteres.
        return [f"Coinciden con tu ficha: {', '.join(usable) or 'ninguno'}. "
                f"El worker solo los usa si también están en el beat y el título cabe en 100 caracteres.",
                f"Fuera de tu ficha (no se usan): {', '.join(missing) or 'ninguno'}"]
    lines = []
    for genre in names:
        found = kit_seo.find_key(report['genres'], genre)
        words = sorted(report['genres'].get(found) or [], key=lambda w: -(w['searches'] or 0))
        lines.append(f"{genre}: " + (', '.join(w['keyword'] for w in words[:3])
                                     if words else 'sin keywords en el informe'))
    return lines
