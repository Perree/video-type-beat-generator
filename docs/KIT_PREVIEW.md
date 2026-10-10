# Previews automáticos de loop kits

Una corrida elige un pack en Dropbox, arma un video 16:9 (imagen fija + audio) y lo sube al canal de la sección **loop kits**, programado en el próximo slot configurado.

## Dos vías de audio

1. **`named_preview`** (default si `kit_preview.prefer_named_preview` es true): en la raíz del pack hay un mp3/wav cuyo nombre contiene `preview` (sin distinguir mayúsculas). Ese archivo es **toda** la pista. No se corta por silencio ni se mezcla con otros loops.
2. **`assembled`**: no hay preview nombrada, o corrés con `--no-named-preview` / `prefer_named_preview: false`. Se eligen entre 6 y 8 loops (o todos si hay menos), se corta cada uno al primer silencio (`core/kit_trim`) y se concatenan en orden aleatorio.

La imagen es siempre una foto hecha a mano del pack (no se genera en la app).

## Carpetas

En Dropbox, `kit_preview.dropbox_root` tiene **una subcarpeta por pack**:

- Raíz del pack: loops (mp3/wav). Un archivo con `preview` en el nombre = pista completa, no loop.
- No se recorren `stems/` ni `layers/`.
- Imágenes: subcarpeta `images/` (jpg, jpeg, png, webp).

Si el pack **no** tiene `images/` en Dropbox, la app usa archivos locales en:

`kit_preview.local_images_root/<nombre-del-pack>/`

Creá esa carpeta en disco y copiá ahí las imágenes del pack.

Ver también [DROPBOX_SETUP.md](DROPBOX_SETUP.md).

## Config (`config/app_config.json`)

```json
"kit_preview": {
  "dropbox_root": "/loop_kits",
  "local_images_root": "images/loop_kits",
  "prefer_named_preview": true,
  "pack_cooldown_days": 30,
  "loops_min": 6,
  "loops_max": 8
}
```

- Al menos un canal con `"section": "loop_kits"` en `channels`.
- Slots de publicación: opcional `kit_preview.slots` como lista de `{ "weekday": 0, "hour": 18, "minute": 0 }` (lunes=0). Si falta, lun/mié/vie 18:00 local.
- Salida de video: `exported_videos/loop_kits/` (o `kit_preview.output_dir`).

## Comando

Desde la raíz del repo (con Dropbox y YouTube ya conectados):

```text
python scripts/run_kit_preview.py
python scripts/run_kit_preview.py --dry-run
python scripts/run_kit_preview.py --no-named-preview
python scripts/run_kit_preview.py --channel MiCanalKits
```

`--dry-run` imprime `audio_mode`, pack, archivos e imagen; **no** renderiza video ni sube a YouTube.

Si ya existe una corrida en estado `scheduled` o `uploaded` con el mismo `publish_at` del próximo slot, el script termina con código 0 sin elegir otro pack (útil si el Programador dispara dos veces).

## Programador de tareas (Windows)

Tres veces por semana, por ejemplo lun/mié/vie a las 17:00 (una hora antes del slot 18:00):

```text
schtasks /Create /TN "LoopKit Preview Lun" /TR "cmd /c cd /d D:\Proyectos\Softs\video-type-beat-generator && python scripts\run_kit_preview.py" /SC WEEKLY /D MON /ST 17:00
schtasks /Create /TN "LoopKit Preview Mie" /TR "cmd /c cd /d D:\Proyectos\Softs\video-type-beat-generator && python scripts\run_kit_preview.py" /SC WEEKLY /D WED /ST 17:00
schtasks /Create /TN "LoopKit Preview Vie" /TR "cmd /c cd /d D:\Proyectos\Softs\video-type-beat-generator && python scripts\run_kit_preview.py" /SC WEEKLY /D FRI /ST 17:00
```

Ajustá la ruta del proyecto y, si tenés varios canales loop kits, añadí `--channel Nombre`.

## YouTube sin auditoría

Si la cuenta no completó la auditoría de la YouTube Data API, `publishAt` puede ser rechazado. La app reintenta la misma subida en **privado** sin fecha y deja el registro en `private_pending`. Abrí YouTube Studio y publicá o programá el video a mano cuando corresponda.

Estado `scheduled`: subida privada con `publishAt` aceptado. Estado `uploaded`: uso manual futuro si lo registrás así.

## Smoke local (sin red)

```text
python scripts/smoke_kit_preview_dry.py
```
