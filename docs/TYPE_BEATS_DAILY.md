# Fase 6: worker diario Type Beats (completada, revisión aplicada)

`scripts/run_beat_daily.py` conecta las Fases 1–5 con `core.youtube.upload`.
No usa `main.py`, los módulos `kit_*`, credenciales `KIT_*` ni el estado de Loopkits.
El workflow independiente es `.github/workflows/type-beats-daily.yml`.

Hardening y procedimientos vigentes: [operación de Fase 8](TYPE_BEATS_OPERATIONS.md).
El cron ahora simula hasta que `BEAT_LIVE_ENABLED=true`; un piloto manual usa
`--private-pilot` (un job, privado sin `publishAt`). El arranque real requiere
`youtube_channel_id` en la configuración remota y verifica la cuenta OAuth.

## Comportamiento

Lee `/type-beats/config.json` y `/type-beats/state.json` con las credenciales de
Beats. La configuración debe tener el perfil público, los canales y sus fichas,
horarios, géneros y recursos visuales de Fases 2–5. El panel de Fase 3 sigue
siendo el editor local; esta fase consume su configuración publicada en Dropbox.
No copia automáticamente la configuración local al servicio remoto.

Escanea el perfil con Fase 1 y sincroniza un catálogo SQLite temporal. Filtra los
tracks activos por `selection_tags` de ese canal antes de planificar o reservar;
la coincidencia es exacta tras quitar espacios exteriores e ignorar mayúsculas.
Ausente o `[]` conserva el comportamiento anterior; `tags` sigue siendo SEO.
Si no hay coincidencias, termina solo ese canal con `blocked: 1` y
`no_matching_tracks: 1`, sin escrituras de estado, intentos, render ni fallback
al catálogo completo. Telegram incluye esos contadores fijos, sin tags ni datos
del catálogo. Los jobs anteriores que ya no coinciden quedan bloqueados antes
del render y conservan su ledger. Ver [selección operativa](TYPE_BEATS_OPERATIONS.md#selección-por-canal).
Llena el buffer global de 14 días bajo el lease de Fase 2. Cada canal procesa sus reservas
futuras en orden de slot, prepara el snapshot SEO inmutable de Fase 5 y renderiza
con Fase 4. El video se inserta privado con `publishAt` del slot; la política de
auditoría de YouTube puede impedir la publicación pública automática.
Los jobs vencidos generan un contador de alerta y no se suben con fechas pasadas.
Para Actions, usar imágenes/videos/miniaturas en Dropbox: las rutas locales del
equipo no existen en el runner.

## Calendario de YouTube

Antes de planificar y antes de cada upload, el worker lee el calendario del canal
de YouTube al que va a subir (mismo token OAuth de la corrida). Es una regla de
calendario compartida con Loopkits y con cualquier automatización futura que elija
su propia fecha: no depende del tipo de contenido. No aplica al flujo de escritorio
donde una persona ya eligió la fecha y la hora; esos videos, una vez en YouTube,
ocupan el día y la siguiente corrida automática los ve.

Un día de calendario en `America/Argentina/Buenos_Aires` queda ocupado si en ese
día hay un video **publicado** (público o no listado) o **programado** (privado con
`status.publishAt`). Un privado sin `publishAt` (borrador o piloto) no ocupa nada.
La ocupación es por **fecha**, no por la hora del slot del canal: dos videos el
mismo día cuentan como un solo día tomado.

Si el cron cae en un día ocupado, el planner salta al siguiente slot libre dentro
del buffer de 14 días. Un día libre **antes** de otro día ya ocupado sigue siendo
usable. Ejemplo: slots lun y jue a las 18:00. Un video programado a mano en Studio
el lunes 26 oct a las 15:00 bloquea todo el lunes 26 oct; el worker no usa el slot
del lunes 18:00 y planifica el jueves 29 oct a las 18:00. Un video solo el jueves
5 nov no impide usar el lunes 2 nov si ese día sigue libre en YouTube.

Si un job `planned` o `failed` quedó en un día que después se ocupó (en YouTube o
por otro job en estado), la corrida lo cancela con el status `cancelled` existente:
el instante del slot sigue reservado en el ciclo y el track vuelve al pool. Los jobs
`uploaded` o ya `cancelled` no se tocan. No hay campos nuevos en
`/type-beats/state.json` ni migración: `schema_version` sigue en `1`; la ocupación
no se persiste, se lee en vivo.

Si la lectura del calendario falla (API, red o canal vacío), esa corrida no planifica
cambios por calendario al inicio, no sube nada y deja los jobs como estaban; Telegram
incluye el contador `calendar_unavailable`. Un fallo justo antes de un insert concreto
cancela ese job sin reservar intento y sigue con los demás elegibles. Los dry-run no
llaman a YouTube: el conjunto de días ocupados queda vacío como antes.

## Presupuesto e idempotencia

El presupuesto es compartido por **todos** los canales en el mismo archivo CAS:
seis intentos por fecha Buenos Aires. Cada llamada a `core.youtube.upload` reserva
el intento antes de invocar YouTube. No se devuelve presupuesto tras un error.
Los reintentos internos del cliente son chunks de la misma sesión resumible,
no nuevas llamadas a `videos.insert` desde el worker.

La reserva exclusiva comprueba todos los intentos históricos del job y registra
el nuevo intento en la misma transacción CAS. Un segundo worker no puede subir
ese job. Esto también bloquea un intento cuyo proceso murió o cuya respuesta fue
ambigua, aunque el siguiente día tenga presupuesto. Es una política conservadora
de **como máximo una llamada por job**, no una promesa de entrega exactamente una
vez. No borrar intentos ni reconstruir el estado para reintentar automáticamente.
Las nuevas reservas de otros ciclos/slots siguen siendo publicaciones distintas.
La reserva exclusiva verifica la fecha Buenos Aires antes de cada commit CAS;
si el backoff cruza medianoche se aborta. Se vuelve a verificar después del
journal y antes del uploader, sin cargar un upload nuevo a la fecha anterior.

Un journal local con flush/fsync guarda el digest SHA256 de la identidad y el ID
validado de YouTube. Después de obtener el ID se registra `orphan` antes del CAS
final. Si Dropbox falla, permanece el orphan y la reserva previa evita repetir.
Al confirmar Dropbox se cambia a `uploaded`. La pérdida de respuesta del CAS se
recupera mediante su revisión y una mutación idempotente. Una respuesta de YouTube
sin ID válido queda `unknown`. Errores previos al intento no consumen presupuesto.
El adaptador `core/beat_youtube.py` llama a `core.youtube.upload` sin miniatura:
primero persiste el ID y después adjunta la miniatura con un callback separado.
Cualquier fallo de la miniatura conserva el ID y genera `thumbnail_failed`; un
orphan no ejecuta ese callback. El módulo compartido `core/youtube.py` no cambia.

Actions conserva los JSON del journal con `if: always()` durante 90 días. Contienen
solo digest, estado e ID; nunca credenciales, nombres, paths privados o excepciones.
Una caída del runner justo entre la respuesta de YouTube y el journal, o fallos
simultáneos de disco y Dropbox, pueden perder el ID recuperable: la reserva remota
continúa bloqueando el upload y requiere conciliación manual en YouTube Studio.
La eliminación o modificación externa de ese estado invalida la garantía.

Para conciliar un orphan, buscar su digest entre los IDs del estado y confirmar
el video en Studio. Registrar ese `youtube_id`, `uploaded_at` y `status=uploaded`
mediante CAS manteniendo los intentos originales. Un `unknown` no se reintenta:
primero verificar el resultado remoto. La Fase 8 agrega el CLI
`scripts/recover_type_beats.py`, con lectura autenticada de YouTube y CAS explícito;
no hay reconciliación automática ni eliminación de videos.

## GitHub Actions

BEAT_CHANNELS es un array JSON de slugs. El Environment compartido `kit-weekly`
conserva Dropbox y Telegram; cada slug selecciona sus propios secretos de YouTube.
Ver TYPE_BEATS_CHANNELS.md para el setup vigente (sustituye Environments por canal).

- BEAT_CHANNEL_ID_<SLUG> y BEAT_YT_TOKEN_JSON_<SLUG>: secretos independientes
  de cada canal. SLUG es mayúsculas con guiones convertidos a guiones bajos.
- KIT_DROPBOX_APP_KEY y KIT_DROPBOX_REFRESH_TOKEN: conexión existente de Dropbox,
  mapeada a BEAT_* únicamente en el worker. Estado exclusivo bajo /type-beats/.
- KIT_TELEGRAM_TOKEN y KIT_TELEGRAM_CHAT_ID: bot existente, sin reconfiguración.
- BEAT_NOTION_TOKEN y BEAT_NOTION_PAGE_ID: opcionales, informes de SEO.

El workflow y el verificador usan kit-weekly restringido exclusivamente a Branch master.
workflow_dispatch acepta channel para probar un slug; vacío ejecuta todos.
El cron corre a las 22:00 UTC (19:00 Buenos Aires), con matriz serializada y locks globales.
BEAT_LIVE_ENABLED controla el modo real del cron; la pausa del canal se consulta en Dropbox.
Las acciones están fijadas por SHA y las dependencias usan --require-hashes.
Los secretos salen del entorno antes del render; el token temporal se elimina al finalizar.
Telegram recibe contadores, nunca credenciales, textos de excepciones ni catálogo privado.

## Dry-run y verificación

Desde Actions, `workflow_dispatch` tiene `dry_run=true` por defecto.
También tiene `private_pilot=true`: con dry_run apagado el video permanece privado.
Local: `python scripts/run_beat_daily.py --dry-run`, con credenciales de Dropbox
y `BEAT_CHANNEL_ID`. No requiere token de YouTube ni Telegram. Puede consultar
catálogo público, estado, catálogos visuales y Notion; no escribe en Dropbox,
reserva presupuesto, descarga medios, ejecuta FFmpeg, sube videos, envía Telegram
ni crea journals. El catálogo y estado propuesto viven en temporales/memoria.

`python scripts/smoke_beat_daily.py` prueba el pipeline completo con transporte
público, Dropbox, HLS, procesos FFmpeg, Google/YouTube y notificaciones falsos.
También invoca `core.youtube.upload` con su SDK y un servicio Google falso.
Requiere las dependencias del worker (incluido `google-api-python-client`), sin red.
Verifica presupuestos compartidos, carreras, respuestas perdidas, orphans,
timeouts, reejecuciones en otro día, cleanup, dry-run y salida sanitizada.

Revisión local aplicada: corregida pérdida del ID ante timeout de miniatura,
selección visual demasiado restrictiva y reserva que podía cruzar de fecha durante
backoff. El callback de miniatura y su prueba fueron verificados nuevamente por
el revisor independiente de seguridad, sin regresiones confirmadas.
Validación: 30 smokes diarios aprobados con el SDK de Google y servicios falsos;
131 pruebas de regresión ejecutadas en el entorno PyQt, 129 aprobadas y 2 omitidas.
Sintaxis Python y `git diff --check` correctos; sin cambios en Loopkits.

Fase cerrada por autorización del usuario tras revisión y correcciones, sin commit.
Pendiente operativo: configuración administrativa de Environments y
secretos, dry-run en Actions y prueba controlada con servicios reales. No se
realizó ningún upload real, no se habilitó un workflow remoto y no se hizo commit.
