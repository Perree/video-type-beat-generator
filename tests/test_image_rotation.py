"""WyreScapes Fase 2: rotación de imágenes con archivos sintéticos."""
import os
import random
import shutil
import subprocess

import pytest

from core import image_rotation as rot
from core.ffmpeg_util import resolve_tool
from core.mixtape_render import HEIGHT, WIDTH, build_command

ALWAYS = lambda path: True  # noqa: E731


def _folder(tmp_path, names):
    for name in names:
        (tmp_path / name).write_bytes(b'x')
    return [str(tmp_path / n) for n in sorted(names)]


def _names(paths):
    return [os.path.basename(p) for p in paths]


def test_scan_excludes_refes_gif_and_other_files(tmp_path):
    _folder(tmp_path, ['a.jpg', 'b.JPEG', 'c.png', 'd.jfif', 'e.webp', 'nowayout_16x9_01.jpg',
                       'descargar (1).jfif', 'anim.gif', 'notes.txt', 'track.wav'])
    refes = tmp_path / 'Refes'
    refes.mkdir()
    (refes / 'nowayout_ref_1.jpg').write_bytes(b'x')
    (tmp_path / 'carpeta.jpg').mkdir()
    names = _names(rot.scan_images(str(tmp_path)))
    assert names == ['a.jpg', 'b.JPEG', 'c.png', 'd.jfif', 'descargar (1).jfif', 'e.webp',
                     'nowayout_16x9_01.jpg']
    assert 'nowayout_ref_1.jpg' not in names


def test_scan_missing_folder():
    assert rot.scan_images('no/existe/aca') == []


def test_no_repeats_within_a_cycle(tmp_path):
    paths = _folder(tmp_path, [f'img{i}.jpg' for i in range(7)])
    for seed in range(20):
        state, seen = rot.empty_state(), []
        rng = random.Random(seed)
        for _ in range(7):
            path, state, _ = rot.pick_image(paths, state, rng, can_open=ALWAYS)
            seen.append(os.path.basename(path))
        assert sorted(seen) == sorted(_names(paths))
        assert state['cycles'] == 1


def test_new_cycle_does_not_start_with_last_image(tmp_path):
    paths = _folder(tmp_path, [f'img{i}.png' for i in range(4)])
    for seed in range(40):
        state, rng, previous = rot.empty_state(), random.Random(seed), None
        for day in range(4 * 6):
            path, state, _ = rot.pick_image(paths, state, rng, can_open=ALWAYS)
            name = os.path.basename(path)
            assert name != previous
            previous = name
            if day % 4 == 3:  # fin de cada vuelta: se usaron todas
                assert len(state['cycle_used']) == 4
        assert state['cycles'] == 6


def test_two_images_alternate_and_single_image_repeats(tmp_path):
    paths = _folder(tmp_path, ['a.jpg', 'b.jpg'])
    state, picks = rot.empty_state(), []
    for seed in range(10):
        path, state, _ = rot.pick_image(paths, state, random.Random(seed), can_open=ALWAYS)
        picks.append(os.path.basename(path))
    assert all(x != y for x, y in zip(picks, picks[1:]))
    one = paths[:1]
    path, state, _ = rot.pick_image(one, rot.empty_state(), can_open=ALWAYS)
    path2, _, _ = rot.pick_image(one, state, can_open=ALWAYS)
    assert path == path2 == one[0]


def test_low_warning(tmp_path):
    paths = _folder(tmp_path, [f'img{i}.jpg' for i in range(6)])
    state, flags = rot.empty_state(), []
    for seed in range(6):
        _, state, warnings = rot.pick_image(paths, state, random.Random(seed), can_open=ALWAYS)
        flags.append(any('Quedan' in w for w in warnings))
    # después de la 3.ª quedan 3: avisa desde ahí hasta cerrar la vuelta
    assert flags == [False, False, True, True, True, True]


def test_unreadable_images_are_skipped_with_warning(tmp_path):
    paths = _folder(tmp_path, ['bad.jpg', 'good1.jpg', 'good2.jpg'])
    can_open = lambda p: not p.endswith('bad.jpg')  # noqa: E731
    state = rot.empty_state()
    for seed in range(6):
        path, state, warnings = rot.pick_image(paths, state, random.Random(seed),
                                               can_open=can_open)
        assert os.path.basename(path) != 'bad.jpg'
    assert 'bad.jpg' not in state['cycle_used']
    _, _, warnings = rot.pick_image(paths, rot.empty_state(), random.Random(1),
                                    can_open=lambda p: False)
    assert any('ninguna' in w for w in warnings)


def test_new_images_join_and_removed_ones_are_forgotten(tmp_path):
    paths = _folder(tmp_path, ['a.jpg', 'b.jpg'])
    state = {'cycle_used': ['a.jpg', 'gone.jpg'], 'last': 'a.jpg', 'cycles': 1}
    paths += _folder(tmp_path, ['c.jpg'])
    path, state, _ = rot.pick_image(sorted(paths), state, random.Random(0), can_open=ALWAYS)
    assert os.path.basename(path) in ('b.jpg', 'c.jpg')
    assert 'gone.jpg' not in state['cycle_used']


def test_state_roundtrip_and_broken_file(tmp_path):
    path = str(tmp_path / 'sub' / 'img.json')
    state = {'cycle_used': ['a.jpg'], 'last': 'a.jpg', 'cycles': 2}
    rot.save_state(state, path)
    assert rot.load_state(path) == state
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('{roto')
    assert rot.load_state(path) == rot.empty_state()


def test_render_uses_cover_crop_to_fill_1080p():
    cmd = build_command('ffmpeg', ['a.wav'], 'img.jfif', 'out.mp4', 10)
    graph = cmd[cmd.index('-filter_complex') + 1]
    assert f'scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase' in graph
    assert f'crop={WIDTH}:{HEIGHT}' in graph


@pytest.mark.skipif(not resolve_tool('ffmpeg'),
                    reason='ffmpeg no disponible')
def test_ffmpeg_can_open_real_and_fake_images(tmp_path):
    good = tmp_path / 'ok.jfif'
    subprocess.run([resolve_tool('ffmpeg'), '-y', '-loglevel', 'error', '-f', 'lavfi',
                    '-i', 'color=c=blue:s=64x48', '-frames:v', '1', '-f', 'mjpeg', str(good)],
                   check=True, stdin=subprocess.DEVNULL)
    bad = tmp_path / 'roto.jpg'
    bad.write_bytes(b'no es una imagen')
    assert rot.ffmpeg_can_open(str(good))
    assert not rot.ffmpeg_can_open(str(bad))


@pytest.mark.skipif(not resolve_tool('ffmpeg'), reason='ffmpeg no disponible')
def test_cli_dry_run_picks_from_rotation_with_emoji_name_on_cp1252(tmp_path):
    import struct
    import sys
    import wave
    tracks, images = tmp_path / 'Tracks', tmp_path / 'Imagenes'
    tracks.mkdir()
    (images / 'Refes').mkdir(parents=True)
    with wave.open(str(tracks / 'Track_01.wav'), 'wb') as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(8000)
        fh.writeframes(struct.pack('<h', 0) * 8000)
    img = images / '\U0001f30a.jfif'
    subprocess.run([resolve_tool('ffmpeg'), '-y', '-loglevel', 'error', '-f', 'lavfi',
                    '-i', 'color=c=blue:s=64x48', '-frames:v', '1', '-f', 'mjpeg', str(img)],
                   check=True, stdin=subprocess.DEVNULL)
    shutil.copy(img, images / 'Refes' / 'ref.jpg')
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = dict(os.environ, PYTHONIOENCODING='cp1252', PYTHONUTF8='0')
    result = subprocess.run(
        [sys.executable, os.path.join(root, 'scripts', 'wyrescapes_render.py'), '--dry-run',
         '--tracks', str(tracks), '--images', str(images),
         '--state', str(tmp_path / 's.json'), '--image-state', str(tmp_path / 'i.json')],
        capture_output=True, env=env, stdin=subprocess.DEVNULL)
    out = result.stdout.decode('cp1252', errors='replace')
    assert result.returncode == 0, result.stderr.decode('cp1252', errors='replace')
    assert 'Imagen:' in out and '.jfif' in out and 'ref.jpg' not in out
    assert not (tmp_path / 'i.json').exists()  # dry-run no guarda estado
