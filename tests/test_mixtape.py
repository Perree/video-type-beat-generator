"""WyreScapes Fase 1: selección de tracks y render con audio sintético."""
import os
import random
import shutil
import struct
import wave

import pytest

from core import mixtape
from core.ffmpeg_util import get_media_duration, resolve_tool
from core.mixtape_render import build_command, render, track_durations


def _wav(path, seconds, rate=8000):
    with wave.open(str(path), 'wb') as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(rate)
        fh.writeframes(struct.pack('<h', 0) * int(seconds * rate))


def test_scan_ignores_asd_and_other_files(tmp_path):
    _wav(tmp_path / 'Track_01.wav', 1)
    (tmp_path / 'Track_01.wav.asd').write_bytes(b'x')
    (tmp_path / 'Track_02.MP3').write_bytes(b'x')
    (tmp_path / 'notes.txt').write_text('x')
    (tmp_path / 'sub.wav').mkdir()
    names = [os.path.basename(p) for p in mixtape.scan_tracks(str(tmp_path))]
    assert names == ['Track_01.wav', 'Track_02.MP3']


def test_scan_missing_folder():
    assert mixtape.scan_tracks('no/existe/aca') == []


def test_all_tracks_once_when_under_cap():
    names = [f't{i}.wav' for i in range(8)]
    durations = {n: 230.0 for n in names}
    for seed in range(30):
        order = mixtape.plan_mixtape(names, durations, rng=random.Random(seed))
        assert sorted(order) == sorted(names)
        assert len(order) == len(set(order))


def test_order_differs_from_previous_video():
    names = [f't{i}.wav' for i in range(8)]
    durations = {n: 200.0 for n in names}
    state = mixtape.empty_state()
    previous = None
    for seed in range(40):
        order = mixtape.plan_mixtape(names, durations, state, rng=random.Random(seed))
        assert order != previous
        state = mixtape.record_use(state, order)
        previous = order


def test_two_tracks_alternate_even_with_stubborn_rng():
    class SameRng(random.Random):
        def shuffle(self, x):
            x.sort()
    state = {'last_order': ['a.wav', 'b.wav'], 'counts': {}, 'videos': 1}
    order = mixtape.plan_mixtape(['a.wav', 'b.wav'], {'a.wav': 5, 'b.wav': 5}, state, SameRng())
    assert order == ['b.wav', 'a.wav']


def test_single_track_still_renders():
    state = {'last_order': ['a.wav'], 'counts': {}, 'videos': 1}
    assert mixtape.plan_mixtape(['a.wav'], {'a.wav': 9}, state) == ['a.wav']


def test_cap_picks_subset_of_least_used():
    names = [f't{i}.wav' for i in range(40)]
    durations = {n: 300.0 for n in names}  # 200 min de música
    counts = {n: (0 if i >= 30 else 5) for i, n in enumerate(names)}
    state = {'last_order': [], 'counts': counts, 'videos': 5}
    order = mixtape.plan_mixtape(names, durations, state, random.Random(1), max_seconds=7200)
    assert len(order) == 24 and len(set(order)) == 24
    assert sum(durations[n] for n in order) <= 7200
    assert set(f't{i}.wav' for i in range(30, 40)) <= set(order)


def test_cap_rotation_covers_everything():
    names = [f't{i}.wav' for i in range(30)]
    durations = {n: 600.0 for n in names}  # 12 por video
    state = mixtape.empty_state()
    for seed in range(5):
        order = mixtape.plan_mixtape(names, durations, state, random.Random(seed), 7200)
        state = mixtape.record_use(state, order)
    counts = state['counts']
    assert set(counts) == set(names)
    assert max(counts.values()) - min(counts.values()) <= 1


def test_track_longer_than_cap_goes_alone():
    order = mixtape.plan_mixtape(['big.wav'], {'big.wav': 9000}, max_seconds=7200)
    assert order == ['big.wav']


def test_unreadable_tracks_are_dropped():
    assert mixtape.plan_mixtape(['a.wav', 'b.wav'], {'a.wav': 3}) == ['a.wav']
    assert mixtape.plan_mixtape([], {}) == []


def test_state_round_trip_and_broken_file(tmp_path):
    path = tmp_path / 'state' / 's.json'
    assert mixtape.load_state(str(path)) == mixtape.empty_state()
    state = mixtape.record_use(mixtape.empty_state(), ['a.wav', 'b.wav'])
    mixtape.save_state(state, str(path))
    assert mixtape.load_state(str(path)) == {
        'last_order': ['a.wav', 'b.wav'], 'counts': {'a.wav': 1, 'b.wav': 1}, 'videos': 1}
    path.write_text('{roto', encoding='utf-8')
    assert mixtape.load_state(str(path)) == mixtape.empty_state()


def test_build_command_still_image_and_concat():
    cmd = build_command('ffmpeg', ['a.wav', 'b.mp3'], 'img.jpg', 'out.mp4', 61.5)
    joined = ' '.join(cmd)
    assert '-loop 1 -framerate 1 -i img.jpg' in joined
    assert 'stillimage' in cmd and '1920:1080' in joined
    assert '[a0][a1]concat=n=2:v=0:a=1[aout]' in joined
    assert cmd[cmd.index('-t') + 1] == '61.500'


@pytest.mark.skipif(not resolve_tool('ffmpeg') or not resolve_tool('ffprobe'),
                    reason='sin ffmpeg/ffprobe')
def test_render_real_short(tmp_path):
    ffmpeg = resolve_tool('ffmpeg')
    tracks = []
    for i, secs in enumerate((2.0, 3.0)):
        p = tmp_path / f't{i}.wav'
        _wav(p, secs, rate=22050 if i else 8000)  # formatos distintos
        tracks.append(str(p))
    img = tmp_path / 'img.png'
    import subprocess
    subprocess.run([ffmpeg, '-y', '-loglevel', 'error', '-f', 'lavfi', '-i',
                    'color=c=blue:s=640x480', '-frames:v', '1', str(img)], check=True)
    durations = track_durations(tracks)
    assert durations == pytest.approx({'t0.wav': 2.0, 't1.wav': 3.0}, abs=0.05)
    out = render(tracks, str(img), str(tmp_path / 'v' / 'out.mp4'), sum(durations.values()))
    assert get_media_duration(out) == pytest.approx(5.0, abs=1.1)
