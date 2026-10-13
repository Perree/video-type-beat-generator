# Type Beats — operación y hardening (Fase 8)

Guía para configurar, verificar y recuperar las Fases 1–7. El código operativo es
`core/beat_*`; `python main.py` / `run_app.bat` conserva el flujo manual. Esta fase
no habilita un workflow remoto ni realiza uploads reales. Las pruebas con servicios
falsos y FFmpeg local se distinguen de las verificaciones con servicios reales.

## Setup

1. Instalar Python 3.12 para el worker de Actions. Para escritorio, usar el entorno
   de la app con PyQt5; ejecutar desde la raíz del repo. Instalar dependencias:

   ```powershell
   .venv\Scripts\python.exe -m pip install -r requirements.txt
   .venv\Scripts\python.exe -m pip install --require-hashes -r requirements-worker.txt
   ```

   El segundo archivo es el lock compartido existente; esta fase no lo modifica.
   Instalar `ffmpeg` **y** `ffprobe` en `bin/` o PATH. Los binarios y credenciales
   están excluidos de Git. En Linux Actions instala ambos desde el paquete FFmpeg.
   Las [descargas de FFmpeg](https://ffmpeg.org/download.html) enlazan proveedores
   de Windows; verificar el checksum publicado del archivo descargado.

2. Crear una app Dropbox exclusiva de Beats, tipo App folder, con
   `files.metadata.read`, `files.content.read`, `files.content.write`. Obtener su
   refresh token por OAuth, con esos scopes y acceso offline. Usar las credenciales
   `BEAT_DROPBOX_APP_KEY` y `BEAT_DROPBOX_REFRESH_TOKEN`; nunca las de Loopkits.
   Todas las automatizaciones productivas de Beats comparten **la misma app y
   estado**. Separarlos por canal permitiría gastar seis intentos por cada archivo.

3. Preparar `/type-beats/config.json` a partir del panel local
   (`beat_automation` de `config/app_config.json`). Publicarlo explícitamente por
   CAS: el panel no sincroniza cambios automáticamente. Configurar perfil público,
   ID del canal, `active`, prioridad, slots, tags/SEO y recursos visuales. Agregar
   `youtube_channel_id` con el ID real `UC` + 22 caracteres del canal de YouTube.
   Para Actions, agregar `actions_slug` igual al slug de su Environment. Los slugs
   deben ser únicos: un secreto `BEAT_CHANNEL_ID` de otro Environment falla antes
   del render, también en dry-run. Cambiar el destino de YouTube durante una corrida
   bloquea el insert; pausar antes de modificar la cuenta.
   Es distinto del nombre/ID interno `BEAT_CHANNEL_ID`. El arranque real verifica
   `channels.list(mine=True)` contra ese ID antes de renderizar o consumir intentos.
   En Actions, imágenes, videos y miniaturas personalizadas deben estar en Dropbox;
   una ruta del escritorio no existe en el runner. Ver los campos en
   [render](TYPE_BEATS_RENDER.md), [SEO](TYPE_BEATS_SEO.md) y
   [rotación](TYPE_BEATS_ROTATION.md).

4. Inicializar el estado vacío **solo en una instalación nueva**, con todos los
   workers detenidos. Publicar config validada e inicializar por CAS:

   ```python
   from core.beat_cloud import BeatCloud, DropboxTransport, decode_document
   from core.beat_schema import migrate
   from pathlib import Path

   cloud = BeatCloud(DropboxTransport.from_env())
   config = migrate(decode_document(Path("tokens/beat_automation.local.json").read_bytes()), "config")
   existing, rev = cloud.read("config")
   # Revisar config antes de escribir; conservar IDs y configuración vigente.
   cloud.write("config", config, rev)
   cloud.initialize()  # ÚNICAMENTE si se confirmó que es una instalación nueva.
   ```

   Guardar el archivo de ejemplo local bajo una carpeta excluida de Git si contiene
   datos del equipo. Un estado ausente durante la operación es pérdida de historial,
   no una instalación nueva: el worker aborta sin reconstruir cuota ni jobs.
   No ejecutar `initialize()` para resolver ese error.

5. Autorizar un token OAuth de YouTube por canal según
   [YOUTUBE_SETUP.md](YOUTUBE_SETUP.md). Guardar el token local en `tokens/`; en
   Actions, cargar `BEAT_YT_TOKEN_JSON` en su Environment. El worker usa un directorio
   temporal privado y elimina las variables `BEAT_*` antes de lanzar FFmpeg.
   La autorización OAuth en modo Testing puede caducar; verificar el estado de
   la aplicación y la cuenta antes de operar sin supervisión. El token actual
   compartido incluye lectura de YouTube para comprobar la cuenta y recuperar IDs.

6. Configurar `BEAT_TELEGRAM_TOKEN` y `BEAT_TELEGRAM_CHAT_ID`. Las corridas reales
   requieren ambos; las notificaciones solo contienen contadores y códigos fijos.
   Un error de Telegram no deshace un upload ni habilita su reintento. Configurar
   Notion opcionalmente con `BEAT_NOTION_TOKEN` y `BEAT_NOTION_PAGE_ID`, con acceso
   de lectura a una página con un único bloque JSON. Un informe inválido cae a
   caché válida del mismo canal/ficha y luego a la ficha manual; no inserta texto
   libre del informe en los metadatos. Ver [SEO](TYPE_BEATS_SEO.md).

7. En GitHub: `BEAT_CHANNELS` es un array JSON de slugs. Cada slug usa un Environment
   `type-beats-<slug>`, restringido a una sola regla **Branch: master**. Todos los
   secretos anteriores van en esos Environments. La consulta administrativa de
   comprobación es anónima y falla cerrada si no puede verificar el Environment
   (incluidos repositorios privados). No ampliar permisos para evitar la guarda.
   Conservar `BEAT_LIVE_ENABLED` ausente o distinto de `true` durante el setup:
   el cron simula y no programa publicación pública. El despacho manual tiene
   `dry_run=true` y `private_pilot=true` por defecto.

   El workflow y el worker aceptan únicamente `Perree/video-type-beat-generator`,
   `master` y eventos `schedule`/`workflow_dispatch`. Un fork requiere un proyecto
   y estado independientes y una revisión explícita de esa política; no trasladar
   secretos productivos ni cambiar la guarda para probarlo. El worker recibe
   `BEAT_SLUG` desde la matriz y lo contrasta con `actions_slug` remoto.

## Dry-run

Prueba de planificación reproducible sin red ni credenciales:

```powershell
.venv\Scripts\python.exe scripts/plan_type_beats.py --dry-run --fake --now 2026-10-12T12:00:00-03:00 --config config/beat_automation.example.json --tracks tests/fixtures/beat_planning_tracks.json
```

Dry-run del worker con lectura real, después del setup:

```powershell
.venv\Scripts\python.exe scripts/run_beat_daily.py --dry-run
```

Requiere `BEAT_CHANNEL_ID` y credenciales de Dropbox. Lee catálogo público, config,
estado y catálogos visuales; Notion es opcional. No escribe en Dropbox, consume
intentos, descarga audios/imágenes, renderiza, crea journals, sube a YouTube ni
envía Telegram. El estado propuesto vive en memoria y SQLite temporal. Requiere
estado remoto existente para no simular sobre una cuota perdida.

En Actions: Run workflow, `dry_run=true`. Revisar summary y exit code; `failed`,
`orphan`, `unknown` o `expired` hacen fallar el job. `blocked` y `budget` son
contadores de atención, no habilitaciones para borrar historial. Inspeccionar
las reservas en estado: un dry-run correcto no confirma decodificación de medios,
OAuth ni la entrega real de Telegram.

## Piloto privado

Usar **un único canal de prueba** en `BEAT_CHANNELS`; pausar los demás y mantener
`BEAT_LIVE_ENABLED` deshabilitado. Cada miembro de la matriz tiene su propio límite
de piloto: varios canales producirían hasta un video por canal. Verificar que la
config remota apunta al canal de prueba y que el token coincide.

```powershell
.venv\Scripts\python.exe scripts/run_beat_daily.py --private-pilot
```

O despachar Actions con `dry_run=false`, `private_pilot=true`. Procesa como máximo
un job elegible, incluso ante respuesta ambigua o fallo posterior al insert.
Usa `privacyStatus=private` **sin `publishAt`**. Consume un intento del presupuesto,
guarda SEO/visual/journal y `publication_mode=private_pilot`. Revisar en Studio:
canal correcto, visibilidad privada sin programación, audio completo, imagen/video,
miniatura, título y tags; comprobar receipt remoto y resumen de Telegram.

No reutilizar/resetear la identidad del piloto para convertirlo en otro upload.
Su historial se conserva y cuenta en ciclos/descanso. Para separarlo de producción,
usar el canal de prueba y una app/instalación de prueba explícita, sin credenciales
productivas. Nunca repartir el presupuesto productivo entre varias apps.

El modo normal sin flags programa la publicación del slot: privado al insertar
no significa privado para siempre. YouTube documenta que un
[`publishAt` pasado publica inmediatamente](https://developers.google.com/youtube/v3/docs/videos#status.publishAt).
El worker vuelve a revisar pausa, fecha de presupuesto y slot inmediatamente antes
de la llamada. Esta fase no habilita producción: `BEAT_LIVE_ENABLED=true` permitiría
que el cron programe publicaciones reales; requiere completar el piloto y una
decisión operativa explícita posterior.

## Pausa

1. Poner `BEAT_LIVE_ENABLED=false` y deshabilitar el workflow de Beats en Actions
   para detener también despachos de piloto. No modifica el workflow de Loopkits.
2. Publicar `active=false` para cada canal por CAS. Pausar solamente en el panel
   local no cambia la config que consume Actions. Para editar un canal:

   ```python
   cloud.update("config", lambda config: next(
       ch for ch in config["channels"] if ch["id"] == "channel-example"
   ).update(active=False))
   ```

3. Revisar las corridas en curso y sus receipts. La pausa se verifica al inicio y
   nuevamente antes/después de reservar un intento. No cancela una llamada a
   YouTube que ya comenzó; su resultado puede quedar uploaded, orphan o unknown.
   Una pausa posterior a reservar conserva ese intento aunque no se haya llamado.
4. Los videos ya programados siguen su calendario en YouTube. Si deben permanecer
   privados, quitar la programación en Studio y confirmar la visibilidad allí.
   Pausar el worker no modifica videos existentes.

## Rollback

Pausar como arriba, esperar a las corridas en curso y conservar config, estado con
sus revisiones e intentos, y artifacts de receipts antes de volver a una versión
anterior del **código** mediante `git revert <commit>` en una rama revisable.
Ejecutar smokes y dry-run antes de habilitarla. No restaurar un estado antiguo:
perder intentos o IDs permitiría duplicar uploads. Un rollback del código no borra
videos ni cancela programaciones ya enviadas.

La base de esta sesión contenía la Fase 7 sin commit; el commit de cierre conserva
esos cambios junto con el hardening para que la versión probada sea reproducible.
Revertir todo ese commit también revierte la rotación de Fase 7: mantener pausado
el worker hasta revisar compatibilidad. Los documentos siguen en schema_version=1,
con campos opcionales nuevos. No cambiar el esquema/namespace ni reducir cuota
manualmente para que el código anterior arranque.

## Recuperación

**Orphan con ID conocido:** pausar el canal y las corridas. Descargar el artifact
`type-beats-receipts-<slug>-<run_id>-<run_attempt>` (retención 90 días), conservar
una copia y usar su JSON. Autorizar localmente el token del canal en `tokens/`.
El CLI primero verifica la cuenta y lee `videos.list` para confirmar ID, dueño y
upload aceptado/procesado. Solo lee YouTube; nunca publica, elimina ni cambia videos.

```powershell
.venv\Scripts\python.exe scripts/recover_type_beats.py --receipt exported_videos/type_beats/receipts/DIGEST.json --channel channel-example --uploaded-at 2026-10-12T12:30:00-03:00
```

El timestamp debe representar la inserción verificada, nunca una fecha anterior
al intento reservado. Si no se conoce, usar la hora actual de conciliación (más
conservadora para el descanso de 180 días), no adivinar una fecha anterior.
El comando cruza digest SHA256 con un único job del canal y exige el intento
original. Sin `--apply` no escribe. Revisar la propuesta y repetir con `--apply`:
actualiza status/ID/timestamp por CAS, preservando intentos, SEO, visual y lock.
Repetir el mismo receipt es idempotente, también ante respuesta perdida.
IDs en conflicto, video de otra cuenta, job inexistente, canal activo y falta de
intento se rechazan. No devuelve cuota. Verificar el estado remoto antes de reanudar.

**Unknown o muerte entre YouTube y journal:** conservar el intento y buscar el
resultado en Studio por canal, slot y snapshot SEO/visual. Nunca reintentar el job
para averiguar si se subió. Si se confirma un ID, crear una copia de receipt con
ese ID y outcome `orphan`, conservando el digest del receipt unknown, y usar el
CLI anterior; aún exige la consulta autenticada de YouTube. Si no puede confirmarse
la correspondencia, mantener bloqueado y escalar a conciliación humana. El CLI
rechaza unknown sin ID; no busca videos por semejanza ni infiere asociaciones.

**Estado ausente/corrupto:** detener todos los canales, recuperar desde revisiones
Dropbox el último estado íntegro y cruzarlo con todos los receipts e intentos
posteriores. No sobrescribir desde un backup antiguo ni crear estado vacío.
Sin ledger completo no reactivar uploads. Corrupción y JSON ambiguo fallan cerrados.

**Lock vencido:** un nuevo dueño toma el lease mediante CAS después del vencimiento.
No borrar el lock para acelerar una corrida en curso. Planner usa 300 s; render
3600 s con checkpoints en montaje y renovación antes de reservar el intento y antes
del insert. Si pierde el lease, no inserta; si ya reservó, conserva ese intento.
El fencing impide confirmar con un dueño viejo;
la liberación anterior no borra el lock de otro runner. Si una solicitud de red
está en curso, esperar su timeout y conciliar intents antes de reanudar.

El transporte Google exclusivo de Beats limita cada solicitud a 30 s y cada upload
a un plazo de 1800 s, sin proxies del entorno ni redirects, incluidos endpoints de
refresh y sesiones resumibles. Los reintentos 5xx continúan la misma sesión hasta
cinco veces, con esperas de 1/2/4/8/16 s. Un timeout queda `unknown`, sin reinsertar.
Dropbox respeta Retry-After de hasta 30 s; ante una demora mayor o inválida aborta,
sin dormir indefinidamente ni reintentar antes de lo indicado por el servidor.

**Slot vencido sin intento:** se informa `expired`, nunca se sube con fecha pasada.
Con todos los workers detenidos, verificar que no exista intento para el job y
cancelarlo por CAS, conservando su identidad y slot ocupados. Un job con intento
permanece bloqueado aun si se cancela; requiere la conciliación anterior.

**Miniatura fallida:** el ID ya está en estado como uploaded; cargar la miniatura
en Studio o usar una llamada específica a `thumbnails.set`. No volver a ejecutar
`videos.insert`. **Telegram fallido:** revisar summary/artifact en Actions y reparar
la configuración; repetir un job no es un método de reenviar la notificación.

**Disco fallido después del upload:** si Dropbox confirmó el ID, su receipt es la
fuente de verdad. Un fallo al reemplazar el journal local final conserva `uploaded`
y permite la miniatura; el journal anterior puede seguir diciendo `orphan`.
Conciliarlo es idempotente. Si tampoco hubo confirmación remota, recuperar como
orphan/unknown según el procedimiento anterior; nunca repetir el insert.

## Verificación y alcance de la revisión

```powershell
$env:BEAT_REAL_FFMPEG_SMOKE='1'
.venv\Scripts\python.exe scripts/smoke_beat_hardening.py
.venv\Scripts\python.exe scripts/smoke_beat_daily.py
.venv\Scripts\python.exe scripts/smoke_beat_video.py
```

El runner completo incluye todas las suites `test_beat_*.py`, los 27 `smoke_kit_*`
y los cuatro smokes manuales: biblioteca por kind, migración de uploads,
conversión publishAt y secciones de UI. El worker de Actions usa `--worker-only`
para excluir PyQt y regresiones de escritorio, sin omitir pruebas de catálogo,
estado, render, SEO, ciclos, publicación, cuota y recuperación. El flujo manual,
`main.py`, módulos `kit_*` y workflow de Loopkits conservan su implementación.
El uploader compartido `core/youtube.py` solo cambia el cierre explícito de streams
de video/miniatura, también ante error, para permitir cleanup de temporales Windows;
su contrato, metadatos, privacidad y política de reintentos se conservan.

Revisión completa:

- Catálogo: scan completo antes de aplicar, transacción SQLite, IDs/owners públicos,
  paginación y límites, incrementales e inactivos. Lectura real adicional documentada
  al cierre; SQLite temporal y ningún audio.
- Locks/cuota/scheduler: CAS, vencimiento y takeover, intents previos al insert,
  seis intentos globales por fecha Buenos Aires, carreras de jobs diferentes,
  medianoche, slots vencidos y reejecución sin duplicar. Estado ausente bloquea.
- HLS: HTTPS/hosts permitidos, redirects rechazados, VOD, tamaños/duración/tipos,
  sin llaves ni playlists remotas en FFmpeg. Fallback solo por asociación explícita.
- Imágenes/video: catálogos y revisiones, límites y decodificación, temporales,
  rotación y snapshots, hash visual, montaje sin audio de clips y cleanup.
- SEO: esquema/tamaño/fechas, canales, whitelist de tags reales, caché por ficha,
  snapshot inmutable, fallo de Notion y variantes de repeticiones.
- YouTube: cuenta correcta, insert privado, piloto sin programación, journal antes
  de miniatura, bloqueo de respuestas ambiguas, conciliación de IDs sin insert.
- Telegram: solo códigos/contadores, sin excepciones/URLs/datos remotos; fallo de
  aviso no invalida receipt. Validación de token/chat, timeout y sin redirects.
- Actions: master y Environment comprobados, sin PR, acciones por SHA,
  `contents: read`, dependencias con hashes, concurrency sin cancelación,
  artifacts `always`, cron simulado hasta habilitación explícita.
- Dropbox autenticado: tanto estado como assets sin proxies del entorno ni
  redirects; documentos leídos por chunks con límite de 8 MiB y plazo de 180 s.

El límite de seis es una regla propia de la app, independiente de los límites del
proyecto/cuenta de Google. Verificar cuota vigente en Cloud Console y la
[documentación de videos.insert](https://developers.google.com/youtube/v3/docs/videos/insert)
antes de habilitar producción; no inferir capacidad a partir del cálculo histórico
de 1600 unidades por upload presente en guías antiguas.

El [cron de GitHub puede retrasarse o perder una corrida](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule);
el buffer reduce ese riesgo pero no garantiza publicación puntual. Revisar el
último éxito, días cubiertos, cuota e intents pendientes desde Actions/estado.
No hay watchdog externo ni recuperación automática de unknown. Los límites de
red/procesos y timeout de Actions pueden terminar una corrida: el ledger bloquea
duplicados, no garantiza entrega exactamente una vez.
El estado tiene un límite de 8 MiB y no hay compactación automática del historial;
si lo alcanza, pausar y conservar el ledger antes de planificar una migración.

Los smokes offline no verifican permisos reales de Dropbox/Notion, Environments,
OAuth, entrega de Telegram ni auditoría de YouTube. Esta sesión no dispone de
credenciales `BEAT_*` para el worker remoto. Esos pasos siguen como aceptación
operativa, con dry-run y piloto privado; no habilitar publicaciones públicas al
cerrar esta fase.

### Resultado de cierre — 2026-10-12

198 pruebas Type Beats aprobadas, sin omisiones (22 casos nuevos de hardening,
incluido cleanup del uploader compartido; dos pruebas con FFmpeg real). Smokes
diario: 30/30; video/montaje: 34/34. Los 27 smokes Loopkits y los cuatro de Beats
manuales pasaron, incluido render con FFmpeg/ffprobe reales. Workflow validado
con actionlint 1.7.12; sintaxis Python y `git diff --check` correctos.

Lectura real adicional del perfil público configurado: 1138 tracks; aplicar el
mismo snapshot por segunda vez deja 1138 sin cambios. Solo SQLite temporal,
cero audios descargados, cero uploads y cero mensajes. Planificación con fixtures
ejecutada en dry-run. Los logs locales de pruebas viven bajo `exported_videos/`
(excluido de Git); no contienen credenciales. Entorno local: Python 3.13 con PyQt
y el lock del worker instalado por hashes. Actions configura Python 3.12, y su
ejecución remota sigue pendiente de setup.

### Auditoría adicional del diff de Fase 8 — 2026-10-12

Al solicitar la revisión, el árbol estaba limpio y Fase 8 ya estaba en `1615c5f`.
Se auditó ese diff antes de editar. Evidencia reproducida sin servicios reales:

- **Alta, secretos en logs:** `beat_worker.main` y `beat_recover_cli.main` redirigían
  streams a StringIO; un handler ya creado de `googleapiclient.http` seguía emitiendo
  un secreto ficticio. El SDK puede registrar cuerpos de respuesta. Corregido con
  logging deshabilitado durante la operación y descarte en devnull, sin acumular
  cuerpos en memoria. Prueba: `test_prebound_logging_handler_cannot_emit_secret`.
- **Alta, aislamiento de Actions:** las guardas aceptaban cualquier repositorio con
  master y no contrastaban Environment/canal. Corregidos repo/evento/ref permitidos,
  binding `actions_slug`, slugs únicos y rechazo antes del render. Pruebas:
  `test_forks_other_refs_and_untrusted_events_rejected` y
  `test_worker_crossed_environment_aborts_before_render`.
- **Media, lease perdido:** quitar el lock antes de `publish` todavía permitía un
  insert. Ahora se verifica y renueva desde el contexto de render en dos puntos.
  Pruebas de pérdida antes/después del intent conservan cero inserts y el ledger.
- **Media, destino cambiado:** la cuenta se comprobaba solo al arrancar y una nueva
  config podía cambiar el destino antes del render/insert. Se fija el ID verificado
  a través de bootstrap, daily y publish. Pruebas de cambio después de verificar
  cuenta y durante el render bloquean sin gastar cuota ni subir.
- **Media, límites de red/retries:** `Transient(1000000)` solicitaba dormir un millón
  de segundos; el loop de YouTube no tenía plazo total. Corregidos los presupuestos
  anteriores y transporte Google específico de Beats. Pruebas de backoff inválido,
  deadline, hosts, proxies, redirects y retries de una única sesión.
- **Media, resultado tras fallo local:** un OSError del journal final propagaba fallo
  aunque Dropbox ya decía uploaded, y omitía la miniatura. Ahora respeta el receipt
  remoto. La regresión comprueba seis IDs, seis miniaturas y cero reuploads.

Las regresiones están en [test_beat_review.py](../tests/test_beat_review.py).
No se modifican Loopkits, Marca personal, main.py ni el uploader compartido en esta
revisión. El cierre de streams de `core/youtube.py` pertenece al commit anterior y
sigue cubierto por las regresiones manuales. No quedan hallazgos confirmados
pendientes en el código revisado; la aceptación remota continúa como setup/piloto
privado, sin afirmar ejecuciones reales con credenciales ausentes.

Resultado de esta revisión: **212/212 pruebas Type Beats**, sin omisiones,
**191/191 en modo worker**, 30/30 del smoke diario y 34/34 de video/montaje.
Pasaron los 27 smokes Loopkits y los cuatro manuales, con FFmpeg real cuando
corresponde; actionlint 1.7.12, compileall y whitespace correctos. Construcción
offline del servicio con el SDK Google real y planificación con fixtures en
dry-run verificadas. Logs locales en `exported_videos/type_beats_review_*.log`.
Cero uploads reales, envíos de Telegram o cambios de configuración remota.
