"""Daily Type Beats orchestration, independent of Qt and Loopkits."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from core.beat_catalog import BeatCatalog
from core.beat_cloud import BeatCloud
from core.beat_fakes import MemoryDropbox
from core.beat_schema import instant
from core.beat_source import BeatStarsSource
from core.beat_state import BeatState, BudgetExhausted
from core.beat_schedule import plan, apply_plan
from core.beat_seo_store import prepare_seo
from core.beat_seo import beat_url
from core.beat_video import render_reserved
from core.beat_publish import publish
from core.beat_notify import COUNTERS
from core.beat_reasons import classify, note
from core.beat_visual import options
from core.beat_guard import ChannelPaused, PublicationExpired
from core.beat_selection import (eligible_tracks, selection_tags, ensure_selection,
                                 selection_fence, SelectionChanged, TrackNotMatching)
from core.publish_calendar import occupied_days


def calendar_days(calendar, channel_id, clock):
    """Lee el calendario de YouTube del canal y devuelve los días ocupados.

    Parámetros: calendar (callable(channel_id) -> filas de list_channel_calendar);
    channel_id (canal de esta corrida; el token es el suyo); clock (reloj con zona).
    Devuelve: set[datetime.date] de Buenos Aires. Cualquier error se propaga: el
    llamador lo trata como calendario desconocido y no sube nada.
    """
    return occupied_days(calendar(channel_id), clock())


def _note_calendar(summary, exc):
    code = classify(exc)
    note(summary, 'calendar_read_failed' if code.startswith('error_') else code)


def visual_genre(channel, track):
    # Genre folders are channel configuration, not a catalog eligibility rule.
    genres = channel.get('genres', [])
    tags = {tag.casefold() for tag in track.get('tags', [])}
    matches = [genre for genre in genres if genre.casefold() in tags]
    spec = options(channel)
    if spec['mode'] == 'video' or channel.get('images_folder'):
        return matches[0] if matches else (genres[0] if genres else '')
    folders = channel.get('dropbox_images', {})
    available = [genre for genre in genres if folders.get(genre)]
    return next((genre for genre in matches if genre in available), next(iter(available), ''))


def run_daily(cloud, channel_id, assets, uploader, receipts, *, dry_run=False,
              source=None, renderer=render_reserved, report_loader=None,
              notify=None, thumbnailer=None, seed=None, private_pilot=False,
              expected_owner=None, share_links=None, calendar=None,
              clock=lambda: datetime.now(timezone.utc)):
    """Planifica el búfer del canal y sube los trabajos que tocan hoy.

    ``calendar`` es el lector del calendario de YouTube de este canal
    (callable(channel_id) -> filas de ``youtube.list_channel_calendar``). Sin él (dry-run
    y pruebas viejas) no hay días ocupados y no se llama a YouTube. Si la lectura falla
    se suma ``calendar_unavailable`` y la corrida no planifica, no cancela ni sube nada.
    Devuelve el resumen de contadores (``COUNTERS``).
    """
    summary = dict.fromkeys(COUNTERS, 0)
    if dry_run:
        calendar = None
    summary['dry_run'] = dry_run
    if private_pilot:
        summary['private_pilot'] = True
    try:
        config, rev = cloud.read('config')
        if rev is None:
            raise ValueError('beat_config_missing')
        channel = next(ch for ch in config['channels'] if ch['id'] == channel_id)
        if expected_owner is not None and channel.get('youtube_channel_id') != expected_owner:
            raise ValueError('youtube_destination_changed')
        if not channel['active']:
            summary['blocked'] += 1
            return summary
        state, state_rev = cloud.read('state')
        if state_rev is None:
            raise ValueError('beat_state_missing')
        snapshot = (source or BeatStarsSource()).scan(config.get('beatstars_profile_url'))
        with TemporaryDirectory(prefix='beat-catalog-') as folder:
            catalog = BeatCatalog(Path(folder) / 'catalog.sqlite')
            catalog.apply(snapshot)
            tracks = {track['id']: track for track in catalog.tracks(snapshot.member_id)}
        ensure_selection(cloud, channel)
        filtered = bool(selection_tags(channel))
        tracks = {track['id']: track for track in eligible_tracks(channel, tracks.values())}
        if filtered and not tracks:
            summary['blocked'] += 1
            summary['no_matching_tracks'] += 1
            return summary
        payload = None
        if report_loader is not None:
            try:
                payload = report_loader()
            except Exception:
                pass
        reports = {channel_id: payload}
        taken = set()
        if calendar is not None:
            try:
                taken = calendar_days(calendar, channel_id, clock)
            except Exception as exc:
                # Calendario desconocido: un fallo de lectura nunca cancela trabajos.
                summary['calendar_unavailable'] += 1
                _note_calendar(summary, exc)
                return summary
        # Each matrix runner owns only its channel's report/credentials. Let
        # other runners reserve their own buffers with their own metrics.
        planning_config = dict(config, channels=[channel])
        selection_cloud = cloud
        ensure_selection(selection_cloud, channel)
        if dry_run:
            additions = plan(planning_config, state, tracks.values(), clock(), seed=seed, reports=reports)
            apply_plan(state, additions)
            # All downstream consumers see the proposed jobs; no real writes.
            cloud = BeatCloud(MemoryDropbox(), sleep=lambda _: None)
            cloud.write('state', state, None)
        else:
            store = BeatState(cloud, clock)
            owner = store.acquire(require_existing=True)
            try:
                ensure_selection(selection_cloud, channel)
                store.cancel_occupied(channel_id, taken, owner)
                additions = store.fill_buffer(planning_config, tracks.values(), owner, seed=seed, reports=reports,
                    before_commit=lambda: ensure_selection(selection_cloud, channel),
                    occupied_days=taken)
            finally:
                store.release(owner)
            state, _ = cloud.read('state')
        summary['planned'] = len(additions)
        attempted = {entry['job_id'] for entries in state['attempts'].values()
                     for entry in entries.values()}
        remaining = 6 - len(state['attempts'].get(instant(clock()).date().isoformat(), {}))
        budget_day = instant(clock()).date()
        jobs = sorted((deepcopy(job) for job in state['jobs'].values()
                       if job['channel'] == channel_id and job['status'] in ('planned', 'failed')),
                      key=lambda job: job['slot'])
        for job in jobs:
            # One eligible job only, even if persistence fails after the insert.
            if private_pilot and summary['eligible'] >= 1:
                break
            # Buffers created before a filter change may contain unrelated tracks.
            # Keep their ledger untouched, but never render or attempt them.
            if filtered and job['track_id'] not in tracks:
                summary['blocked'] += 1
                continue
            if job['id'] in attempted:
                summary['blocked'] += 1
                continue
            now = instant(clock())
            if now.date() != budget_day:
                latest, _ = cloud.read('state')
                budget_day = now.date()
                remaining = 6 - len(latest['attempts'].get(budget_day.isoformat(), {}))
            if instant(job['slot']) <= now:
                summary['expired'] += 1
                note(summary, 'slot_expired')
                continue
            if instant(job['slot']) > now + timedelta(days=14):
                continue
            if calendar is not None and remaining > 0:
                # Segunda lectura: el trabajo pudo quedar hasta 14 días en el búfer y alguien
                # pudo agendar ese día a mano mientras tanto. Se relee antes de reservar el
                # intento, así un día tomado no gasta cupo ni llega a videos.insert.
                try:
                    taken = calendar_days(calendar, channel_id, clock)
                except Exception as exc:
                    summary['calendar_unavailable'] += 1
                    _note_calendar(summary, exc)
                    break
                day = instant(job['slot']).date()
                if day in taken:
                    try:
                        BeatState(cloud, clock).cancel_occupied(channel_id, {day})
                    except Exception as exc:
                        summary['failed'] += 1
                        note(summary, exc)
                    continue
            summary['eligible'] += 1
            if remaining <= 0:
                summary['budget'] += 1
                continue
            try:
                track = tracks[job['track_id']]
                ensure_selection(selection_cloud, channel)
                genre = visual_genre(channel, track)
                seo = prepare_seo(cloud, job['id'], track, channel, clock().isoformat(),
                                  report_loader=lambda: payload, dry_run=dry_run)
                ensure_selection(selection_cloud, channel)
                with renderer(cloud, job['id'], track, channel, genre,
                              config.get('beatstars_profile_url'), assets, dry_run=dry_run) as media:
                    if dry_run:
                        remaining -= 1
                        continue
                    # The global CAS reservation is authoritative across the matrix.
                    media = dict(media, before_upload=selection_fence(
                        selection_cloud, channel, media.get('before_upload')),
                        selection_guard=lambda: ensure_selection(selection_cloud, channel))
                    selected = seo['selected']
                    link = share_links.get(track['id'], config.get('beatstars_profile_url')) if share_links else None
                    # Short link when BeatStars exposes it; otherwise the beat page URL (always valid).
                    seo = dict(seo, selected=dict(selected, description=selected['description'].replace(
                        '{url}', link or beat_url(track))))
                    outcome = publish(cloud, job, media, seo, uploader, receipts, clock,
                                      thumbnailer=thumbnailer, private_pilot=private_pilot,
                                      expected_owner=channel.get('youtube_channel_id'), selection_track=track,
                                      on_error=lambda exc: note(summary, exc))
                    summary[outcome] += 1
                    if outcome == 'thumbnail_failed':
                        summary['uploaded'] += 1
                    remaining -= 1
            except BudgetExhausted:
                summary['budget'] += 1
                remaining = 0
            except ChannelPaused:
                summary['blocked'] += 1
                break
            except (SelectionChanged, TrackNotMatching):
                summary['blocked'] += 1
                break
            except PublicationExpired:
                summary['expired'] += 1
                note(summary, 'slot_expired')
            except Exception as exc:
                summary['failed'] += 1
                note(summary, exc)
    except SelectionChanged:
        summary['blocked'] += 1
    except Exception as exc:
        summary['failed'] += 1
        note(summary, exc)
    finally:
        # Dry-run has NO Telegram sends either. Notifications never affect receipts.
        if notify is not None and not dry_run:
            try:
                notify(summary)
            except Exception:
                summary['failed'] += 1
    return summary
