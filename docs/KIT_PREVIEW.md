# Previews automáticos de loop kits

Una corrida elige un pack en Dropbox, arma un video 16:9 (imagen fija + audio) y lo sube al canal de la sección **loop kits**, programado en el próximo slot configurado.

## Audio

El audio se arma siempre con loops del kit: se eligen entre 6 y 8 (o todos si hay menos), se corta cada uno al primer silencio (`core/kit_trim`) y se concatenan en orden aleatorio. Un archivo con `preview` o `tag` en el nombre no es un loop y se ignora.

La imagen es una foto hecha a mano del kit; con `kit_preview.cover_mode: "auto"` el fondo se genera y el kit no necesita imágenes propias.

## Carpetas

`kit_preview.dropbox_root` es la carpeta de la tienda. Adentro hay **categorías** y, dentro de cada una, una carpeta por kit:

```text
<dropbox_root>/
  <categoría>/
    <kit>/
      LOOPS/        loops (mp3/wav)
      images/       opcional: jpg, jpeg, png, webp
      ...           drum kit, midis, starters, vocals, phrases, stems: no se recorren
```

- **Categorías:** se recorren las de `kit_preview.scan_folders`, en ese orden. Una categoría que no está en la lista no se toca. Con `"scan_folders": []` los kits cuelgan directo de `dropbox_root`.
- **Loops:** los audios de la subcarpeta del kit que se llame como alguna de `kit_preview.loops_dirs` (nombre exacto, sin distinguir mayúsculas: `LOOPS`, `Loops`). Una carpeta que solo contiene la palabra, como `Drum Loops`, no cuenta. Si el kit no tiene esa subcarpeta, valen los audios de su raíz.
- **Nombres ignorados:** los archivos con alguna palabra de `kit_preview.ignore_names` como palabra suelta (`Kit TAG.wav`, `kit_preview.mp3`; `Vintage.wav` no).
- **mp3 y wav del mismo loop:** cuentan una vez y se usa el wav.
- **Bundles:** una carpeta sin loops se recorre hacia adentro hasta `kit_preview.scan_max_depth` niveles; ahí adentro un kit tiene que tener su subcarpeta de loops.
- **Imágenes:** subcarpeta `images/` del kit. Si no existe, la app usa los archivos locales de `kit_preview.local_images_root/<nombre-del-kit>/`.

Ver también [DROPBOX_SETUP.md](DROPBOX_SETUP.md).

## Config (`config/app_config.json`)

```json
"kit_preview": {
  "dropbox_root": "/loop_kits",
  "scan_folders": ["Individual Kits", "Production Suites", "Genre Bundles", "free kits"],
  "loops_dirs": ["loops"],
  "ignore_names": ["tag", "preview"],
  "scan_max_depth": 3,
  "min_loops_per_video": 4,
  "local_images_root": "images/loop_kits",
  "pack_cooldown_days": 30,
  "loops_min": 6,
  "loops_max": 8
}
```

Los valores de `scan_folders`, `loops_dirs`, `ignore_names` y `scan_max_depth` del ejemplo son los que se usan si la clave falta. Se editan desde el panel de la app ("Carpeta de kits en Dropbox"), que los guarda en la config del canal en Dropbox.

- Al menos un canal con `"section": "loop_kits"` en `channels`.
- Slots de publicación: opcional `kit_preview.slots` como lista de `{ "weekday": 0, "hour": 18, "minute": 0 }` (lunes=0). Si falta, lun/mié/vie 18:00 local.
- Salida de video: `exported_videos/loop_kits/` (o `kit_preview.output_dir`).

## Comando

Desde la raíz del repo (con Dropbox y YouTube ya conectados):

```text
python scripts/run_kit_preview.py
python scripts/run_kit_preview.py --dry-run
python scripts/run_kit_preview.py --channel MiCanalKits
```

`--dry-run` imprime pack, loops elegidos e imagen; **no** renderiza video ni sube a YouTube.

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
python scripts/smoke_kit_scan.py
```
