# Type Beats — Fase 3 completada, revisión aplicada

> **2026-10-18:** las credenciales ya no viven en `tokens/`: Dropbox va al llavero de Windows y el resto a GitHub Secrets. Ver [CLOUD_CREDENTIALS.md](CLOUD_CREDENTIALS.md); donde este documento nombre `tokens/*.json`, vale ese reemplazo.

En la sección **Beats**, el botón **Automatizaciones de Beats** abre un diálogo
independiente. Solo muestra canales pertenecientes a Beats, incluyendo los canales
históricos sin sección explícita. Loopkits y marca personal conservan sus paneles.

El panel usa cuatro pestañas (misma lógica y handlers que antes; solo cambia el layout):

| Pestaña | Contenido |
| --- | --- |
| **Conexiones** | Placeholder para el hub de APIs (fase siguiente). |
| **Canal** | Perfil BeatStars, lista de automatizaciones, canal activo/pausado, prioridad, géneros, carpeta e imágenes locales, opciones visuales y horarios semanales. |
| **SEO y tendencias** | Tags de selección, tags SEO y **plantillas del canal** (título, descripción, redes, hashtags; se guardan en `/automatizacion/canales.json`). |
| **Avanzado** | Consulta de estado, recargar desde Dropbox, simulación de 14 días, resumen de análisis y tabla de jobs planificados. |

La barra de estado bajo las pestañas resume la operación en curso o errores de lectura.

**Solo Dropbox (desde 2026-10-18).** El panel lee y escribe `/type-beats/config.json`
(documento del worker, mismo formato que antes) y el registro `/automatizacion/canales.json`.
`config/app_config.json` ya no se lee ni se escribe. Los canales del combo son los de tipo
`beats` del registro; los canales nuevos se crean desde **Agregar canal** (ficha de Beats en el
registro, slug derivado del nombre e inmutable). Antes del primer uso hay que migrar el
registro: ver `docs/TYPE_BEATS_CHANNELS.md` («Migración al registro en Dropbox»).

Contenido de `/type-beats/config.json`:

- Perfil público HTTPS de BeatStars para el catálogo compartido.
- Una automatización por canal: activa/pausada, prioridad, horarios semanales en
  Buenos Aires, **Tags de selección**, tags SEO y géneros separados por comas,
  carpeta local de imágenes. `selection_tags` es independiente de `tags` (SEO).
- Cuota global fija de **6 intentos diarios**, incluyendo fallos, y buffer de
  **14 días**, según el contrato de Fase 2. No son límites editables por canal.

Agregar canal crea una automatización pausada con lunes a las 18:00. El formulario
conserva los cambios al cambiar de canal; guardar valida todos los canales y
horarios. La carpeta puede quedar vacía, pero si se indica debe existir. El guardado
publica por CAS con merge de 3 vías por campo (`core/cloud_merge.py`): si otra PC cambió
otros campos se fusionan; si cambió el mismo campo, el panel informa el choque, conserva el
borrador y exige recargar.
La barra inferior muestra el checklist de preparación (`readiness_beats` + informe SEO)
y si el canal está listo para piloto.

**Analizar perfil** usa el extractor público de Fase 1 en un `QThread`: muestra
progreso por página y un resumen de tracks, duraciones disponibles y tags frecuentes.
El resultado queda en memoria hasta cambiar de perfil o cerrar el panel; no altera
el catálogo SQLite ni descarga audio. Cancelar descarta el resultado y detiene las
solicitudes siguientes. Una solicitud de red en curso debe terminar o alcanzar su
timeout (10 segundos por operación de socket en el transporte existente). No se
termina el hilo a la fuerza; cerrar o Escape cancela y difiere el cierre hasta que
el hilo termine. Los fallos de red no muestran respuestas ni URLs del servidor.

**Consultar estado de Beats en Dropbox** hace solo una lectura en otro `QThread`,
con la conexión local de Dropbox descripta abajo. Muestra cantidades
por estado, presencia de lock e intentos consumidos hoy. No inicializa documentos,
toma locks ni reserva intentos. Si falla, conserva la última instantánea disponible;
la cancelación interrumpe las esperas de reintento y descarta el resultado de una
operación en curso. Si el documento no existe, lo informa sin crearlo.

**Probar sin subir** (simulación de 14 días) usa `beat_schedule.plan`, sobre el borrador del formulario y el
perfil analizado. Por defecto muestra explícitamente un escenario con estado vacío.
La casilla para usar estado remoto exige haberlo consultado; usa esa instantánea,
no un estado en tiempo real. Muestra slots, canal, track ID y ciclo, junto al
presupuesto disponible hoy. La simulación no cambia el estado ni el archivo de
configuración. Fase 2 planifica slots independientemente de la cuota: los intentos
se cuentan al subir. **Tags de selección** restringe los tracks activos del canal:
basta que un tag del track coincida exactamente con uno de `selection_tags`,
ignorando mayúsculas y espacios exteriores. No busca fragmentos ni palabras dentro
de otro tag. Ausente o vacío conserva la selección anterior del catálogo activo.
Sin coincidencias no propone jobs para ese canal; los demás canales siguen su plan.
Tags SEO, géneros e imágenes mantienen su función de metadata y recursos visuales.
Se aceptan hasta 40 tags de selección, de hasta 100 caracteres cada uno.

El panel permite publicar configuración remota mediante el botón explícito descripto abajo.
Fase cerrada el 2026-10-12 con autorización del usuario después de revisar y corregir.

Validación offline:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_beat_*.py' -v
```

Las pruebas del panel verifican persistencia aislada, selección de canales,
validación, simulación sin mutaciones, recepción de metadata con fixtures, UI
responsiva mientras espera una solicitud, cancelación sin resultados tardíos y
cierre diferido. No requieren BeatStars ni Dropbox reales.

## Revisión y cierre

La revisión local de bugs corrigió la carga de tags/géneros inválidos y JSON
ambiguo, la pérdida silenciosa de prioridades fuera del rango de un `QSpinBox`,
el resumen obsoleto tras un análisis fallido, y la construcción de miles de celdas
en el hilo de UI. La tabla usa un modelo de datos que conserva todas las filas
(probado con 33.600 jobs). La prioridad admite los enteros del esquema de Fase 2.

La consulta remota ahora interrumpe sus esperas de Retry-After al cancelar, comprueba
el evento antes de cada reintento y distingue un estado remoto ausente de un estado
vacío existente. Una solicitud de Dropbox en curso aún debe terminar o alcanzar el
timeout del adaptador (30 segundos por operación). No cambia el adaptador de Fase 2.
La revisión de seguridad independiente no encontró vulnerabilidades confirmadas.

Validación final: **67 tests de Beats aprobados** (18 del panel y 49 de Fases 1/2),
`smoke_sections.py`, `smoke_kit_panel.py`, importación de `main.py` y chequeo de
whitespace. NumPy y watchdog, ya declarados por el proyecto, se instalaron únicamente
en `.venv` para desbloquear las verificaciones. No se modificaron requisitos ni
archivos de Loopkits o marca personal. No se hizo una consulta real a BeatStars o
Dropbox durante el cierre: las verificaciones funcionales usan fixtures y dobles.

## Corrección incremental: conexión local y configuración Dropbox

El panel de Beats prioriza `tokens/dropbox_worker.json`, el archivo privado que
ya usa Loopkits y genera `scripts/kit_dropbox_auth.py`. Lee su `app_key` y
`refresh_token` en memoria, sin copiarlos al formulario, configuración local,
logs o mensajes. No cambia el cliente ni el funcionamiento de Loopkits.
Si el archivo existe pero está mal formado o la autorización falla, se informa
un error sanitizado; no se cambia silenciosamente de cuenta. Si no existe,
se usan `BEAT_DROPBOX_APP_KEY` y `BEAT_DROPBOX_REFRESH_TOKEN` del entorno local.
Si tampoco están presentes, el guardado local sigue disponible.

Los botones **Elegir carpeta Dropbox**, **Elegir carpeta Dropbox por género** y
**Elegir archivo Dropbox** abren un navegador remoto. Doble clic abre carpetas;
**Subir** vuelve al nivel anterior. Para videos/imágenes, abrir la carpeta deseada
y seleccionar esa carpeta. Para la miniatura, seleccionar un archivo PNG, JPG,
JPEG o WebP. La carpeta de imágenes se asigna al género ingresado; elegirla de
nuevo reemplaza solo esa asignación. Seleccionar no guarda ni publica automáticamente.

Las rutas tienen la forma `/Videos`, `/imagenes/trap`, `/imagenes/miniatura.png`:
son relativas a la raíz visible de la app de Dropbox autorizada. Para una app
de tipo App folder, no agregar `/Apps/<nombre de app>` ni una ruta del disco.
La raíz se usa para navegar; seleccionar una carpeta requiere abrir una subcarpeta.
Videos y miniatura pasan a origen Dropbox al seleccionarlos.

**Recargar configuración de Dropbox** lee solo `/type-beats/config.json` y su
revisión. Si existe, reemplaza el borrador del formulario: guardar localmente
sigue siendo una acción separada. Si no existe, conserva el borrador local y
habilita su creación por CAS. Una lectura fallida o cancelada no habilita publicación.
La configuración remota debe ser válida para los canales locales; las rutas
locales configuradas deben existir en este equipo.

**Publicar al robot** (barra inferior) exige una lectura previa de Dropbox (se hace al
abrir el panel o con **Recargar desde Dropbox**). Si cambiaron plantillas o canales, primero
guarda `/automatizacion/canales.json`; después publica `/type-beats/config.json` por CAS:
creación estricta si estaba ausente o update con la revisión consultada. Ante un conflicto de
revisión relee y fusiona por campo; un choque en el mismo campo conserva el borrador y exige
recargar. Nunca hay overwrite. Tras cancelar o una respuesta
incierta también se exige recargar: una solicitud enviada podría haber terminado.

El panel **nunca inicializa, reemplaza, migra en Dropbox ni reconstruye
`/type-beats/state.json`**. Consultarlo sigue siendo una lectura; si falta o es
inválido, lo informa sin escribirlo. Publicar configuración no crea estado.
La puesta en marcha del worker continúa siendo un procedimiento independiente.

Todas las operaciones remotas corren en QThread. El listado no es recursivo y
tiene topes por carpeta de 10 páginas, 2.000 entradas y 120 segundos, comprobados
entre solicitudes. Un listado que supera el límite falla sin mostrar resultados
parciales. Cancelar interrumpe nuevas solicitudes y descarta resultados; cerrar
el navegador espera la finalización del hilo. Solicitudes en curso esperan su
timeout (30 segundos por operación de socket); la lectura JSON conserva el
límite de 8 MiB y plazo de 180 segundos del adaptador existente. Los errores
no muestran respuestas, credenciales, cursores ni excepciones del SDK.

GitHub Actions sigue usando exclusivamente **`BEAT_DROPBOX_APP_KEY`** y
**`BEAT_DROPBOX_REFRESH_TOKEN`**. Para que Actions vea las mismas rutas elegidas
en el panel, configurar allí los valores de la misma app autorizada en Loopkits,
desde el archivo privado, sin pegarlos en documentos ni commits. No renombrar
los secretos a `KIT_*`: ambos workers mantienen su configuración independiente.
No se modificaron workflows, `main.py`, Loopkits ni Marca Personal.

Pruebas offline específicas: `test_beat_panel_cloud.py` cubre credenciales locales,
fallback, errores sanitizados, navegación paginada y limitada, carpetas/archivos,
cancelación y cierre, CAS y preservación byte a byte del estado existente o ausente.


## Pestaña Conexiones (Automation Hub, Fase 2)

Muestra por canal de Beats semáforos de YouTube (`tokens/<canal>.json`), Dropbox worker
(`tokens/dropbox_worker.json`), Notion Beats y GitHub CLI, más un checklist de preparación.
La lógica está en `core/automation_status.py` (sin Qt, solo códigos `ok/missing/invalid/unknown`);
los widgets, en `core/beat_connections_form.py`.

- **Conectar YouTube**: reusa `ConnectChannelWorker` (OAuth en el navegador).
- **Guardar Notion**: token y page ID van a `tokens/beat_secrets.json` (no versionado); los campos
  se limpian al guardar y nunca se vuelven a mostrar.
- **Sincronizar secretos del canal**: `QProcess` a `scripts/beat_secrets_sync.py --channel --slug`
  (lista de argumentos, sin shell, sin stdin). El log se sanitiza y recorta.
- El canal necesita `actions_slug` en la configuración para poder sincronizar.
- TODO (manual): instalar GitHub CLI y correr `gh auth login` antes de sincronizar.