#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke de varios canales de loop kits: rutas, estados independientes, avisos y secretos.

Sin red. Dos canales falsos sobre un mismo Dropbox en memoria. La parte del panel necesita
PyQt5 (``.venv\\Scripts\\python.exe``); sin PyQt5 se omite y se avisa.
"""

import contextlib
import io
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')
for path in (ROOT, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

import smoke_kit_weekly as base  # fakes de Dropbox, YouTube, render y Telegram
from smoke_kit_state import FakeDropbox

from core import (kit_channel, kit_channel_setup, kit_notify, kit_settings, kit_source,
                  kit_state, youtube)
import kit_plan
import kit_secrets_sync
import run_kit_weekly

CH_A, CH_B = 'Canal Smoke Á', 'canal smoke b'
GENRE = 'genre-a'
SECRETS = {'KIT_DROPBOX_REFRESH_TOKEN': 'SMOKE-DBX-REFRESH-1', 'KIT_DROPBOX_APP_KEY': 'SMOKE-APP-KEY-2',
           'KIT_LLM_API_KEY': 'SMOKE-LLM-KEY-3', 'KIT_IMAGE_API_KEY': 'SMOKE-IMG-KEY-4',
           'KIT_TELEGRAM_TOKEN': 'SMOKE-TG-TOKEN-5', 'KIT_TELEGRAM_CHAT_ID': 'SMOKE-TG-CHAT-6',
           'KIT_NOTION_TOKEN': 'SMOKE-NOTION-KEY-8', 'KIT_NOTION_PAGE_ID': 'SMOKE-NOTION-PAGE-9'}
YT_REFRESH = 'SMOKE-YT-REFRESH-7'
FAILS = []
OUTPUT = io.StringIO()  # todo lo que imprimen los módulos durante el smoke


def check(cond, msg):
    if not cond:
        FAILS.append(msg)


def _raises(exc_type, fn, *args, **kw):
    try:
        fn(*args, **kw)
    except exc_type:
        return True
    return False


def _put(dbx, path, data):
    dbx.files[path] = (f"{len(dbx.files) + 0xa00:012x}", json.dumps(data).encode('utf-8'))


def _catalog(indices):
    return [{'folder': base.PACK_NAMES[i], 'name': f'Nombre {i}',
             'payhip_url': 'https://example.com/p', 'genre': GENRE, 'active': True}
            for i in indices]


def _run(dbx, tg, channel, out_dir, paths=None, label=None, now=base.NOW):
    hooks = {'list_packs_fn': base._packs, 'render_fn': base._fake_render,
             'cut_fn': base._fake_cut, 'end_fn': lambda path, **_k: 28.0}
    config = base._config(out_dir)
    config['kit_preview']['genres'] = [GENRE]
    with contextlib.redirect_stdout(OUTPUT):
        return run_kit_weekly.run_weekly(
            app_config=config, channel=channel, channel_templates={}, dbx=dbx, now=now,
            seed=1, notifier=tg, hooks=hooks, output_dir=out_dir, paths=paths, label=label)


def _used_paths(dbx, state_path):
    state = kit_state.load(state_path, dbx=dbx)
    by_id = {p['id']: path for path, p in state['packs'].items()}
    return [by_id[r['pack_id']] for r in state['runs']], state


def _check_paths():
    a, b = kit_channel.for_channel(CH_A), kit_channel.for_channel(CH_B)
    check(kit_channel.slug(CH_A) == 'canal-smoke-a' == kit_channel.slug('  CANAL   smoke a!! '),
          "slug no es estable ante mayúsculas, tildes y espacios")
    check(kit_channel.slug('Ж') == kit_channel.slug('Ж') and kit_channel.slug('Ж').startswith('canal-'),
          "slug de un nombre sin letras latinas")
    for key in (None, '', 'default', ' Default '):
        d = kit_channel.paths(key)
        check((d.config, d.kits, d.state, d.is_default) ==
              (kit_settings.CONFIG_PATH, kit_settings.KITS_PATH, kit_state.STATE_PATH, True),
              f"las rutas del canal por defecto cambiaron ({key!r})")
    check(kit_channel.default_paths({}) == kit_channel.Paths(
        'default', '/Soft Projects/Type Beat Generator/datos/loop_kits/config.json', '/Soft Projects/Type Beat Generator/datos/loop_kits/kits.json',
        '/Soft Projects/Type Beat Generator/datos/loop_kits/estado/state.json', True), "los valores por defecto ya no son los de hoy")
    env = {'KIT_CONFIG_PATH': '/x/c.json', 'KIT_CATALOG_PATH': '/y/k.json',
           'KIT_STATE_PATH': '/z/s.json'}
    d = kit_channel.paths(None, env)
    check((d.config, d.kits, d.state) == ('/x/c.json', '/y/k.json', '/z/s.json'),
          "KIT_*_PATH ya no mandan en el canal por defecto")
    check(kit_channel.paths('otro', env).state == '/z/otro/s.json',
          "el canal nuevo no cuelga de la carpeta configurada")
    files = {a.config, a.kits, a.state, b.config, b.kits, b.state,
             kit_settings.CONFIG_PATH, kit_settings.KITS_PATH, kit_state.STATE_PATH}
    check(len(files) == 9, "dos canales comparten alguna ruta")
    check(a.state == '/Soft Projects/Type Beat Generator/datos/loop_kits/estado/canal-smoke-a/state.json'
          and a.config == '/Soft Projects/Type Beat Generator/datos/loop_kits/canal-smoke-a/config.json',
          "las rutas del canal no quedan dentro de las carpetas actuales")
    for bad in ('../otro', 'a/b', 'A B', '-x', 'x' * 60):
        check(_raises(kit_channel.KitChannelError, kit_channel.paths, bad), f"slug aceptado: {bad}")
    check(_raises(kit_channel.KitChannelError, kit_channel.for_channel, 'Default'),
          "un canal llamado default pisaría al canal por defecto")
    check(kit_channel.environment() == 'kit-weekly'
          and kit_channel.environment(a.slug) == 'kit-weekly-canal-smoke-a', "nombre del Environment")
    kit_channel.check_owner(a, CH_A, CH_A)
    kit_channel.check_owner(kit_channel.paths(), CH_B, CH_A)  # el canal por defecto no se controla
    check(_raises(kit_channel.KitChannelError, kit_channel.check_owner, a, CH_B),
          "una config de otro canal pasó el control")
    check(_raises(kit_channel.KitChannelError, kit_channel.check_owner, a, CH_A, CH_B),
          "un token de otro canal pasó el control")
    return a, b


def _check_runs(a, b, out_dir):
    dbx = FakeDropbox()
    shared = f'/smoke/{base.PACK_NAMES[2]}'  # el mismo kit en los dos canales
    _put(dbx, a.kits, _catalog([0, 1, 2]))
    _put(dbx, b.kits, _catalog([2, 3, 4]))
    tg_a, tg_b = base.FakeTelegram(), base.FakeTelegram()

    base._reset()
    check(_run(dbx, tg_a, CH_A, out_dir, a, CH_A) == 0, "canal A: la corrida falló")
    snapshot_a = dbx.files[a.state]
    check(_run(dbx, tg_b, CH_B, out_dir, b, CH_B) == 0, "canal B: la corrida falló")
    check(dbx.files[a.state] == snapshot_a, "la corrida de B tocó el estado de A")
    check(kit_state.STATE_PATH not in dbx.files, "un canal escribió el estado del canal por defecto")

    used_a, state_a = _used_paths(dbx, a.state)
    used_b, state_b = _used_paths(dbx, b.state)
    check(len(used_a) == 3 and len(used_b) == 3 and base.Counters.uploads == 6,
          f"cada canal debía subir 3 videos: {len(used_a)} y {len(used_b)}")
    check(set(used_a) == {f'/smoke/{base.PACK_NAMES[i]}' for i in (0, 1, 2)}
          and set(used_b) == {f'/smoke/{base.PACK_NAMES[i]}' for i in (2, 3, 4)},
          "un canal usó el catálogo del otro")
    check(shared in used_a and shared in used_b, "el kit compartido no salió en los dos canales")
    cycle_a = kit_state.get_cycle(shared, db_path=a.state, dbx=dbx)
    check(cycle_a['cycle_videos'] == 1
          and kit_state.get_cycle(shared, db_path=b.state, dbx=dbx)['cycle_videos'] == 1,
          "el ciclo del kit compartido no se cuenta por canal")

    # El ciclo, el descanso, los nombres y las referencias de un canal no llegan al otro.
    kit_state.update_cycle(shared, db_path=a.state, dbx=dbx, cycle_videos=3,
                           rest_until='2099-01-01', used_names=['Uno'], used_ref_images=['r.png'])
    cycle_b = kit_state.get_cycle(shared, db_path=b.state, dbx=dbx)
    check(cycle_b == {'cycle_videos': 1, 'rest_until': None, 'used_names': [],
                      'used_ref_images': []}, "el ciclo de A se filtró a B")
    check(state_a['lock'] is None and state_b['lock'] is None, "quedó un lock tomado")

    # Lock de A tomado: A avisa con su nombre y B corre igual la semana siguiente.
    later = base.NOW + timedelta(days=7)
    kit_state.acquire_lock(owner='otra-corrida', now=later.replace(tzinfo=timezone.utc),
                           db_path=a.state, dbx=dbx)
    real_now = kit_state._utcnow
    kit_state._utcnow = lambda: later.replace(tzinfo=timezone.utc)
    try:
        code_a = _run(dbx, tg_a, CH_A, out_dir, a, CH_A, now=later)
        code_b = _run(dbx, tg_b, CH_B, out_dir, b, CH_B, now=later)
    finally:
        kit_state._utcnow = real_now
    check(code_a == 1 and code_b == 0, f"el lock de A debía frenar solo a A: {code_a}, {code_b}")
    check(tg_a.sent[-1].startswith(f'[{CH_A}] ') and 'fallo el worker' in tg_a.sent[-1]
          and "'lock'" in tg_a.sent[-1], "la alerta no empieza con el nombre del canal")
    check(tg_a.sent and all(t.startswith(f'[{CH_A}] ') for t in tg_a.sent)
          and tg_b.sent and all(t.startswith(f'[{CH_B}] ') for t in tg_b.sent),
          "algún aviso no empieza con el nombre de su canal")
    check(any('studio.youtube.com' in t for t in tg_b.sent), "el resumen de B no trae los links")

    # Canal por defecto: mismas rutas y mismos textos que antes (sin prefijo si no hay label).
    tg_d = base.FakeTelegram()
    check(_run(dbx, tg_d, 'canal-smoke', out_dir, kit_channel.paths()) == 0
          and kit_state.STATE_PATH in dbx.files, "el canal por defecto no usó su estado de siempre")
    check(tg_d.sent and not tg_d.sent[0].startswith('['), "el canal por defecto cambió su aviso")
    check(len(kit_state.load(dbx=dbx)['runs']) == 3
          and len(kit_state.load(a.state, dbx=dbx)['runs']) == 3,
          "el canal por defecto y el canal A se mezclaron")

    # El aviso del fondo con IA también lleva el nombre del canal.
    sent = []

    class _Tg:
        send = staticmethod(lambda text, photo=None: sent.append(text))
    kit_channel.Prefixed(_Tg, CH_A).send('hola')
    check(sent == [f'[{CH_A}] hola'] and kit_channel.prefixed(None, 'x') == 'x', "prefijo de avisos")
    check(kit_channel.prefixed(CH_A, kit_notify.alert(RuntimeError('dato privado'), step='inicio'))
          .startswith(f'[{CH_A}] Loop kits: fallo'), "alerta de inicio sin prefijo")
    log = OUTPUT.getvalue()
    check(not any(name in log for name in base.PACK_NAMES) and CH_A not in log and CH_B not in log,
          "el log imprimió un nombre de kit o de canal")


def _check_schedule():
    m = kit_channel.matrix
    check(m('', 6) == [{'channel': 'default', 'suffix': ''}] and m(None, 0) == [],
          "sin KIT_CHANNELS debe correr solo el canal por defecto, el domingo")
    text = 'default, canal-b ,canal-c=vie,canal-d=2'
    check(kit_channel.parse_schedule(text) == [('default', 6), ('canal-b', 0), ('canal-c', 4),
                                               ('canal-d', 2)], "calendario: un canal por día")
    check(m(text, 0) == [{'channel': 'canal-b', 'suffix': '-canal-b'}] and m(text, 1) == [],
          "matriz del día")
    check(m(text, 3, only='canal-c') == [{'channel': 'canal-c', 'suffix': '-canal-c'}]
          and m(text, 3, only='default') == [{'channel': 'default', 'suffix': ''}],
          "corrida manual de un canal")
    for bad_only in ('no-esta', 'x"; echo hola', '../a'):
        check(_raises(kit_channel.KitChannelError, m, text, 0, bad_only), f"only aceptado: {bad_only}")
    for bad in ('a,a', 'a=9', 'a=lunes', 'A B'):
        check(_raises(kit_channel.KitChannelError, kit_channel.parse_schedule, bad),
              f"calendario aceptado: {bad}")
    out, err = io.StringIO(), io.StringIO()
    sunday = datetime(2026, 10, 12, 1, 0, tzinfo=timezone.utc)  # domingo 22:00 en Buenos Aires
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        ok = kit_plan.main({'KIT_CHANNELS': text}, sunday)
        bad = kit_plan.main({'KIT_CHANNELS': text, 'KIT_ONLY': 'no-esta'}, sunday)
    check(ok == 0 and out.getvalue().strip() == 'matrix=[{"channel":"default","suffix":""}]',
          f"kit_plan: {out.getvalue()!r}")
    check(bad == 1 and 'no-esta' not in err.getvalue(), "kit_plan aceptó un canal desconocido")

    with open(os.path.join(ROOT, '.github', 'workflows', 'kit-weekly.yml'), encoding='utf-8') as f:
        workflow = f.read()
    head = workflow.split('jobs:')[0]
    check('schedule:' in head and 'workflow_dispatch:' in head and 'channel:' in head
          and 'dry_run:' in head and 'push:' not in head and 'pull_request_target' not in workflow,
          "triggers del workflow")
    check('permissions:\n  contents: read' in workflow and workflow.count('permissions:') == 1,
          "permisos del workflow")
    check('environment: kit-weekly${{ matrix.suffix }}' in workflow
          and 'group: kit-weekly${{ matrix.suffix }}' in workflow
          and 'cancel-in-progress: false' in workflow, "Environment y concurrency por canal")
    uses = [line.split('uses:')[1].split('#')[0].strip()
            for line in workflow.splitlines() if 'uses:' in line]
    check(uses and all(len(u.split('@')[-1]) == 40 for u in uses), "acciones sin SHA fijo")
    plan = workflow.split('  weekly:')[0]
    check('secrets.' not in plan and '${{ inputs.' not in workflow.split('run:', 1)[1].split('env:')[0],
          "el job plan usa secretos o interpola el input en el shell")


def _check_setup(a, b):
    dbx = FakeDropbox()
    default_cfg = {'channels': {CH_A: {'section': 'loop_kits', 'title_template': 'T {name}',
                                       'groups': ['g']},
                                'otro': {'section': 'beats'}},
                   'kit_preview': {'dropbox_root': '/smoke', 'genres': [GENRE], 'channel': 'primero',
                                   'cover': {'template': {'brand': {'text': 'MARCA'}}}}}
    _put(dbx, kit_settings.CONFIG_PATH, default_cfg)
    before = dbx.files[kit_settings.CONFIG_PATH]
    local = {'channels': {CH_B: {'section': 'loop_kits', 'description_template': 'D {link}'}}}
    check(kit_channel_setup.loop_kit_channels(local, default_cfg) == [CH_B, CH_A],
          "lista de canales de Loop kits")
    check(kit_channel_setup.create(CH_A, default_cfg, local, dbx) == a, "create devuelve las rutas")
    kit_channel_setup.create(CH_B, default_cfg, local, dbx)
    cfg_a, cfg_b = json.loads(dbx.files[a.config][1]), json.loads(dbx.files[b.config][1])
    check(cfg_a['kit_preview']['channel'] == CH_A and cfg_a['kit_preview']['dropbox_root'] == '/smoke'
          and cfg_a['kit_preview']['genres'] == [GENRE] and len(cfg_a['kit_preview']['slots']) == 3
          and 'cover' not in cfg_a['kit_preview'], "config mínima del canal nuevo")
    check(cfg_a['channels'] == {CH_A: {'section': 'loop_kits', 'title_template': 'T {name}'}}
          and cfg_b['channels'][CH_B]['description_template'] == 'D {link}',
          "plantillas del canal nuevo")
    check(dbx.files[kit_settings.CONFIG_PATH] == before, "crear un canal tocó la config por defecto")
    check(kit_channel_setup.load_registry(dbx) == [{'name': CH_A, 'slug': a.slug},
                                                   {'name': CH_B, 'slug': b.slug}], "índice de canales")
    saved = dbx.files[a.config]
    kit_channel_setup.create(CH_A, {}, {}, dbx)
    check(dbx.files[a.config] == saved and len(kit_channel_setup.load_registry(dbx)) == 2,
          "crear dos veces pisó la config o duplicó el canal")
    check(_raises(kit_channel_setup.ChannelSetupError, kit_channel_setup.create,
                  'canal  SMOKE a', {}, {}, dbx), "dos canales con el mismo slug")
    check(_raises(kit_channel_setup.ChannelSetupError, kit_channel_setup.create, ' ', {}, {}, dbx),
          "canal vacío aceptado")

    # kit_settings con rutas de canal: lee y guarda solo lo de ese canal.
    settings = kit_settings.validate_settings({
        'channel': CH_A, 'genres': [GENRE, 'genre-b'], 'refs_root': '', 'cover_mode': 'manual',
        'slots': [{'weekday': d, 'hour': 10, 'minute': 0} for d in (1, 3, 5)]})
    kit_settings.save_config(settings, dbx, a)
    kit_settings.save_kits(_catalog([0]), None, dbx, a)
    check(kit_settings.load_all(dbx, a)['config']['kit_preview']['genres'] == [GENRE, 'genre-b']
          and len(kit_settings.load_all(dbx, a)['kits']) == 1
          and kit_settings.load_all(dbx, b)['kits'] is None
          and kit_settings.load_all(dbx)['kits'] is None
          and dbx.files[kit_settings.CONFIG_PATH] == before and dbx.files[b.config][1]
          == json.dumps(cfg_b, ensure_ascii=False, indent=1, sort_keys=True).encode('utf-8'),
          "guardar un canal tocó otro")
    return dbx


def _check_panel(dbx, a, b):
    try:
        from PyQt5.QtWidgets import QApplication
    except ImportError:
        return False
    from loop_kit_panel import LoopKitPanel
    from smoke_kit_panel import _wait
    app = QApplication.instance() or QApplication([])
    with tempfile.TemporaryDirectory() as empty:  # sin config/app_config.json local
        panel = LoopKitPanel(dbx_provider=lambda: dbx, script_dir=empty)
        panel.reload()
        check(_wait(app, panel), "panel: la lectura termina")
        items = [(panel.automation.itemText(i), panel.automation.itemData(i))
                 for i in range(panel.automation.count())]
        check(items == [('Canal por defecto', ''), (CH_A, a.slug), (CH_B, b.slug)],
              "panel: el selector no lista los canales")
        check(panel.paths().is_default and panel.channel.isEnabled()
              and panel.table.rowCount() == 0, "panel: no abre en el canal por defecto")

        panel.automation.setCurrentIndex(1)
        check(_wait(app, panel), "panel: cambiar de canal recarga")
        check(panel.paths() == a and panel.table.rowCount() == 1
              and panel.channel.currentText() == CH_A and not panel.channel.isEnabled()
              and 'genre-b' in panel.genres.toPlainText(), "panel: no cargó lo del canal A")
        default_before = dbx.files[kit_settings.CONFIG_PATH]
        b_before = dbx.files[b.config]
        panel.add_kit_row(_catalog([1])[0])
        panel.save()
        check(_wait(app, panel) and panel.status.text().startswith('Guardado'),
              "panel: no guardó el canal A")
        check(len(json.loads(dbx.files[a.kits][1])) == 2 and b.kits not in dbx.files
              and kit_settings.KITS_PATH not in dbx.files and dbx.files[b.config] == b_before
              and dbx.files[kit_settings.CONFIG_PATH] == default_before,
              "panel: guardar el canal A tocó otro canal")

        state = kit_state._empty()
        state['runs'].append({'id': 7, 'estado': 'scheduled', 'publish_at': 'x',
                              'youtube_id': 'solo-de-a'})
        _put(dbx, a.state, state)
        panel.show_last_state()
        _wait(app, panel)
        check('solo-de-a' in panel.output.toPlainText(), "panel: no muestra el estado del canal A")
        panel.automation.setCurrentIndex(2)
        _wait(app, panel)
        panel.show_last_state()
        _wait(app, panel)
        check(panel.paths() == b and 'solo-de-a' not in panel.output.toPlainText(),
              "panel: el canal B muestra el estado de A")

        panel.create_automation('Canal Nuevo')
        check(_wait(app, panel) and _wait(app, panel), "panel: crear la automatización termina")
        new = kit_channel.for_channel('Canal Nuevo')
        check(new.config in dbx.files and panel.paths() == new
              and panel.channel.currentText() == 'Canal Nuevo'
              and 'conectar su YouTube' in panel.status.text(),
              "panel: Crear automatización no dejó el canal nuevo elegido")
        check(json.loads(dbx.files[new.config][1])['kit_preview']['dropbox_root'] == '/smoke',
              "panel: el canal nuevo no heredó la carpeta de kits")
        panel.shutdown()
    return True


def _check_secrets(tmp):
    shared = os.path.join(tmp, 'shared.json')
    token = os.path.join(tmp, 'yt.json')
    with open(shared, 'w', encoding='utf-8') as f:
        json.dump(SECRETS, f)
    with open(token, 'w', encoding='utf-8') as f:
        json.dump({'refresh_token': YT_REFRESH, 'client_id': 'id'}, f)
    calls, exists = [], [False]

    def runner(args, stdin=None):
        calls.append((list(args), stdin))
        if args[:1] == ['api'] and '--method' not in args:
            return 0 if exists[0] else 1
        return 0

    env = kit_channel.environment(kit_channel.slug(CH_A))
    argv = ['--env', env, '--channel', CH_A, '--shared-file', shared, '--yt-token-file', token]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = kit_secrets_sync.main(argv, runner=runner)
    OUTPUT.write(out.getvalue())
    sets = {c[0][2]: c for c in calls if c[0][:2] == ['secret', 'set']}
    check(code == 0 and set(sets) == set(SECRETS) | {'KIT_YT_CHANNEL', 'KIT_YT_TOKEN_JSON'},
          f"no se cargaron todos los secretos: {sorted(sets)}")
    check(all(c[0][3:5] == ['--env', env] for c in sets.values()), "secreto fuera del Environment")
    check(all(sets[name][1] == value for name, value in SECRETS.items())
          and YT_REFRESH in sets['KIT_YT_TOKEN_JSON'][1], "los valores no viajan por stdin")
    values = list(SECRETS.values()) + [YT_REFRESH]
    argv_blob = json.dumps([c[0] for c in calls])
    check(not any(v in argv_blob for v in values), "un secreto viajó como argumento")
    check(not any(v in out.getvalue() for v in values) and CH_A not in out.getvalue(),
          "el script imprimió un secreto o el canal")
    methods = [c[0][2] for c in calls if c[0][:2] == ['api', '--method']]
    check(methods == ['PUT', 'POST'] and '"name": "master"' in calls[2][1],
          "el Environment nuevo no se creó restringido a master")

    calls.clear()
    exists[0] = True
    with contextlib.redirect_stdout(io.StringIO()):
        kit_secrets_sync.main(argv, runner=runner)
    check(not any('--method' in c[0] for c in calls), "se modificó un Environment que ya existía")
    calls.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        wrong = kit_secrets_sync.main(['--env', 'kit-weekly-otro-canal'] + argv[2:], runner=runner)
    check(wrong == 1 and not calls, "se cargó el token de un canal en el Environment de otro")
    check(kit_secrets_sync.shared_values(shared, os.path.join(tmp, 'no.json'), {},
                                         ask=lambda _p: '') == SECRETS
          and kit_secrets_sync.shared_values(os.path.join(tmp, 'no.json'),
                                             os.path.join(tmp, 'no.json'), {},
                                             ask=lambda _p: '') == {},
          "un prompt vacío debe dejar el secreto sin tocar")
    ignored = __import__('subprocess').run(
        ['git', 'check-ignore', '-q', kit_secrets_sync.SHARED_FILE], cwd=ROOT).returncode
    check(ignored == 0, "tokens/kit_secrets.json no está ignorado por git")


def main():
    # Sin gh real ni llavero de Windows (core/cloud_fakes).
    from core import cloud_login, gh_status
    from core.cloud_fakes import FakeGhRun, MemoryKeyring
    gh_status.set_default(gh_status.GhStatus(run=FakeGhRun()))
    cloud_login.set_backend(MemoryKeyring())
    kit_source.download_pack_files = base._fake_download
    youtube.upload = base._fake_upload
    saved = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith('KIT_')}
    panel = True
    try:
        with tempfile.TemporaryDirectory() as tmp:
            a, b = _check_paths()
            _check_runs(a, b, tmp)
            _check_schedule()
            dbx = _check_setup(a, b)
            panel = _check_panel(dbx, a, b)
            _check_secrets(tmp)
    except Exception as exc:  # noqa: BLE001
        FAILS.append(f"excepción: {type(exc).__name__}: {exc}")
    finally:
        os.environ.update(saved)
    printed = OUTPUT.getvalue()
    check(not any(v in printed for v in list(SECRETS.values()) + [YT_REFRESH]),
          "apareció un secreto en la salida")
    if FAILS:
        for msg in FAILS:
            print('FAIL:', msg)
        return 1
    print('OK: smoke_kit_multichannel' + ('' if panel else ' (panel omitido: sin PyQt5)'))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
