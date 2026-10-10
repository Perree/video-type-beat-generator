# -*- coding: utf-8 -*-
"""Programa y sube un preview de loop kit.

``next_slot`` elige el próximo horario local. ``publish_preview`` intenta
``videos.insert`` con publishAt; si YouTube lo rechaza (cuenta sin auditoría
o programación no permitida), reintenta el mismo archivo en privado y deja
``estado=private_pending``. El pack se marca usado solo si la subida terminó.
"""
from datetime import datetime, timedelta

from core import channel_templates, description, kit_store, youtube
from core.publish_at import local_to_youtube_publish_at

# weekday: lunes=0 … domingo=6 (datetime.weekday).
DEFAULT_SLOTS = (
    {'weekday': 0, 'hour': 18, 'minute': 0},
    {'weekday': 2, 'hour': 18, 'minute': 0},
    {'weekday': 4, 'hour': 18, 'minute': 0},
)

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


def _metadata(channel, pack_name, templates):
    """Título, descripción y tags a partir de las plantillas del canal.

    ``{name}`` es el nombre del pack; ``{link}`` el ``templates['link']`` si lo
    hay (vacío si no). Los tags salen de la config si existen.
    """
    templates = templates or {}
    group = templates.get('group') or ''
    if not group:
        groups = templates.get('groups') or []
        group = groups[0] if groups else ''
    title = channel_templates.render_title(
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
    desc_template = templates.get('description_template') or description.DEFAULT_TEMPLATE
    body = description.render(
        desc_template,
        pack_name,
        tags=tags_text,
        socials=templates.get('socials', ''),
        hashtags=templates.get('hashtags', ''),
    )
    # {link} lo toma de templates['link']; sin marcador no se agrega nada.
    # Se mira la plantilla, no el cuerpo: un nombre con "{link}" no cuenta.
    if '{link}' in desc_template:
        body = body.replace('{link}', str(templates.get('link') or ''))
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
                    video_name=None, tracking_id=None, ref_images=None):
    """Sube el preview al próximo slot y registra la corrida.

    Args:
        channel: canal de la app (token en tokens/<canal>.json).
        video: mp4 ya renderizado.
        thumbnail: ruta de miniatura, o None.
        pack_name: valor de ``{name}`` en título y descripción.
        slots: horarios de ``next_slot``.
        templates: dict del canal (title_template, description_template, tags, …).
        pack_id: id en kit_packs. Obligatorio para no subir sin poder registrar.
        audio_mode: ``named_preview`` o ``assembled``.
        db_path: library.db alternativo (smokes).
        now: reloj inyectable; default datetime.now().
        image_path, loops_json: se guardan en kit_runs.
        tz: zona para datetimes naive al armar publishAt.
        store: módulo con ``record_run`` (default ``kit_store``).
        video_name, tracking_id, ref_images: se guardan en la corrida si vienen (estado en
            la nube). ``ref_images`` son las referencias usadas para el fondo con IA.

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
    title, body, tags = _metadata(channel, pack_name, templates)

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
                               ('ref_images', ref_images)) if v}
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
