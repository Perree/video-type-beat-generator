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
from core.beat_video import render_reserved
from core.beat_publish import publish
from core.beat_notify import COUNTERS
from core.beat_visual import options
from core.beat_guard import ChannelPaused, PublicationExpired


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
              clock=lambda: datetime.now(timezone.utc)):
    summary = dict.fromkeys(COUNTERS, 0)
    summary['dry_run'] = dry_run
    if private_pilot:
        summary['private_pilot'] = True
    try:
        config, rev = cloud.read('config')
        if rev is None:
            raise ValueError('beat_config_missing')
        channel = next(ch for ch in config['channels'] if ch['id'] == channel_id)
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
        payload = None
        if report_loader is not None:
            try:
                payload = report_loader()
            except Exception:
                pass
        reports = {channel_id: payload}
        # Each matrix runner owns only its channel's report/credentials. Let
        # other runners reserve their own buffers with their own metrics.
        planning_config = dict(config, channels=[channel])
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
                additions = store.fill_buffer(planning_config, tracks.values(), owner, seed=seed, reports=reports)
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
                continue
            if instant(job['slot']) > now + timedelta(days=14):
                continue
            summary['eligible'] += 1
            if remaining <= 0:
                summary['budget'] += 1
                continue
            try:
                track = tracks[job['track_id']]
                genre = visual_genre(channel, track)
                seo = prepare_seo(cloud, job['id'], track, channel, clock().isoformat(),
                                  report_loader=lambda: payload, dry_run=dry_run)
                with renderer(cloud, job['id'], track, channel, genre,
                              config.get('beatstars_profile_url'), assets, dry_run=dry_run) as media:
                    if dry_run:
                        remaining -= 1
                        continue
                    # The global CAS reservation is authoritative across the matrix.
                    outcome = publish(cloud, job, media, seo, uploader, receipts, clock,
                                      thumbnailer=thumbnailer, private_pilot=private_pilot)
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
            except PublicationExpired:
                summary['expired'] += 1
            except Exception:
                summary['failed'] += 1
    except Exception:
        summary['failed'] += 1
    finally:
        # Dry-run has NO Telegram sends either. Notifications never affect receipts.
        if notify is not None and not dry_run:
            try:
                notify(summary)
            except Exception:
                summary['failed'] += 1
    return summary
