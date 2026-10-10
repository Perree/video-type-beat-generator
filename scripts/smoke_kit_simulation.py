#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke de integración: 6 semanas del worker semanal con 12 kits falsos (sin red ni ffmpeg).

Corre ``run_kit_weekly.run_weekly`` real sobre un Dropbox en memoria, con dobles de YouTube,
Telegram, LLM, API de imágenes, descarga, corte y render. Verifica las reglas del plan:
3 kits distintos por semana, rotación pareja, ciclo de 3 videos con descanso de 30 días,
duración entre 135 y 195 s, tramos sin repetir dentro del ciclo, nombres y referencias sin
repetir, link del kit con seguimiento y solo kits elegibles del catálogo. Después repasa los
casos borde (kit sin imágenes o sin audio, un único kit, Dropbox caído, estado corrupto,
dos corridas a la vez). No corta en el primer fallo: lista todas las reglas rotas.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
import urllib.parse
import wave
from datetime import datetime, timedelta, timezone

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')
for path in (ROOT, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from smoke_kit_state import FakeDropbox  # también instala el doble de dropbox.files si falta

from core import kit_art, kit_catalog, kit_cycle, kit_names, kit_settings, kit_source, kit_state
from core import youtube
import run_kit_weekly

START = datetime(2026, 10, 4, 20, 0)   # domingo 20:00, hora de Buenos Aires
WEEKS = 6
CHANNEL = 'canal-sim'
KITS_ROOT = '/sim'
REFS_ROOT = '/sim_refs'
GENRES = ('reggaeton house', 'guitarras')
WINDOW = (135.0, 195.0)
MAX_VIDEOS, REST_DAYS, GAP_DAYS = 3, 30, 7
LOOP_SEC = 28.0
REFS_PER_GENRE = 40
FRAME = (320, 180)
TEMPLATES = {'title_template': '{name} | sim', 'link': 'https://example.com/canal',
             'description_template': 'Kit {name}\nLink: {link}\n'}
NAME_POOL = [f'{a} {b}' for a in ('Luna', 'Brisa', 'Fuego', 'Niebla', 'Costa', 'Selva')
             for b in ('Roja', 'Lenta', 'Azul', 'Clara', 'Viva')]

RESULTS = []


def check(name, problems):
    RESULTS.append((name, list(problems)))


class Clock:
    now = START
    week = 0


class Sim:
    uploads = []        # una entrada por video subido
    last_render = {}
    art_prompts = []
    art_warnings = []
    seconds = {}        # duración de cada audio falso, por ruta de Dropbox
    on_upload = None    # gancho de los casos borde


def _reset():
    Sim.uploads, Sim.last_render, Sim.art_prompts, Sim.art_warnings = [], {}, [], []
    Sim.on_upload = None


class DownDropbox(FakeDropbox):
    """Dropbox falso que se puede "caer": toda llamada levanta un error de red."""
    down = False

    def files_download(self, path):
        if self.down:
            raise ConnectionError('dropbox caido (simulado)')
        return super().files_download(path)

    def files_upload(self, data, path, mode=None, mute=False):
        if self.down:
            raise ConnectionError('dropbox caido (simulado)')
        return super().files_upload(data, path, mode=mode, mute=mute)


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send(self, text, photo=None):
        self.sent.append(text)


# --- Kits falsos ---

def _kit(i, work_dir, loops=16, images=True, active=True, link=True, name=None):
    name = name or f'SimKit{i:02d}'
    path = f'{KITS_ROOT}/{name.lower()}'
    loop_recs = [{'name': f'loop{j:02d}.wav', 'path': f'{path}/loop{j:02d}.wav'}
                 for j in range(loops)]
    for rec in loop_recs:
        Sim.seconds[rec['path']] = LOOP_SEC
    image = os.path.join(work_dir, 'manual.png')
    if not os.path.isfile(image):
        Image.new('RGB', (96, 96), (90, 60, 40)).save(image)
    return {
        'pack': {'name': name, 'dropbox_path': path, 'loops': loop_recs,
                 'images': [{'name': 'manual.png', 'path': image, 'source': 'local'}]
                 if images else []},
        'entry': {'folder': name, 'name': f'Sim Producto {i:02d}', 'genre': GENRES[i % 2],
                  'payhip_url': f'https://example.com/b/k{i:02d}?ref=sim' if link else '',
                  'active': active},
    }


def _twelve_kits(work_dir):
    """12 kits elegibles y 2 que el catálogo descarta."""
    kits = [_kit(i, work_dir) for i in range(1, 13)]
    traps = [_kit(13, work_dir, active=False, name='SimTrapInactivo'),
             _kit(14, work_dir, link=False, name='SimTrapSinLink')]
    return kits, traps


def _config():
    return {'kit_preview': {
        'dropbox_root': KITS_ROOT, 'genres': list(GENRES), 'cover_mode': 'auto',
        'art': {'refs_root': REFS_ROOT, 'genre': GENRES[0]},
        'names': {'genre': GENRES[0]},
        'cover': {'template': {'size': 240}, 'frame': {'size': list(FRAME)}},
        'target_min_s': WINDOW[0], 'target_max_s': WINDOW[1], 'cycle_max_videos': MAX_VIDEOS,
        'cycle_rest_days': REST_DAYS, 'kit_min_gap_days': GAP_DAYS, 'kits_per_week': 3}}


def _put_catalog(dbx, kits):
    dbx.files_upload(json.dumps([k['entry'] for k in kits]).encode('utf-8'),
                     kit_settings.KITS_PATH, mode=_Overwrite())


class _Overwrite:
    def is_add(self):
        return False

    def is_update(self):
        return False


# --- Dobles de lo externo ---

def _write_wav(path, seconds):
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(1)
        w.setframerate(1000)
        w.writeframes(b'\x80' * int(round(seconds * 1000)))


def _wav_seconds(path):
    with wave.open(path, 'rb') as w:
        return w.getnframes() / float(w.getframerate())


def _fake_download(paths, dest_dir, dbx=None):
    os.makedirs(dest_dir, exist_ok=True)
    out = []
    for p in paths:
        local = os.path.join(dest_dir, os.path.basename(p))
        if p.lower().endswith('.wav'):
            _write_wav(local, Sim.seconds[p])
        else:
            Image.new('RGB', (64, 64), (40, 90, 120)).save(local)
        out.append(local)
    return out


def _fake_end(path, **_k):
    """Preview de un loop: el archivo falso dura justo eso."""
    return _wav_seconds(path)


def _fake_cut(plan, dest_dir, local_fn=None):
    os.makedirs(dest_dir, exist_ok=True)
    out = []
    for i, seg in enumerate(plan['segments']):
        out.append(os.path.join(dest_dir, f'seg_{i:02d}.wav'))
        _write_wav(out[-1], seg['end'] - seg['start'])
    return out


def _fake_render(image, wavs, out):
    with Image.open(image) as img:
        frame = img.size
    Sim.last_render = {'seconds': round(sum(_wav_seconds(w) for w in wavs), 3), 'frame': frame}
    open(out, 'wb').close()
    return out


def _fake_upload(channel, video, title, description='', tags=None, thumbnail=None,
                 privacy='private', publish_at=None, **_k):
    vid = f'sim{len(Sim.uploads) + 1:03d}'
    Sim.uploads.append({
        'id': vid, 'week': Clock.week, 'title': title, 'description': description,
        'publish_at': publish_at, 'thumbnail': bool(thumbnail and os.path.isfile(thumbnail)),
        **Sim.last_render})
    if Sim.on_upload:
        Sim.on_upload(len(Sim.uploads))
    return {'youtube_id': vid, 'url': f'https://youtu.be/{vid}', 'privacy': privacy,
            'thumbnail_error': ''}


def _fake_llm(system, user):
    # Un LLM "terco": siempre propone lo mismo y en el mismo orden.
    return '\n'.join(NAME_POOL)


def _fake_art(prompt, image_paths, cfg):
    Sim.art_prompts.append(prompt)
    buf = io.BytesIO()
    Image.new('RGB', (64, 64), (30 + len(Sim.art_prompts) % 200, 60, 90)).save(buf, 'PNG')
    return buf.getvalue()


def _fake_refs(refs_root, genre, dbx=None):
    folder = kit_art.genre_folder(refs_root, genre)
    return [{'name': f'ref{n:02d}.png', 'path': f'{folder}/ref{n:02d}.png'}
            for n in range(REFS_PER_GENRE)]


def _install_fakes():
    kit_source.download_pack_files = _fake_download
    youtube.upload = _fake_upload
    kit_art.list_refs = _fake_refs
    real_for_video = kit_art.for_video
    # El reloj de la simulación también rige el plazo de las referencias y el estado.
    kit_art.for_video = lambda *a, **k: real_for_video(*a, **{**k, 'now': Clock.now})
    kit_state._now = lambda: Clock.now.isoformat(timespec='seconds')
    kit_state._utcnow = lambda: Clock.now.replace(tzinfo=timezone.utc)


def _run_week(dbx, tg, kits, out_dir, seed=0):
    packs = [k['pack'] for k in kits]
    hooks = {'list_packs_fn': lambda *a, **k: packs, 'render_fn': _fake_render,
             'cut_fn': _fake_cut, 'end_fn': _fake_end,
             'llm_call': _fake_llm, 'art_client': _fake_art,
             'art_notify': Sim.art_warnings.append}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = run_kit_weekly.run_weekly(
            app_config=_config(), channel=CHANNEL, channel_templates=dict(TEMPLATES), dbx=dbx,
            now=Clock.now, seed=seed, notifier=tg, hooks=hooks, output_dir=out_dir)
    return code, buf.getvalue()


# --- Estado previo: 3 kits con 2 videos en el ciclo y 1 kit descansando ---

def _seed_state(dbx, kits):
    ids = {k['pack']['dropbox_path']: kit_state.upsert_pack(
        k['pack']['dropbox_path'], k['pack']['name'], dbx=dbx) for k in kits}
    count = [0]

    def past_run(kit, days_ago, first_loop):
        when = START - timedelta(days=days_ago)
        count[0] += 1
        loops = kit['pack']['loops'][first_loop:first_loop + 5]
        kit_state.record_run(
            ids[kit['pack']['dropbox_path']], dbx=dbx, canal=CHANNEL, audio_mode='assembled',
            loops_json=[{'name': l['name'], 'path': l['path'], 'start': 0.0, 'end': LOOP_SEC}
                        for l in loops],
            youtube_id=f'old{count[0]:03d}', estado='scheduled',
            publish_at=(when + timedelta(days=1)).strftime('%Y-%m-%dT21:00:00Z'),
            subido_en=when.isoformat(timespec='seconds'))

    by_name = {k['pack']['name']: k for k in kits}
    for name in ('SimKit10', 'SimKit11', 'SimKit12'):       # les falta el tercer video
        past_run(by_name[name], 28, 0)
        past_run(by_name[name], 14, 5)
        kit_state.update_cycle(by_name[name]['pack']['dropbox_path'], dbx=dbx, cycle_videos=2)
    resting = by_name['SimKit09']                           # cerró el ciclo hace 20 días
    for days_ago, first in ((48, 0), (34, 5), (20, 10)):
        past_run(resting, days_ago, first)
    rest_until = START - timedelta(days=20) + timedelta(days=REST_DAYS)
    kit_state.update_cycle(resting['pack']['dropbox_path'], dbx=dbx, cycle_videos=MAX_VIDEOS,
                           rest_until=rest_until.isoformat(timespec='seconds'))


# --- Reglas ---

def _runs_by_kit(state, kits):
    """``{nombre: corridas del kit ordenadas por fecha de subida}``."""
    out = {}
    for kit in kits:
        saved = state['packs'].get(kit['pack']['dropbox_path']) or {}
        runs = [r for r in state['runs'] if r.get('pack_id') == saved.get('id')]
        out[kit['pack']['name']] = sorted(runs, key=lambda r: r.get('subido_en') or '')
    return out


def _when(run):
    return datetime.fromisoformat(run['subido_en'])


def _check_weeks(codes):
    problems = []
    for week, code in enumerate(codes, 1):
        count = sum(1 for u in Sim.uploads if u['week'] == week - 1)
        if code != 0 or count != 3:
            problems.append(f"semana {week}: código {code}, {count} video(s)")
    check("cada semana termina bien con 3 videos", problems)


def _check_distinct_and_catalog(state, kits, traps):
    run_by_id = {r.get('youtube_id'): r for r in state['runs']}
    name_by_pack_id = {p['id']: p['nombre'] for p in state['packs'].values()}
    eligible = {k['pack']['name'] for k in kits}
    repeated, outside = [], []
    for week in range(WEEKS):
        names = [name_by_pack_id.get((run_by_id.get(u['id']) or {}).get('pack_id'))
                 for u in Sim.uploads if u['week'] == week]
        if len(set(names)) != len(names):
            repeated.append(f"semana {week + 1}: {names}")
        outside += [f"semana {week + 1}: {n}" for n in names if n not in eligible]
    check("3 kits distintos por semana", repeated)
    check("solo kits elegibles del catálogo (activos y con link)", outside)


def _check_rotation(by_kit):
    sim = {name: sum(1 for r in runs if str(r.get('youtube_id', '')).startswith('sim'))
           for name, runs in by_kit.items()}
    problems = [f"{name}: sin videos en {WEEKS} semanas" for name, n in sim.items() if not n]
    plain = [sim[f'SimKit{i:02d}'] for i in range(1, 9)]   # los que no arrancan con historial
    if max(plain) - min(plain) > 1:
        problems.append(f"reparto desparejo entre kits sin historial: {sorted(plain)}")
    check("rotación pareja", problems)


def _check_cycle(state, kits, by_kit, end):
    cfg = kit_cycle.settings(_config()['kit_preview'])
    problems = []
    for kit in kits:
        name = kit['pack']['name']
        saved = state['packs'].get(kit['pack']['dropbox_path']) or {}
        in_cycle, rest_until = 0, None
        previous = None
        for run in by_kit[name]:
            day = _when(run)
            if previous and (day.date() - previous.date()).days < GAP_DAYS:
                problems.append(f"{name}: dos videos con menos de {GAP_DAYS} días")
            previous = day
            if rest_until is not None:
                if day.date() < rest_until.date():
                    problems.append(f"{name}: video durante el descanso")
                in_cycle, rest_until = 0, None
            in_cycle += 1
            if in_cycle >= MAX_VIDEOS:
                rest_until = day + timedelta(days=REST_DAYS)
        resting = rest_until is not None and end.date() < rest_until.date()
        expected = MAX_VIDEOS if resting else (0 if rest_until is not None else in_cycle)
        cur = kit_cycle.current(saved.get('cycle'), end, cfg, saved.get('last_used_at'))
        if cur['cycle_videos'] != expected:
            problems.append(f"{name}: el estado dice {cur['cycle_videos']} video(s) en el "
                            f"ciclo y son {expected}")
        elif resting:
            late = (datetime.fromisoformat(cur['rest_until']).date() - rest_until.date()).days
            if not 0 <= late <= 6:
                problems.append(f"{name}: descanso guardado a {late} días del esperado")
    check(f"ciclo de {MAX_VIDEOS} videos con descanso de {REST_DAYS} días", problems)


def _ranges(run):
    loops = run.get('loops_json') or []
    if isinstance(loops, str):
        loops = json.loads(loops)
    return [(seg['path'], float(seg.get('start') or 0.0),
             float('inf') if seg.get('end') is None else float(seg['end'])) for seg in loops]


def _check_segments(by_kit):
    problems = []
    for name, runs in by_kit.items():
        used, in_cycle, rest_until = [], 0, None
        for run in runs:
            if rest_until is not None and _when(run).date() >= rest_until.date():
                used, in_cycle, rest_until = [], 0, None
            for path, start, end in _ranges(run):
                if any(path == p and start < e and s < end for p, s, e in used):
                    problems.append(f"{name}: repite audio dentro del mismo ciclo")
                    break
            used += _ranges(run)
            in_cycle += 1
            if in_cycle >= MAX_VIDEOS:
                rest_until = _when(run) + timedelta(days=REST_DAYS)
    check("tramos de audio sin repetir dentro del ciclo", sorted(set(problems)))


def _check_durations():
    check(f"duración entre {WINDOW[0]:.0f} y {WINDOW[1]:.0f} s",
          [f"semana {u['week'] + 1}: {u.get('seconds')} s" for u in Sim.uploads
           if not WINDOW[0] <= (u.get('seconds') or 0) <= WINDOW[1]])


def _check_names(state, kits, traps):
    run_by_id = {r.get('youtube_id'): r for r in state['runs']}
    reserved = {kit_names._norm(k['pack']['name']) for k in kits + traps}
    reserved |= {kit_names._norm(k['entry']['name']) for k in kits + traps}
    seen, problems = {}, []
    for u in Sim.uploads:
        name = (run_by_id.get(u['id']) or {}).get('video_name')
        if not name:
            problems.append(f"{u['id']}: sin nombre de video en el estado")
            continue
        key = kit_names._norm(name)
        if key in seen:
            problems.append(f"«{name}» repetido ({seen[key]} y {u['id']})")
        seen.setdefault(key, u['id'])
        if key in reserved:
            problems.append(f"«{name}» es el nombre de un kit")
        if name not in u['title']:
            problems.append(f"{u['id']}: el título no lleva el nombre del video")
    check("un nombre distinto por video", problems)


def _check_refs(state, kits):
    run_by_id = {r.get('youtube_id'): r for r in state['runs']}
    genre_by_pack_id = {
        (state['packs'].get(k['pack']['dropbox_path']) or {}).get('id'): k['entry']['genre']
        for k in kits}
    last, problems = {}, []
    for u in Sim.uploads:
        run = run_by_id.get(u['id']) or {}
        refs = run.get('ref_images') or []
        if not 1 <= len(refs) <= 2:
            problems.append(f"{u['id']}: {len(refs)} referencia(s)")
        genre = genre_by_pack_id.get(run.get('pack_id'))
        folder = kit_art.genre_folder(REFS_ROOT, genre) if genre else None
        if folder and any(not ref.startswith(folder + '/') for ref in refs):
            problems.append(f"{u['id']}: referencias de otro género")
        day = START + timedelta(days=7 * u['week'])
        for ref in refs:
            if ref in last and (day.date() - last[ref].date()).days < REST_DAYS:
                problems.append(f"{u['id']}: referencia repetida antes de {REST_DAYS} días")
            last[ref] = day
    if Sim.art_warnings:
        problems.append(f"{len(Sim.art_warnings)} video(s) cayeron a la imagen manual")
    names = [k['pack']['name'].lower() for k in kits]
    if any(n in p.lower() for p in Sim.art_prompts for n in names):
        problems.append("un prompt de imagen lleva el nombre de un kit")
    check("referencias del género del kit, sin repetir en 30 días", problems)


def _check_links(state, kits):
    run_by_id = {r.get('youtube_id'): r for r in state['runs']}
    url_by_pack_id = {
        (state['packs'].get(k['pack']['dropbox_path']) or {}).get('id'): k['entry']['payhip_url']
        for k in kits}
    seen, problems = set(), []
    for u in Sim.uploads:
        want = url_by_pack_id.get((run_by_id.get(u['id']) or {}).get('pack_id'))
        line = next((l for l in u['description'].splitlines() if l.startswith('Link: ')), '')
        got = urllib.parse.urlsplit(line[len('Link: '):].strip())
        query = dict(urllib.parse.parse_qsl(got.query))
        base = urllib.parse.urlsplit(want or '')
        if not want or (got.netloc, got.path) != (base.netloc, base.path):
            problems.append(f"{u['id']}: la descripción no lleva el link de su kit")
        elif query.get('ref') != 'sim' or query.get('utm_source') != 'youtube':
            problems.append(f"{u['id']}: el link perdió su query o el utm_source")
        tracking = query.get('utm_content')
        if not tracking or tracking in seen:
            problems.append(f"{u['id']}: utm_content ausente o repetido")
        seen.add(tracking)
    check("link del kit con seguimiento por video", problems)


def _check_slots_and_cover():
    slots, cover = [], []
    for week in range(WEEKS):
        monday = (START + timedelta(days=7 * week + 1)).date()
        want = sorted((monday + timedelta(days=d)).strftime('%Y-%m-%dT21:00:00Z')
                      for d in (0, 2, 4))
        got = sorted(u['publish_at'] or '' for u in Sim.uploads if u['week'] == week)
        if got != want:
            slots.append(f"semana {week + 1}: {got}")
    for u in Sim.uploads:
        if tuple(u.get('frame') or ()) != FRAME or not u['thumbnail']:
            cover.append(f"{u['id']}: cuadro {u.get('frame')}, miniatura {u['thumbnail']}")
    check("lun/mié/vie 18:00 de Buenos Aires (21:00 UTC)", slots)
    check("portada: cuadro 16:9 al render y miniatura a YouTube", cover)


# --- Simulación principal ---

def _simulate(work_dir):
    kits, traps = _twelve_kits(work_dir)
    everything = kits + traps
    dbx, tg = FakeDropbox(), FakeTelegram()
    _put_catalog(dbx, everything)
    Clock.now, Clock.week = START, 0
    _seed_state(dbx, everything)
    _reset()

    codes, leaks, locks = [], [], []
    for week in range(WEEKS):
        Clock.now, Clock.week = START + timedelta(days=7 * week), week
        code, log = _run_week(dbx, tg, everything, work_dir, seed=week)
        codes.append(code)
        if 'simkit' in log.lower() or 'simtrap' in log.lower():
            leaks.append(f"semana {week + 1}")
        if kit_state.load(dbx=dbx)['lock'] is not None:
            locks.append(f"semana {week + 1}")
        if week == 2:   # repetir la corrida de la misma semana no sube nada
            before = len(Sim.uploads)
            _run_week(dbx, FakeTelegram(), everything, work_dir, seed=99)
            check("repetir la corrida de una semana no duplica",
                  [] if len(Sim.uploads) == before else
                  [f"{len(Sim.uploads) - before} video(s) de más"])
            del Sim.uploads[before:]

    end = START + timedelta(days=7 * (WEEKS - 1))
    state = kit_state.load(dbx=dbx)
    by_kit = _runs_by_kit(state, kits)
    _check_weeks(codes)
    _check_distinct_and_catalog(state, kits, traps)
    _check_rotation(by_kit)
    _check_cycle(state, kits, by_kit, end)
    _check_durations()
    _check_segments(by_kit)
    _check_names(state, kits, traps)
    _check_refs(state, kits)
    _check_links(state, kits)
    _check_slots_and_cover()
    check("el log no nombra kits y el lock queda libre", leaks + [f"lock: {w}" for w in locks])


# --- Casos borde ---

def _edge_broken_kits(work_dir):
    """Un kit sin imágenes y otro sin audio no pueden cortar la semana."""
    kits = [_kit(i, work_dir) for i in range(21, 25)]
    kits.append(_kit(25, work_dir, images=False))
    kits.append(_kit(26, work_dir, loops=0))
    problems = []
    for seed in range(6):
        _reset()
        Clock.now, Clock.week = START, 0
        dbx = FakeDropbox()
        _put_catalog(dbx, kits)
        code, _ = _run_week(dbx, FakeTelegram(), kits, work_dir, seed=seed)
        if code != 0 or len(Sim.uploads) != 3:
            problems.append(f"semilla {seed}: código {code}, {len(Sim.uploads)} video(s)")
    check("borde: kit sin imágenes o sin audio no corta la semana", problems)


def _edge_single_kit(work_dir):
    """Con un solo kit sale un video y un aviso, no una alerta de fallo."""
    _reset()
    Clock.now, Clock.week = START, 0
    kits = [_kit(31, work_dir)]
    dbx, tg = FakeDropbox(), FakeTelegram()
    _put_catalog(dbx, kits)
    code, _ = _run_week(dbx, tg, kits, work_dir)
    problems = []
    if code != 0 or len(Sim.uploads) != 1:
        problems.append(f"código {code}, {len(Sim.uploads)} video(s)")
    if any('fallo el worker' in text for text in tg.sent):
        problems.append("mandó una alerta de fallo en vez de un aviso")
    check("borde: un único kit elegible", problems)


def _edge_corrupt_state(work_dir):
    """Un state.json roto frena la corrida sin pisarlo."""
    _reset()
    Clock.now, Clock.week = START, 0
    kits = [_kit(i, work_dir) for i in range(41, 45)]
    dbx, tg = FakeDropbox(), FakeTelegram()
    _put_catalog(dbx, kits)
    dbx.files[kit_state.STATE_PATH] = ('0000000000aa', b'{"runs": [ esto no es json')
    code, _ = _run_week(dbx, tg, kits, work_dir)
    problems = []
    if code != 1 or Sim.uploads:
        problems.append(f"código {code}, {len(Sim.uploads)} video(s)")
    if dbx.files[kit_state.STATE_PATH][1] != b'{"runs": [ esto no es json':
        problems.append("el estado roto fue reemplazado")
    if not any('fallo el worker' in text for text in tg.sent):
        problems.append("no hubo alerta")
    check("borde: state.json corrupto frena sin pisar", problems)


def _edge_dropbox_down(work_dir):
    """Dropbox se cae al subir el segundo video: aviso con el link, y la corrida siguiente
    (con el lock ya vencido) completa los slots sin repetir el que quedó registrado."""
    _reset()
    Clock.now, Clock.week = START, 0
    kits = [_kit(i, work_dir) for i in range(51, 57)]
    dbx, tg = DownDropbox(), FakeTelegram()
    _put_catalog(dbx, kits)

    def fall(count):
        if count == 2:
            dbx.down = True
    Sim.on_upload = fall
    code, _ = _run_week(dbx, tg, kits, work_dir)
    problems = []
    if code != 1 or len(Sim.uploads) != 2:
        problems.append(f"primera corrida: código {code}, {len(Sim.uploads)} video(s)")
    if not any('video/sim002/edit' in text for text in tg.sent):
        problems.append("el aviso no trae el link del video sin registrar")
    dbx.down, Sim.on_upload = False, None
    code, _ = _run_week(dbx, FakeTelegram(), kits, work_dir)
    if code != 1 or len(Sim.uploads) != 2:
        problems.append("con el lock todavía vigente la segunda corrida subió algo")
    Clock.now = START + timedelta(hours=3)
    code, _ = _run_week(dbx, FakeTelegram(), kits, work_dir)
    state = kit_state.load(dbx=dbx)
    slots = sorted(r.get('publish_at') for r in state['runs'])
    if code != 0 or len(slots) != 3 or len(set(slots)) != 3 or state['lock'] is not None:
        problems.append(f"tras vencer el lock: código {code}, slots {slots}")
    if len(Sim.uploads) != 4:
        problems.append(f"se esperaban 4 subidas en total y hubo {len(Sim.uploads)}")
    check("borde: Dropbox caído a mitad de corrida", problems)


def _edge_two_runs(work_dir):
    """Otra corrida toma el lock justo antes: esta no sube nada y no lo libera."""
    _reset()
    Clock.now, Clock.week = START, 0
    kits = [_kit(i, work_dir) for i in range(61, 65)]
    dbx, tg = FakeDropbox(), FakeTelegram()
    _put_catalog(dbx, kits)
    dbx.before_upload = lambda: kit_state.acquire_lock(owner='otra-corrida', dbx=dbx)
    code, _ = _run_week(dbx, tg, kits, work_dir)
    lock = kit_state.load(dbx=dbx)['lock'] or {}
    problems = []
    if code != 1 or Sim.uploads:
        problems.append(f"código {code}, {len(Sim.uploads)} video(s)")
    if lock.get('owner') != 'otra-corrida':
        problems.append("el lock de la otra corrida se perdió")
    check("borde: dos corridas casi simultáneas", problems)


def main():
    _install_fakes()
    with tempfile.TemporaryDirectory(prefix='kit_sim_') as work_dir:
        steps = (_simulate, _edge_broken_kits, _edge_single_kit, _edge_corrupt_state,
                 _edge_dropbox_down, _edge_two_runs)
        for step in steps:
            try:
                step(work_dir)
            except Exception as exc:  # una regla que explota también es un fallo
                check(f"{step.__name__} no terminó", [f"{type(exc).__name__}: {exc}"])

    failed = 0
    for name, problems in RESULTS:
        if not problems:
            print(f"OK    {name}")
            continue
        failed += 1
        print(f"FAIL  {name}")
        for problem in problems[:4]:
            print(f"        - {problem}")
        if len(problems) > 4:
            print(f"        - … y {len(problems) - 4} más")
    if failed:
        print(f"FAIL: smoke_kit_simulation ({failed} de {len(RESULTS)} reglas)")
        return 1
    print('OK: smoke_kit_simulation')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
