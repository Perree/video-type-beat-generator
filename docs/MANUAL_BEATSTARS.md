# BeatStars en el modo manual

## Estado

Fases 1, 2 y 3 implementadas: búsqueda/descarga en «Crear videos ahora», historial
compartido, enlace en el TXT de cada video y movimiento conjunto a `hechos`.

La fuente es el preview público del reproductor, no el MP3/WAV original. No usa
login, cookies, Playwright ni Dropbox como alternativa. El catálogo y los medios
conservan las restricciones de hosts y tamaños de la integración existente.
Servicio remoto comprobado el 2026-10-24 con autorización: catálogo `matwyre`,
descarga de un preview real, filtros/exclusión en Qt y generación manual de
MP4/miniatura/TXT. Ver [la revisión real](BEATSTARS_LIVE_REVIEW_2026_10_24.md).
Las pruebas automáticas siguen usando respuestas falsas y audio sintético.

## Uso desde la pantalla manual

1. Elegir un canal y tocar **Descargar desde BeatStars…**, junto a Agregar beats
   y Agregar carpeta. No hace falta tener fondos para descargar audios.
2. Ingresar el perfil y tags separados por comas; sin tags se considera todo el
   catálogo. Elegir Cualquiera o Todos, y una cantidad de 1 a 100 (10 inicial).
3. Tocar **Buscar beats**. Se muestra título, tags, enlace y estado. Se seleccionan
   los primeros disponibles hasta la cantidad solicitada; las casillas permiten
   cambiar la selección sin superar esa cantidad. Doble clic en un enlace abre
   la página del beat, únicamente por acción del usuario.
4. Tocar **Descargar seleccionados**. Al terminar, el resumen muestra éxitos,
   errores y omitidos. Los audios completos aparecen en la entrada y tabla del
   canal, sin iniciar videos. Cerrar el diálogo y continuar el flujo manual.
5. Generar los videos con los fondos y el estilo habituales. Todos los videos y
   miniaturas de la tanda quedan juntos en `<salida>/<fecha>/<canal>/`, con un
   único `info.txt` (o `info (2).txt`... si ya había uno de otra tanda). Cada
   bloque del `info.txt` trae archivo, BPM, tono, link corto (`bsta.rs`, o la
   página del beat si BeatStars no lo expone) y TÍTULO / DESCRIPCIÓN / TAGS para
   pegar en YouTube. Los TAGS son las etiquetas del beat en BeatStars (hasta 500
   caracteres); un audio sin metadata usa las del perfil. La descripción usa el
   link corto si su plantilla contiene `{beatstars_url}`. Editar el título de la
   tabla solo cambia el título del video. BPM y tono salen del título del beat
   (`140bpm`, `key A Minor`); si no los trae quedan vacíos y no se analiza el audio.

Al terminar una generación desde la entrada del canal, audio, `.beatstars.json`
y `.beatstars.txt` pasan a `hechos` con el mismo nombre final. Si el nombre ya
existe, incluso si solo quedó un archivo asociado, se elige un sufijo nuevo para
todo el paquete. El título original se conserva en la metadata, por lo que el ID
del nombre del archivo y los sufijos de colisión no aparecen en el título generado.
Podés volver a arrastrar el audio de `hechos`: conserva su título original y su
enlace. Si copiás el audio a otra carpeta, copiá también sus archivos asociados
manteniendo el mismo nombre base. Los audios arrastrados desde otras carpetas
conservan su ubicación, como antes; solo se archivan los de la entrada del canal.

El historial es compartido por todos los canales. **Incluir ya descargados**
permite buscarlos y volver a seleccionarlos explícitamente. Los errores de un
beat no frenan los demás; los errores de historial detienen la tanda y conservan
los éxitos anteriores. Los detalles de cada error también están en el tooltip
de la columna Estado. Cambiar los filtros invalida los resultados anteriores;
cambiar la cantidad vuelve a seleccionar los primeros beats disponibles.

El perfil y los filtros se recuerdan en `config/manual_mode.json`, dentro de
`beatstars` (`profile_url`, `tags`, `quantity`, `match`, `include_downloaded`).
En el primer uso se propone el perfil de `beat_automation.beatstars_profile_url`
en la configuración local, si existe. Esto solo lee ese valor; no consulta ni
modifica la configuración remota de las automatizaciones.

El diálogo captura canal y carpeta al abrirse. Mientras está abierto bloquea
generación, edición de canal y cambios de carpetas en la pantalla local. La
búsqueda y descarga usan un worker; **Cancelar operación** conserva el diálogo y
los audios completos. Cerrar, pulsar Escape o cerrar la app cancela y espera a que
el hilo termine antes de destruirlo. Una petición en curso puede tardar hasta su
timeout en responder a la cancelación. El estado de búsqueda que llega después
de cancelar se descarta; los éxitos de descarga se conservan.

La pantalla local tiene scroll vertical para mantener accesibles las acciones
con la guía abierta y en ventanas pequeñas. No hay cambios SQL ni dependencias
nuevas en esta fase.

## API del motor

`core.manual_beatstars.ManualBeatStars` permite inyectar almacén, catálogo,
resolver, HTTP, herramientas multimedia y un callback `cancelled()`.

```python
from core.manual_beatstars import ManualBeatStars

# Ejemplo del motor; search/download acceden a red si no se inyectan dobles.
service = ManualBeatStars(cancelled=lambda: False)
search = service.search(
    "https://www.beatstars.com/MI_PERFIL", tags="trap, dark", match="any"
)
selected = [candidate.track.id for candidate in search.candidates[:10]]
if selected:
    result = service.download(search, selected, "RUTA_LOCAL/entrada/MI_CANAL")
```

- `search` devuelve perfil, ID estable del miembro y candidatos en orden de
  catálogo. `Candidate` contiene `track` y `downloaded`. `match` admite `any` o
  `all`; la coincidencia es exacta tras quitar espacios extremos y normalizar
  mayúsculas. Sin tags se considera todo el catálogo. No busca subcadenas.
- `include_downloaded=True` en la búsqueda muestra descargados; debe pasarse
  también al descargar para autorizar repetirlos. Se vuelve a consultar el
  historial bajo bloqueo antes de descargar, evitando usar una búsqueda obsoleta.
- `download` acepta de 1 a 100 IDs distintos pertenecientes a esa búsqueda y un
  destino explícito. No genera videos. Devuelve `BatchResult` con `downloads`
  (rutas), `errors` (ID y código), `skipped` (IDs) y `cancelled`.
- `progress(done, total, track_id)` informa el avance de la tanda. El último aviso
  lleva `track_id` vacío. Los callbacks deben ser rápidos y no lanzar excepciones.
- Los fallos de un preview no frenan otros beats. `HistoryError` es fatal y lleva
  `result` con los éxitos previos de la tanda, si hubo alguno. La UI debe presentar
  mensajes traducidos para los códigos y conservar esos éxitos.

## Archivos y persistencia

Cada descarga publica, sin reemplazar archivos existentes:

- `TK<ID> - <título>.m4a`: audio AAC. Si el preview ya usa AAC, se copia sin
  recodificar; en otro caso se convierte a AAC 192 kb/s.
- `<audio>.beatstars.json`: versión 1, miembro, track, título, tags, URL pública,
  fecha UTC, tamaño y SHA-256 del audio. Campos opcionales (ausentes en paquetes
  anteriores, que siguen siendo válidos): `short_url` (`https://bsta.rs/...`),
  `bpm` y `key`.
- `<audio>.beatstars.txt`: el link corto si existe; si no, la URL pública, y salto
  de línea. El hash de recuperación usa ese mismo texto.

El link corto se consulta una sola vez por tanda (`core.beat_share.ShareLinks`) y
nunca detiene la descarga: si falla, se guarda la URL de la página. El motor solo
consulta links cortos con su catálogo real; al inyectar `source` sin `shares`
(pruebas) no sale a la red.

Se valida duración, tipo de stream y decodificación antes de publicar. El audio
aparece al final, después de sus archivos asociados. Si hay colisión se elige un
nombre nuevo; el ID permanece en el nombre. El título de metadata debe usarse
como origen de las variables del beat, no el nombre físico truncado del audio.

`core.manual_beatstars_files.read_metadata` lee hasta 32 KiB y valida el esquema
y la URL. La vista previa usa esa lectura breve; el worker de render comprueba
además tamaño y SHA-256 del audio antes de usar el enlace. Una metadata ilegible,
incompleta o que no corresponda al audio se informa como error de ese beat; no
se genera un video con un enlace ajeno y los demás beats siguen. Un TXT asociado
sin su JSON indica un paquete incompleto. Un JSON válido basta para generar el
enlace aunque falte el TXT asociado. Audios sin archivos asociados conservan su
comportamiento anterior; su bloque del `info.txt` no lleva link.

Los helpers manuales aceptan metadata opcional en `beat_name`, `beat_values`,
`beat_title`, `beat_tags` y `beat_text`. `render_beat` y `upload_text` aceptan
`beatstars_url=''` al final de sus argumentos. Las llamadas anteriores siguen
funcionando. `render_beat(..., flat=True)` deja video y miniatura directo en la
carpeta del canal y no escribe texto (lo usa la tanda); sin `flat` conserva la
carpeta por título con su TXT (vista previa del editor de estilos). Con metadata,
`beat_tags` devuelve las etiquetas del beat y el perfil solo se usa si no hay.

El movimiento reserva un nombre libre para los tres componentes, mueve los
archivos asociados antes del audio y revierte los pasos completados ante un
error de I/O. Si también falla la reversión se informa el problema y se conservan
los archivos existentes para revisar entrada y hechos. No se reemplazan colisiones
concurrentes. Para destinos en otra unidad, cada archivo se copia a un temporal
del destino, se publica sin sobrescribir y luego se retira del origen. Esto no
constituye una transacción de varios archivos ante un cierre forzado o un fallo
físico del disco.

El historial vive en `config/manual_beatstars_history.json`, relativo al
repositorio, no al directorio de ejecución. Tiene versión 1, un mapa `downloads`
por `MR<miembro>:TK<track>` y un registro `pending` para recuperar publicaciones
interrumpidas. El JSON y su `.lock` están ignorados por Git. No hay SQL ni cambios
en el catálogo o estado de automatización. El historial empieza con esta función,
es común a todos los canales de esta instalación y no se sincroniza entre PCs.
No se guardan playlists ni URLs temporales de medios.

Las operaciones se serializan mediante un bloqueo no bloqueante del sistema
operativo: una segunda operación recibe `history_busy`. El bloqueo se libera
al cerrar el proceso, sin locks exclusivos obsoletos tras un crash. El JSON se
escribe a un temporal, se sincroniza y se reemplaza atómicamente. Límite: 16 MiB.
Un historial ausente empieza vacío; uno ilegible o de versión desconocida bloquea
la operación y nunca se reinicializa silenciosamente. Conservar el archivo para
diagnóstico o restaurarlo desde una copia válida antes de reintentar.

## Recuperación y cancelación

Antes de publicar se guarda la intención en `pending`. En la siguiente búsqueda
o descarga, incluso para otro canal:

- Paquete completo con hashes correctos: incorporar al historial sin descargar
  ni convertir otra vez. Si ya se archivó en `hechos`, buscar allí el nombre
  original o su sufijo de colisión y comprobar los tres componentes por sus
  hashes. Esto resuelve un fallo del guardado final del historial seguido de una
  generación y archivado del audio; no reconstruye descargas antiguas.
- Paquete incompleto: quitar únicamente los componentes de ese paquete cuyo
  contenido coincida con el registro y limpiar la intención.
- Archivos modificados o enlaces simbólicos: detenerse con
  `package_recovery_conflict`, sin borrarlos ni marcar éxito. Se requiere revisar
  los tres archivos y restaurar el paquete o retirar sus restos antes de reintentar.
  Un archivo de metadata del paquete pendiente repartido entre entrada y hechos
  también detiene la recuperación antes de quitar el audio original.

Un fallo al guardar el historial detiene la tanda; si los archivos ya estaban
completos, permanecen con su intención pendiente para recuperarlos. Un fallo al
revertir archivos también detiene la tanda y conserva la intención.

La cancelación se comprueba entre queries, lecturas HTTP, segmentos y procesos
multimedia. Una lectura de red en curso puede consumir hasta el timeout existente
de 10 segundos; no se promete una interrupción instantánea del socket. Los
subprocesos locales se supervisan cada 100 ms y se terminan al cancelar o vencer
el plazo. El pequeño bloque de publicación se termina antes de atender una
cancelación, para no dejar un paquete a medias. Los éxitos anteriores permanecen.

Los temporales de la operación terminan en `.part` y se limpian al salir por
éxito, error o cancelación. Un cierre forzado puede dejar directorios ocultos
`.beatstars-*` con `.part` en el destino; no contienen audios finales importables
y no se barren directorios ajenos automáticamente. La recuperación cubre cierres
de proceso; no garantiza transacciones ante un fallo físico del disco.

## Validación offline

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_manual_beatstars*.py" -v
```

Los fixtures cubren filtros, identidad, exclusión global y reinicio, repetición,
errores parciales, historial corrupto, colisiones, bloqueos, publicación
interrumpida y cancelación. Dos pruebas con FFmpeg generan audio sintético:
HLS/AAC → M4A sin recodificación y WAV → M4A/AAC con conversión y verificación.
Se omiten explícitamente si faltan FFmpeg/FFprobe; no descargan medios reales.

Para regresiones amplias usar un runner que renueve `FakeGhRun` y `MemoryKeyring`
antes de cada test, como indica `docs/APP_REVIEW_2026_10_23.md`, o pytest si está
instalado. No ejecutar una suite amplia sin aislar las conexiones locales.
En el sandbox Windows de esta sesión fue necesario apuntar TEMP/TMP a una
carpeta de pruebas dentro del workspace para evitar errores de permisos del
directorio temporal del sandbox.

Resultado del 2026-10-24: 27 pruebas nuevas aprobadas; regresión conjunta de 378
pruebas con 376 aprobadas y dos omitidas, sin fallos. Incluye `test_beat_*.py`,
`test_manual_render.py`, `test_bulk_queue.py` y `test_local_view.py`. No se usó
BeatStars real. Revisión propia del diff y escenarios de fallos; Bugbot local
no disponible, sin revisión independiente automatizada.

Pruebas de interfaz de la fase 2:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_manual_beatstars_dialog.py" -v
```

Cubren selección y límite, filtros, resultados vacíos, errores parciales/fatales,
cancelación, Escape, cierre diferido de diálogo/app, preferencias y destino
capturado. También prueban el motor real con HTTP/medios falsos y el historial al
reabrir. No realizan peticiones reales ni generan videos automáticamente.
Para QA visual offscreen en Windows se carga Segoe UI explícitamente cuando Qt
no descubre fuentes; esto solo afecta las pruebas, no la configuración de la app.

Cierre de fase 2 (2026-10-24): 24 pruebas nuevas aprobadas y regresión seleccionada
de 114 pruebas aprobadas, sin fallos ni omisiones. Se verificaron motor, diálogo,
vista local, render manual, bulk, shell, layout, revisión general y asistente con
GitHub/llavero falsos por prueba. Capturas inspeccionadas del diálogo, incluidos
errores a 650 × 500, y del modo local a 900 × 620 con guía y scroll vertical.
Revisión propia del diff; sin Bugbot local ni revisión independiente. Sin prueba
de descarga real contra BeatStars. La integración de los enlaces al TXT final y
al movimiento a `hechos` sigue pendiente en la fase 3.

## Cierre de la fase 3

Implementada el 2026-10-24. La nota anterior de cierre de fase 2 describe su estado
en ese momento; el TXT final y el movimiento de archivos asociados ya están conectados.

24 pruebas nuevas cubren metadata inválida o ajena al audio, lectura acotada,
compatibilidad de helpers y audios locales, título editado, colisiones de audio
y archivos asociados, errores de movimiento y reversión, copia entre unidades y
recuperación del historial tras archivar. La prueba integral usa el diálogo y el
motor real con HTTP falso y audio sintético: HLS → M4A → MP4/miniatura/TXT → hechos
con sufijo → reutilización → exclusión desde otro canal al reabrir.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_manual_beatstars_files.py" -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_manual_beatstars_flow.py" -v
```

Regresión seleccionada: 178 pruebas aprobadas, sin fallos ni omisiones; incluye
motor, diálogo, archivos/flujo nuevos, render manual, bulk, vista local, shell,
layout, asistente, revisión general, perfiles, estilo, caché y títulos. GitHub y
llavero aislados por prueba. No hubo SQL ni cambios en automatizaciones, ni se
descargaron beats reales. Revisión propia del diff; Bugbot local no disponible,
sin revisión independiente. La prueba contra el servicio real sigue siendo
opcional y requiere autorización. Se realizó después con autorización explícita;
ver [la revisión real](BEATSTARS_LIVE_REVIEW_2026_10_24.md).
