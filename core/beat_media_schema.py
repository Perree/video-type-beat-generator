"""Optional Phase 4 state fields, validated without changing schema version."""
import re
from core.beat_download import dropbox_path, duration


def validate_media_state(state):
    associations = state.get('audio_associations', {})
    rotation = state.get('image_rotation', {})
    if not isinstance(associations, dict) or len(associations) > 10000 or not isinstance(rotation, dict):
        raise ValueError('invalid_media_state')
    for tid, row in associations.items():
        if (not isinstance(tid, str) or not re.fullmatch(r'TK[0-9]{1,20}', tid)
                or not isinstance(row, dict) or row.get('track_id') != tid):
            raise ValueError('invalid_audio_association')
        dropbox_path(row.get('path'))
        duration(row.get('duration'))
    if len(rotation) > 100:
        raise ValueError('invalid_image_rotation')
    for channel, genres in rotation.items():
        if not isinstance(channel, str) or not channel or not isinstance(genres, dict) or len(genres) > 40:
            raise ValueError('invalid_image_rotation')
        for genre, rows in genres.items():
            if not isinstance(genre, str) or not genre or not isinstance(rows, list) or len(rows) > 5000:
                raise ValueError('invalid_image_rotation')
            seen = set()
            for row in rows:
                if (not isinstance(row, dict) or row.get('job_id') not in state['jobs']
                        or state['jobs'][row['job_id']]['channel'] != channel
                        or row['job_id'] in seen or not isinstance(row.get('rev'), str)):
                    raise ValueError('invalid_image_rotation')
                seen.add(row['job_id'])
                dropbox_path(row.get('path'))
