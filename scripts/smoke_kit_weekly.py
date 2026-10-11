#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Smoke del worker semanal con fakes de Dropbox, YouTube, render y Telegram (sin red)."""

import contextlib
import io
import json
import os
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, 'scripts')
for path in (ROOT, SCRIPTS):
    if path not in sys.path:
        sys.path.insert(0, path)

from smoke_kit_state import FakeDropbox  # también instala el doble de dropbox.files si falta

from core import kit_notify, kit_source, kit_state, youtube
import run_kit_weekly

# Miércoles 10:00 hora de Buenos Aires: slots mié, vie y lun (18:00).
NOW = datetime(2026, 10, 7, 10, 0)
EXPECTED_UTC = ['2026-10-07T21:00:00Z', '2026-10-09T21:00:00Z', '2026-10-12T21:00:00Z']
PACK_NAMES = [f'SmokePack{i}' for i in range(5)]
FAKE_TOKEN = 'SMOKE-TELEGRAM-TOKEN-123'


class FakeTelegram:
    def __init__(self):
        self.sent = []

    def send(self, text, photo=None):
        self.sent.append(text)


class Counters:
    uploads = 0
    renders = 0
    publish_ats = []
    fail_on_upload = None       # número de subida (1-based) que levanta error
    reject_schedule = False     # simula cuenta sin auditoría: publishAt rechazado


def _packs(*_a, **_k):
    out = []
    for name in PACK_NAMES:
        out.append({
            'name': name,
            'dropbox_path': f'/smoke/{name}',
            # 16 loops: un video usa 5 y quedan de sobra, así el kit no cierra el ciclo.
            'loops': [{'name': f'L{j}.wav', 'path': f'/smoke/{name}/l{j}.wav'} for j in range(16)],
            'images': [{'name': 'a.png', 'path': 'a.png', 'source': 'local'}],
        })
    return out


def _fake_download(paths, dest_dir, dbx=None):
    out = []
    os.makedirs(dest_dir, exist_ok=True)
    for p in paths:
        local = os.path.join(dest_dir, os.path.basename(p))
        if p.startswith('/refs/'):  # portada modelo y fondos del modo template
            from PIL import Image
            Image.new('RGB', (64, 64), (30, 60, 90)).save(local, 'PNG')
        else:
            open(local, 'wb').close()
        out.append(local)
    return out


def _fake_cut(plan, dest_dir, local_fn=None):
    os.makedirs(dest_dir, exist_ok=True)
    out = []
    for i, _seg in enumerate(plan['segments']):
        out.append(os.path.join(dest_dir, f'seg_{i:02d}.wav'))
        open(out[-1], 'wb').close()
    return out


def _fake_render(image, wavs, out):
    Counters.renders += 1
    open(out, 'wb').close()
    return out


def _fake_upload(channel, video, title, description='', tags=None, thumbnail=None,
                 privacy='private', publish_at=None, **_k):
    Counters.uploads += 1
    if Counters.fail_on_upload == Counters.uploads:
        raise RuntimeError('boom con datos privados SmokePack0')
    if publish_at and Counters.reject_schedule:
        raise youtube.YouTubeError('publishAt no permitido')
    Counters.publish_ats.append(publish_at)
    vid = f'vid{Counters.uploads:03d}'
    return {'youtube_id': vid, 'url': f'https://youtu.be/{vid}', 'privacy': privacy,
            'thumbnail_error': ''}


def _reset(**kw):
    Counters.uploads = Counters.renders = 0
    Counters.publish_ats = []
    Counters.fail_on_upload = kw.get('fail_on_upload')
    Counters.reject_schedule = kw.get('reject_schedule', False)


def _config(out_dir):
    return {'kit_preview': {'dropbox_root': '/smoke', 'output_dir': out_dir,
                            'pack_cooldown_days': 30}}


def _run(dbx, tg, out_dir, dry_run=False, now=NOW, config=None, extra_hooks=None):
    hooks = {'list_packs_fn': _packs, 'render_fn': _fake_render, 'cut_fn': _fake_cut,
             'end_fn': lambda path, **_k: 28.0, **(extra_hooks or {})}
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = run_kit_weekly.run_weekly(
            app_config=config or _config(out_dir), channel='canal-smoke', channel_templates={},
            dbx=dbx, dry_run=dry_run, now=now, seed=1, notifier=tg, hooks=hooks,
            output_dir=out_dir)
    return code, buf.getvalue()


def _check_notify():
    """kit_notify: links de Studio, alerta sin datos y token fuera de los errores."""
    text = kit_notify.summary([{'youtube_id': 'abc123', 'title': 'T', 'slot': NOW}])
    if 'https://studio.youtube.com/video/abc123/edit' not in text:
        return "summary no trae el link de Studio"
    msg = kit_notify.alert(RuntimeError('dato privado'), step='preview 2/3')
    if 'dato privado' in msg or 'preview 2/3' not in msg:
        return "alert filtra el mensaje o no nombra el paso"

    import urllib.request
    real = urllib.request.urlopen

    def boom(req, timeout=None):
        raise OSError(req.full_url)  # el texto de este error trae la URL con el token

    urllib.request.urlopen = boom
    try:
        kit_notify.send('hola', env={kit_notify.ENV_TOKEN: FAKE_TOKEN, kit_notify.ENV_CHAT: '1'})
        return "send no levantó error"
    except kit_notify.KitNotifyError as e:
        if FAKE_TOKEN in str(e) or FAKE_TOKEN in repr(e.__cause__):
            return "el token apareció en el error"
    finally:
        urllib.request.urlopen = real
    try:
        kit_notify.send('hola', env={})
        return "send sin credenciales no levantó error"
    except kit_notify.KitNotifyError:
        pass
    return None


def _check_template(out_dir):
    """Portada por plantilla: el máximo por corrida corta, pasa a manual y el gasto queda guardado."""
    from PIL import Image
    from core import kit_spend, kit_template_art
    calls = []

    def art_client(prompt, image_paths, cfg):
        calls.append(prompt)
        buf = io.BytesIO()
        Image.new('RGB', (64, 64), (200, 40, 40)).save(buf, 'PNG')
        return buf.getvalue()

    def list_folder(folder, dbx=None):
        if folder.endswith('/fondos'):
            return [{'name': f'f{i}.jfif', 'path': f'{folder}/f{i}.jfif', 'is_folder': False}
                    for i in range(5)]
        return [{'name': 'modelo.png', 'path': folder + '/modelo.png', 'is_folder': False}]

    config = _config(out_dir)
    config['kit_preview'].update({
        'cover_mode': 'template', 'names': {'genre': 'genero smoke', 'enabled': False},
        'art': {'refs_root': '/refs', 'verify': {'enabled': False}},
        'spend': {'max_images_per_run': 2, 'image_cost_usd': 0.25}})
    real = kit_template_art.list_folder
    kit_template_art.list_folder = list_folder
    try:
        _reset()
        dbx, tg = FakeDropbox(), FakeTelegram()
        code, log = _run(dbx, tg, out_dir, config=config, extra_hooks={'art_client': art_client,
                                                                      'art_notify': tg.send})
    finally:
        kit_template_art.list_folder = real
    state = kit_state.load(dbx=dbx)
    if code != 0 or Counters.uploads != 3:
        return f"template: code={code} subidas={Counters.uploads}"
    if len(calls) != 2:
        return f"template: el máximo por corrida no cortó ({len(calls)} pedidos)"
    month = kit_spend.month_entry(state, kit_spend.month_key(NOW))
    if month != {'usd': 0.5, 'images': 2, 'verifications': 0}:
        return f"template: gasto del mes mal guardado: {month}"
    refs = [r.get('ref_images') for r in state['runs']]
    if sum(1 for r in refs if r) != 2 or len({r[0] for r in refs if r}) != 2:
        return f"template: los fondos usados no quedaron en el estado: {refs}"
    caps = [t for t in tg.sent if 'máximo de imágenes' in t]
    if len(caps) != 1 or len(tg.sent) != 2:
        return f"template: debía haber un aviso del tope y el resumen: {tg.sent}"
    if any(name in t for t in caps + [log] for name in PACK_NAMES):
        return "template: un aviso o el log nombra un kit"
    return None


def main():
    import tempfile
    kit_source.download_pack_files = _fake_download
    youtube.upload = _fake_upload

    err = _check_notify()
    if err:
        return _fail(err)

    # El cálculo de slots no depende del reloj del sistema (Actions corre en UTC).
    slots = run_kit_weekly.upcoming_slots(NOW, list(run_kit_weekly.DEFAULT_SLOTS))
    if [s.strftime('%a %H:%M') for s in slots] != ['Wed 18:00', 'Fri 18:00', 'Mon 18:00']:
        return _fail(f"slots inesperados: {slots}")

    with tempfile.TemporaryDirectory() as out_dir:
        # 1) Semana normal: 3 slots, 3 kits distintos, lock liberado, un resumen.
        _reset()
        dbx, tg = FakeDropbox(), FakeTelegram()
        code, log = _run(dbx, tg, out_dir)
        state = kit_state.load(dbx=dbx)
        paths = [r['pack_id'] for r in state['runs']]
        if code != 0 or Counters.uploads != 3 or len(set(paths)) != 3:
            return _fail(f"semana normal: code={code} subidas={Counters.uploads} packs={paths}")
        if Counters.publish_ats != EXPECTED_UTC:
            return _fail(f"publishAt en UTC incorrecto: {Counters.publish_ats}")
        if state['lock'] is not None:
            return _fail("el lock quedó tomado")
        if len(tg.sent) != 1 or tg.sent[0].count('https://studio.youtube.com/video/') != 3:
            return _fail(f"resumen de Telegram incorrecto: {tg.sent}")
        if any(name in log for name in PACK_NAMES):
            return _fail("el log imprimió un nombre de kit")

        # 2) Segunda corrida de la misma semana: no duplica nada.
        before = Counters.uploads
        code, _ = _run(dbx, FakeTelegram(), out_dir)
        if code != 0 or Counters.uploads != before:
            return _fail("la segunda corrida volvió a subir")

        # 2b) Cuenta sin auditoría: subida privada (sin publishAt) tampoco se duplica.
        _reset(reject_schedule=True)
        dbx2 = FakeDropbox()
        code, _ = _run(dbx2, FakeTelegram(), out_dir)
        runs = kit_state.load(dbx=dbx2)['runs']
        if code != 0 or any(r['estado'] != 'private_pending' for r in runs) or len(runs) != 3:
            return _fail("la subida privada no quedó como private_pending")
        before = Counters.uploads
        _run(dbx2, FakeTelegram(), out_dir)
        if Counters.uploads != before:
            return _fail("una subida privada se duplicó en la segunda corrida")

        # 3) Error de subida en el slot 2: alerta, resumen parcial y lock liberado.
        _reset(fail_on_upload=2)
        dbx3, tg3 = FakeDropbox(), FakeTelegram()
        code, log = _run(dbx3, tg3, out_dir)
        alerts = [t for t in tg3.sent if 'fallo el worker' in t]
        if code != 1 or len(alerts) != 1 or 'preview 2/3' not in alerts[0]:
            return _fail(f"el error no mandó la alerta esperada: code={code} {tg3.sent}")
        if 'SmokePack' in alerts[0] or 'SmokePack' in log or 'boom' in log:
            return _fail("la alerta o el log filtran datos privados")
        if kit_state.load(dbx=dbx3)['lock'] is not None:
            return _fail("tras el error el lock quedó tomado")
        if Counters.uploads != 2:
            return _fail("tras el error siguió subiendo")

        # 3b) Video subido pero el estado no se guarda: el aviso trae su link.
        _reset()
        dbx3b, tg3b = FakeDropbox(), FakeTelegram()
        orig = kit_state.record_run

        def broken(*a, **k):
            raise RuntimeError('estado caido')
        kit_state.record_run = broken
        try:
            code, _ = _run(dbx3b, tg3b, out_dir)
        finally:
            kit_state.record_run = orig
        if code != 1 or not any('video/vid001/edit' in t for t in tg3b.sent):
            return _fail(f"no avisó el video sin registrar: {tg3b.sent}")
        if kit_state.load(dbx=dbx3b)['lock'] is not None:
            return _fail("lock tomado tras fallo de estado")

        # 4) Dry-run: no renderiza, no sube, no escribe en Dropbox.
        _reset()
        dbx4, tg4 = FakeDropbox(), FakeTelegram()
        code, _ = _run(dbx4, tg4, out_dir, dry_run=True)
        if code != 0 or Counters.uploads or Counters.renders or dbx4.uploads:
            return _fail(f"dry-run tocó algo externo: subidas={Counters.uploads} "
                         f"renders={Counters.renders} dropbox={dbx4.uploads}")
        if len(tg4.sent) != 1 or '3 kit(s) distintos' not in tg4.sent[0]:
            return _fail(f"dry-run no eligió 3 kits distintos: {tg4.sent}")

        # 5) Lock ajeno vigente: no corre y no lo libera.
        _reset()
        dbx5, tg5 = FakeDropbox(), FakeTelegram()
        kit_state.acquire_lock(owner='otro', dbx=dbx5)
        code, _ = _run(dbx5, tg5, out_dir)
        lock = kit_state.load(dbx=dbx5)['lock']
        if code != 1 or Counters.uploads or not lock or lock['owner'] != 'otro':
            return _fail("con lock ajeno el worker corrió o lo liberó")
        if not tg5.sent or 'lock' not in tg5.sent[0]:
            return _fail("con lock ajeno no hubo alerta")

        err = _check_template(out_dir)
        if err:
            return _fail(err)

        # 6) Nada de secretos/tokens en el estado guardado.
        blob = json.dumps(kit_state.load(dbx=dbx))
        if FAKE_TOKEN in blob:
            return _fail("el estado contiene un token")

    print('OK: smoke_kit_weekly')
    return 0


def _fail(msg):
    print('FAIL:', msg)
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
