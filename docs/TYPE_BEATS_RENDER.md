# Type Beats — Fase 4 completada (revisión aplicada)

`core/beat_video.py` prepara un job ya reservado; no planifica nuevos jobs ni consume
intentos de subida. No importa módulos YouTube ni Loopkits. `main.py` permanece
sin cambios. La fase y la corrección visual se cerraron el 2026-10-12 después de
la revisión y las correcciones, con 102 tests aprobados. Sin commit por instrucción
explícita del usuario.

## Configuración y estado

En `/type-beats/config.json`, cada canal puede definir `genres` y un mapa
`dropbox_images` por género. Las carpetas son explícitas y se listan sin recursión:

```json
{"id":"channel-example", "genres":["trap"],
 "dropbox_images":{"trap":"/type-beats/images/channel-example/trap"}}
```

Se mantienen los campos de Fase 2 (`active`, `priority`, `slots`, etc.). Esto es
configuración remota; `images_folder` del panel permite elegir imágenes locales.
Si hay una carpeta Dropbox para el género, se mantiene su catálogo y rotación.
Credenciales exclusivas: `BEAT_DROPBOX_APP_KEY` y `BEAT_DROPBOX_REFRESH_TOKEN`.
La app Dropbox necesita lectura de contenido y metadata.

El panel de Beats permite configurar, **por canal**, imagen fija o montaje,
carpeta de videos local/Dropbox, segundos mínimo/máximo del fragmento y archivo
de miniatura local/Dropbox. Las carpetas de imágenes Dropbox se cargan como
`género=carpeta`, una por línea. Sin `visual.mode` se utiliza **imagen fija**.
Los campos existentes conservan su significado; no se modifican otras secciones.

```json
{"visual":{
  "mode":"video", "video_source":"dropbox",
  "videos_folder":"/type-beats/videos/channel-example",
  "clip_min_seconds":3, "clip_max_seconds":6,
  "thumbnail_source":"dropbox",
  "thumbnail_path":"/type-beats/thumbnails/channel-example.png"
}}
```

`mode`: `image` o `video`. `video_source`: `local` o `dropbox`.
`thumbnail_source`: `auto` (default), `local` o `dropbox`.
Con miniatura automática se usa la imagen fija o un frame del primer fragmento.
Una miniatura configurada se usa independientemente del modo visual, con el título.

El audio principal se resuelve de nuevo desde el perfil público configurado
(`beatstars_profile_url`), comprobando track ID y propietario. No se almacenan
URLs firmadas. Solo cuando el preview no está disponible o falla la conexión,
se permite esta asociación explícita en `/type-beats/state.json`:

```json
{"audio_associations":{"TK101":{
  "track_id":"TK101", "path":"/type-beats/audio/track.mp3", "duration":180
}}}
```

Sin asociación no hay fallback ni búsqueda por título. Un rechazo de seguridad
no activa el fallback. MP3/WAV en Dropbox, sin links compartidos; descarga fijada
a la revisión obtenida de metadata y con cierre de la respuesta en `finally`.
Estos campos son opcionales y compatibles con el esquema 1 existente.

## Validaciones y límites

- HLS: HTTPS, host exacto `content.beatstars.com`, puerto 443, sin credenciales,
  fragmentos, cookies, proxies del entorno ni redirects (ni siquiera entre hosts
  permitidos). También se comprueban los hosts de variantes y segmentos.
- Manifiestos de hasta 256 KiB, MIME HLS u octet-stream **y** firma `#EXTM3U`.
  Hasta tres niveles y 500 segmentos. Solo VOD terminado, sin cifrado,
  mapas fMP4, byte ranges ni pistas alternativas. Esos formatos fallan cerrados.
- Segmentos de hasta 8 MiB; audio total hasta 80 MiB; firma MPEG-TS, ADTS,
  MP3 o WAV. Descarga HLS hasta 180 s, timeout de socket hasta 10 s.
- Duración de 1–900 s; comparación manifiesto/metadata/ffprobe con tolerancia
  de 3 s o 3%. Un único stream de audio y decodificación completa obligatoria
  antes del render. FFmpeg/ffprobe reciben solo archivos locales con demuxer
  explícito y whitelist `file`, subprocess sin shell, con timeout y errores fijos.
  Se excluyen variables de credenciales de su entorno; no se imprimen stderr ni URLs.
- Imágenes JPEG/PNG/WebP: 20 MiB, 25 millones de píxeles, al menos 320×180,
  un solo frame y decodificación completa con Pillow antes de FFmpeg. El catálogo
  pagina hasta diez veces y admite hasta 5000 imágenes por carpeta.

Los plazos globales de descarga se comprueban entre lecturas; una lectura en
curso puede consumir el timeout de socket. No se ofrece interrupción instantánea.

## Rotación, render y temporales

La rotación es independiente por canal y género: primero imágenes sin uso,
luego la usada hace más jobs, con desempate por ruta. `image_rotation` conserva
hasta 5000 selecciones por canal/género. Un reintento del mismo job conserva ruta
y revisión; si el archivo cambió o desapareció, falla. Se registra únicamente
tras render exitoso, por CAS y lease con vencimiento y comprobación de propietario.
Un render fallido no consume una imagen. No se cambia el status del job.

Imagen adaptada a 1920×1080 y completamente fija durante todo el beat: sin zoom,
movimiento, efectos ni animaciones. Texto pintado con Pillow (sin interpolarlo
en filtros), H.264/AAC y miniatura JPEG 1280×720. Textos extensos se limitan a tres
líneas. El lease máximo es 3600 s; render y decodificación tienen timeouts de 1200
y 180 s, respectivamente.

Revisión aplicada: los borradores visuales inválidos se conservan al cambiar de
canal y no se guardan hasta corregirlos. Se rechazan rangos que no contienen un
cuadro a 30 FPS. El montaje renueva el lease entre recursos y antes de concatenar
y renderizar; si perdió el propietario, aborta. Al alcanzar el presupuesto de
bytes se prueban recursos siguientes más pequeños. Un error al liberar el lock
no reemplaza el error original; los temporales igualmente se eliminan.

El montaje (`core/beat_montage.py`) elige una secuencia determinista por reserva
de hasta 12 recursos únicos MP4/MOV/MKV/WebM, locales o Dropbox (sin recursión).
Máximo 150 MiB por recurso y 512 MiB en total. Valida firma, stream, duración,
resolución, FPS y códec; recorta un fragmento de cada recurso válido, entre los
límites configurados (0.5–30 s). Archivos dañados/incompatibles se descartan; si
ninguno sirve, falla. Fallos de descarga o herramientas abortan la corrida.

Normaliza cada fragmento a 1920×1080, 30 FPS, H.264/yuv420p, SAR 1, sin audio,
subtítulos ni metadata. Verifica los fragmentos antes de concatenarlos. Repite
la secuencia en loop y corta video y audio a la duración del beat con `-t`/`atrim`.
El plan cubre exactamente esa duración, incluido el fragmento final parcial.
La comprobación del archivo admite la precisión de un cuadro (1/30 s) del MP4.
Con dos o más recursos válidos, ni los vecinos ni el final/inicio del loop repiten
el mismo fragmento. Con uno solo se repite ese recurso. Únicamente el audio del
beat se mapea a la salida; el audio de los videos se elimina antes del concat.

`render_reserved(...)` es un context manager: audio, imagen, frame, miniatura y
video viven en `TemporaryDirectory`. El consumidor debe usar los resultados
**dentro** del `with`; al salir, incluso ante un error del consumidor, se borran.
No hay exportación permanente en esta fase. El lease se libera en `finally`;
si Dropbox no permite liberarlo, vence por tiempo. Una salida abrupta del proceso
o apagado del equipo queda fuera de la garantía de limpieza de excepciones.

## Ejecución y pruebas

```powershell
.venv\Scripts\python.exe scripts\smoke_beat_video.py
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_beat_*.py"
# Opcional: incluye los dos tests con FFmpeg real (sin red).
$env:BEAT_REAL_FFMPEG_SMOKE = '1'
.venv\Scripts\python.exe -m unittest discover -s tests -p "test_beat_montage.py"
.venv\Scripts\python.exe scripts\render_type_beat.py --job-id '<identidad reservada>' --track track.json --genre trap --dry-run
.venv\Scripts\python.exe scripts\render_type_beat.py --job-id '<identidad reservada>' --track track.json --genre trap --config config/app_config.json --dry-run
```

El CLI usa config/estado remoto y un JSON de metadata del catálogo. `--config`
permite usar las opciones por canal guardadas en el panel local, sin sincronizar
ni escribir la configuración remota. Dry-run lee la reserva y los catálogos del
modo elegido, sin lock, descarga, render ni escrituras.
Sin `--dry-run` valida/renderiza y borra los resultados al terminar; sirve como
prueba operativa, no como exportador o publicador. Para inspeccionar o consumir
los artefactos desde otro módulo, usar `render_reserved` dentro de un `with`.

Los smokes predeterminados no usan red, credenciales ni binarios reales: HLS falso,
cliente con forma del SDK oficial Dropbox y procesos FFmpeg/ffprobe falsos. Cubren hosts,
redirects, MIME, tamaño, duración, decodificación, fallback explícito, paginación
HLS, rotación y limpieza. Las pruebas de montaje agregan imagen estática, corte
final y loop sin vecinos repetidos, descarte del audio original, normalización,
carpetas vacías, recursos dañados/incompatibles, miniaturas y persistencia por canal.
Se verificaron contra el servicio real únicamente
el campo público `bundle.hls.url`, su host y el formato del manifiesto; no se
descargaron segmentos ni se probó Dropbox autenticado. Los dos tests opcionales
con FFmpeg real verifican hashes idénticos para imagen fija, loop de dos colores,
45 cuadros para 1.5 s y eliminación efectiva del audio original. Como falta
ffprobe en este equipo, usan metadata falsa de fixtures generados conocidos;
la decodificación y el análisis de cuadros/audio sí usan FFmpeg real.
