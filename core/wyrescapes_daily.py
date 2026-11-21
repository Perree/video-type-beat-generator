# -*- coding: utf-8 -*-
"""WyreScapes Fase 4: flujo diario en dos pasos (prepare → metadata escrita por Claude → publish).

``prepare(day)`` deja la carpeta ``Videos/<AAAA-MM-DD>/`` con:
  - ``wyrescapes_<AAAAMMDD>.mp4`` y su ``.json`` (imagen, tracks, segundos) — Fases 1 y 2;
  - ``imagen.txt`` con la ruta absoluta de la imagen (para mirarla);
  - ``info.json`` (minutos reales, títulos ya usados, tags base);
  - ``metadata.json`` por llenar: title, description, tags (base precargados), pinned_comment.
Si el video del día ya existe, no se vuelve a renderizar.

``publish(day)`` valida ``metadata.json`` y sube programado a las 12:00 AR de ese mismo día
(Fase 3). Si ya pasó la hora (con margen), avisa y no sube. Si el día ya se subió, no hace nada.
"""
import json
import os
from datetime import date, datetime, timezone

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


def slot_for(day, now=None, lead=wu.MIN_LEAD):
    """12:00 AR de ``day``. Raises DailyError si ya no hay margen (nunca otro horario)."""
    slot = datetime(day.year, day.month, day.day, wu.PUBLISH_HOUR, tzinfo=wu.ARGENTINA)
    now = (now or datetime.now(timezone.utc)).astimezone(wu.ARGENTINA)
    if slot - now < lead:
        raise DailyError(f'Ya pasaron las {slot:%H:%M} del {day.isoformat()} (con margen de '
                         f'{int(lead.total_seconds() // 60)} min): no se sube para otro horario.')
    return slot


def published_entry(day, log, base=BASE):
    return wu.already_uploaded(video_path(day, base), log)


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
    Raises DailyError si falta algo, la metadata no valida o ya pasó la hora.
    """
    log = wu.load_log(log_path)
    previous = published_entry(day, log, base)
    if previous:
        return 'already', previous
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
    slot = slot_for(day, now)
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


__all__ = ['DailyError', 'prepare', 'publish', 'validate_metadata', 'slot_for', 'tags_length',
           'BASE_TAGS', 'parse_day', 'day_dir', 'video_path']
