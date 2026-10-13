"""Phase 4 only: reserved job -> temporary video/thumbnail; never uploads."""
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
from core.beat_http import BeatError
from core.beat_schema import migrate
from core.beat_state import BeatState
from core.beat_preview import PreviewResolver
from core.beat_download import acquire_audio
from core.beat_render import MediaTools, compose
from core.beat_visual import options, image_resource, video_catalog, fetch, thumbnail_resource
from core.beat_montage import render_montage, thumbnail_frame
from core.beat_rotation import image_digest, previous_publication, publication_visual


def reserved_job(state, job_id, track, channel):
    if channel.get('active') is False:
        raise BeatError('channel_paused')
    state = migrate(state, 'state')
    job = state['jobs'].get(job_id)
    if (not job or job['status'] not in ('planned', 'failed')
            or job['track_id'] != track.get('id') or job['channel'] != channel.get('id')):
        raise BeatError('reserved_job_required')
    return state, job


@contextmanager
def render_reserved(cloud, job_id, track, channel, genre, profile_url, dropbox,
                    *, dry_run=False, resolver=None, http=None, tools=None):
    """Consume artifacts INSIDE the context. Cleanup also on caller failure.

    Dry-run reads reservation + selected visual catalog; no downloads or writes.
    Successful rendering commits image selection under a fenced Beats lease.
    """
    store = BeatState(cloud)
    owner = None
    try:
        if not dry_run:
            owner = store.acquire(ttl=3600, require_existing=True)
        state, _ = cloud.read('state')
        state, job = reserved_job(state, job_id, track, channel)
        spec = options(channel)
        image = image_resource(channel, genre, state, job, dropbox) if spec['mode'] == 'image' else None
        videos = video_catalog(spec, dropbox) if spec['mode'] == 'video' else []
        custom_thumbnail = thumbnail_resource(spec)
        if dry_run:
            yield {'dry_run': True, 'job_id': job_id, 'image': image['path'] if image else None,
                   'visual_mode': spec['mode'], 'video_resources': len(videos),
                   'audio_policy': 'public_hls_then_explicit_dropbox', 'uploads': False}
            return
        with TemporaryDirectory(prefix='type-beat-') as folder:
            root = Path(folder)
            audio, source_image = root / 'audio.bin', root / 'image.bin'
            frame, thumbnail, video = root / 'frame.png', root / 'thumbnail.jpg', root / 'video.mp4'
            expected, provider = acquire_audio(track, state, profile_url, audio,
                resolver or PreviewResolver(), dropbox, http)
            tools = tools or MediaTools()
            seconds = tools.verify_audio(audio, expected)
            montage = {}
            if image:
                fetch(image, source_image, 20 * 1024 * 1024, dropbox)
                compose(source_image, track.get('title'), frame, thumbnail)
                image['sha256'] = image_digest(source_image)
                prior = previous_publication(state, job)
                prior_visual = publication_visual(state, prior) if prior else None
                if prior_visual and prior_visual.get('sha256') == image['sha256']:
                    raise BeatError('repeat_image_unchanged')
                if job.get('visual_snapshot', {}).get('sha256') not in (None, image['sha256']):
                    raise BeatError('reserved_image_changed')
                tools.render(audio, frame, video, seconds)
            else:
                montage = render_montage(audio, video, seconds, videos, spec, root, dropbox, tools, job_id,
                                         checkpoint=lambda: store.renew(owner, ttl=3600))
                if not custom_thumbnail:
                    thumbnail_frame(montage['first_clip'], source_image, tools)
                    compose(source_image, track.get('title'), frame, thumbnail)
            if custom_thumbnail:
                fetch(custom_thumbnail, root / 'thumbnail-source.bin', 20 * 1024 * 1024, dropbox)
                compose(root / 'thumbnail-source.bin', track.get('title'), root / 'thumbnail-frame.png', thumbnail)

            def record(document):
                store._lease(document, owner)
                _, current = reserved_job(document, job_id, track, channel)
                committed = dict(job, visual_snapshot=dict(image)) if image else job
                if current != job and current != committed:
                    raise BeatError('reservation_changed')
                if image:
                    document['jobs'][job_id]['visual_snapshot'] = dict(image)
                if image and image.get('source', 'dropbox') == 'dropbox':
                    rows = document.setdefault('image_rotation', {}).setdefault(channel['id'], {}).setdefault(genre, [])
                    if not any(row['job_id'] == job_id for row in rows):
                        rows.append({'job_id': job_id, 'path': image['path'], 'rev': image['rev']})
                        del rows[:-5000]
            cloud.update('state', record, guard=lambda doc: store._lease(doc, owner))
            yield {'dry_run': False, 'job_id': job_id, 'video': video,
                   'before_upload': lambda: store.renew(owner, ttl=3600),
                   'thumbnail': thumbnail, 'seconds': seconds, 'audio_source': provider,
                   'visual_mode': spec['mode'], 'skipped_videos': montage.get('skipped_videos', 0),
                   'uploads': False}
    finally:
        if owner is not None:
            original_error = sys.exc_info()[1]
            try:
                store.release(owner)
            except Exception:
                if original_error is None:
                    raise
                if hasattr(original_error, 'add_note'):
                    original_error.add_note('lease_release_failed')
