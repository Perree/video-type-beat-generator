# Type Beats — Fase 2 completada, revisión aplicada

La implementación prepara configuración, estado y planificación. No está conectada a
la UI, FFmpeg, YouTube ni workers de Loopkits. Ningún comando de esta fase renderiza
o sube videos. No se escribieron datos en Dropbox durante la implementación.

## Documentos y concurrencia

`core/beat_cloud.py` usa un cliente propio del SDK de Dropbox. Lee exclusivamente
`BEAT_DROPBOX_APP_KEY` y `BEAT_DROPBOX_REFRESH_TOKEN`; configurar una app independiente
de tipo App folder, con permisos de lectura y escritura de archivos. No hay fallback
a tokens generales ni a `KIT_*`. Rutas fijas relativas a esa app:

- `/type-beats/config.json`: canales, prioridad, slots, esquema y límites.
- `/type-beats/state.json`: jobs, lock y todas las reservas diarias de todos los canales.

No guardar credenciales en ninguno de los documentos. `config/beat_automation.example.json`
es un ejemplo sintético; no modifica `config/app_config.json`.

Cada lectura devuelve documento y `rev`. Cada escritura exige esa revisión (`WriteMode.update`),
o creación exclusiva si `rev=None` (`add`); `autorename=False`, `strict_conflict=True`.
Nunca usa overwrite. Contrato de CAS verificado contra la
[documentación del SDK](https://dropbox-sdk-python.readthedocs.io/en/latest/api/files.html).
Dropbox conserva sus revisiones; el esquema lógico comienza en `schema_version=1`.
No hay un archivo de historial adicional que necesite una segunda escritura atómica.

`BeatCloud.update(kind, mutate)` relee y vuelve a aplicar una mutación pura cuando hay
conflicto; no hacer llamadas externas dentro de `mutate`. Los fallos transitorios de
red, 5xx y rate limit tienen reintentos limitados con backoff exponencial y respeto al
Retry-After. Un fallo definitivo o documento corrupto aborta, sin reemplazarlo por vacío.
Las respuestas perdidas se resuelven por CAS e identidades idempotentes. Los errores
del adaptador no incluyen credenciales ni respuestas del servidor.

`initialize()` crea documentos ausentes o migra la versión 0 (sin `schema_version`) a
la 1, preservando campos existentes. Versiones futuras y namespaces ajenos se rechazan.
Repetir la inicialización de documentos ya migrados no escribe otra revisión.
Inicialización y edición son explícitas; el dry-run nunca las ejecuta.
Los documentos v1 deben contener todos sus campos obligatorios, incluyendo las
opciones de cada canal; no se reconstruyen contadores ni se activan canales por
campos faltantes. Se rechazan claves JSON duplicadas y números no finitos.

## Slots, rondas y ciclos

El rango de buffer es `(ahora, ahora + 14 días]`; nunca agenda un slot pasado ni el
instante exacto de inicio. `weekday=0` es lunes, `6` domingo. Se validan horas/minutos,
IDs de canal únicos y ausencia de slots duplicados. Todos los instantes requieren
offset; el almacenamiento canónico usa hora de Buenos Aires, UTC-3. La implementación
usa la regla fija vigente desde 2009 y rechaza fechas anteriores a 2010; no requiere
tzdata en Windows. Un cambio futuro en la regla horaria argentina requerirá actualización.

Cada ronda recorre todos los canales activos por prioridad descendente, luego por ID
para empates; asigna un track al primer slot libre de cada canal. Después empieza la
siguiente ronda, hasta llenar el buffer o quedarse sin tracks activos. IDs de track
ordenados hacen el resultado estable ante cambios de orden del catálogo.

Cada canal tiene ciclos independientes: utiliza todos sus tracks activos elegibles una vez
antes de iniciar el ciclo siguiente. Las reservas planificadas y fallidas cuentan
como usadas; el futuro worker reintentará el mismo job. Los jobs cancelados conservan
su slot ocupado, pero no consumen el track del ciclo. El buffer puede contener varios
ciclos si el catálogo es chico. No se introduce descanso entre ciclos en esta fase.
Un track nuevo entra al ciclo vigente si todavía no fue asignado; uno inactivo deja
de participar en nuevas asignaciones. Los jobs existentes no se borran ni reasignan
por cambios posteriores del catálogo o de la configuración.
Cancelar todos los jobs del ciclo más reciente no hace retroceder el número de ciclo.

El campo opcional `selection_tags` define la elegibilidad por canal antes de crear
jobs: basta una coincidencia exacta con un tag del track tras `strip().casefold()`.
Sin el campo o con `[]`, todos los activos siguen elegibles. `tags` pertenece al SEO
y no filtra. Sin coincidencias, ese canal no recibe nuevas reservas; el resto de
las rondas continúa. La rotación y los grupos de rendimiento usan solo el catálogo
elegible del canal, sin fallback al catálogo completo. El worker también bloquea
antes del render los jobs existentes cuyo track dejó de ser elegible.

Identidad: JSON canónico de `[track ID, canal, ciclo, slot con offset -03:00]`.
Así, títulos/URLs cambiantes no afectan la identidad. Un slot de canal solo puede
contener un job. `plan()` es pura; `fill_buffer()` agrega jobs bajo lock y CAS,
recalculando tras conflictos. Repetir con el mismo estado/instante no duplica jobs.
Si una escritura del plan se confirma pero pierde su respuesta, `fill_buffer()`
recupera los mismos jobs propuestos por esa llamada en vez de devolver una lista vacía.
`BeatCatalog.tracks(member_id)` de Fase 1 se puede pasar directamente como catálogo.

## Lock y presupuesto

`BeatState.acquire(ttl=300)` devuelve un token aleatorio de dueño; TTL permitido de
1 a 3600 segundos. `renew()` y `fill_buffer()` exigen el token y un lock sin vencer.
La liberación de un dueño anterior no elimina el lock de su sucesor. Lock y jobs
comparten documento y CAS: un dueño anterior no puede pisar el takeover de otro.
Liberar siempre en `finally`. No se toma lock en dry-run.
La vigencia se comprueba justo antes de cada envío, incluyendo los reintentos.
La renovación comprueba el vencimiento original, evitando revivir un lock vencido
durante el backoff. Un envío ya en curso puede terminar después del vencimiento;
el CAS impide pisar el estado si otro dueño tomó el lock mientras tanto.

`reserve_attempt(job_id, attempt_id)` registra, mediante CAS, el intento antes de
una futura llamada de upload. El día es el de Buenos Aires al reservar, no el del
slot de publicación. El límite global es seis, incluyendo fallos y resultados
desconocidos. Los reintentos reales de upload requieren otro `attempt_id` y consumen
otro intento. Reintentar la reserva con el mismo ID es idempotente y devuelve
`replayed=True`: NO autoriza otra llamada de upload. No se devuelve presupuesto.
Un intento que atraviesa medianoche sigue cargado al día de su reserva; una reserva
nueva usa el nuevo día. El consumidor futuro debe reservar inmediatamente antes de
la llamada externa. Esta fase solo expone la reserva; no efectúa la llamada.

## Uso

Prueba offline determinista con fixtures (mismo instante, misma salida):

```powershell
.venv\Scripts\python.exe scripts/plan_type_beats.py --dry-run --fake --now 2026-10-12T12:00:00-03:00 --config config/beat_automation.example.json --tracks tests/fixtures/beat_planning_tracks.json
```

Opcional `--state ruta.json` carga un estado falso. Sin `--fake`, lee el estado de
Dropbox y la configuración remota (o `--config` local), siempre sin escribir. El CLI
exige `--now` para que el instante sea explícito; los tracks se pasan como JSON local.
No descarga el catálogo ni audios. Devuelve jobs nuevos y presupuesto restante del día.

Uso desde Python, cuando se autorice persistir configuración/plan:

```python
from core.beat_cloud import BeatCloud, DropboxTransport
from core.beat_state import BeatState

cloud = BeatCloud(DropboxTransport.from_env())
cloud.initialize()
config, rev = cloud.read("config")
# Editar config['channels']; luego cloud.write('config', config, rev).
store = BeatState(cloud)
owner = store.acquire()
try:
    jobs = store.fill_buffer(config, tracks, owner)  # tracks del catálogo Fase 1
finally:
    store.release(owner)
```

Pruebas sin red:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_beat_*.py' -v
```

`MemoryDropbox` tiene revisiones, creación exclusiva, CAS bajo mutex, fallos de lectura,
escritura y respuesta perdida después del commit. Las pruebas ejercitan conflictos
con ocho escritores concurrentes, vencimiento/takeover, límites de slots y buffer,
repetición, ciclos, medianoche, migraciones y dry-run sin escrituras.

Validación tras revisión del 2026-10-12: 49 tests aprobados (27 de esta fase y 22 de Fase 1),
dry-run offline ejecutado y chequeo de whitespace sin errores. Las pruebas del
adaptador usan un cliente falso y las uniones de error del SDK oficial 12.2.3;
se omiten si ese SDK no está instalado. No se hizo una prueba con Dropbox real.

Revisión local y correcciones: documentos v1 incompletos y JSON ambiguo, vencimiento
durante reintentos de adquisición/renovación/planificación, recuperación del resultado
tras respuesta perdida y monotonía de ciclos al cancelar jobs. Nueve pruebas de
regresión adicionales. Fase cerrada el 2026-10-12 con autorización del usuario
después de la revisión, sin renderizar ni subir videos.
