# Plan: automatizar publicación de type beats (biblioteca + BPM/key + YouTube + Dropbox)

## Context
La app (PyQt, `main.py` 2055 líneas) genera videos con FFmpeg pero la publicación y la promoción son manuales.
Objetivo: reducir tiempo de creación → subida. Dolor principal: subir a YouTube y armar la descripción
(link BeatStars, BPM, key). Además: navegar Dropbox, guardar beats con metadata, y saber hace cuánto se subió cada uno.
Restricciones del usuario: varias cuentas de Google distintas; pocos tokens (plan barato de Claude) → fases chicas,
una sesión por fase, prompts cortos y específicos.

Código existente a reutilizar (`main.py`): `VideoGeneratorWorker` (L147, genera el video; recibe `beats_info`),
`ChannelManager` (L410, canales/grupos en `config/app_config.json`), `MainWindow._load_beats_from_files` (L1178),
`_assign_channel_to_beats` (L1433), `_process_finished` (L1905, punto donde enganchar la subida), `EditBeatDialog`
(`edit_beat_dialog.py`, ideal para editar BPM/key/link).

## Reglas de ahorro de tokens (aplican a todas las fases)
- Una fase = una sesión nueva. No arrastrar contexto viejo (`/clear` entre fases).
- No pedir "analiza todo el proyecto": en cada prompt nombrar los archivos y líneas exactos.
- Módulos nuevos chicos en `core/` (no seguir engordando `main.py`); así Claude lee archivos pequeños.
- Pedir primero un plan de 5 líneas y recién después el código; pedir diffs, no reescrituras completas.
- Modelo: **Sonnet** para casi todo; **Haiku** para tareas mecánicas (Fase 0, plantillas, tests simples);
  **Opus** solo si Sonnet falla 2 veces en algo difícil (OAuth/auditoría YouTube).
- Hacer commit al terminar cada fase para poder volver atrás.

## Fase 0 — Preparación de automatización Type Beats ✅ COMPLETADA (revisión aplicada)
Esta fase prepara el roadmap aprobado de Type Beats sin cambiar el comportamiento productivo.
- Alcance: documentación del roadmap, inventario de smokes aplicables, línea base y revisión de exposición documental.
- Organización futura: lógica nueva en módulos pequeños `core/beat_*`; el panel de automatización será separado de la UI existente;
  los entry points y verificaciones irán en scripts propios bajo `scripts/`.
- Límites: no tocar Loopkits ni marca personal; no ampliar `main.py`; no alterar el flujo actual de generación, configuración,
  publicación o render. Las fases 1+ ya descritas siguen siendo el roadmap aprobado y no se reescriben en esta preparación.
- Revisión aplicada: alcance, smokes y exposición documental revisados; sin hallazgos que amplíen el alcance ni expongan secretos o rutas personales.
- Línea base (2026-10-12, `.venv\\Scripts\\python.exe`): `smoke_publish_at.py` no corre porque falta `tzdata`
  para `America/Argentina/Buenos_Aires`; `smoke_transcribe_extract.py` no corre porque no se encuentra `ffmpeg`/`ffprobe`
  en `bin/` ni en `PATH`. No se habilitó la variante de Whisper que descarga un modelo.
- Revisión documental: no se encontraron valores de credenciales; las guías nombran variables secretas y archivos locales
  sin publicar sus contenidos. No hay rutas personales concretas en la documentación vigente; el `app_config.json` local
  contiene rutas del equipo y permanece fuera del cambio para no alterar configuración ni comportamiento.

## Fase 1 — Catálogo público de BeatStars para Type Beats ✅ COMPLETADA (2026-10-12)
- Alcance de esta fase: extractor público en `core/beat_http.py`, `beat_queries.py`, `beat_source.py`,
  `beat_catalog.py` y `beat_sync.py`, independiente de la UI y de la biblioteca histórica.
- Lee el perfil configurado en `beat_automation.beatstars_profile_url`, sin login ni cambios en BeatStars:
  queries públicas de solo lectura, sin descargar audios. Captura título, URL, tags, duración y referencias
  estables para resolver el preview en otra fase; no guarda URLs de audio temporales ni datos privados del perfil.
- Catálogo SQLite separado y versionado por perfil/ID estable: actualización incremental, altas, reactivaciones,
  tracks inactivos y revisiones de las últimas 20 versiones. Solo aplica escaneos completos en una transacción.
- Seguridad: destino HTTPS fijo, allowlist, sin redirects/cookies/auth/proxies del entorno, límites de recursos,
  timeouts y errores con códigos fijos. Revisión de seguridad sin vulnerabilidades confirmadas en este alcance.
- Bugbot: corregidos los dos hallazgos sobre duraciones enteras enormes y límite de tracks realmente acumulados.
  Validación: 22 tests sin red con fixtures/fakes aprobados; prueba real del perfil configurado con 1138 tracks,
  seguida de otra sincronización con 1138 sin cambios y la misma versión del catálogo.
- Uso y límites: `docs/BEATSTARS_CATALOG.md`. Configuración y catálogo locales excluidos de Git.
  Limitaciones: endpoint público sin contrato garantizado; plazo global comprobado entre operaciones de socket.
  Resolución/descarga de previews, UI y automatización de videos quedan para fases posteriores.
- Sin cambios en `main.py`, `kit_*`, Loopkits ni marca personal. Las fases históricas siguientes se conservan.

## Fase 2 — Estado y planificación Type Beats ✅ COMPLETADA (2026-10-12, revisión aplicada)
- Implementación aislada en `core/beat_schema.py`, `beat_cloud.py`, `beat_state.py`,
  `beat_schedule.py` y `beat_fakes.py`; configuración y estado versionados en `/type-beats/`
  con credenciales `BEAT_DROPBOX_*`, sin reutilizar estado ni configuración de Loopkits.
- Escrituras por rev, reintentos limitados, lock con vencimiento y token de dueño,
  migración idempotente de esquema 0 a 1 y validación de documentos.
- Slots Buenos Aires, buffer de 14 días, rondas por prioridad y ciclos por canal;
  identidad track ID + canal + ciclo + slot. Presupuesto global atómico de seis
  intentos diarios, cargados antes de cada futura llamada y sin devolución ante fallos.
- Dry-run determinista: `scripts/plan_type_beats.py`, con dobles Dropbox y pruebas
  de concurrencia sin red. Uso, decisiones y límites: `docs/TYPE_BEATS_PLANNING.md`.
- Sin render, uploads ni integración con UI/workers. La Fase 2 histórica siguiente se conserva.
- Revisión local aplicada (2026-10-12): corregidos documentos v1 incompletos/JSON ambiguo,
  vencimiento de lock durante reintentos, resultado del plan tras respuesta perdida
  y retroceso del ciclo por cancelación. 49 tests aprobados y dry-run determinista verificado.
- Cierre autorizado después de la revisión. No se hizo una prueba con Dropbox real;
  la validación del adaptador usa el SDK oficial con un cliente falso.

## Fase 3 — Panel de automatizaciones Type Beats ✅ COMPLETADA (2026-10-12, revisión aplicada)
- Panel PyQt independiente en `core/beat_panel.py` y `beat_panel_form.py`:
  perfil público, canales de Beats, horarios Buenos Aires, prioridad, tags, géneros,
  carpeta local de imágenes, activa/pausada, estado y cuota global de seis intentos.
- `beat_settings.py` guarda solo `beat_automation` en la configuración local,
  mediante reemplazo atómico; simulación pura del buffer de 14 días con Fase 2.
- `beat_tasks.py` analiza metadata pública con el extractor de Fase 1 en QThread,
  con progreso, cancelación cooperativa, descarte de resultados y cierre diferido.
  Lectura opcional del estado Dropbox de Beats, sin escrituras ni reservas.
- Revisión de bugs aplicada: metadata/JSON inválidos, prioridades sin truncar,
  resúmenes obsoletos, cancelación de backoff y estado remoto ausente. Tabla con
  modelo `beat_job_model.py` para no crear miles de celdas en el hilo de UI.
- Revisión independiente de seguridad: sin vulnerabilidades confirmadas.
  Validación: 67 tests offline, smokes de secciones y panel Loopkits, carga de
  `main.py` y whitespace aprobados. Uso y límites: `docs/TYPE_BEATS_PANEL.md`.
- `main.py` contiene seis líneas nuevas de cableado; Loopkits y marca personal
  sin cambios. No hay render, uploads ni worker de publicación. No se probaron
  servicios reales durante el cierre; solicitudes en curso esperan su timeout.
- Cierre y commit autorizados por el usuario después de revisión y correcciones.
  Las fases históricas siguientes se conservan.

## Corrección incremental — Dropbox local del panel de Beats ✅ COMPLETADA (2026-10-12, /review-bugbot aplicada)
- El panel reutiliza `tokens/dropbox_worker.json` en memoria; token inválido no
  cambia de cuenta. Sin archivo usa `BEAT_DROPBOX_*`; Actions mantiene esos nombres.
- Navegador remoto para videos, imágenes por género y miniatura, con rutas relativas
  a la raíz visible de la app, QThread, límites de páginas/entradas/plazo y cancelación.
- Guardado local separado de publicación explícita CAS de `/type-beats/config.json`.
  Exige lectura previa y recarga ante conflicto o respuesta incierta; nunca overwrite.
- Sin inicialización ni escrituras de estado remoto; no se modificaron Loopkits,
  Marca Personal, `main.py`, workflows ni archivos privados de configuración/tokens.
- Documentación operativa actualizada. 21 tests nuevos offline; suite final con
  260 aprobados y 2 omitidos, smokes de panel Loopkits y secciones aprobados.
- `/review-bugbot` en el mismo agente según la skill: sin bugs encontrados.
  Sin llamadas a Dropbox real. Commit posterior a la revisión, según lo solicitado.

## Fase 4 — Preview y render Type Beats ✅ COMPLETADA (2026-10-12, revisión aplicada)
- Resolución pública HLS para un job ya reservado, descarga acotada y validación
  de hosts, redirects, tipo, tamaño, duración y decodificación local.
- Fallback Dropbox solo con asociación explícita por track ID en el estado;
  catálogo y rotación de imágenes por canal/género, render 16:9 y miniatura.
- Corrección visual revisada: imagen completamente fija (default),
  montaje opcional de videos locales/Dropbox, fragmentos normalizados sin su audio,
  loop hasta la duración del beat y opciones por canal en el panel de Beats.
- Módulos pequeños `core/beat_preview.py`, `beat_download.py`, `beat_assets.py`,
  `beat_media_schema.py`, `beat_render.py` y `beat_video.py`; temporales y cleanup.
- CLI con dry-run y smokes offline con HLS, Dropbox y FFmpeg falsos.
  Uso, límites y campos opcionales: `docs/TYPE_BEATS_RENDER.md`.
- Revisión y correcciones aplicadas; 102 tests aprobados, incluidos dos con FFmpeg
  real. Límites de validación real documentados en la guía.
- Sin subida a YouTube ni cambios en Loopkits, Marca Personal o `main.py`.
  Cierre autorizado por el usuario; sin commit por instrucción explícita.

## Fase 5 — SEO seguro Type Beats ✅ COMPLETADA (2026-10-12, revisión aplicada)
- Consumidor del JSON de Notion generado con Claude Code, vidIQ y YouTube Analytics:
  validación estricta de versión, fecha, canal, tamaño, campos, tipos y rangos.
- Candidatos deterministas desde tags reales del beat y ficha manual del canal;
  el informe solo ordena coincidencias. Sin LLM ni texto libre del informe en SEO.
- Fallback a última ficha buena del mismo canal/huella manual (30 días), luego manual;
  snapshot reproducible e inmutable por reserva mediante CAS en estado de Beats.
- Lector Notion aislado con `BEAT_NOTION_*`, export JSON local, CLI `--seo-only`
  y `--dry-run`; documentación en `docs/TYPE_BEATS_SEO.md` y tests offline.
- Revisión local y correcciones aplicadas: UTF-8 estricto, plazo durante lectura
  de Notion, snapshots compactos compatibles y reemplazo de caché llena.
  Validación: 129 tests aprobados y 2 omitidos, incluidos casos de regresión
  e integración CLI offline. No se probaron Notion ni informes reales de Claude Code.
- Cierre autorizado por el usuario; sin commit por instrucción explícita.

## Fase 6 — Worker diario Type Beats ✅ COMPLETADA (2026-10-12, revisión aplicada)
- Worker y workflow independientes de Loopkits: catálogo público, buffer CAS,
  render y SEO de Fases 1–5 conectados con `core.youtube.upload`.
- Presupuesto global previo al intento, reserva exclusiva por job, journal de
  receipts/orphans y bloqueo de resultados ambiguos; resumen Telegram sanitizado.
- Matriz por canal, Environments con verificación de restricción a master,
  concurrency sin cancelación, acciones por SHA y permisos `contents: read`.
- Dry-run sin efectos remotos y smokes end-to-end con servicios falsos.
  Uso, conciliación y requisitos de GitHub: `docs/TYPE_BEATS_DAILY.md`.
- Revisión aplicada: ID persistido antes de miniatura mediante adaptador propio,
  selección visual compatible con tags de artistas/video sin géneros y guardas
  de fecha Buenos Aires durante CAS y antes del upload. Hallazgo de miniatura
  cerrado por revisión independiente de seguridad, sin regresiones confirmadas.
- Validación: 30 smokes end-to-end y 129 pruebas de regresión aprobadas;
  2 omitidas. Sintaxis Python y whitespace correctos.
- Sin servicios reales ni cambios al worker/workflow de Loopkits. Quedan como
  pendientes operativos Environments/secretos, dry-run en Actions y pruebas reales.
- Cierre autorizado por el usuario después de revisión y correcciones.
  Sin commit por instrucción explícita.

## Fase 7 — Ciclos y selección por rendimiento Type Beats ✅ COMPLETADA (2026-10-12, revisión aplicada)
- Cubrir el catálogo activo una vez por canal y por ciclo; las reservas cuentan
  como usadas. No repetir hasta 180 días desde la publicación anterior, usando
  el mayor de `slot` y `uploaded_at`; las reservas pendientes/ambiguas bloquean.
- Definición aprobada en esta sesión: score = 50% vistas + 30% CTR + 20%
  porcentaje visto, normalizados por rango percentil con promedio para empates.
  El informe vigente de Fase 5 aporta métricas por etiqueta; el score del beat
  es el promedio de sus etiquetas coincidentes. No se usa el `score` externo.
- Tres grupos por score (tercios, redondeo hacia arriba): mejores, intermedios,
  restantes. Tras la primera vuelta, cada bloque de diez decisiones solicita
  7/2/1 grupos con orden reproducible por seed. Si falta evidencia para algún
  beat activo o se agota el grupo solicitado, fallback LRU sin relajar el descanso.
- Repeticiones con imagen y combinación título/tags distintas de la última
  publicación del mismo beat/canal; si faltan alternativas o historial, bloquear.
- Revisión local con la skill Bugbot aplicada: corregida persistencia del snapshot
  visual (la validación devolvía una copia), planificación de canales ajenos sin
  sus informes, cancelación de inserts ambiguos y tags mal formados en métricas.
- Validación: 174 pruebas aprobadas y 2 omitidas; incluye repetición completa con
  render/SEO/upload falsos, persistencia tras respuesta perdida, cancelación de
  resultados desconocidos y aislamiento del buffer por canal. Sin servicios reales.
- Cierre autorizado por el usuario después de revisión y correcciones.
  Sin commit por instrucción explícita. Guía: `docs/TYPE_BEATS_ROTATION.md`.

## Fase 8 — Hardening y operación Type Beats ✅ COMPLETADA (2026-10-12)
- Revisión completa de catálogo, CAS/locks, cuota global, scheduler, HLS, imágenes/video,
  SEO, YouTube, Telegram, workflow de Actions y receipts/orphans. Alcance limitado a
  fallos reproducidos y procedimientos operativos; sin implementar otras fases.
- Corregidos estado ausente reconstruido como ledger vacío (incluida liberación de lock),
  pausa no observada tras render y slot/fecha Buenos Aires vencidos después de reservar.
  Dropbox de estado usa HTTPS sin redirects/proxies y lectura por chunks acotada.
- Verificación de cuenta OAuth contra `youtube_channel_id`; piloto de un job privado
  sin `publishAt`. Cron en dry-run hasta `BEAT_LIVE_ENABLED=true`, despachos seguros por
  defecto y suite de worker ampliada. No se habilitó producción ni se cambió Actions remoto.
- Recuperación con CLI de solo lectura por defecto, consulta autenticada de YouTube y
  aplicación explícita por CAS, sin reupload, devolución de intentos ni overwrite de IDs.
  Uploader compartido: únicamente cierre explícito de streams para cleanup en Windows.
- Validación final tras auditoría: 212 pruebas Type Beats aprobadas, sin omisiones,
  incluidas dos con FFmpeg
  real; smokes diarios (30) y de video/montaje (34) verdes; los 27 smokes de Loopkits y
  los cuatro de Beats manuales aprobados. actionlint, sintaxis Python y whitespace verdes.
- Lectura real en dry-run del catálogo configurado: 1138 tracks, segunda aplicación con
  1138 sin cambios en SQLite temporal. Cero uploads reales, descargas de audio o mensajes.
- Setup, dry-run, piloto, pausa, rollback, recuperación y límites documentados en
  `docs/TYPE_BEATS_OPERATIONS.md`. Credenciales BEAT_* y aceptación del worker remoto
  siguen pendientes del setup: no se afirma haber probado OAuth/Dropbox/Telegram/Actions reales.
- El commit de cierre conserva los cambios de Fase 7 que ya estaban pendientes al iniciar
  esta sesión, para versionar exactamente la base probada. `main.py`, `kit_*`, workflow y
  dependencias de Loopkits sin cambios; sin cambios funcionales al flujo manual de Beats.
- Revisión adicional de `1615c5f` antes de editar: corregidos logging con handlers previos,
  forks/eventos no confiables, Environment cruzado, destino OAuth cambiado durante la
  corrida, lease perdido antes del insert, backoff ilimitado, plazo total de YouTube
  y falso fallo tras confirmar el receipt remoto. Se suman 14 regresiones; 191 pruebas
  en modo worker verdes. Transporte Google exclusivo de Beats, sin modificar
  uploader compartido, Loopkits ni Marca personal durante esta revisión.
- Evidencia, severidades y nuevos campos de setup (`actions_slug`) documentados en
  `docs/TYPE_BEATS_OPERATIONS.md`. Sin hallazgos confirmados pendientes en código;
  cero uploads reales, mensajes o cambios remotos durante la revisión.

## Corrección postimplementación — Filtro de selección de beats por canal ✅ COMPLETADA (2026-10-12, revisión aplicada)

- Campo opcional `selection_tags` independiente por canal, editable como **Tags de selección**;
  `tags` conserva su función SEO y los géneros conservan su función visual. Un track activo
  es elegible si al menos un tag coincide exactamente tras `strip().casefold()`, sin coincidencias
  parciales ni etiquetas hardcodeadas. Campo ausente o vacío conserva el comportamiento anterior.
- Filtrado antes de planificar y reservar; también protege jobs antiguos pendientes y consumidores
  directos de SEO/render/publicación. Sin coincidencias: `no_matching_tracks` bloquea solo ese canal,
  sin jobs nuevos, consumo de cuota, render, uploads ni fallback al catálogo completo. Telegram
  recibe únicamente códigos fijos y contadores, sin títulos, URLs, tokens ni datos sensibles.
- `/review` con Bugbot aplicado: dos hallazgos medios reproducidos y corregidos. El filtro
  desactualizado durante escaneo/render ahora se verifica antes de cada transición y escritura CAS,
  incluidos reintentos. El bypass de jobs excluidos desde CLI/API ahora falla cerrado con guardas
  compartidas. Un intento ya confirmado conserva su ledger aunque se bloquee el insert.
- Validación: **241 pruebas Type Beats aprobadas, sin omisiones**, con FFmpeg real habilitado;
  incluye coincidencia exacta, rechazo de parciales, cuota intacta, aislamiento, compatibilidad,
  jobs anteriores, carreras y Telegram sanitizado. Sintaxis Python y whitespace correctos.
  Servicios externos falsos: cero uploads, mensajes o cambios remotos reales.
- Archivos nuevos `core/beat_selection.py` y `tests/test_beat_selection.py`; documentación operativa
  actualizada. Cierre y único commit autorizados por el usuario después de la revisión.
  Sin cambios en Loopkits, Marca Personal ni `main.py`; no se habilita producción.

## Fase 0 histórica — Limpieza del repo (registrada previamente)
La limpieza original de herramientas/configuración fue anotada como completada en una versión anterior del plan; se conserva
como antecedente y no cuenta como cierre de la Fase 0 de preparación de automatización definida arriba.
Incluía excluir `ffmpeg-8.0/` y `bin/ffmpeg.exe`, unificar PyQt en `requirements.txt` y evitar versionar configuración
con rutas personales usando `config/app_config.example.json`.

## Fase 1 histórica — Biblioteca local + historial (Sonnet) — la base ✅ COMPLETADA
- `core/library.py`: SQLite `library.db`. Tablas `beats` (id, nombre, ruta, hash, bpm, key, beatstars_url, notas, creado)
  y `uploads` (beat_id, canal, grupo, youtube_id, url, título, subido_en, estado).
- Importar beats copiando el audio a `library/` (dedupe por hash).
- Vista "Biblioteca" (nuevo diálogo) con columnas: nombre, BPM, key, "subido hace X" por canal, filtros
  (nunca subido / sin subir al canal X / >6 meses).
- Función `humanize_ago(fecha)` ("hace 3 meses").
- Enganchar en `_load_beats_from_files` y `_process_finished`.
Prompt: "Crea core/library.py con SQLite (tablas beats y uploads, esquema en PLAN). Implementa import_beat(path),
list_beats(filtros), record_upload(...), humanize_ago(). Luego agrega un diálogo library_dialog.py que liste beats y
permita seleccionarlos para el flujo existente de main.py (_load_beats_from_files, línea ~1178). Pregunta antes de
cambiar firmas existentes. Sin tocar la generación de video."

## Fase 2 — BPM/key + link BeatStars + plantilla de descripción (Sonnet; plantillas con Haiku) ✅ COMPLETADA
- `core/audio_analysis.py`: BPM y key con `librosa` (cargar solo ~60 s del audio para rapidez), corrigiendo
  doble/mitad de tempo. Resultado siempre editable.
- Ampliar `edit_beat_dialog.py` con campos BPM, key y link BeatStars (se guardan en la biblioteca).
- `core/description.py`: plantilla por canal (guardada en `app_config.json`) con variables
  `{name} {bpm} {key} {beatstars_url} {tags}` + redes/hashtags del canal.
Prompt: "Crea core/audio_analysis.py: analyze(path)->(bpm,key) con librosa sobre los primeros 60 s. Agrega campos bpm,
key y beatstars_url a edit_beat_dialog.py (pre-rellenados, editables) y guárdalos con core/library.py. Crea
core/description.py que renderiza una plantilla por canal con {name},{bpm},{key},{beatstars_url}. Muestra una vista
previa de la descripción en el diálogo."

## Fase 3 — Subida a YouTube, multi-cuenta (Sonnet; Opus solo si OAuth se complica) ✅ COMPLETADA
(Implementado: `core/youtube.py`, `core/upload_worker.py`, guía en `docs/YOUTUBE_SETUP.md`.
Pendiente del usuario: pasos de Google Cloud y prueba real F3 con un canal de prueba.)
Pasos manuales previos del usuario (documentar en la fase): crear proyecto en Google Cloud, activar YouTube Data API v3,
crear credenciales OAuth "Escritorio", pasar la app a "In production", agregar cada cuenta como usuario de prueba,
(más adelante) pedir auditoría de la API — hasta entonces los videos suben **privados** y se publican a mano en Studio.
- `core/youtube.py`: un token por canal en `tokens/<canal>.json` (no versionado); `connect_channel()`, `upload()`
  con título, descripción, tags, miniatura, `privacyStatus`/`publishAt`.
- Botón "Conectar canal" en `ChannelManager` y checkbox "Subir a YouTube al terminar" en `MainWindow`
  (`_process_finished`, L1905); registrar en `uploads`.
- Aviso si el beat ya fue subido a ese canal (usa Fase 1).
Prompt: "Implementa core/youtube.py con google-api-python-client: connect_channel(nombre) guarda token en
tokens/<nombre>.json, upload(video, título, descripción, tags, thumbnail, privacy). Agrega botón 'Conectar canal'
en ChannelManager (main.py L410) y la subida opcional en _process_finished (L1905), registrando en core/library.py.
Antes de subir, avisa si el beat ya está en ese canal. Verifica en la documentación oficial el costo actual de cuota."

## Fase 4 — Dropbox por API (Sonnet) ✅ COMPLETADA
(Implementado: `core/dropbox_client.py`, `dropbox_browser_dialog.py`, botón "Dropbox..." en la biblioteca, guía en `docs/DROPBOX_SETUP.md`. Pendiente del usuario: crear la app de Dropbox y prueba real F4.)
- `core/dropbox_client.py`: OAuth con PKCE (refresh token), `list_folder`, `download`.
- Diálogo navegador de carpetas Dropbox (solo audio: mp3/wav) con selección múltiple → descarga e importa a la
  biblioteca (Fase 1).
Prompt: "Implementa core/dropbox_client.py (SDK oficial, OAuth PKCE con refresh token) y dropbox_browser_dialog.py:
árbol de carpetas, filtrar mp3/wav, selección múltiple y botón 'Importar a biblioteca' que descarga y llama a
library.import_beat()."

## Fase 5 — Importar historial existente de YouTube (Haiku/Sonnet) ✅ COMPLETADA
`videos.list` por canal para importar títulos/fechas ya publicados a `uploads` y emparejar con beats por nombre;
refrescar vistas (cuota casi nula). Cierra el "hace cuánto" también para videos anteriores a la app.

## Fase 6 — Extras opcionales (según presupuesto de tokens)
Miniaturas automáticas (Pillow), carpeta vigilada (`watchdog`), modo CLI, aceleración GPU `h264_nvenc`,
versión vertical 9:16 para Shorts, partir `main.py` en módulos.

## Fase 7 — Título/descripción por canal, link BeatStars al importar, clip vertical y UI responsive (Sonnet) ✅ COMPLETADA
- `core/channel_templates.py`: `title_template` por canal en `app_config.json` (marcador `{name}`; fallback a la plantilla
  global `[Type] {name} | Free for Profit`). Separar título crudo (YouTube, conserva `|`) de nombre de archivo (sanitizado).
- Gestionar Canales (`ChannelManager`): panel con título y descripción del canal (cuadro grande, se estira), vista previa;
  se guarda con `save_config()` (único escritor). Quitar el editor de plantilla de `EditBeatNameDialog`.
- Importación manual (`_load_beats_from_files`): pedir el link de BeatStars por cada beat nuevo y guardarlo en
  `beats.beatstars_url`. No se pide en la carpeta vigilada ni en Dropbox.
- Clip vertical: campo de segundos (15-60) recordado en `app_config.json` (`vertical_seconds`).
- Layout responsive: sin alturas/anchos máximos fijos, listas con stretch, panel derecho con scroll, fuentes ≥12 px,
  mínimo usable en pantalla chica.
Verificación: importar un beat y cargar el link; guardar título/descripción en un canal y reabrir; generar y ver título
(con `|`) y descripción con el link en `{beatstars_url}`; cambiar los segundos del vertical; achicar/maximizar la ventana.

## Loop kits — Análisis de packs, solo lectura ✅ COMPLETADA
- `core/kit_analyze.py` + `scripts/analyze_kits.py` (`--pack`, `--max-loops`, `--show-names`): por pack, cantidad de loops,
  preview nombrada y su duración, preview de cada loop (`kit_trim.preview_end_sec` sobre copia temporal que se borra siempre),
  suma total y cuántos videos de 135-195 s salen sin repetir loops (previews largas partidas en tramos de ≤45 s).
  No sube ni escribe en Dropbox ni en `library.db`. Guarda `exported_videos/loop_kits/analysis.json` (ignorado por git).
- Smoke: `scripts/smoke_kit_analyze.py` (sin red).

## Loop kits — Estado y credenciales en la nube ✅ COMPLETADA
- `core/kit_cloud.py`: `read_json` / `read_json_rev` / `write_json` en Dropbox vía `dropbox_client._client()` (un solo commit
  por escritura, con `rev` opcional para detectar pisadas). `bootstrap_credentials(env)` arma `config/` y `tokens/` en un
  directorio temporal (0700/0600) desde variables `KIT_*`, sin imprimirlas; `credentials_dir(env)` hace `chdir` y lo borra.
- `core/kit_state.py`: `upsert_pack`, `record_run`, `selection_history`, `has_scheduled_run` con la firma de `kit_store` sobre
  un `state.json` en Dropbox (`KIT_STATE_PATH`), lock con vencimiento (`acquire_lock` / `release_lock` / `locked`) y ciclo
  por kit (`cycle_videos`, `rest_until`, `used_names`, `used_ref_images`).
- Todavía no está conectado a `run_kit_preview` ni a `kit_publish`: siguen usando `kit_store`.
- Smoke: `scripts/smoke_kit_state.py` (sin red, Dropbox falso en memoria).

## Loop kits — Worker semanal (Telegram + GitHub Actions) ✅ COMPLETADA
- `core/kit_notify.py` (Telegram por urllib: `send`, `summary` con links a YouTube Studio, `alert` sin datos privados),
  `scripts/run_kit_weekly.py` (lock, 3 slots lun/mié/vie 18:00 en hora de Buenos Aires con `tz` explícito, 3 kits distintos,
  estado en Dropbox, resumen y lock liberado en `finally`; `--dry-run` no renderiza ni sube),
  `.github/workflows/kit-weekly.yml` (solo `schedule` y `workflow_dispatch`, `contents: read`, acciones fijadas por SHA),
  `requirements-worker.txt`, `docs/KIT_WEEKLY.md`.
- Cambios aditivos en `run_preview` y `publish_preview`: parámetros opcionales `store`, `tz` y `exclude_paths`.
- Smoke: `scripts/smoke_kit_weekly.py` (sin red).

## Loop kits — Catálogo de kits y marcador `{link}` ✅ COMPLETADA
- `core/kit_catalog.py`: `load(path, genres=None)` valida `kits.json` (lista de `{folder, name, payhip_url, genre, active}`:
  link vacío permitido pero no elegible, link con valor debe ser https, género dentro de los configurados, carpetas sin repetir);
  `eligible(catalog, packs)` deja solo kits activos, con link https y carpeta presente en los packs de Dropbox.
  `configured_genres(app_config)` lee `kit_preview.genres`. Los errores nombran la entrada por número, nunca el nombre ni el link.
- `core/kit_publish.py`: `{link}` en la plantilla de descripción se reemplaza por `templates['link']` (vacío si falta);
  sin el marcador la descripción no cambia. Sin cambios de firma.
- Todavía no está conectado a `run_kit_weekly`.
- Smoke: `scripts/smoke_kit_catalog.py` (sin red).

## Loop kits — Audio por duración y ciclo de 3 videos por kit ✅ COMPLETADA
- `core/kit_audio.py`: `plan_audio(pack, used_before, rng, target_min=135, target_max=195)` devuelve tramos
  `{name, path, start, end}`. Con archivo preview toma el primer tramo libre y corta en el silencio más cercano al punto
  ideal (reparte el hueco en partes parejas), sin pisar tramos ya usados; sin silencio en la ventana corta directo con
  fundido y avisa. Sin preview (o con la preview agotada) suma previews de loops no usados en el ciclo y recién después
  repite, empezando por el que hace más que no suena. `cut_segments` escribe los wav; `downloader(tmp)` baja de Dropbox
  solo lo que se usa. Los avisos no llevan nombres de archivo ni de kit.
- **Kits chicos:** `scripts/analyze_kits.py` no dio datos (en esta PC `kit_preview.dropbox_root` no está configurado y
  reporta 0 loops), así que la regla es un default configurable: un loop nunca se repite dentro del mismo video; si el
  kit no llega a `target_min_s` sale un video más corto con warning siempre que supere `short_min_s` (60 s) y ese kit
  cierra el ciclo con ese único video; por debajo de `short_min_s` no se arma nada (`ok` False). Revisar `short_min_s`
  cuando haya un análisis real.
- `core/kit_cycle.py`: funciones puras sobre el estado de `kit_state.load()`. `advance` (al tercer video, o con `close`,
  el kit descansa 30 días), `current` / `status` (descanso cumplido = ciclo nuevo en 0; separación de 7 días),
  `eligible_packs`, `pick_week` (3 kits distintos con `kit_select.choose`, sin modificarlo) y `used_segments` (tramos del
  ciclo vigente desde `loops_json` de las corridas). Los plazos se cuentan por fecha de calendario para que la corrida
  semanal no falle por minutos.
- Config en `kit_preview`: `target_min_s`, `target_max_s`, `short_min_s`, `cycle_max_videos`, `cycle_rest_days`,
  `kit_min_gap_days`, `kits_per_week`.
- `core/kit_trim.py`: helper aditivo `silence_points(path)`; lo existente no cambia.
- Todavía no está conectado a `run_kit_preview` ni a `run_kit_weekly`: siguen con `choose` y `pack_cooldown_days`.
- Smokes: `scripts/smoke_kit_audio.py` y `scripts/smoke_kit_cycle.py` (sin red).

## Loop kits — Nombres de video por LLM y link con seguimiento ✅ COMPLETADA
- `core/kit_llm.py`: `call(system, user, cfg, key=None)` por urllib (API estilo chat/completions). `cfg` trae `base_url`
  (https), `model` y `key_file` (archivo con la clave, fuera del repo); opcionales `max_tokens`, `temperature`, `timeout`.
  La clave no se imprime ni aparece en los errores (solo el tipo de excepción).
- `core/kit_names.py`: `propose(kit, genre, used_names, n=5, llm_call=None, cfg=None, key=None)` devuelve hasta `n` nombres de
  1 o 2 palabras, sin vacíos, duplicados (sin distinguir mayúsculas ni tildes), usados ni el nombre del kit (modo manual: el
  usuario elige). `pick(...)` es el modo automático: la primera válida o `None`. `track_link(url, id)` agrega
  `utm_source=youtube&utm_content=<id>` conservando query y fragmento, una sola vez; `new_tracking_id()` da el id por video
  (se genera antes de subir porque el `youtube_id` aún no existe).
- `core/kit_state.py`: `record_run` acepta además `video_name` y `tracking_id` (cambio aditivo), guardados junto al kit y al
  `youtube_id`. Los nombres usados del ciclo siguen en `update_cycle(used_names=...)`.
- Config del LLM: `base_url`, `model`, `key_file`.
- **Conectado** al worker (vía `run_preview`): `kit_names.for_pack` pide el nombre con `kit_preview.names` (`genre` obligatorio,
  `enabled` opcional; clave de `KIT_LLM_API_KEY` o `key_file`) evitando los `used_names` del ciclo; `remember` lo guarda ahí
  tras subir. El nombre reemplaza al del pack en `{name}` (título y descripción) y en la portada. Con `names` activo se genera
  un `tracking_id` por video, el link del canal lleva `track_link`, y `video_name` / `tracking_id` quedan en el estado.
  Si el LLM falla se usa el nombre del pack y la subida sigue (solo se imprime el tipo de error). `CloudStore` expone
  `get_cycle` / `update_cycle`; el workflow pasa el secret `KIT_LLM_API_KEY`. Sin `kit_preview.names`, nada cambia.
- Pendiente: el género sale de `names.genre` (uno solo); por kit saldrá del catálogo cuando se conecte `kit_catalog`.
- Smoke de conexión: `scripts/smoke_kit_names_wiring.py` (LLM falso).
- Smoke: `scripts/smoke_kit_names.py` (sin red, `llm_call` falso).

## Loop kits — Portada del kit y cuadro 16:9 ✅ COMPLETADA
- `core/kit_cover.py`: `compose(background_path, title, out_path, template=None)` arma la portada 1500x1500: fondo recortado al
  centro, viñeta, grano, borde desgastado, título en mayúsculas condensado con desgaste (manchas, puntos y rayones), marca arriba,
  "LOOP KIT" abajo, sello y código de barras decorativos. El título elige líneas y cuerpo de letra para entrar en su caja.
  La misma semilla da la misma portada (por defecto se deriva del título).
- Todo está en `DEFAULT_TEMPLATE` (tamaño, fracciones de posición, colores, textos, fuentes, desgaste); `template` se mezcla
  encima y solo indica lo que cambia. Textos vacíos o `bars: 0` / `border.width: 0` apagan una pieza. El texto de marca por
  defecto es un placeholder (`BRAND NAME`): la marca real va en la plantilla, no en el código.
- `to_video_frame(cover, out_path, frame=None)`: cuadro 16:9 (1920x1080 por defecto, `FRAME_DEFAULTS`) con la portada centrada
  sobre una copia desenfocada y oscurecida de sí misma.
- Fuentes en `assets/kit_cover/`, ambas SIL OFL 1.1 con su licencia al lado: Oswald (título y "LOOP KIT") y Courier Prime Bold
  (marca, sello y código). Sin logos ni marcas de terceros.
- Smoke: `scripts/smoke_kit_cover.py` (sin red, fondo generado por código).
- **Conectado** en `scripts/run_kit_preview.py` (el worker semanal lo usa a través de `run_preview`): `kit_cover.for_video(cfg,
  fondo, título, tmp)` arma el cuadro 16:9 que recibe el render y una miniatura JPEG (la misma imagen) que va a `publish_preview`.
  El título de la portada es el nombre del pack (cuando se conecte `kit_names`, pasará el nombre del video). `image_path` del
  historial sigue siendo la imagen original.
- Config en `kit_preview.cover` (opcional): `{"template": {...}, "frame": {...}, "enabled": true}`. Sin la clave, o con
  `enabled: false`, nada cambia (imagen original y sin miniatura). Hay que poner la marca real en `template.brand.text`;
  el placeholder `BRAND NAME` es solo del código.
- Smoke: `scripts/smoke_kit_cover_wiring.py` (sin red, Dropbox y YouTube falsos).

## Loop kits — Fondo de portada con IA ✅ COMPLETADA
- `core/kit_art.py`: `background(kit, genre, refs, used, rng, client=None, *, cfg, out_dir, now, fetch, dbx, report)` devuelve
  la ruta local del PNG. `choose_refs` toma 1-2 referencias sin uso en `ref_cooldown_days` (30, por fecha de calendario); si
  no queda ninguna libre repite la más antigua con warning. `list_refs(refs_root, genre)` lee `<refs_root>/<genero>` de Dropbox.
- `api_client` llama a `<base_url>/images/edits` por urllib (multipart, referencias como entrada de edición): `base_url` https,
  `model`, `size`, `quality` y `key_file` configurables; clave de `KIT_IMAGE_API_KEY` o `key_file`, solo en el header. Un único
  pedido por video, sin reintentos. HTTP 400 → `KitArtRejected`; el resto → `KitArtError` (solo código o tipo de error).
- Las referencias se bajan a un temporal que se borra siempre y se envían achicadas, sin metadatos y con nombre genérico.
- `build_prompt`: texto fijo de solo estética (paleta, grano, bokeh, motivos), sin texto en la imagen, sin personas ni parecido
  de nadie. Paleta y motivos salen de `STYLES` por género o de `art.styles`; el nombre del kit nunca entra y los motivos que
  lo contengan (o una palabra de `art.banned_words`) se descartan.
- `for_video(...)`: con `kit_preview.cover_mode: auto` genera el fondo; ante rechazo o cualquier fallo ese video usa la imagen
  manual del pack, avisa por Telegram (sin nombres ni mensajes de error) y la corrida sigue. Sin la clave, o `manual`, nada cambia.
- Estado: cada corrida guarda `ref_images` (cambio aditivo en `kit_state.record_run` y `kit_publish.publish_preview`);
  `kit_art.used_refs(state)` arma el último uso por referencia y `CloudStore.ref_usage()` lo expone al worker.
- **Conectado** en `scripts/run_kit_preview.py`: el fondo generado reemplaza a la imagen del pack como entrada de `kit_cover`.
  En corridas locales (`kit_store`) no hay historial de referencias: la regla de 30 días solo aplica con el estado en la nube.
- Workflow: secret `KIT_IMAGE_API_KEY`. Config y detalles en `docs/KIT_WEEKLY.md`.
- Pendiente: el género sale de `art.genre` (o `names.genre`), uno solo; por kit saldrá del catálogo cuando se conecte.
  Falta la prueba real con 2-3 referencias antes de activar `auto`.
- Smoke: `scripts/smoke_kit_art.py` (sin red, cliente falso).

## Loop kits — Panel de configuración en la app ✅ COMPLETADA
- `loop_kit_panel.py` (PyQt5, independiente): canal y 3 horarios (hora de Buenos Aires), tabla editable de kits (carpeta,
  nombre, link, género, activo), géneros + carpeta de referencias (muestra la carpeta de cada género), modo de portada
  (manual/auto), estado de Telegram ("configurado", sin valores), "Probar dry-run" (`QProcess` sobre `run_kit_weekly.py
  --dry-run`) y "Ver último estado" (corridas sin nombres). Dropbox va en un `QThread`; guarda con `rev`, así que un cambio
  hecho desde otro lado da conflicto en vez de pisarse. Ninguna ventana tiene campos de clave.
- `core/kit_settings.py` (sin Qt): validación (https, sin usuario/clave en el link, género obligatorio y configurado, carpetas
  sin repetir, horarios en rango, refs obligatorias con `auto`) y `apply_to_config`, que solo toca `kit_preview.{channel, slots,
  genres, cover_mode}` y `kit_preview.art.refs_root`. `kits.json` en `/loop_kits/_automation/` (`KIT_CATALOG_PATH`). Si no
  hay config del worker en Dropbox, los kits se guardan igual y los ajustes no (no se crea una config a medias).
- Cambios aditivos: `kit_catalog.validate(data, genres)` (`load` lo reutiliza); `run_kit_weekly` usa `kit_preview.channel`
  como canal por defecto.
- `main.py` (+5 líneas): botón "Configuración de automatización", visible solo en Loop kits, abre el panel en un diálogo.
  El panel no se monta en el `QStackedWidget` porque Loop kits comparte la página de Beats.
- Pendiente: probar a mano en `run_app.bat` que Beats y Marca personal se ven igual.
- Smoke: `scripts/smoke_kit_panel.py` (offscreen, sin red; se corre con `.venv\Scripts\python.exe`, que es donde está PyQt5).

## Verificación por fase
- F0: `git status` limpio y la app abre (`python main.py`).
- F1: importar 2 beats, reabrir la app y ver que persisten; importar el mismo audio dos veces no duplica.
- F2: analizar un beat con BPM/key conocidos y comparar; ver la descripción renderizada con las variables.
- F3: conectar un canal de prueba, subir un video como privado, comprobar el registro en `uploads` y el aviso de duplicado.
- F4: conectar Dropbox, importar un lote y confirmar los archivos en `library/`.
- F5: el "hace cuánto" aparece también en beats anteriores a la app.

## Loop kits — Revisión completa de bugs ✅ COMPLETADA
- `core/kit_week.py` (nuevo) conecta lo que faltaba al worker: catálogo (`kits.json`, solo kits activos, con link y carpeta),
  ciclo (`kit_cycle`: 3 videos, descanso de 30 días, separación de 7), audio por duración (`kit_audio`), y link, nombre y
  género por kit. `scripts/run_kit_weekly.py` lo usa: un kit que no da un video se saltea, que falten kits es un aviso y
  los avisos van al resumen de Telegram. `run_preview` queda igual para el uso local.
- Arreglos: `numpy` en `requirements-worker.txt`; `SystemExit` e import fallido ahora avisan; credenciales locales y
  `--cloud-config` para el dry-run del panel; nombres de video sin repetir entre kits; `pick_week` prioriza el kit que hace
  más que no sale y sigue ante un kit sin audio; cortes a 44,1 kHz estéreo; el panel no pisa tras un conflicto ni se cae
  con un link mal formado; carpetas `_...` y kits sin audio o imágenes quedan afuera; aviso si una entrada del catálogo no
  tiene carpeta.
- Con rotación pareja, 12 kits, 3 videos por semana y 30 días de descanso puede salir una semana incompleta cada tanto
  (se avisa); se evita con más kits o `cycle_rest_days: 28`.
- Pendientes menores: si la miniatura falla por red el video queda sin registrar; el panel no edita la marca de la portada
  (`cover.template.brand.text`) ni más de 3 horarios; `smoke_clip_layouts.py` (Marca personal) ya fallaba y no se tocó.
- Smoke: `scripts/smoke_kit_simulation.py` (6 semanas, 12 kits y casos borde, sin red ni ffmpeg).

## Loop kits — Varios canales ✅ COMPLETADA
- `core/kit_channel.py` (solo librería estándar): `slug(canal)` estable y `paths(slug)` con config, catálogo y estado
  por canal en una subcarpeta `<slug>` de las carpetas actuales. El canal por defecto conserva sus rutas
  (`KIT_CONFIG_PATH`, `KIT_CATALOG_PATH` y `KIT_STATE_PATH` siguen mandando). Estado y lock independientes: un kit puede
  estar en varios canales y su ciclo, descanso, nombres y referencias se cuentan por canal. `check_owner` corta si la
  config o el token de YouTube son de otro canal.
- Cambios aditivos (sin el parámetro nuevo todo se llama igual que antes): `run_weekly(paths=, label=)`,
  `CloudStore(state_path=)`, `--automation` / `KIT_AUTOMATION` en `run_kit_weekly.py`, `kit_week.open_week(kits_path=)`,
  `kit_settings.load_all` / `save_kits` / `save_config(paths=)`.
- Telegram: un solo chat; cada resumen y cada alerta empieza con `[nombre del canal]` (también en el canal por defecto
  cuando corre desde `main()`).
- Workflow: cron diario, job `plan` sin secretos (`scripts/kit_plan.py` lee la variable `KIT_CHANNELS`, `slug[=dia]`,
  por defecto un canal por día desde el domingo) y job `weekly` en matriz con Environment y `concurrency`
  `kit-weekly<-slug>`. `workflow_dispatch` con `channel` y `dry_run`. Sin `KIT_CHANNELS` corre solo el canal por
  defecto los domingos, con el Environment `kit-weekly` de siempre.
- Panel: selector de canal arriba (carga y guarda la config, los kits y el estado de ese canal) y "Crear
  automatización…" (`core/kit_channel_setup.py`: config mínima e índice `channels.json`; no pisa una existente).
  `main.py` no se tocó.
- `scripts/kit_secrets_sync.py`: carga con `gh` los secretos de un Environment (compartidos desde archivos locales,
  entorno o prompt; token de YouTube del canal), siempre por stdin, y crea el Environment limitado a `master` si falta.
- Pendiente del usuario: probar el selector a mano en `run_app.bat`, y la primera corrida real de `kit_secrets_sync.py`
  y del workflow con dos canales (acá solo se probó con dobles de `gh`, Dropbox y YouTube).
- Smoke: `scripts/smoke_kit_multichannel.py` (sin red; la parte del panel necesita PyQt5).

## Loop kits — Carpeta de tienda, categorías y fin del preview nombrado ✅ COMPLETADA
- `core/kit_source.py`: `dropbox_root` es la tienda. Recorre las categorías de `kit_preview.scan_folders` en orden
  (default Individual Kits, Production Suites, Genre Bundles, free kits; `[]` = kits directo en la raíz). Un kit es una
  carpeta con loops en una subcarpeta de `loops_dirs` (nombre exacto, sin mayúsculas: "Drum Loops" no entra) o, si no
  la tiene, en su raíz. Ignora los nombres con las palabras de `ignore_names` (palabra suelta) y las subcarpetas de
  drums, midis, starters, vocals, phrases, stems y layers; mp3+wav del mismo loop cuentan una vez (queda el wav);
  `scan_max_depth` limita cuánto se entra en un bundle (ahí adentro el kit necesita su carpeta de loops).
- **Se quitó el modo "preview nombrado" entero:** `named_previews` y `_is_named_preview` (`kit_source`),
  `_pick_named_preview` y `prefer_named_preview` (`kit_select`), `_plan_preview`, el corte por silencios, los fundidos y
  `silences_fn` (`kit_audio`), `prefer_named_preview` y el hook `silences_fn` (`kit_week`), `--no-named-preview` y la rama
  sin corte (`run_kit_preview`), `preview_file` / `preview_sec` (`kit_analyze`, `analyze_kits`), el valor `named_preview`
  de `AUDIO_MODES` y la clave de `app_config.example.json`. El único `audio_mode` es `assembled`; las corridas viejas
  guardadas con el otro valor se siguen leyendo.
- Mínimo de loops (`min_loops_per_video`, 4): con menos loops sin usar el kit se saltea; con 4 o más que no llegan a
  `target_min_s` sale un video más corto con aviso. Ya no se repiten loops de videos anteriores del ciclo: el video
  corto, o el que deja al kit sin loops para otro, cierra el ciclo. `short_min_s` pasa a 0 (piso opcional).
- Con `cover_mode: auto` un kit sin imágenes es elegible (`kit_select.choose(require_image=)`,
  `kit_cycle.pick_week(require_images=)`); con `manual` sigue necesitando imágenes. Si el fondo no se genera, ese kit se
  saltea. `pick_week(keep_order=True)`: entre kits parejos manda el orden del recorrido.
- Panel: grupo "Carpeta de kits en Dropbox" (raíz, casillas de categorías leídas de Dropbox y reordenables, carpetas de
  loops, nombres a ignorar, profundidad) y botón "Detectar kits" (`core/kit_detect.py`): suma a la tabla los kits que
  falten, sin link ni género; una carpeta duplicada (nombre terminado en " (N)") llega con `active` en false. Todo se
  guarda en la config del canal (`kit_settings`); `main.py` no se tocó.
- Pendiente del usuario: en el panel, cargar la carpeta raíz, "Detectar kits", completar links y géneros y guardar;
  después un dry-run. Revisar a mano los kits que queden afuera por nombre de carpeta.
- Smokes: `scripts/smoke_kit_scan.py` (estructura falsa igual a la real) y los `smoke_kit_*` existentes actualizados.

## Loop kits — Portada por plantilla + fondo y tope de gasto ✅ COMPLETADA
- `core/kit_template_art.py` (nuevo): `cover_mode: template`. La API de imágenes (`images/edits`, vía
  `kit_art.api_client`) recibe la portada modelo del género y un fondo, en ese orden, más el prompt con el título, y
  devuelve la portada cuadrada completa. En Dropbox: `<refs_root>/<genero>/modelo.png` y `.../fondos/` (se listan
  también `.jfif`; todo se convierte a PNG achicado, sin metadatos y con nombre genérico). El fondo no se repite en 30
  días (misma regla y mismo estado `ref_images` que el modo auto); sin fondos libres se relaja con warning.
- Prompt en `kit_preview.art.prompt` con `{titulo}` (reemplazo literal, el título llega sin cambios); sin prompt se usa
  `DEFAULT_PROMPT`, que no nombra personas ni kits. Parámetros configurables: `model`, `size`, `quality`,
  `input_fidelity`, `n`.
- Verificación: `vision_client` (chat/completions con imagen) lee el título y `titles_match` lo compara sin mayúsculas ni
  espacios. Si no coincide, un único reintento; si vuelve a fallar se usa la imagen y Telegram avisa con la portada. Si
  la verificación no responde, se usa la imagen sin reintentar.
- Sin reintentos ante errores de la API: ese video cae a manual y avisa. `KitArtError.billable` marca qué fallos se
  cuentan como cobrados (timeout y 5xx sí; 4xx, rechazo y errores de config no).
- `core/kit_spend.py` (nuevo): gasto estimado por mes en el estado del canal (`state['spend'][YYYY-MM]`), `check` antes
  y `record` después de cada llamada, `Budget` por corrida con `monthly_cap_usd` (10), `max_images_per_run` (6),
  `image_cost_usd` (0.25, a verificar con la tarifa real) y `verify_cost_usd` (0.01) en `kit_preview.spend`. Al llegar a
  un tope no genera más, pasa a manual y avisa una vez por corrida; si el gasto no se puede leer o guardar, tampoco
  genera. `kit_state.get_spend` / `add_spend` y `CloudStore.spend_month` / `add_spend` (aditivos).
- Conexión: `kit_art.for_cover` (despacha por modo; `for_video` del modo auto no cambia), `kit_cover.frame_for_video`
  (cuadro 16:9 y miniatura de una portada ya terminada, sin `compose`), `kit_week.make_video(budget=)`,
  `run_kit_weekly` crea el `Budget` de la corrida y `run_kit_preview` usa el mismo camino. Con `template`, igual que con
  `auto`, un kit sin imágenes es elegible (`kit_art.generates`).
- Descripción por kit: `description` opcional (hasta 200 caracteres) en `kit_catalog` y `kit_settings`; `kit_names` la
  manda al LLM como contexto. Una entrada sin descripción queda igual que antes.
- Panel: modo "Plantilla + fondo", editor del prompt con botón para restaurar el de fábrica (igual al de fábrica no se
  guarda), tope mensual y máximo por corrida, columna "Descripción" y el gasto estimado del mes en "Ver último estado".
  `main.py` no se tocó.
- En corridas locales con `kit_store` no hay gasto guardado: solo cuenta el máximo por corrida.
- Pendiente del usuario: crédito prepago con recarga automática apagada, subir `modelo.png` y `fondos/` de cada género,
  ajustar `image_cost_usd` a la tarifa real y una corrida real de un solo video en modo `template`.
- Smokes: `scripts/smoke_kit_template_art.py` (nuevo, sin red) y los de `kit_art`, `kit_cover`, `kit_cover_wiring`,
  `kit_weekly` y `kit_panel` actualizados; el modo manual sigue igual.

## Loop kits — SEO de títulos y descripción, capítulos y cantidad de videos ✅ COMPLETADA
- `core/kit_seo.py` (nuevo, solo librería estándar): ficha por género en `kit_preview.seo.<genero>`
  (`{phrase, artists[], tags[], title_template, examples[]}`, hasta 40 artistas/etiquetas de 80 caracteres).
  `load` devuelve None sin ficha (el flujo sigue con la plantilla del canal) y `KitSeoError` si está mal formada.
- `build_title(seo, name, used_variants, rng, recent_titles)`: nombre real del kit, frase dentro de los primeros 40
  caracteres, máximo 100 (objetivo 90; recorta etiquetas, nunca el nombre ni la frase), sin `<>` ni espacios dobles,
  sin repetir los últimos 20 títulos del canal. Rota el artista principal y la mezcla de etiquetas sin repetir una
  variante del kit; determinístico con el rng. Si nada cumple las reglas devuelve `(None, None)` y se usa la plantilla
  del canal, con aviso.
- `chapters(segments)`: `0:00 Loop 1`… acumulando `end - start` (h:mm:ss si pasa la hora); con menos de 3 capítulos o
  alguno de menos de 10 s devuelve '' y un aviso. `hook(...)`: una llamada de texto (modelo de `kit_preview.names`),
  1-2 frases en inglés; se descarta con links o si nombra a un artista sin "inspired by" / "style of"; nunca corta el
  video.
- Cambios aditivos: `kit_publish` (`title`, `desc_vars` con `{hook}` / `{chapters}`, y `seo` para la corrida),
  `kit_state` (campo `seo` por corrida), `kit_spend` (`text_cost_usd`, 0.01, dentro del mismo tope mensual),
  `kit_names` (`one_word`). Sin esos argumentos todo queda igual.
- `kit_week.make_video`: con ficha usa `kit_seo`; `kit_names` solo corre con `names.vary_name` (default false) y
  entonces pide un nombre de una palabra. El gancho se pide después del render, para no pagar por un kit salteado.
- `run_kit_weekly`: la corrida arma `min(horarios configurados, 3)` videos (antes siempre 3).
- Panel y `kit_settings`: sección "SEO por género" (frase, artistas y etiquetas una por línea, plantilla y ejemplos) y
  casilla "Variar también el nombre". Además, tres filas con el mismo horario cuentan como un solo horario (era la
  única forma de cargar menos de 3 desde el panel). `main.py` no se tocó.
- Decisiones propias: `phrase` es una sola frase por género (para varias frases, un género por frase); la variante
  guardada incluye el título; las variantes usadas se miran en todo el historial del kit, no solo en el ciclo actual;
  `kit_week` siempre pasa `desc_vars`, así un `{hook}` sin ficha no queda escrito en la descripción.
- Pendiente del usuario: cargar la ficha de cada género en el panel, agregar `{hook}` y `{chapters}` a la descripción
  del canal, una corrida real con un solo horario y, a las 2-3 semanas, comparar vistas por variante.
- `scripts/run_kit_preview.py` (corrida local de un video) no usa la ficha: sigue con la plantilla del canal.
- **Chequeo de bugs y seguridad hecho** (`/code-review high` y revisión de seguridad): sin hallazgos de seguridad;
  los 8 de bugs quedaron aplicados. (1) Gancho y capítulos solo si la plantilla trae `{hook}` / `{chapters}`.
  (2) Un fallo al armar el SEO no descarta el video ya renderizado: sale con la plantilla del canal y avisa.
  (3) Sin frase no hay ficha: se guarda a medias y no se usa; una ficha huérfana y rota se descarta en vez de trabar
  el guardado. (4) La frase que no entra en 40 caracteres se rechaza al guardar; el panel avisa qué artistas no
  entran y `{artists}` se acorta para cumplir la regla. (5) El gancho se descarta con frases de autoría, cifras que
  no están en la descripción del kit o artistas sin la fórmula pegada al nombre. (6) `kit_names` pasa por el tope
  de gasto (también sin ficha: cada nombre generado suma `text_cost_usd`) y el tope que frena un texto se avisa.
  (7) Un loop de menos de 10 s comparte capítulo con el vecino y la suma se redondea. (8) `{link}`, `{hook}` y
  `{chapters}` se completan sin reinterpretar el nombre del kit ni tocar otros saltos de línea.
- Sin hacer: un contador propio de llamadas de texto en el gasto del mes (cambiaría el formato del estado que
  comparan los smokes de semana); el gasto de texto se suma al total en USD.
- Smoke: `scripts/smoke_kit_seo.py` (nuevo, sin red); `smoke_kit_panel.py` suma los casos del panel. Los demás smokes
  de kits pasan sin cambios.

## Loop kits — Tendencias semanales de SEO (vidIQ → Notion → worker) ✅ COMPLETADA (falta la prueba real)
- `core/kit_notion.py` (nuevo): lectura de solo lectura de una página de Notion (`KIT_NOTION_TOKEN`, `KIT_NOTION_PAGE_ID`),
  host fijo `api.notion.com`, sin seguir redirecciones, errores con un código fijo (sin URL, clave ni contenido).
- `core/kit_trends.py` (nuevo): valida el informe semanal (versión, fecha, largos, rangos, antigüedad), la IA elige solo entre
  opciones existentes (frase del informe que cabe en el título y no repite artista; etiquetas y artistas de la ficha) y el
  resultado se vuelve a validar con `kit_seo`. Sin informe, usa la última ficha buena de esa misma ficha del panel (huella
  y vencimiento por género) y, si no, la del panel. El panel nunca se modifica. Avisos por Telegram sin datos del informe.
- `scripts/run_kit_weekly.py`: aplica la ficha de la semana solo si hay un horario libre y kits para armar, y solo para los
  géneros de esos kits, dentro del bloque que libera el lock. Workflow, `kit_secrets_sync.py` y docs con los dos secretos.
- Tarea programada de Claude (domingo 20:00 UTC, antes del worker de las 23:00 UTC) con vidIQ y Notion; se crea desactivada
  y se activa tras una corrida manual de prueba. Smoke: `scripts/smoke_kit_trends.py` (nuevo, sin red).
- Revisión de bugs y seguridad: hallazgos corregidos (la ficha guardada no pisa cambios del panel, vencimiento por género,
  aviso sin IA, gasto acotado, enteros enormes, artistas cortos por palabra entera, bloques vacíos).

## Loop kits — Revisión de seguridad ⏳ INFORME ENTREGADO, FALTA LA PRIMERA CORRIDA REAL
- Revisión de solo lectura de todo lo agregado (workflow, worker, `core/kit_*`, panel).
- Sin secretos, links de venta ni nombre de canal en los archivos a commitear; acciones fijadas por SHA (verificadas
  contra sus tags); sin `pull_request`; `permissions: contents: read`; Beats y Marca personal sin cambios.
- Arreglado: (1) la config ya no decide a dónde va una clave ni de qué archivo sale: `kit_llm.check_base_url` exige https
  y un host permitido (`api.openai.com` más la variable `KIT_API_HOSTS`), y en la nube `key_file` no se lee;
  (2) `requirements-worker.txt` con versiones exactas y hashes (desde `requirements-worker.in`) e instalación con
  `--require-hashes`. Smoke: `scripts/smoke_kit_api_hosts.py`.
- También arreglado en el código: (5) en la nube el worker descarta `stderr` y registra como máscaras los valores
  sueltos de los secretos JSON; (6) `KIT_YT_CLIENT_SECRET_JSON` ya no se pide ni se escribe, y los secretos salen del
  entorno al arrancar para que ffmpeg no los herede. Smoke: `scripts/smoke_kit_hardening.py`.
- Preparado, falta tu parte (pasos en `docs/KIT_WEEKLY.md`): (3) app de Dropbox aparte tipo "App folder"
  (`scripts/kit_dropbox_auth.py`, `tokens/dropbox_worker.json`); (4) el job usa el Environment `kit-weekly` y solo corre
  en `master`, pero hay que restringir el Environment a `master` y mover ahí los secretos.
- Sigue abierto: el token de YouTube incluye `youtube.readonly` (está en `core/youtube.py`, módulo compartido).
- Falta para cerrar la fase: los pasos manuales de (3) y (4), dry-run en Actions revisando el log, una corrida real de
  un solo video y la primera semana completa.

## Setup del canal "ey mat" en la nube ✅ CÓDIGO COMPLETADO (2026-10-13), falta cargar GitHub y pilotar
- Reutiliza la app/token de Dropbox y el proyecto OAuth de Google de Loopkits (solo cambian los nombres `BEAT_*`).
- Límite por video de Dropbox 150 → 256 MiB (`MAX_VIDEO_BYTES` en `core/beat_assets.py`).
- Modo video + carpeta `dropbox_images` del género y miniatura `auto`: las imágenes rotan como miniaturas
  (misma rotación y anti-repetición que el modo imagen). Test nuevo en `tests/test_beat_montage.py`.
- Config del canal publicada en `/type-beats/config.json` y estado inicializado (instalación nueva); copia local
  en `tokens/beat_automation.local.json`. Dry-run real: 14 jobs planificados, 0 fallos.
- Beats usa el Environment `kit-weekly` (constante `ENVIRONMENT` en `core/beat_actions.py`): reutiliza `KIT_DROPBOX_*` y `KIT_TELEGRAM_*`; `scripts/beat_secrets_sync.py` solo sube `BEAT_CHANNEL_ID`, `BEAT_YT_TOKEN_JSON` y `BEAT_CHANNELS`. Un solo canal de Beats por Environment mientras se comparta; renombrar luego.
- Pendiente: push a master, correr el script, dry-run en Actions, piloto privado y `BEAT_LIVE_ENABLED=true`.

## Alta de otro canal de Beats y conexiones independientes ✅ CÓDIGO COMPLETADO (2026-10-14)
- Workflow exclusivo de Beats: Environment `type-beats-<slug>` y secretos BEAT_* por canal.
  Sustituye el setup compartido de Beats del 2026-10-13; antes de usarlo, migrar también
  el canal existente a su Environment propio. No se modifican secretos ni código de Loopkits.
- El verificador consulta el Environment del slug; el script de carga conserva los canales
  existentes y aborta si no puede leer la lista o falla la carga de credenciales.
- Nuevo modo visual alternate en módulos core/beat_* y en el panel de Beats: alternancia
  por slots entre semanas, formato congelado por job y soporte de imagen simple.
  Canales pausados permiten preparar carpetas de video pendientes sin activar publicaciones.
- mattwyyre agregado localmente, pausado: martes/jueves/sábados a las 10:00 Buenos Aires,
  perfil público compartido, filtro de 16 tags solicitado y variantes cercanas. Análisis real
  de 1.138 tracks: 132 elegibles. Simulación local de 6 slots futuros, sin reservar estado remoto.
- Validación: suite completa de 281 tests Beats, 279 aprobados y 2 omitidos; prueba adicional
  de la rama video/miniatura en alternate aprobada (4 tests de alternancia). git diff --check correcto.
- Guía: docs/TYPE_BEATS_CHANNELS.md. Configuración privada y reportes permanecen excluidos de Git.
- Pendiente operativo: imágenes/videos/miniatura Dropbox, ID real y OAuth de YouTube al final,
  preparar Environments (incluido canal actual), publicar configuración por CAS, dry-run y piloto.
  Sin push, escrituras remotas, uploads, habilitación de producción ni cambios en marca personal.

## Recursos de mattwyyre y soporte JFIF ✅ PREPARACIÓN LOCAL COMPLETADA (2026-10-14)
- Los links compartidos se resolvieron por files_list_folder(shared_link=...)
  con la conexión de Dropbox del escritorio; sharing_get_shared_link_metadata
  no estaba autorizado. No se cambió la autorización ni se modificó Dropbox.
- Rutas asignadas al canal local pausado: 28 imágenes para fondos/miniaturas
  y 4 videos, todos aceptados por extensión/tamaño. Configuración privada excluida de Git.
- Beats admite .jfif en su catálogo y selector. La decodificación mantiene
  validación de JPEG/PNG/WebP; no se modificaron módulos de Loopkits ni marca personal.
- Validación: prueba JFIF de catálogo → video → miniatura y las 22 pruebas de render aprobadas.
  No se descargaron ni decodificaron los medios reales en esta preparación;
  la comprobación remota fue de metadata. git diff --check correcto.
- Pendiente: OAuth/ID de YouTube de mattwyyre, conexión del worker a las mismas carpetas,
  preparación de Environments, configuración remota por CAS, dry-run y piloto antes de activar.

## Activación de mattwyyre: servicios existentes y secretos por slug ✅ CÓDIGO COMPLETADO (2026-10-14)
- Sustituye la propuesta de Environments por canal: Beats conserva kit-weekly y reutiliza
  KIT_DROPBOX_* / KIT_TELEGRAM_* sin modificar esos secretos ni el funcionamiento de Loopkits.
- Cada slug selecciona BEAT_CHANNEL_ID_<SLUG> y BEAT_YT_TOKEN_JSON_<SLUG> independientes.
  El worker mantiene la comprobación del ID real de YouTube y el bind del slug remoto.
- workflow_dispatch admite channel para limitar dry-run/piloto al canal nuevo. El cron
  sigue procesando todos los slugs; no se ejecuta un piloto extra en el canal actual.
- OAuth de mattwyyre verificado contra el handle y su ID; configuración publicada pausada
  por CAS en Dropbox, conservando ey mat activo, sus campos y todo el historial existente.
- Las 28 imágenes reales descargadas temporalmente fueron decodificadas y generaron
  frames/miniaturas de prueba correctamente. No se modificaron los originales remotos.
- Validación: 284 tests Beats, 282 aprobados y 2 omitidos, incluidas 6 pruebas de aislamiento
  y filtro de canal. Sin cambios en main.py, workflows/módulos de Loopkits o marca personal.
- Pendiente: autorización explícita para transferir tokens locales a los secretos de GitHub,
  publicar workflow, incorporar slug, dry-run, piloto privado y activación del canal.
  La revisión automática rechazó la primera transferencia por requerir aprobación del payload
  y destino; se solicitó confirmación. No se transfirieron tokens ni se publicaron videos.

## Plantillas guardadas del canal para la automatización de Beats ✅ CÓDIGO COMPLETADO (2026-10-14)
- core/beat_templates.py vincula los modelos de Gestionar canales al perfil SEO del worker
  mediante use_channel_templates=true, solo para mattwyyre. Se aplica al leer, validar y guardar.
  Conserva la descripción completa y adapta {beatstars_url} a {url}; el nombre se rellena por beat.
- Plantilla de título y descripción reales publicadas en la configuración remota con el canal
  pausado durante la corrección. La aplicación seguirá compilando los cambios guardados en el
  modelo al abrir/guardar el panel; la publicación remota continúa siendo explícita.
- core/beat_metadata.py renueva únicamente snapshots pendientes sin intentos; archiva el
  snapshot anterior y conserva IDs, cuotas, intentos, archivos visuales y subidas existentes.
  Rechaza cambios durante un render. Se archivó una ficha pendiente después de terminar el lote.
- Verificación: 290 tests Beats, 288 aprobados y 2 omitidos, incluidas 4 pruebas de plantillas
  y 2 de renovación sin alterar el ledger. Sin modificaciones en Loopkits ni marca personal.
- Estado operativo previo a esta corrección: piloto privado Emboscada exitoso y DECISIÓN
  subido/programado para 2026-10-17 10:00 Buenos Aires; otros cuatro jobs siguen pendientes.
- Pendiente externo: editar la metadata de esos dos videos ya subidos. El token actual solo
  tiene upload/readonly y videos.update devolvió 403 por scopes insuficientes, sin cambios.
  Computer Use no pudo verificar la URL del navegador y detuvo la sesión; no se editaron
  mediante UI. Las próximas subidas usarán el modelo corregido al reanudar.

## Automation Hub — Fase 1: shell UI Beats (pestañas) ✅ COMPLETADA (2026-10-15)
- Panel de Beats reorganizado en `QTabWidget`: Conexiones (placeholder), Canal, SEO y tendencias, Avanzado.
- Tags de selección y SEO movidos a su pestaña; guardado local, Dropbox, simulación, output y jobs en Avanzado.
- Sin cambios de handlers ni de Loop kits/`main.py`. Docs en `docs/TYPE_BEATS_PANEL.md` y smoke en `tests/test_beat_panel.py`.
## Automation Hub — Fase 2: módulo de conexiones + pestaña Conexiones ✅ COMPLETADA (2026-10-15)
- `core/automation_status.py` (sin Qt) y `core/beat_connections_form.py`: semáforos, Conectar YouTube, Guardar Notion (`tokens/beat_secrets.json`), sync por `QProcess` y checklist.
- `scripts/beat_secrets_sync.py` incluye `BEAT_NOTION_*`. Tests: `tests/test_automation_status.py`; smoke: `scripts/smoke_automation_status.py`.
- TODO manual: `gh auth login`. Sin commit; pendiente Bugbot y security-review.

## Automation Hub — Fase 3: shell + Conexiones Loop kits ✅ COMPLETADA (2026-10-15)
- `loop_kit_panel.py` con las mismas 4 pestañas (Portada en Canal; topes/IA, Dropbox y dry-run en Avanzado).
- `core/kit_connections_form.py` y extensiones de `automation_status`: Telegram (estado y prueba), wizard Dropbox, YouTube, Notion/LLM/Image en `tokens/kit_secrets.json`, sync `QProcess` a `kit_secrets_sync.py --no-prompt`.
- Smoke `scripts/smoke_kit_panel.py`; docs en `docs/KIT_WEEKLY.md`. Sin commit; pendiente Bugbot.
## Automation Hub — Fase 4: puente informe Claude Code (SEO) ✅ COMPLETADA (2026-10-15)
- `core/seo_report_status.py` (sin Qt, reusa `beat_seo_report`/`kit_trends`) y `core/seo_report_box.py`, cableado en la pestaña SEO de Beats y Loop kits: edad, origen, errores por código, import local a `tokens/seo_reports/`, copiar schema y sugerencias de solo lectura.
- Docs en `docs/CLAUDE_SEO_REPORT.md`; smoke `scripts/smoke_seo_report_status.py`. Sin commit; pendiente Bugbot.
## Automation Hub — Fase 5: guardado unificado + checklist piloto ✅ COMPLETADA (2026-10-15)
- `core/automation_save_bar.py`: barra inferior con **Guardar y publicar**, checklist `readiness_*` e indicador de piloto (conexiones + informe SEO válido).
- Beats: el CTA guarda local y publica `/type-beats/config.json` por CAS (recarga remota si hace falta); Avanzado conserva acciones sueltas. Loop kits: el mismo CTA publica solo en Dropbox (kits + config del worker).
- Tests: `test_beat_panel_cloud.py` (cadena y conflicto CAS); smokes `smoke_kit_panel.py` y `test_beat_panel.py`. Sin commit; pendiente Bugbot.

## Automation Hub — Fase 6: asistente de alta de canal + chips ✅ COMPLETADA (2026-10-15)
- `core/channel_wizard.py`: lógica sin Qt (5 pasos, gate de activación, chips) y diálogo no modal que reusa `automation_status`, OAuth de YouTube, sync por `QProcess` y guardar y publicar de la Fase 5. Flags de sesión (secretos, config en Dropbox, dry-run) marcados por los handlers existentes.
- **Activar** solo con el checklist final en verde (config en Dropbox, secretos GH, dry-run; en Beats el dry-run de Actions se confirma a mano). Chips en la lista de Beats y en el selector de Loop kits (color + tooltip; el texto del combo no cambia).
- Smoke: `scripts/smoke_channel_wizard.py`. TODO manual: `gh auth login` y sumar el slug a `KIT_CHANNELS` en kits. Sin commit; pendiente Bugbot.

## Automation Hub — Fase 7: copy + miniaturas (solo lectura) ✅ COMPLETADA (2026-10-16)
- CTAs unificados: barra inferior **Publicar al robot**; pruebas **Probar sin subir** (simulación Beats y dry-run kits). Avanzado conserva acciones sueltas (local, Dropbox, recargar).
- Labels alineados con `main.py`: **Automatizaciones de Beats**, diálogo kits **Configuración de automatización**, recarga **Recargar desde Dropbox**.
- `SeoReportBox`: bloque **Recomendaciones de miniaturas** vía `seo_report_status.thumbnail_recommendations` (`thumbnail_suggestions` / `suggestions` del informe local o nota fija); sin autoaplicar ni cambios de render.
- Asserts de labels en `tests/test_beat_panel.py` y `scripts/smoke_kit_panel.py`. Sin commit.

## Solo Dropbox — registro de canales y merge de 3 vías ✅ CÓDIGO COMPLETADO (2026-10-18), migración pendiente de autorización
- `core/channel_kind.py` (tipo beats|loops, `spec()` con documento/Environment/secretos/lista/workflow,
  `validate_registry`), `core/cloud_registry.py` (`/automatizacion/canales.json` y `ajustes.json`, CAS)
  y `core/cloud_merge.py` (merge por campo; listas por id/slug/clave/folder).
- Beats lee y publica solo Dropbox (config + registro); plantillas en la pestaña SEO; `ChannelManager`
  eliminado. Loop kits toma los canales del registro y guarda kits/config con merge.
  `sections.py` ya no asume Beats: sin `section` es error.
- `scripts/migrate_to_cloud.py` listo (dry-run por defecto); **no se ejecutó `--apply`**.
- Smokes: `smoke_channel_kind`, `smoke_cloud_merge`, `smoke_cloud_migration` (diff vacío del config de Beats).

## Solo nube — credenciales en el llavero y GitHub Secrets ✅ CÓDIGO COMPLETADO (2026-10-18), falta la prueba manual con `tokens/` renombrado
- `core/cloud_login.py` (Dropbox PKCE → llavero `video-type-beat-generator`, `client_secret` de Google en el llavero,
  `gh auth status`), `core/gh_status.py` (`gh secret list --json name,updatedAt` / `gh variable get`, caché 60 s,
  escritura solo por stdin), `core/cloud_login_box.py` («Esta PC» en las dos pestañas Conexiones).
- `local_transport` y `kit_cloud.client()` (escritorio) leen del llavero; nunca `tokens/`. YouTube: OAuth en memoria
  (`youtube.authorize`) y subida directa al secreto del slug. Telegram/Notion/claves van directo a Secrets
  (compartidos a `kit-weekly` y cada `kit-weekly-<slug>`); la UI muestra «cargado ✓ (fecha)».
- Sync scripts con `push_channel` en memoria; la CLI se conserva. `keyring` en `requirements.txt`.
- Archivos obsoletos de `tokens/` y `config/`: ver `docs/CLOUD_CREDENTIALS.md`. Smoke: `smoke_cloud_credentials`.

## Modo Manual local (pestaña «Manual») ✅ COMPLETADO (2026-10-22)
- Vuelve el flujo local que se había borrado con el paso a solo nube: arrastrar beats (archivos o carpetas)
  y generar los videos en esta PC, sin subir nada. Beats y Loop kits (nube) no cambian.
- `core/manual_render.py` (sin Qt): canales de `config/app_config.json` + carpetas `images/`, `videos/`,
  `miniaturas/<canal>/<grupo>`; fondo Imagen o Video stock (en loop), sin repetir dentro de la tanda.
  Deja `<título>.mp4`, `.jpg` (1280x720, título opcional encima) y `.txt` (título, descripción con BPM y tono
  sacados del nombre, tags) en `Escritorio/Type Beat Videos/<canal>/`. Cancelar corta FFmpeg y no deja `.part`.
- `core/manual_panel.py`: pestaña con arrastrar/soltar, canal/grupo, plantilla de título por canal y carpeta
  de salida; preferencias en `config/manual_mode.json` (ignorado por git).
- Velocidad: foto fija a 6 fps y video stock con preset `veryfast` (beat de 3:24: imagen 23 s, video ~100 s).
- Tests: `tests/test_manual_render.py` (incluye render real corto con FFmpeg).

## Modo local en bulk con perfiles por canal (plan aprobado 2026-10-22)
Objetivo: soltar beats en `entrada/<canal>/`, revisar títulos, «Generar todo» y recibir en el Escritorio
carpetas listas para subir a mano (sin API de YouTube). Perfiles y fondos en `<Dropbox>/TypeBeat Local/`
(carpeta sincronizada, leída como disco; separada de la automatización en la nube).
- **Fase A — Perfiles por canal** ✅ COMPLETADA (2026-10-22): `core/channel_profile.py` (perfil.json: fondo,
  título ≤100, descripción, redes, hashtags, tags ≤500, título en miniatura; fondos/ y miniaturas/; aviso de
  copias en conflicto y de archivos «solo en línea»), `core/dropbox_local.py` (info.json → ~/Dropbox),
  `core/profile_editor.py` (editor con «Duplicar como…»), `core/local_migration.py` +
  `scripts/migrate_local_channels.py` (21 canales; cada grupo ≠ Principal = canal propio; copia sin borrar).
  Pestaña Manual: carpeta de canales, Editar perfil, Nuevo canal, Importar canales anteriores.
  Pendiente del usuario: importar a su Dropbox real (botón o `--apply`). Tests: `tests/test_channel_profile.py`.
- **Fase B — Títulos limpios** ✅ COMPLETADA (2026-10-22): `core/beat_title.py` separa {name} {artist} {bpm} {key} {mood} del nombre del archivo (formato BeatStars y nombres simples); bloques opcionales `[[…]]` y atajos `{bpm} BPM` / `{artist} Type Beat` que desaparecen si falta el dato; limpieza de separadores. Campo `artistas` en el perfil (escritura correcta del artista). Tabla de revisión en la pestaña Manual (título editable por beat, solo para esa tanda; «Restablecer títulos»). Tests: `tests/test_beat_title.py`.
- **Fase C — Bulk** ✅ COMPLETADA (2026-10-22): `core/bulk_queue.py` (entrada/<canal>/ → cola; saltea archivos copiándose o «solo en línea»; hecho → `hechos/`, error → `errores.txt`; un canal con problemas no frena a los demás). Salida para subir a mano: `<salida>/<fecha>/<canal>/<título>/` con `<título>.mp4`, `<título> - miniatura.jpg` y `<título>.txt` (bloques TÍTULO/DESCRIPCIÓN/TAGS; el nombre del archivo es el título porque YouTube Studio lo usa como título inicial) + `<fecha>/pendientes.csv`. Pestaña Manual con subpestañas «Arrastrar» y «Tandas por canal» (`core/manual_tab.py`, `core/bulk_panel.py`: tabla canal/beat/título editable, «Generar todo»). Tests: `tests/test_bulk_queue.py`.
- **Fase D — Velocidad del video stock** ✅ COMPLETADA (2026-10-22): `core/stock_cache.py` convierte cada video stock una vez a 1080p30 (sin B-frames, keyframe cada 2 s) en `%LOCALAPPDATA%/TypeBeat/cache` (no en Dropbox; clave ruta+tamaño+fecha; tope `cache_max_gb` en `config/manual_mode.json`, 5 GB por defecto, borra lo menos usado). Cada beat repite la caché y copia el video sin recodificar; si la caché falla, vuelve al método anterior. Medido en la PC sin NVENC (libx264), 3 beats con stock 1440p: 153 s → 61 s la primera vez → 17 s con la caché armada (≈6 s por beat de 3:24 vs 58 s). Video vs audio: < 1 cuadro de diferencia, sin saltos en el loop. Falta medir en la PC con NVIDIA. Tests: `tests/test_stock_cache.py`.
- Fuera de alcance: subir a YouTube desde lo local, render en paralelo, Shorts, cambios en la nube.

## Fase E — UI simple: Inicio, modo local en 3 pasos y guía ✅ COMPLETADA (2026-10-22)
- `core/home_screen.py`: Inicio con una sola decisión — «Crear videos ahora» (local) o «Automatizar en la nube»
  (Beats y Loop kits quedan detrás, en `core/cloud_page.py`). Armadura en `core/app_shell.py` (← Inicio, ? Guía).
- `core/local_view.py`: canal → beats → generar en una pantalla; junta arrastrar/soltar y las carpetas de entrada
  (los beats de `entrada/<canal>/` aparecen solos con 📥; aviso + «Generar todos esos canales» para el resto).
  Lo poco usado (carpetas, importar, nuevo canal, caché) pasa a ⚙ Configuración (`core/local_settings.py`).
- `core/profile_editor.py`: estilos de título listos (o «Personalizado…»), artistas y miniatura a la vista;
  descripción/redes/hashtags/tags en «Más opciones».
- `core/guide_panel.py`: guía checklist por pantalla; los pasos se tildan solos y tienen «Llevarme ahí».
  Se abre sola la primera vez (`guide_seen` en `config/manual_mode.json`).
- Se quitaron `core/manual_tab.py` y `core/bulk_panel.py`; `core/manual_panel.py` queda con piezas compartidas.
  Tests: `tests/test_local_view.py`, `tests/test_main_shell.py`.

## Fase G — Asistente «Guiame paso a paso» (local) ✅ COMPLETADA (2026-10-22)
- Se hizo antes que la F porque arma la base reusable: `core/wizard.py` (una pantalla por paso, «Atrás» /
  «Siguiente», «Paso X de N»; «Siguiente» se habilita solo y abajo dice qué falta).
- `core/assistant.py`: «¿Qué querés lograr?» → caminos: videos para un canal (canal con vista previa de fondos →
  beats → títulos → generar → listo + cómo subir a YouTube), videos para varios canales (carpetas de entrada →
  títulos → generar → resumen) y crear un canal nuevo (nombre → copiar estilo → imagen/video → estilo de título →
  fondos, se tilda solo → «Hacer videos para este canal»). «Automatizar en la nube» lleva a la sección nube.
- Botón «🧭 Guiame paso a paso» en Inicio y en «Crear videos ahora». Reusa `LocalWorker`, perfiles y cola.
  Tests: `tests/test_assistant.py`.

## Fase F — Nube en modo asistente ✅ COMPLETADA (2026-10-22)
- `core/cloud_assistant.py`: camino «Automatizar un canal en la nube» del asistente (`core/wizard.py`): Beats o
  Loop kits → conectar esta PC (el mismo `CloudLoginBox`, adentro del asistente) → elegir el canal → credenciales
  del robot (YouTube, Dropbox worker, Telegram en kits) → «Publicar al robot». Cada paso con luces del checklist
  real (`readiness_beats` / `readiness_kits`, mismos requisitos que `automation_save_bar`); los botones llevan a la
  pestaña exacta con un aviso «← Volver al asistente» que retoma donde estaba.
- `core/cloud_page.py`: «Mostrar opciones avanzadas» (oculta «SEO y tendencias» y «Avanzado»; `cloud_advanced` en
  `config/manual_mode.json`), estado real (`readiness()`) y guía que se tilda sola.
- Conexiones de Beats con scroll (antes se aplastaba). Sin cambios en cómo trabaja el robot.
  Tests: `tests/test_cloud_page.py`.
- Pendiente del usuario para usar la nube: conectar Dropbox y GitHub (`gh auth login`) en esta PC y correr la
  migración `scripts/migrate_to_cloud.py --apply` (falta `/automatizacion/canales.json`).

## Fase H — Conexiones guiadas ✅ COMPLETADA (2026-10-22)
- `core/connections_view.py`: pantalla «🔌 Conexiones» (botón propio en Inicio) con tarjetas y luces: necesarias
  para la nube (Dropbox esta PC, GitHub, Google/YouTube, Dropbox del robot, Preparar la nube) y opcionales
  (Telegram —obligatorio solo para Loop kits—, Notion, IA). Para crear videos en esta PC no hace falta ninguna.
- `core/connection_steps.py`: un mini asistente por conexión (`core/wizard.py`) con links y explicación:
  Dropbox (App key → autorizar → código → llavero), GitHub (instalar GitHub CLI con winget previa confirmación,
  o link; abrir `gh auth login` en una consola; se tilda solo), Google (pasos de Google Cloud + importar el JSON;
  ofrece el `config/client_secret.json` viejo si existe), Dropbox del robot (código nuevo → GitHub Secrets),
  Telegram (con «Probar»), Notion, IA, y «Preparar la nube» (vista previa de `migrate_to_cloud.build` → aplicar).
  Guarda con lo existente (`cloud_login`, `automation_status`); los valores nunca van como argumento ni a disco.
- Tests: `tests/test_connections.py`.

## Fase I — Mis canales automatizados ✅ COMPLETADA (2026-10-22)
- `core/my_channels.py`: pantalla simple con una tarjeta por canal (botón azul de Inicio). Beats: interruptor
  Activa/Pausada, horario en palabras («Lun, Jue · 18:00») con «Cambiar horario» (días + hora), salud en frase
  («Faltan 4 de 5 pasos para publicar» / «✔ Listo») con «Arreglar» (abre el asistente de alta del canal), «Quitar»,
  «+ Agregar canal» y un solo «Guardar cambios» que usa el guardado del panel (`save_and_publish`: CAS + merge).
  Loop kits: salud y «Editar horario y estilo» (abre su pestaña en esa automatización; el robot de kits no tiene
  «pausa», así que no se muestra un interruptor que no haría nada). Sin Dropbox o sin «Preparar la nube», explica y
  lleva a Conexiones. Las pestañas técnicas quedan en «Modo avanzado».
- La ventana se mudó a `core/main_window.py` (`main.py` queda como punto de entrada, más chico).
- Tests: `tests/test_my_channels.py`.

## Mis canales — Loop kits editables y «Editar todo» ✅ (2026-10-23)
- `core/kit_manage.py`: activo/pausado y día de cada kit en la variable `KIT_CHANNELS` (lo que de verdad decide qué
  publica el robot); «Quitar» lo saca de esa lista y del índice `channels.json` (kits, config y secretos quedan:
  se puede recrear). El canal por defecto se puede pausar, no quitar.
- `core/kit_channel.parse_schedule`: `-` = ningún canal (antes no había forma de pausar todo).
- `core/my_channels.py`: tarjetas de kits con Activa/Pausada, día, Quitar (con Deshacer) y «Editar todo»; Beats con
  «Editar todo» (pestaña completa con el canal elegido). Todo se aplica con el mismo «Guardar cambios».
  Tests: `tests/test_kit_manage.py`.

## Fase J1 — Editor de estilo de video y miniatura (local) ✅ COMPLETADA (2026-10-23)
- `core/style.py`: estilo por canal en `perfil.json` → `estilo` (sin estilo, sale como antes). Video: encuadre
  (llenar / centrado con fondo difuminado), oscurecer, tinte, grano, título sobre el video (arriba/centro/abajo),
  logo (`canales/<canal>/logo.png`), zoom lento (imagen fija) y fundido. Miniatura: plantilla (solo imagen / franja /
  título grande / logo), fuente (Oswald y Courier Prime incluidas; Arial e Impact de Windows), color, tamaño,
  contorno y origen (fondo / carpeta miniaturas / cuadro del video). 5 estilos listos: Limpio, Franja oscura,
  Título grande, Neón, Cine.
- `core/manual_render.py` usa el estilo; video stock sin nada encima sigue con copia rápida; con capa (título,
  oscurecer, logo, fundido) se procesa (~14 s por minuto de beat). Caché de stock separa el encuadre difuminado.
- `core/style_editor.py`: editor con vista previa en vivo y «Probar con un beat (10 s)»; se abre desde el perfil del
  canal («🎨 Estilo de video y miniatura…»).
- Medido (60 s de beat, PC sin NVENC): imagen 3,5 s; + grano/tinte 4,4 s; + zoom 6,2 s; video stock 1,8 s;
  + título/oscurecer 14,5 s; difuminado: la primera vez arma su caché (~86 s con un stock 1440p de 3 min).
- Encuadre «Centrado con barras» ✅ (2026-10-24): foto recortada al alto completo entre dos barras de igual ancho
  (`barras` 8–32 % por lado, `barras_color`), igual en video y miniatura; oscurecer/tinte no tocan las barras; el
  zoom las vuelve a tapar; la caché de stock usa la clave `barras:<%>:<hex>`.
- Tests: `tests/test_style.py`. Siguen: J2 (mismo estilo en el robot de Beats) y J3 (portadas de Loop kits).

## Dropbox ordenado — todo en una carpeta ✅ COMPLETADA (2026-10-23)
- Todo lo de la app (datos que usa el robot + contenido del usuario) vive en `/Soft Projects/Type Beat Generator/`
  (`datos/`, `contenido/`, `_archivo/`). Rutas en `core/dropbox_layout.py`; detalle en `docs/DROPBOX_LAYOUT.md`.
- Se movieron `/automatizacion`, `/type-beats`, `/loop_kits/_automation`, `/loop_kits_state`, `/loop_kits/_referencias`,
  los fondos y miniaturas de «ey mat» y la copia vieja del código (a `_archivo/`).
- Rutas viejas guardadas dentro de los JSON se traducen al leer; quedan con la ruta nueva al volver a guardarse.
- Modo local: usa `<Dropbox>/Soft Projects/Type Beat Generator/contenido` si la PC lo sincroniza; si no, `TypeBeat Local`.
- Tests: `tests/test_dropbox_layout.py`.

## Distribución semanal — asistente de Beats ✅ COMPLETADA (2026-10-23)
- Guía de dos pasos desde Mis canales y el panel avanzado: proteger horarios
  existentes, elegir 1–7 videos semanales, recomendar según cantidad de canales,
  prioridad y capacidad, y revisar la carga de lunes a domingo antes de aplicar.
- Lógica pura en `core/beat_distribution.py`, UI en `core/beat_distribution_dialog.py`;
  equilibrio de carga y separación de días, calendario fijo/pausado intacto,
  rechazo de propuestas imposibles y de aplicación sobre un borrador cambiado.
- Aplicación solo al borrador, luego guardado CAS existente de Dropbox. Sin
  cambios en `main.py`, uploader, workflows ni producción. No reprograma jobs
  anteriores ni videos ya subidos. Reservas externas y tope son por propuesta,
  no coordinación automática entre workers ni nuevos límites persistidos.
- Verificación oficial de cuota: 100 llamadas diarias predeterminadas a insert
  por proyecto según Google; cuota efectiva pendiente de comprobar en Cloud.
  Se conserva el presupuesto local de seis intentos y se aclara su origen en UI.
  Guía incluye límites de contenido repetitivo/spam, sin promesas contra bloqueos.
- Nueve pruebas nuevas con 400 combinaciones contrastadas con un criterio de
  factibilidad independiente, cancelación, borrador obsoleto y round-trip CAS
  sobre Dropbox falso. UI renderizada y revisada con 15 canales; sintaxis y
  whitespace correctos. Regresión offline: 94 aprobadas (79 de planificación/UI
  y 15 del adaptador Dropbox), con GitHub/llavero aislados mediante dobles.
  Detalles y fuentes: `docs/TYPE_BEATS_DISTRIBUTION.md`.

## Revisión general de bugs y seguridad ✅ COMPLETADA (2026-10-23)
- Transporte HTTPS común para IA/Telegram de Loop kits: sin redirecciones/proxies,
  respuestas acotadas y descarga de imágenes por hosts permitidos, sin reenviar claves.
- Upload compartido conserva el ID si falla la miniatura; tandas locales sobreviven
  a fallos de archivo/CSV/log, protegen celdas CSV y manejan nombres reservados Windows.
- Validación finita de caché y gasto de IA; saldo corrupto bloquea nuevas llamadas;
  ffprobe con timeout. `tzdata` declarado para el escritorio y pruebas Qt excluidas
  de la suite del worker, verificada con PyQt prohibido.
- Recorrido de Inicio, local, Mis canales, Conexiones y asistente: corregidos textos
  cortados con guía abierta, tarjetas y scroll, también a 900 × 620.
- 19 regresiones nuevas, suite completa offline de 468 pruebas (466 aprobadas y
  dos checks optativos verificados por separado), 257 pruebas del worker con dos
  checks FFmpeg reales y 31 smokes compartidos/Loop kits aprobados. Sin servicios
  reales ni cambios de configuración/secretos remotos. `main.py` sin cambios.
- Hallazgos, verificación y límites: `docs/APP_REVIEW_2026_10_23.md`.
  Commit y push solicitados por el usuario para el cierre de esta fase.

## BeatStars en el modo manual local (2026-10-24)

Objetivo: sumar beats propios por tags y cantidad a la creación manual, con
historial global de esta instalación y enlace por video. Preview público;
historial desde esta función, sin reconstruir descargas previas ni tocar los
estados de automatización. Una fase por sesión. Migración SQL: no.

### Fase 1 — Motor, historial y archivos asociados ✅ COMPLETADA

- `core/manual_beatstars.py`: servicio sin Qt con búsqueda por tags exactos
  (cualquiera/todos), selección de 1–100 IDs, exclusión por miembro/track y
  repetición explícita; errores parciales y cancelación conservan éxitos previos.
- `core/manual_beatstars_store.py`: JSON local versionado y atómico, bloqueo del
  SO entre procesos y journal de publicación. Recupera paquetes completos sin
  volver a descargarlos; revierte incompletos; conflictos/corrupción frenan la
  operación sin reinicializar el historial ni borrar archivos modificados.
- `core/manual_beatstars_media.py`: validación y M4A/AAC local; AAC compatible se
  copia, otros codecs se convierten. FFmpeg solo recibe archivos locales y puede
  cancelarse. Cada audio tiene `.beatstars.json` y `.beatstars.txt`, con ID estable
  y URL pública; sin URLs HLS temporales. Publicación sin reemplazar archivos.
- Hooks opcionales de cancelación en catálogo, resolver y HTTP/HLS, manteniendo
  sus contratos predeterminados. Sin fallback a Dropbox, login ni dependencias
  nuevas. `main.py`, UI y render manual sin cambios funcionales en esta fase.
- 27 pruebas nuevas offline aprobadas, incluidas dos verificaciones reales con
  audio sintético y FFmpeg: HLS/AAC → M4A sin recodificar y WAV → M4A/AAC.
- Regresión conjunta: 378 pruebas ejecutadas, 376 aprobadas y dos omitidas,
  sin fallos (BeatStars, motor nuevo, render manual, bulk y vista local).
  GitHub/llavero aislados por prueba; TEMP/TMP dentro del workspace por permisos
  del sandbox. Sin pytest instalado: runner unittest con dobles de credenciales.
- Revisión local del diff: corregido fsync de archivos en Windows, fallos al
  revertir paquetes detienen la tanda, colisiones no reemplazan archivos ajenos,
  historial con versión inválida o demasiado grande falla explícitamente.
  Bugbot local no disponible; revisión propia, sin afirmar revisión independiente.
- Uso, API, recuperación y límites: `docs/MANUAL_BEATSTARS.md`. Prueba contra
  BeatStars real pendiente de autorización; no se descargaron beats reales.

### Fase 2 — Diálogo y conexión con la pantalla manual ✅ COMPLETADA (2026-10-24)

- Botón «Descargar desde BeatStars…» junto a las entradas actuales. Perfil y
  filtros recordados, cantidad 1–100 (10 inicial), cualquiera/todos, tabla con
  título/tags/enlace/estado y opción de incluir descargados.
- Worker Qt con progreso, cancelación y cierre seguro; capturar canal/destino,
  impedir cambios incompatibles y sumar únicamente paquetes completos a la
  entrada/tabla. No iniciar generación automáticamente. Pruebas Qt offscreen.
- `core/manual_beatstars_dialog.py` y `core/manual_beatstars_task.py`: selección
  hasta la cantidad pedida, resultados inválidos al cambiar filtros, progreso y
  errores traducidos. Perfil/filtros en `manual_mode.json`; perfil local inicial
  leído sin modificar automatizaciones. Apertura de enlaces solo por doble clic.
- Canal/destino congelados; controles incompatibles bloqueados. Cancelar conserva
  éxitos; Escape/cerrar difiere el cierre hasta que termine el hilo. `LocalView`
  y `core/main_window.py` coordinan también el cierre de la app sin destruir un
  worker activo. No se agrandó `main.py` ni se modificó el motor de la fase 1.
- Scroll vertical local y acciones en dos filas para conservar 900 × 620 con la
  guía abierta; capturas inspeccionadas, sin scroll horizontal. Formulario del
  diálogo legible también con resúmenes de error y en tamaño 650 × 500.
- 24 pruebas nuevas: Qt offscreen, selección/filtros, errores/cancelación/cierre,
  preferencias y canal capturado, más UI → motor real con HTTP y medios falsos,
  incorporación a la tabla y exclusión al reabrir. Regresión seleccionada: 114
  pruebas aprobadas, sin omisiones ni fallos (motor, UI, render manual, bulk,
  shell, layout, revisión general y asistente). GitHub/llavero aislados por prueba.
- Revisión propia: cierre diferido y sin reentrada al cerrar un diálogo inactivo,
  resultados tardíos descartados al cancelar búsquedas, errores sin detalles de
  excepciones internas, controles sin recortes al mostrar errores. Bugbot local
  no disponible; no se afirma revisión independiente.
- Migración SQL: no. Sin red real, credenciales ni publicación. La fase 3 sigue
  pendiente para el TXT final de videos y movimiento conjunto de sidecars.

### Fase 3 — Enlaces por video y movimiento de tandas ✅ COMPLETADA (2026-10-24)

- Leer metadata del audio para preservar título original y URL aunque se edite
  el título del video; habilitar `{beatstars_url}` y bloque BEATSTARS en TXT final.
- Mover sidecars junto al audio a `hechos`, conservando asociaciones ante
  colisiones. Audios sin metadata mantienen su comportamiento actual.
- Render sintético corto y validación integral de reinicio, repetición y enlaces;
  prueba live opcional autorizada. Actualizar documentación y cerrar con commit.
- `core/manual_beatstars_files.py`: lectura acotada y esquema/URL validados;
  tamaño/SHA-256 verificados por el worker de render. Metadata dañada o ajena
  produce error por beat, sin contaminar los demás. Vista previa sin hashing en Qt.
- Helpers manuales con metadata opcional: título original para nombre, artista,
  BPM, tono y tags del perfil, sin prefijos TK ni sufijos de archivo. Título editado
  conserva identidad y URL. `{beatstars_url}` rellena la descripción y un bloque
  BEATSTARS queda siempre en el TXT si hay enlace, sin editar perfiles existentes.
- Audio y archivos asociados se archivan con el mismo basename; colisiones de
  cualquiera de los tres componentes reservan un sufijo para todo el paquete.
  Movimientos sin sobrescritura, reversión ante errores y copia temporal segura
  si el destino está en otra unidad. Sin metadata, formato y flujo anteriores.
- Recuperación de historial pendiente también reconoce paquetes completos en
  `hechos`, incluyendo colisiones, sin volver a descargarlos. Archivos repartidos
  o modificados detienen la recuperación antes de borrar el audio original.
- 24 pruebas nuevas; prueba integral Qt con motor y FFmpeg reales, audio sintético
  y HTTP falso: descarga → título editado → MP4/miniatura/TXT con URL → archivado
  con colisión → reutilización → exclusión al reabrir desde otro canal.
  Perfil original intacto; CSV de pendientes, duración y miniatura comprobados.
- Regresión seleccionada: 178 pruebas aprobadas, sin fallos ni omisiones, incluyendo
  las fases anteriores, render/bulk/local, shell/layout/asistente, perfiles,
  estilos, caché y títulos. GitHub/llavero falsos por prueba y temporales aislados.
- Revisión propia del diff y escenarios de fallo; Bugbot local no disponible,
  sin revisión independiente. Migración SQL: no. `main.py` sin cambios. Las tres
  fases de código quedan completas; compatibilidad live de BeatStars pendiente
  de una prueba opcional autorizada, sin audios reales ni publicaciones en esta sesión.

### Revisión de bugs y descarga real ✅ COMPLETADA (2026-10-24)

- Prueba live autorizada por el usuario: catálogo `matwyre` de 1.139 beats y
  descarga pública real de `TK18425328` (New York). M4A/AAC de 161,724082 s y
  4.203.887 bytes, duración, SHA-256 y decodificación completa verificados.
- Reinicio del diálogo/servicio con otro canal e historial compartido de prueba:
  tag `BAD BUNNY` ofrece 58 candidatos; al incluir descargados, 59. El beat
  descargado solo reaparece con la opción explícita y una selección anterior se
  omite antes de volver a pedir el audio.
- Render manual del preview completo: MP4 H.264/AAC 1920 × 1080, miniatura
  1280 × 720 y TXT con enlace correcto pese al título editado. Movimiento a
  `hechos` y metadata/enlace/tamaño/hash comprobados. Historial, canal y artefactos
  de prueba aislados; no se alteró la configuración ni el historial habitual.
- Corregidos dos bugs reproducidos: limpieza de temporales que ocultaba un
  fallo fatal del historial y permitía continuar la tanda; límite de lectura
  de metadata insuficiente para Unicode válido (ahora 32 KiB, todavía acotado).
- Regresión amplia inicial: 426 pruebas, 424 aprobadas y 2 smokes opcionales
  omitidos. Tras corregir: 111 pruebas manuales aprobadas, sin omisiones,
  incluyendo tres nuevas de regresión. GitHub/llavero aislados por prueba.
- Revisión propia y `git diff --check`, sin Bugbot local ni revisión independiente.
  Migración SQL: no. Sin push ni publicaciones. Evidencia y límites en
  `docs/BEATSTARS_LIVE_REVIEW_2026_10_24.md`; compatibilidad real comprobada para
  este beat y el catálogo en esta fecha, sin garantizar todos los previews.

### Link corto, BPM/tono y un info.txt por tanda ✅ COMPLETADA (2026-10-24)

- Descarga: el JSON del beat suma short_url (bsta.rs, vía ShareLinks, sin frenar la descarga si falla), pm y key
  (del título). El .beatstars.txt guarda el link corto y el hash de recuperación usa ese texto; paquetes anteriores siguen válidos.
- Generación: videos y miniaturas de la tanda juntos en <salida>/<fecha>/<canal>/ y un único info.txt por tanda
  (archivo, BPM, tono, link, TÍTULO/DESCRIPCIÓN/TAGS). Etiquetas del beat (≤500 caracteres); sin metadata, las del perfil.
  ender_beat(flat=True); sin lat conserva la carpeta por título (vista previa de estilos). main.py sin cambios.
- Guía: docs/MANUAL_BEATSTARS.md. Pruebas nuevas en 	est_manual_beatstars_files.py y flujo/render actualizados.

## Loop kits — Portada sin IA cuando falla la API de imágenes ✅ COMPLETADA (2026-10-31)

- Causa: con `cover_mode` `auto`/`template` los kits sin imágenes propias entran a la cola; si la API
  fallaba (sin saldo en OpenAI) no había imagen manual de respaldo y cada video terminaba en `KitSkip('cover')`.
- `kit_art.free_background`: imagen del género desenfocada (fondos de plantilla o referencias, con la misma
  rotación) y, si no hay, degradado con los colores del género. `for_cover` la usa cuando no hay portada.
- El aviso de Telegram por fallo de la IA sale una vez por corrida (antes, uno por video).
- Pruebas: `tests/test_kit_free_cover.py`; smokes de kit_art, plantilla, cableado, semanal y simulación OK.
- Pendiente del diagnóstico (próximas fases): motivo legible en Telegram de Beats, liberar el día de una
  subida fallida que no llegó a YouTube y aviso de token de YouTube vencido.
