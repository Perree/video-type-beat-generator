#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Migración única de ``config/app_config.json`` al registro de Dropbox.

Arma ``/automatizacion/canales.json`` (canales de Beats y Loops, con sus plantillas) y
``/automatizacion/ajustes.json``. La sección ``personal`` se ignora. Un canal sin ``section``
(o con una desconocida) NO se migra como Beats: se informa como "tipo sin definir" y se omite.
Slugs: Beats usa su ``actions_slug`` de ``beat_automation``; Loops, ``kit_channel.slug`` del
nombre. El canal de kits por defecto (``kit_preview.channel`` o ``--kits-default``) sale con
``legacy_default: true``. Un slug repetido o inválido aborta todo.

Uso (ver docs/CLOUD_ONLY_SPIKE.md y docs/TYPE_BEATS_CHANNELS.md):
    py -3 scripts/migrate_to_cloud.py                      # dry-run: solo imprime
    py -3 scripts/migrate_to_cloud.py --kits-default WyreSounds
    py -3 scripts/migrate_to_cloud.py --apply              # escribe solo si no existe
    py -3 scripts/migrate_to_cloud.py --apply --force      # reemplaza usando el rev actual

Nunca escribe ``config/app_config.json`` ni lee ``tokens/`` (salvo la credencial de Dropbox de
``beat_panel_cloud.local_transport`` al usar ``--apply``). No imprime secretos.
"""
import argparse
from datetime import datetime, timezone
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import channel_kind, cloud_registry, kit_channel, kit_publish, kit_spend  # noqa: E402
from core.beat_actions import TRUSTED_REPOSITORY  # noqa: E402
from core.beat_cloud import CloudError, Conflict  # noqa: E402
from core.beat_settings import read_app  # noqa: E402

CONFIG_FILE = os.path.join(ROOT, 'config', 'app_config.json')
# Defaults de ajustes.json (spike §8): kit_spend.DEFAULTS, kit_publish.DEFAULT_SLOTS y el
# horario que crea beat_panel.add_channel.
SPEND_DEFAULTS = {key: kit_spend.DEFAULTS[key] for key in ('monthly_cap_usd', 'max_images_per_run')}
BEAT_SLOTS = [{'weekday': 0, 'hour': 18, 'minute': 0}]
LOOP_SLOTS = [dict(slot) for slot in kit_publish.DEFAULT_SLOTS]


class MigrationError(Exception):
    """Aborta la migración; el mensaje no lleva secretos."""


def _templates(cfg):
    out = {}
    for key in cloud_registry.TEMPLATE_KEYS:
        if isinstance(cfg.get(key), str):
            out[key] = cfg[key]
    tags = cfg.get('tags')
    if isinstance(tags, list) and all(isinstance(t, str) for t in tags):
        out['tags'] = list(tags)
    return out


def build(app, kits_default=None, now=None):
    """``(canales, ajustes, informe)`` a partir de ``app_config``. Levanta MigrationError."""
    if not isinstance(app, dict):
        raise MigrationError('app_config no es un objeto JSON.')
    stamp = (now or datetime.now(timezone.utc)).strftime('%Y-%m-%dT%H:%M:%SZ')
    channels = app.get('channels') if isinstance(app.get('channels'), dict) else {}
    automation = app.get('beat_automation') if isinstance(app.get('beat_automation'), dict) else {}
    beat_rows = {row.get('id'): row for row in automation.get('channels') or []
                 if isinstance(row, dict)}
    kits_default = kits_default or ((app.get('kit_preview') or {}).get('channel') or None)
    if kits_default is not None and kits_default not in channels:
        raise MigrationError('El canal de kits por defecto no está en channels.')
    report = {'migrados': [], 'omitidos': [], 'avisos': []}
    rows, slugs = [], {}
    for name, cfg in channels.items():
        cfg = cfg if isinstance(cfg, dict) else {}
        legacy = name == kits_default
        if legacy:
            tipo = channel_kind.LOOPS
            if cfg.get('section') != 'loop_kits':
                report['avisos'].append(f'{name}: section={cfg.get("section")!r} corregida a '
                                        'loops (canal de kits por defecto).')
        else:
            try:
                tipo = channel_kind.from_section(cfg.get('section'))
            except channel_kind.ChannelKindError:
                report['omitidos'].append({'canal': name, 'motivo': 'tipo sin definir'})
                continue
            if tipo is None:
                report['omitidos'].append({'canal': name, 'motivo': 'sección personal (ignorada)'})
                continue
        if tipo == channel_kind.BEATS:
            slug = (beat_rows.get(name) or {}).get('actions_slug')
            if not slug:
                report['omitidos'].append({'canal': name, 'motivo': 'Beats sin actions_slug en '
                                           'beat_automation (no hay slug en el inventario)'})
                continue
        else:
            slug = kit_channel.slug(name)
        try:
            channel_kind.check_slug(slug)
        except channel_kind.ChannelKindError:
            raise MigrationError(f'Slug inválido para el canal {name!r}.') from None
        if slug in slugs:
            raise MigrationError(f'Slug repetido {slug!r}: {slugs[slug]!r} y {name!r}.')
        slugs[slug] = name
        active = (beat_rows.get(name) or {}).get('active', True) if tipo == channel_kind.BEATS else True
        rows.append({'slug': slug, 'tipo': tipo, 'clave': name, 'nombre': name,
                     'activo': active is True, 'legacy_default': legacy,
                     'plantillas': _templates(cfg), 'creado': stamp})
        report['migrados'].append({'canal': name, 'slug': slug, 'tipo': tipo,
                                   'legacy_default': legacy})
    for cid in beat_rows:
        if cid not in channels:
            report['omitidos'].append({'canal': cid, 'motivo': 'en beat_automation sin ficha en '
                                       'channels (tipo sin definir)'})
    canales = cloud_registry.empty('canales')
    canales['canales'] = rows
    try:
        canales = cloud_registry.normalize('canales', canales)
    except ValueError as exc:
        raise MigrationError(f'Registro inválido: {exc}') from None
    ajustes = dict(cloud_registry.empty('ajustes'),
                   beatstars={'profile_url': str(automation.get('beatstars_profile_url') or '')},
                   gasto_kits_default=dict(SPEND_DEFAULTS),
                   horarios_default={'beats': BEAT_SLOTS, 'loops': LOOP_SLOTS},
                   zona_horaria='America/Argentina/Buenos_Aires',
                   github={'repo': TRUSTED_REPOSITORY, 'rama': 'master'})
    return canales, cloud_registry.normalize('ajustes', ajustes), report


def apply(documents, transport, force=False):
    """Escribe cada documento. Sin ``force`` solo crea (rev None = add). Devuelve líneas."""
    registry = cloud_registry.CloudRegistry(transport)
    lines, ok = [], True
    for kind, doc in documents:
        current, rev = registry.read(kind)
        if rev is not None and not force:
            lines.append(f'{kind}: ya existe en Dropbox; no se escribió (usá --force).')
            ok = False
            continue
        try:
            registry.write(kind, doc, rev if force else None, current if rev is not None else None)
        except Conflict:
            lines.append(f'{kind}: cambió durante la migración; no se escribió. Repetí.')
            ok = False
            continue
        again, _ = registry.read(kind)
        verified = again == cloud_registry.normalize(kind, doc)
        lines.append(f'{kind}: escrito en {cloud_registry.PATHS[kind]}; '
                     f'releído {"y verificado" if verified else "PERO DISTINTO"}.')
        ok = ok and verified
    return ok, lines


def main(argv=None, transport_factory=None, out=None):
    out = out or sys.stdout
    if hasattr(out, 'reconfigure'):
        out.reconfigure(errors='replace')
    parser = argparse.ArgumentParser(description='Migra app_config.json al registro de Dropbox.')
    parser.add_argument('--config', default=CONFIG_FILE, help='Ruta a app_config.json (solo lectura).')
    parser.add_argument('--kits-default', help='Canal de kits por defecto (legacy_default).')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--dry-run', action='store_true', help='Solo imprime (por defecto).')
    mode.add_argument('--apply', action='store_true', help='Escribe si el destino no existe.')
    parser.add_argument('--force', action='store_true', help='Con --apply: usa el rev actual.')
    args = parser.parse_args(argv)
    if args.force and not args.apply:
        parser.error('--force solo va con --apply')
    try:
        if not os.path.isfile(args.config):
            raise MigrationError('No existe el app_config indicado.')
        app = read_app(args.config)
        canales, ajustes, report = build(app, args.kits_default)
    except (MigrationError, ValueError, OSError) as exc:
        print(f'ABORTADO: {exc}', file=out)
        return 2
    print(json.dumps({'informe': report, 'canales.json': canales, 'ajustes.json': ajustes},
                     ensure_ascii=False, indent=2, sort_keys=True), file=out)
    if not args.apply:
        print('Dry-run: no se escribió nada. Para escribir: --apply.', file=out)
        return 0
    if transport_factory is None:
        from core.beat_panel_cloud import local_transport
        transport_factory = local_transport
    try:
        ok, lines = apply((('canales', canales), ('ajustes', ajustes)), transport_factory(),
                          force=args.force)
    except (CloudError, ValueError) as exc:
        print(f'No se pudo escribir en Dropbox: {exc}', file=out)
        return 1
    for line in lines:
        print(line, file=out)
    return 0 if ok else 3


if __name__ == '__main__':
    sys.exit(main())
