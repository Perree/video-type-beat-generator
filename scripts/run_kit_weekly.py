#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Worker semanal de loop kits: un preview por horario configurado (hasta 3) en privado,
estado en Dropbox, aviso por Telegram.

Corre en GitHub Actions (UTC), por eso los horarios se calculan en hora de Buenos Aires y la
zona se pasa explícita. El repo es público: no se imprime ningún nombre de kit ni mensaje de
error de las librerías, solo el paso que falló y el tipo de excepción.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import os
import random
import sys
import tempfile
import time
import warnings
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
SCRIPTS = os.path.join(ROOT, 'scripts')
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from core import (kit_art, kit_channel, kit_cloud, kit_notify, kit_settings, kit_spend,
                  kit_state, kit_trends)
from core.kit_publish import DEFAULT_SLOTS, next_slot
from core.publish_at import local_to_youtube_publish_at
from core.publish_calendar import next_free_slots, occupied_days, slot_day

CONFIG_DROPBOX_PATH = kit_settings.CONFIG_PATH
TZ_NAME = 'America/Argentina/Buenos_Aires'
SLOTS_PER_WEEK = 3
# Recorrido máximo para buscar días libres: con un cron semanal, 4 semanas sobran.
HORIZON_DAYS = 28
# Pasado este tiempo desde la última lectura, se relee el calendario antes de videos.insert.
CALENDAR_MAX_AGE_S = 20 * 60
_PENDING_STATES = ('scheduled', 'uploaded', 'private_pending')


def local_tz():
    """Zona de los horarios. Buenos Aires no tiene cambio de hora (UTC-3 fijo)."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(TZ_NAME)
    except Exception:
        return timezone(timedelta(hours=-3), TZ_NAME)


def upcoming_slots(now_local, slots, count=SLOTS_PER_WEEK):
    """Próximos ``count`` slots (naive, hora de Buenos Aires) estrictamente posteriores."""
    found, cur = [], now_local
    for _ in range(count):
        cur = next_slot(cur, slots)
        found.append(cur)
    return found


def _iso_day(iso):
    """Día de Buenos Aires de un publishAt guardado (``...Z``), o None si no se entiende."""
    try:
        return slot_day(datetime.fromisoformat(str(iso).replace('Z', '+00:00')))
    except (TypeError, ValueError):
        return None


def free_slots(now_local, slots_cfg, count, youtube_days, taken, tz):
    """Slots de la semana salteando los días ocupados en YouTube por otros videos.

    Parámetros: now_local (naive, hora de ``tz``); slots_cfg (cron del canal); count (tope,
    hasta SLOTS_PER_WEEK); youtube_days (días ocupados según ``occupied_days``); taken
    (``scheduled_packs`` del estado del kit); tz (zona de los horarios).
    Devuelve la lista de slots (naive). Los días de videos que este worker ya registró no
    cuentan como ajenos: ese slot sigue saliendo y la deduplicación por iso lo omite, así
    una segunda corrida de la semana no avanza a otros días ni sube de más.
    """
    own = {day for day in map(_iso_day, taken) if day is not None}
    return next_free_slots(slots_cfg, now_local, set(youtube_days) - own, count,
                           HORIZON_DAYS, tz=tz)


def scheduled_packs(state):
    """``{publish_at: dropbox_path}`` de las corridas ya subidas o programadas."""
    path_by_id = {p['id']: path for path, p in state['packs'].items()}
    return {run['publish_at']: path_by_id.get(run.get('pack_id'))
            for run in state['runs']
            if run.get('publish_at') and run.get('estado') in _PENDING_STATES}


class CloudStore:
    """Interfaz de kit_store sobre kit_state con el cliente de Dropbox ya armado.

    Una subida privada (sin publishAt) queda registrada con el slot propuesto, así una
    segunda corrida de la misma semana la detecta en ``has_scheduled_run`` y no duplica.
    ``now`` (hora local de la corrida) es la fecha de uso que se guarda: el ciclo y la
    separación entre usos se cuentan en la misma zona que los horarios.
    ``state_path`` es el estado de otro canal; sin él, el del canal por defecto.
    """

    def __init__(self, dbx, now=None, state_path=None):
        self.dbx = dbx
        self.now = now
        self.proposed = None
        self.orphan = None  # video subido cuyo registro en el estado falló
        self._kw = {'dbx': dbx, 'db_path': state_path} if state_path else {'dbx': dbx}

    def load(self):
        return kit_state.load(**self._kw)

    def has_scheduled_run(self, publish_at, db_path=None):
        return bool(publish_at) and publish_at in scheduled_packs(self.load())

    def selection_history(self, db_path=None):
        return kit_state.selection_history(**self._kw)

    def upsert_pack(self, dropbox_path, nombre, db_path=None):
        return kit_state.upsert_pack(dropbox_path, nombre, **self._kw)

    def get_cycle(self, dropbox_path):
        return kit_state.get_cycle(dropbox_path, **self._kw)

    def update_cycle(self, dropbox_path, **fields):
        return kit_state.update_cycle(dropbox_path, **self._kw, **fields)

    def ref_usage(self):
        return kit_art.used_refs(self.load())

    def spend_month(self, month):
        return kit_state.get_spend(month, **self._kw)['usd']

    def add_spend(self, month, usd, images=0, verifications=0):
        return kit_state.add_spend(month, usd, **self._kw, images=images,
                                   verifications=verifications)

    def used_video_names(self):
        return [run['video_name'] for run in self.load()['runs'] if run.get('video_name')]

    def record_run(self, pack_id, db_path=None, **fields):
        if not fields.get('publish_at'):
            fields['publish_at'] = self.proposed
        if self.now is not None:
            fields.setdefault('subido_en', self.now.isoformat(timespec='seconds'))
        for attempt in range(3):
            try:
                return kit_state.record_run(pack_id, **self._kw, **fields)
            except Exception:
                if attempt == 2:
                    # El video ya está en YouTube: guardar el id para avisar con su link.
                    self.orphan = fields.get('youtube_id')
                    raise


def _notify(notifier, text):
    try:
        notifier.send(text)
    except Exception as exc:
        print(f"Aviso por Telegram no enviado ({type(exc).__name__}).")


def _with_warnings(text, warnings):
    unique = list(dict.fromkeys(warnings))
    return text if not unique else text + "\nAvisos:\n" + "\n".join(f"- {w}" for w in unique)


def run_weekly(*, app_config, channel, channel_templates, dbx, dry_run=False, now=None,
               seed=None, notifier=kit_notify, output_dir=None, hooks=None, paths=None,
               label=None, calendar_fn=None):
    """Corre la semana y devuelve el código de salida (0 ok, 1 hubo un fallo).

    ``hooks`` son reemplazos para pruebas: ``list_packs_fn``, ``monotonic`` y los de
    ``kit_week.make_video``.
    ``paths`` (``kit_channel.paths``) son el estado y el catálogo del canal; sin él, los del
    canal por defecto. Con ``label`` cada aviso de Telegram empieza con el nombre del canal.
    ``calendar_fn(channel)`` devuelve las filas de ``youtube.list_channel_calendar`` del canal
    que sube esta corrida (con su propio token). Sin él, o en dry-run, no se lee YouTube y
    no hay días ocupados. Si la lectura falla no se sube nada y se avisa por Telegram.
    Un kit que no da un video se saltea y se prueba con el siguiente; que no alcancen los
    kits para todos los horarios es un aviso, no un fallo.
    """
    hooks = dict(hooks or {})
    own = paths is not None and not paths.is_default
    state_kw = {'dbx': dbx, 'db_path': paths.state} if own else {'dbx': dbx}
    if label:
        notifier = kit_channel.Prefixed(notifier, label)
        hooks.setdefault('art_notify', notifier.send)
    tz = local_tz()
    now_local = now or datetime.now(tz).replace(tzinfo=None)
    kit_cfg = app_config.get('kit_preview') or {}
    slots_cfg = kit_cfg.get('slots') or list(DEFAULT_SLOTS)
    # Un video por horario configurado, hasta SLOTS_PER_WEEK: con un solo horario sale uno.
    count = min(len(slots_cfg), SLOTS_PER_WEEK)
    slots, proposed = [], []
    store = CloudStore(dbx, now_local, paths.state if own else None)
    # Tope de gasto de las portadas con IA: uno por corrida, contra el mes del canal.
    budget = kit_spend.Budget(kit_spend.settings(kit_cfg), store, now_local)
    rng = random.Random(seed)

    if dry_run:
        calendar_fn = None
    monotonic = hooks.pop('monotonic', time.monotonic)
    youtube_days = set()
    if calendar_fn is not None:
        # Una lectura al empezar alcanza: esta corrida elige y sube en el mismo proceso.
        # Si un slot se sube mucho después (render largo), se relee antes de su insert.
        try:
            youtube_days = occupied_days(calendar_fn(channel), now_local.replace(tzinfo=tz))
        except Exception as exc:
            # Calendario desconocido: no se toma el lock ni se escribe nada en el estado.
            _notify(notifier, kit_notify.alert(exc, step='calendario'))
            print(f"Fallo en calendario ({kit_notify.error_kind(exc)}).")
            return 1
    read_at = monotonic()
    # Días de los videos subidos en esta corrida: no bloquean otro horario del mismo día.
    uploaded_days = set()

    def before_insert(slot):
        """Relee el calendario si la última lectura es vieja; levanta SlotTaken si el día se ocupó."""
        nonlocal read_at
        if calendar_fn is None or monotonic() - read_at < CALENDAR_MAX_AGE_S:
            return
        days = occupied_days(calendar_fn(channel), now_local.replace(tzinfo=tz))
        read_at = monotonic()
        if slot_day(slot, tz) in days - uploaded_days:
            raise kit_week.SlotTaken()

    owner = None
    if not dry_run:
        try:
            owner = kit_state.acquire_lock(**state_kw)
        except Exception as exc:
            _notify(notifier, kit_notify.alert(exc, step='lock'))
            print(f"Fallo en lock ({type(exc).__name__}).")
            return 1

    videos, warnings, used, failure = [], [], set(), None
    skipped = unfilled = collided = 0
    try:
        try:
            # kit_week trae numpy y Pillow: se importa acá para que un fallo también avise.
            from core import kit_week
            state = store.load()
            taken = scheduled_packs(state)
            slots = free_slots(now_local, slots_cfg, count, youtube_days, taken, tz)
            proposed = [local_to_youtube_publish_at(True, slot, tz=tz) for slot in slots]
            if len(slots) < count:
                warnings.append(f"Solo {len(slots)} de {count} horario(s) libres en YouTube en "
                                f"los próximos {HORIZON_DAYS} días: el resto ya está ocupado.")
            # Los kits de los slots ya subidos esta semana no se vuelven a elegir.
            used.update(path for iso, path in taken.items() if iso in proposed and path)
            week = kit_week.open_week(
                app_config, state, store.selection_history(), now_local, rng, dbx=dbx,
                exclude=sorted(used), list_packs_fn=hooks.get('list_packs_fn'),
                **({'kits_path': paths.kits} if own else {}))
            queue = list(week['queue'])
            warnings += week['warnings']
            if not dry_run and queue and any(iso not in taken for iso in proposed):
                # Ficha de SEO de la semana según el informe de tendencias (Notion), solo para
                # los géneros de los kits de hoy. Nunca levanta: sin informe o sin secretos se
                # sigue con la última buena o con la del panel.
                genres = {str((week['entries'].get(sel['pack']['dropbox_path']) or {})
                              .get('genre') or '') for sel in queue}
                config_path = (paths or kit_channel.default_paths()).config
                kit_cfg, trend_warnings = kit_trends.apply(
                    kit_cfg, dbx=dbx, path=kit_trends.saved_path(config_path), budget=budget,
                    llm_call=hooks.get('trends_llm'), fetch=hooks.get('trends_fetch'),
                    only=genres)
                warnings += trend_warnings
        except (Exception, SystemExit) as exc:
            failure = (exc, 'kits')
            slots = []
        for n, (slot, iso) in enumerate(zip(slots, proposed), 1):
            step = f"preview {n}/{len(slots)}"
            if iso in taken:
                print(f"{step}: ya estaba programado, se omite.")
                continue
            if slot_day(slot, tz) in youtube_days:
                # Día de un video propio con otro horario (cambió el cron): no se duplica.
                collided += 1
                print(f"{step}: el día ya tiene un video en YouTube, se omite.")
                continue
            store.proposed = iso
            done = slot_taken = False
            while queue and not done:
                selection = queue.pop(0)
                path = selection['pack']['dropbox_path']
                if dry_run:
                    used.add(path)
                    done = True
                    break
                try:
                    # Los módulos imprimen avisos con datos del kit; el log de Actions es público.
                    with contextlib.redirect_stdout(io.StringIO()):
                        video = kit_week.make_video(
                            selection, week['entries'].get(path), kit_cfg=kit_cfg,
                            channel=channel, channel_templates=channel_templates,
                            slots_cfg=slots_cfg, slot=slot, now=now_local, state=state,
                            store=store, rng=rng, dbx=dbx, tz=tz,
                            hooks=dict(hooks, before_insert=before_insert), budget=budget,
                            output_dir=output_dir or tempfile.gettempdir())
                except kit_week.KitSkip:
                    skipped += 1
                    continue
                except kit_week.SlotTaken:
                    # El kit no se subió: vuelve primero a la cola para el próximo horario.
                    queue.insert(0, selection)
                    slot_taken = True
                    break
                except (Exception, SystemExit) as exc:
                    failure = (exc, step)
                    if store.orphan:
                        videos.append({'youtube_id': store.orphan, 'slot': slot,
                                       'title': 'subido pero sin registrar en el estado'})
                    break
                used.add(path)
                uploaded_days.add(slot_day(slot, tz))
                warnings += video['warnings']
                if video.get('youtube_id'):
                    videos.append({'youtube_id': video['youtube_id'], 'slot': slot,
                                   'title': video.get('title')})
                done = True
            if failure:
                break
            if done:
                print(f"{step}: ok.")
            elif slot_taken:
                collided += 1
                print(f"{step}: el día se ocupó en YouTube antes de subir, se omite.")
            else:
                unfilled += 1
                print(f"{step}: sin kit disponible.")
    finally:
        if owner:
            try:
                kit_state.release_lock(owner, **state_kw)
            except Exception as exc:
                print(f"No se pudo liberar el lock ({type(exc).__name__}).")

    if budget.broken:
        warnings.append("No se pudo leer o guardar el gasto estimado de portadas: se dejó de "
                        "generar con IA en esta corrida.")
    if skipped:
        warnings.append(f"{skipped} kit(s) no dieron un video (audio insuficiente o error al "
                        "prepararlo).")
    if unfilled:
        warnings.append(f"{unfilled} horario(s) quedaron sin video: no hay más kits disponibles "
                        "(el resto descansa o se usó hace poco).")
    if collided:
        warnings.append(f"{collided} horario(s) se omitieron: el día ya tenía un video en "
                        "YouTube.")
    if failure is None and skipped and not videos and not dry_run:
        failure = ('ningún kit dio un video', 'previews')

    if dry_run and failure is None:
        _notify(notifier, _with_warnings(
            f"Loop kits (dry-run): {len(used)} kit(s) distintos elegidos para "
            f"{len(slots)} slots. No se subió nada.", warnings))
    elif videos or warnings:
        _notify(notifier, _with_warnings(kit_notify.summary(videos), warnings))
    if failure:
        exc, step = failure
        _notify(notifier, kit_notify.alert(exc, step=step))
        print(f"Fallo en {step} ({kit_notify.error_kind(exc)}).")
        return 1
    return 0


@contextlib.contextmanager
def _local_credentials():
    """Corre con los tokens y la config de esta PC (cwd en el repo)."""
    previous = os.getcwd()
    os.chdir(ROOT)
    try:
        yield ROOT
    finally:
        os.chdir(previous)


@contextlib.contextmanager
def _public_log():
    """En la nube el log es público: sin ``stderr`` (warnings y logging de las librerías).

    También registra como máscaras de GitHub los valores sueltos de los secretos JSON.
    """
    if not kit_cloud.in_cloud():
        yield
        return
    if os.environ.get('GITHUB_ACTIONS') == 'true':
        for value in kit_cloud.nested_secrets():
            print(f"::add-mask::{value}")
    warnings.simplefilter('ignore')
    with contextlib.redirect_stderr(io.StringIO()):
        yield


def main(argv=None):
    parser = argparse.ArgumentParser(description='Worker semanal de previews de loop kits.')
    parser.add_argument('--dry-run', action='store_true',
                        help='Elige kits y slots; no renderiza, no sube, no guarda estado.')
    parser.add_argument('--channel', help='Canal loop_kits (obligatorio si hay varios).')
    parser.add_argument('--automation', default=os.environ.get(kit_channel.ENV_AUTOMATION),
                        help='Slug del canal cuya automatización corre (vacío o "default": '
                             'el canal por defecto).')
    parser.add_argument('--config', default=os.path.join(ROOT, 'config', 'app_config.json'))
    parser.add_argument('--cloud-config', action='store_true',
                        help='Lee la config de Dropbox aunque exista la local.')
    parser.add_argument('--seed', type=int)
    args = parser.parse_args(argv)

    label = None
    try:
        paths = kit_channel.paths(args.automation)
        if not paths.is_default:
            # Hasta leer la config, el aviso de un fallo lleva el slug del canal.
            label = paths.slug
        from run_kit_preview import load_app_config, resolve_channel
        # Sin ninguna variable KIT_* de credenciales (PC del usuario) se usan las locales.
        with _public_log(), (kit_cloud.credentials_dir() if kit_cloud.in_cloud()
                             else _local_credentials()):
            dbx = kit_cloud.client()
            if os.path.exists(args.config) and not args.cloud_config and paths.is_default:
                app_config = load_app_config(args.config)
            else:  # en Actions no hay app_config.json (está ignorado por git)
                app_config = kit_cloud.read_json(
                    CONFIG_DROPBOX_PATH if paths.is_default else paths.config, dbx=dbx)
                if not isinstance(app_config, dict):
                    raise kit_cloud.KitCloudError("No hay configuración del worker.")
            default_channel = (app_config.get('kit_preview') or {}).get('channel')
            channel, templates = resolve_channel(app_config, args.channel or default_channel)
            kit_channel.check_owner(
                paths, channel,
                kit_cloud.secret(kit_cloud.ENV_YT_CHANNEL) if kit_cloud.in_cloud() else None)
            label = channel
            calendar_fn = None
            if not args.dry_run:
                # Antes de gastar en portadas: ¿se puede entrar al canal? Es solo lectura
                # (1 unidad de cuota) y, si falla, avisa sin haber generado nada.
                from core import youtube
                youtube.channel_title(channel)
                # Mismo token del canal que sube (KIT_YT_TOKEN_JSON de este Environment).
                calendar_fn = youtube.list_channel_calendar
            with tempfile.TemporaryDirectory(prefix='kit_weekly_') as out:
                return run_weekly(app_config=app_config, channel=channel,
                                  channel_templates=templates, dbx=dbx,
                                  dry_run=args.dry_run, seed=args.seed, output_dir=out,
                                  paths=paths, label=label, calendar_fn=calendar_fn)
    except (Exception, SystemExit) as exc:
        # Sin traceback ni mensaje: el log de Actions es público. Los nombres de las
        # variables que faltan no son secretos.
        _notify(kit_notify, kit_channel.prefixed(label, kit_notify.alert(exc, step='inicio')))
        detail = f": {exc}" if isinstance(exc, kit_cloud.KitCloudEnvError) else ''
        print(f"Fallo al iniciar ({kit_notify.error_kind(exc)}{detail}).")
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
