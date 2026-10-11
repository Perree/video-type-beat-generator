# -*- coding: utf-8 -*-
"""Programa y sube un preview de loop kit.

``next_slot`` elige el próximo horario local. ``publish_preview`` intenta
``videos.insert`` con publishAt; si YouTube lo rechaza (cuenta sin auditoría
o programación no permitida), reintenta el mismo archivo en privado y deja
``estado=private_pending``. El pack se marca usado solo si la subida terminó.
"""
import re
from datetime import datetime, timedelta

from core import channel_templates, description, kit_store, youtube
from core.publish_at import local_to_youtube_publish_at

# weekday: lunes=0 … domingo=6 (datetime.weekday).
DEFAULT_SLOTS = (
    {'weekday': 0, 'hour': 18, 'minute': 0},
    {'weekday': 2, 'hour': 18, 'minute': 0},
    {'weekday': 4, 'hour': 18, 'minute': 0},
)

# Marcadores de la descripción que llegan ya armados en ``desc_vars``.
DESC_VARS = ('hook', 'chapters')


def _token(key):
    # Sin llaves: pasa intacto por description.render y no puede venir en un nombre de kit.
    return f'\x00kit:{key}\x00'


def description_template(templates):
    """Plantilla de descripción que se va a usar para el canal."""
    return (templates or {}).get('description_template') or description.DEFAULT_TEMPLATE


def desc_markers(templates):
    """Marcadores de ``DESC_VARS`` presentes en la plantilla de descripción del canal."""
    template = description_template(templates)
    return {key for key in DESC_VARS if '{' + key + '}' in template}


def _drop_token(body, token):
    """Quita un marcador sin contenido junto con el hueco de líneas que dejaría."""
    def gap(match):
        if match.start() == 0 or match.end() == len(body):
            return ''
        return max(match.group(1), match.group(2), key=len)
    return re.sub(r'((?:\r?\n)*)[ \t]*' + re.escape(token) + r'[ \t]*((?:\r?\n)*)', gap, body)

# Textos que YouTube mete en el HttpError cuando publishAt no está permitido.
_SCHEDULE_MARKERS = ('publishat', 'unaudited', 'scheduling')


def next_slot(now, slots):
    """Próximo datetime local estrictamente posterior a ``now``.

    Args:
        now: hora local (naive o con tz). La comparación usa esa misma referencia.
        slots: lista de ``{weekday, hour, minute}``. weekday 0 = lunes.

    Returns:
        datetime con la misma tzinfo que ``now`` (o naive), segundos en cero.

    Raises:
        ValueError: slots vacíos o weekday fuera de 0..6.
    """
    if not slots:
        raise ValueError('No hay slots de publicación.')
    found = []
    for slot in slots:
        weekday = int(slot['weekday'])
        if weekday < 0 or weekday > 6:
            raise ValueError(f'weekday inválido: {weekday}')
        hour = int(slot['hour'])
        minute = int(slot.get('minute') or 0)
        days = (weekday - now.weekday()) % 7
        candidate = (now + timedelta(days=days)).replace(
            hour=hour, minute=minute, second=0, microsecond=0)
        # El slot de hoy ya pasó (o es este mismo instante): la próxima semana.
        if candidate <= now:
            candidate += timedelta(days=7)
        found.append(candidate)
    return min(found)


def _schedule_rejected(exc):
    """True si el error es de publishAt / programación / cuenta sin auditar."""
    parts = [str(exc)]
    cause = getattr(exc, '__cause__', None)
    if cause is not None:
        parts.append(str(cause))
    blob = ' '.join(parts).lower()
    return any(marker in blob for marker in _SCHEDULE_MARKERS)


def _metadata(channel, pack_name, templates, title=None, desc_vars=None):
    """Título, descripción y tags a partir de las plantillas del canal.

    ``{name}`` es el nombre del pack; ``{link}`` el ``templates['link']`` si lo
    hay (vacío si no). Los tags salen de la config si existen.
    Con ``title`` el título se usa tal cual. Con ``desc_vars`` (dict con ``hook`` y
    ``chapters``) se reemplazan ``{hook}`` y ``{chapters}`` de la plantilla de descripción.
    """
    templates = templates or {}
    group = templates.get('group') or ''
    if not group:
        groups = templates.get('groups') or []
        group = groups[0] if groups else ''
    title = title or channel_templates.render_title(
        channel_templates.get_title_template(templates),
        pack_name,
        channel,
        group,
    )
    raw_tags = templates.get('tags')
    if isinstance(raw_tags, (list, tuple)):
        tags_text = ', '.join(str(t) for t in raw_tags if str(t).strip())
        tags = list(raw_tags)
    else:
        tags_text = raw_tags or ''
        tags = raw_tags
    desc_template = description_template(templates)
    # {link}, {hook} y {chapters} se marcan en la plantilla y se completan después de
    # renderizar: un nombre de kit o un texto de redes con "{hook}" queda literal, y un
    # gancho con llaves no pasa por el formateo.
    values = {}
    if '{link}' in desc_template:
        values['link'] = str(templates.get('link') or '')
    for key in DESC_VARS if desc_vars else ():
        if '{' + key + '}' in desc_template:
            values[key] = str(desc_vars.get(key) or '').strip()
    for key in values:
        desc_template = desc_template.replace('{' + key + '}', _token(key))
    body = description.render(
        desc_template,
        pack_name,
        tags=tags_text,
        socials=templates.get('socials', ''),
        hashtags=templates.get('hashtags', ''),
    )
    # {link} lo toma de templates['link']; sin marcador no se agrega nada.
    for key in DESC_VARS:
        if key in values and not values[key]:
            body = _drop_token(body, _token(key))
    if values:
        # Una sola pasada: un gancho que traiga "{chapters}" no se vuelve a interpretar.
        tokens = {_token(key): value for key, value in values.items()}
        body = re.sub('|'.join(map(re.escape, tokens)), lambda m: tokens[m.group(0)], body)
    return title, body, tags


def _insert(channel, video, title, body, tags, thumbnail, publish_at):
    """Inserta siempre en privado. ``publish_at`` None = sin programación."""
    return youtube.upload(
        channel,
        video,
        title,
        body,
        tags,
        thumbnail,
        privacy='private',
        publish_at=publish_at,
    )


def publish_preview(channel, video, thumbnail, pack_name, slots, templates, *,
                    pack_id, audio_mode, db_path=None, now=None,
                    image_path=None, loops_json=None, tz=None, store=None,
                    video_name=None, tracking_id=None, ref_images=None,
                    title=None, desc_vars=None, seo=None):
    """Sube el preview al próximo slot y registra la corrida.

    Args:
        channel: canal de la app (token en tokens/<canal>.json).
        video: mp4 ya renderizado.
        thumbnail: ruta de miniatura, o None.
        pack_name: valor de ``{name}`` en título y descripción.
        slots: horarios de ``next_slot``.
        templates: dict del canal (title_template, description_template, tags, …).
        pack_id: id en kit_packs. Obligatorio para no subir sin poder registrar.
        audio_mode: ``assembled`` (loops cortados y unidos).
        db_path: library.db alternativo (smokes).
        now: reloj inyectable; default datetime.now().
        image_path, loops_json: se guardan en kit_runs.
        tz: zona para datetimes naive al armar publishAt.
        store: módulo con ``record_run`` (default ``kit_store``).
        video_name, tracking_id, ref_images: se guardan en la corrida si vienen (estado en
            la nube). ``ref_images`` son las referencias usadas para el fondo con IA.
        title: título ya armado (``kit_seo``); sin él sale de la plantilla del canal.
        desc_vars: ``{hook, chapters}`` para los marcadores de la descripción; si la
            plantilla no trae el marcador no se agrega nada.
        seo: variante de título del video (artista, etiquetas, frase); se guarda en la corrida.

    Returns:
        dict con estado (``scheduled`` o ``private_pending``), slot local,
        publish_at (ISO o None), youtube_id, url, title y run_id.

    Raises:
        youtube.YouTubeError: cualquier fallo que no sea de programación,
            y también el segundo intento si el reintento privado falla.
            En ese caso no se llama a record_run.
    """
    when = now if now is not None else datetime.now()
    slot = next_slot(when, slots)
    publish_iso = local_to_youtube_publish_at(True, slot, tz=tz)
    title, body, tags = _metadata(channel, pack_name, templates, title, desc_vars)

    estado = 'scheduled'
    try:
        uploaded = _insert(channel, video, title, body, tags, thumbnail, publish_iso)
    except youtube.YouTubeError as exc:
        if not _schedule_rejected(exc):
            raise
        # publishAt rechazado: mismo archivo, privado, sin fecha.
        uploaded = _insert(channel, video, title, body, tags, thumbnail, None)
        estado = 'private_pending'
        publish_iso = None

    extra = {k: v for k, v in (('video_name', video_name), ('tracking_id', tracking_id),
                               ('ref_images', ref_images), ('seo', seo)) if v}
    run_id = (store or kit_store).record_run(
        pack_id,
        db_path=db_path,
        canal=channel,
        audio_mode=audio_mode,
        loops_json=loops_json,
        image_path=image_path,
        video_path=video,
        youtube_id=uploaded.get('youtube_id'),
        url=uploaded.get('url'),
        publish_at=publish_iso,
        estado=estado,
        **extra,
    )
    return {
        'estado': estado,
        'slot': slot,
        'publish_at': publish_iso,
        'youtube_id': uploaded.get('youtube_id'),
        'url': uploaded.get('url'),
        'privacy': uploaded.get('privacy'),
        'title': title,
        'run_id': run_id,
        'thumbnail_error': uploaded.get('thumbnail_error') or '',
    }
