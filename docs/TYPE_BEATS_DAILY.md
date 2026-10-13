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

Variable del repositorio `BEAT_CHANNELS`: array JSON de slugs, por ejemplo
`["channel-a","channel-b"]`. Los slugs aceptan letras minúsculas, números y guiones;
deben comenzar con una letra. Un Environment por slug: `type-beats-<slug>`.

Antes de habilitar la corrida real, configurar **cada Environment** en Settings:
Deployment branches and tags → Selected branches and tags → una sola regla de
tipo **Branch** con nombre exacto **master**, sin reglas de tags ni comodines.
El YAML no puede crear estas restricciones administrativas. El workflow consulta
su política antes de ejecutar el worker y falla si falta, permite otras ramas o
no puede verificarse. Usa consultas anónimas de recursos públicos para conservar
`permissions: contents: read`; para un repositorio privado no verificado se
detiene, sin ampliar permisos.

Referencias oficiales:
[Environments](https://docs.github.com/en/rest/deployments/environments),
[Deployment branch policies](https://docs.github.com/en/rest/deployments/branch-policies).

Secretos de cada Environment:

- `BEAT_CHANNEL_ID`: ID exacto del canal en la configuración de Beats.
- `BEAT_YT_TOKEN_JSON`: token OAuth autorizado del canal correspondiente.
- `BEAT_DROPBOX_APP_KEY`, `BEAT_DROPBOX_REFRESH_TOKEN`: todos los Environments
  deben acceder al **mismo** estado de Beats para compartir el presupuesto.
- `BEAT_TELEGRAM_TOKEN`, `BEAT_TELEGRAM_CHAT_ID`: resumen y alertas obligatorios
  para corridas reales.
- `BEAT_NOTION_TOKEN`, `BEAT_NOTION_PAGE_ID`: opcionales, informes de Fase 5.

No guardar estos secretos a nivel repositorio. No pasar credenciales de Loopkits.
El token de YouTube se escribe en un directorio temporal 0700 y archivo 0600,
se usa con `tokens_dir` y se borra al finalizar. Los secretos `BEAT_*` salen del
entorno antes del render. La salida de dependencias y sus errores se suprimen.
Telegram recibe exclusivamente etiquetas fijas y contadores; alerta por `orphan`,
`unknown`, errores, bloqueos, vencidos y miniaturas fallidas sin incluir textos
de las excepciones. Un fallo de Telegram nunca dispara otro upload.

El cron corre a las 22:00 UTC (19:00 Buenos Aires). Solo corre en `master`, sin
eventos de PR. Matriz por canal, `fail-fast: false`, canales serializados por el
lease global y concurrency global y por canal con `cancel-in-progress: false`.
Todas las acciones están fijadas por SHA; las dependencias usan el lock existente
con `--require-hashes`, sin modificar el worker/workflow ni el lock de Loopkits.
Las carpetas visuales se eligen entre los géneros configurados del canal:
prioriza una coincidencia con los tags, luego la primera carpeta configurada.
No exige tags de género para procesar beats con tags de artistas; video y
carpetas locales de imágenes permiten la lista de géneros vacía.

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
