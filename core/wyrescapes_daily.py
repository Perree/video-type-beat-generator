# -*- coding: utf-8 -*-
"""WyreScapes Fase 4: flujo diario en dos pasos (prepare → metadata escrita por Claude → publish).

``prepare(day)`` deja la carpeta ``Videos/<AAAA-MM-DD>/`` con:
  - ``wyrescapes_<AAAAMMDD>.mp4`` y su ``.json`` (imagen, tracks, segundos) — Fases 1 y 2;
  - ``imagen.txt`` con la ruta absoluta de la imagen (para mirarla);
  - ``info.json`` (minutos reales, títulos ya usados, tags base);
  - ``metadata.json`` por llenar: title, description, tags (base precargados), pinned_comment.
Si el video del día ya existe, no se vuelve a renderizar.

``publish(day)`` valida ``metadata.json`` y sube programado a las 12:00 AR de ese mismo día
(Fase 3). Si ya pasó la hora (PC apagada a la mañana), sube igual y publica ~15 min después.
Si el día ya se subió, no hace nada; si la subida falla, la próxima corrida reintenta.

``status(day)`` dice en qué quedó el día sin renderizar nada (la tarea corre cada hora).
``record_missed_days(today)`` anota en el registro los días sin video (PC apagada todo el día):
nunca se recuperan, así no se suben dos videos el mismo día.
"""
import json
import os
import re
from datetime import date, datetime, timedelta, timezone

from core import image_rotation, mixtape
from core import wyrescapes_upload as wu
from core.mixtape_render import render, track_durations

BASE = os.path.join(os.path.expanduser('~'), 'Desktop', 'WyreScapes')
TAGS_MAX_CHARS = 500
TITLE_MAX_CHARS = 100
# Subido a mano el 2026-11-21 (no está en el registro de la API).
MANUAL_TITLES = ('someone is still beside you.',)
BASE_TAGS = ['sleep music', 'calm music', 'ambient music', 'relaxing music', 'music for sleep',
             'night music', 'deep sleep', "can't sleep", 'insomnia music', 'late night music',
             '3am music', 'calm your mind', 'overthinking', 'peaceful music', 'chill ambient',
             'dark ambient', 'ambient mixtape', 'mixtape', 'beach at night', 'ocean ambience',
             'music to rest', 'WyreScapes']
BANNED_WORDS = ('nowayout', 'no way out')  # nunca nombres de otros canales
LATE_LEAD = timedelta(minutes=15)  # pasadas las 12:00: tiempo para que YouTube procese
MISSED_LOOKBACK_DAYS = 30
_VIDEO_DAY = re.compile(r'^wyrescapes_(\d{8})\.mp4$')


class DailyError(RuntimeError):
    pass


def day_dir(day, base=BASE):
    return os.path.join(base, 'Videos', day.isoformat())


def video_path(day, base=BASE):
    return os.path.join(day_dir(day, base), f'wyrescapes_{day:%Y%m%d}.mp4')


def used_titles(log):
    titles = [str(e.get('title') or '') for e in log] + list(MANUAL_TITLES)
    return {t.strip().lower() for t in titles if t.strip()}


def tags_length(tags):
    """Largo como lo cuenta YouTube: separados por coma, con comillas si tienen espacios."""
    return sum(len(t) + (2 if ' ' in t else 0) for t in tags) + max(len(tags) - 1, 0)


def validate_metadata(meta, log=()):
    """Chequea las reglas del canal y devuelve la metadata normalizada (Fase 3)."""
    if not isinstance(meta, dict):
        raise DailyError('metadata.json tiene que ser un objeto JSON')
    title = str(meta.get('title') or '').strip()
    problems = []
    if not title:
        problems.append('falta el título')
    else:
        if len(title) > TITLE_MAX_CHARS:
            problems.append(f'título de {len(title)} caracteres (máx. {TITLE_MAX_CHARS})')
        if title != title.lower():
            problems.append('el título va en minúscula')
        if not title.endswith('.'):
            problems.append('el título termina con punto')
        if title.lower() in used_titles(log):
            problems.append(f'título ya usado: «{title}»')
    if not str(meta.get('description') or '').strip():
        problems.append('falta la descripción')
    tags = meta.get('tags') or []
    if not isinstance(tags, list):
        problems.append('tags tiene que ser una lista')
        tags = []
    tags = [str(t).strip() for t in tags if str(t).strip()]
    if not tags:
        problems.append('faltan los tags')
    if tags_length(tags) > TAGS_MAX_CHARS:
        problems.append(f'tags de {tags_length(tags)} caracteres (máx. {TAGS_MAX_CHARS})')
    text = ' '.join([title, str(meta.get('description') or ''), ' '.join(tags),
                     str(meta.get('pinned_comment') or '')]).lower()
    for word in BANNED_WORDS:
        if word in text:
            problems.append(f'no nombrar otros canales («{word}»)')
    if not str(meta.get('pinned_comment') or '').strip():
        problems.append('falta el comentario fijado')
    if problems:
        raise DailyError('metadata.json inválido: ' + '; '.join(problems))
    try:
        clean = wu.validate_meta(dict(meta, title=title, tags=tags))
    except wu.UploadError as exc:
        raise DailyError(str(exc)) from exc
    return clean


def slot_for(day, now=None, late_lead=LATE_LEAD):
    """Hora de publicación (AR): las 12:00 de ``day``, o ``ahora + late_lead`` si eso es más tarde.

    Así una PC prendida tarde igual sube el video del día. Raises DailyError si ``day`` ya
    terminó (nunca se publica un día viejo).
    """
    noon = datetime(day.year, day.month, day.day, wu.PUBLISH_HOUR, tzinfo=wu.ARGENTINA)
    now = (now or datetime.now(timezone.utc)).astimezone(wu.ARGENTINA)
    if now.date() > day:
        raise DailyError(f'El {day.isoformat()} ya pasó: no se sube un día viejo.')
    late = (now + late_lead).replace(second=0, microsecond=0) + timedelta(minutes=1)
    return max(noon, late)


def published_entry(day, log, base=BASE):
    return wu.already_uploaded(video_path(day, base), log)


def _entry_day(entry):
    if entry.get('day'):
        return date.fromisoformat(entry['day'])
    match = _VIDEO_DAY.match(str(entry.get('video') or ''))
    return datetime.strptime(match.group(1), '%Y%m%d').date() if match else None


def missed_days(today, log, lookback=MISSED_LOOKBACK_DAYS):
    """Días entre el último subido y ayer sin video ni marca de perdido (más viejo primero)."""
    uploaded = {_entry_day(e) for e in log if e.get('youtube_id')}
    noted = {_entry_day(e) for e in log if e.get('missed')}
    uploaded.discard(None)
    if not uploaded:
        return []
    start = max(max(uploaded) + timedelta(days=1), today - timedelta(days=lookback))
    out, day = [], start
    while day < today:
        if day not in uploaded and day not in noted:
            out.append(day)
        day += timedelta(days=1)
    return out


def record_missed_days(today, log_path=wu.DEFAULT_LOG_PATH):
    """Anota los días perdidos en el registro (sin duplicar). Devuelve la lista anotada."""
    days = missed_days(today, wu.load_log(log_path))
    for day in days:
        wu.append_log({'day': day.isoformat(), 'missed': True,
                       'reason': 'sin video ese día (PC apagada); no se recupera',
                       'noted_at': datetime.now(wu.ARGENTINA).isoformat(timespec='seconds')},
                      log_path)
    return days


def _metadata_filled(path):
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        return False
    return isinstance(meta, dict) and bool(str(meta.get('title') or '').strip()) and         bool(str(meta.get('description') or '').strip())


def status(day, base=BASE, log_path=wu.DEFAULT_LOG_PATH):
    """``{'state': 'uploaded'|'prepared'|'rendered'|'pending', ...}`` sin tocar nada.

    uploaded: ya subido (terminar). prepared: video + metadata escrita (solo publish).
    rendered: video sin metadata (escribirla, sin re-renderizar). pending: falta prepare.
    """
    entry = published_entry(day, wu.load_log(log_path), base)
    out = {'day': day.isoformat(), 'video': video_path(day, base),
           'metadata': os.path.join(day_dir(day, base), 'metadata.json')}
    if entry:
        return dict(out, state='uploaded', url=entry.get('url'),
                    publish_at=entry.get('publish_at'))
    if not os.path.isfile(out['video']):
        return dict(out, state='pending')
    return dict(out, state='prepared' if _metadata_filled(out['metadata']) else 'rendered')


def _write_json(path, data):
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def empty_metadata():
    return {'title': '', 'description': '', 'tags': list(BASE_TAGS), 'pinned_comment': ''}


def prepare(day, base=BASE, track_state=mixtape.DEFAULT_STATE_PATH,
            image_state=image_rotation.DEFAULT_STATE_PATH, log_path=wu.DEFAULT_LOG_PATH,
            renderer=render, probe=None, can_open=image_rotation.ffmpeg_can_open,
            record=True, rng=None):
    """Arma la carpeta del día. Devuelve ``info`` (dict). Idempotente si el video ya existe."""
    folder = day_dir(day, base)
    out = video_path(day, base)
    previous = published_entry(day, wu.load_log(log_path), base)
    if previous:
        raise DailyError(f'El video del {day.isoformat()} ya se subió: {previous.get("url")}')
    sidecar = os.path.splitext(out)[0] + '.json'
    warnings = []
    if os.path.isfile(out) and os.path.isfile(sidecar):
        with open(sidecar, 'r', encoding='utf-8') as fh:
            rendered = json.load(fh)
        image, seconds, reused = rendered['image'], float(rendered['seconds']), True
    else:
        paths = mixtape.scan_tracks(os.path.join(base, 'Tracks'))
        durations = track_durations(paths, probe) if probe else track_durations(paths)
        tstate = mixtape.load_state(track_state)
        order = mixtape.plan_mixtape(list(durations), durations, tstate, rng=rng)
        if not order:
            raise DailyError('No hay tracks legibles en Tracks/')
        image, istate, warnings = image_rotation.pick_image(
            image_rotation.scan_images(os.path.join(base, 'Imagenes')),
            image_rotation.load_state(image_state), rng=rng, can_open=can_open)
        if not image:
            raise DailyError('No hay imágenes utilizables en Imagenes/')
        seconds = sum(durations[n] for n in order)
        os.makedirs(folder, exist_ok=True)
        by_name = {os.path.basename(p): p for p in paths}
        renderer([by_name[n] for n in order], image, out, seconds)
        image = os.path.abspath(image)
        _write_json(sidecar, {'image': image, 'tracks': order, 'seconds': round(seconds, 3)})
        if record:
            mixtape.save_state(mixtape.record_use(tstate, order), track_state)
            image_rotation.save_state(istate, image_state)
        reused = False
    with open(os.path.join(folder, 'imagen.txt'), 'w', encoding='utf-8') as fh:
        fh.write(image + '\n')
    meta_path = os.path.join(folder, 'metadata.json')
    if not os.path.isfile(meta_path):
        _write_json(meta_path, empty_metadata())
    info = {'day': day.isoformat(), 'video': out, 'image': image,
            'seconds': round(seconds, 3), 'minutes': int(round(seconds / 60)),
            'metadata': meta_path, 'used_titles': sorted(used_titles(wu.load_log(log_path))),
            'base_tags': BASE_TAGS, 'spotify': wu.SPOTIFY_URL, 'reused_render': reused,
            'warnings': warnings}
    _write_json(os.path.join(folder, 'info.json'), info)
    return info


def publish(day, base=BASE, log_path=wu.DEFAULT_LOG_PATH, dry_run=False, now=None,
            upload=wu.upload_scheduled):
    """Sube el video del día a las 12:00 AR. Devuelve ``(estado, detalle)``.

    estado: 'already' (ya subido, no hace nada), 'dry-run' (validado, sin subir) o 'uploaded'.
    Raises DailyError si falta algo, la metadata no valida o ``day`` ya terminó.
    """
    log = wu.load_log(log_path)
    previous = published_entry(day, log, base)
    if previous:
        return 'already', previous
    slot = slot_for(day, now)
    out = video_path(day, base)
    if not os.path.isfile(out):
        raise DailyError(f'No está el video del día: {out} (correr prepare)')
    meta_path = os.path.join(day_dir(day, base), 'metadata.json')
    try:
        with open(meta_path, 'r', encoding='utf-8') as fh:
            raw = json.load(fh)
    except (OSError, ValueError) as exc:
        raise DailyError(f'No se pudo leer {meta_path}: {exc}') from exc
    meta = validate_metadata(raw, log)
    with open(os.path.splitext(out)[0] + '.json', 'r', encoding='utf-8') as fh:
        image = json.load(fh).get('image')
    if dry_run:
        return 'dry-run', {'video': out, 'image': image, 'slot': slot.isoformat(),
                           'publish_at': wu.publish_at_utc(slot), **meta}
    try:
        entry = upload(out, meta, image, slot, log_path=log_path)
    except wu.UploadError as exc:
        raise DailyError(str(exc)) from exc
    _write_json(os.path.join(day_dir(day, base), 'published.json'), entry)
    return 'uploaded', entry


def parse_day(text=None):
    return date.fromisoformat(text) if text else date.today()


__all__ = ['DailyError', 'prepare', 'publish', 'status', 'record_missed_days', 'missed_days',
           'validate_metadata', 'slot_for', 'tags_length', 'BASE_TAGS', 'parse_day', 'day_dir',
           'video_path']
