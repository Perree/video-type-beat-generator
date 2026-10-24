# BeatStars en el modo manual

## Estado

Fases 1 y 2: motor y selector disponibles en «Crear videos ahora». La fase 3
conecta los enlaces al TXT de cada video y al movimiento conjunto a `hechos`.
Actualmente el enlace queda en los archivos asociados al audio descargado.

La fuente es el preview público del reproductor, no el MP3/WAV original. No usa
login, cookies, Playwright ni Dropbox como alternativa. El catálogo y los medios
conservan las restricciones de hosts y tamaños de la integración existente.
La compatibilidad del servicio remoto actual queda pendiente de una prueba live
autorizada: los tests usan respuestas falsas y audio sintético.

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

# Ejemplo de uso futuro; search/download acceden a red si no se inyectan dobles.
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
  fecha UTC, tamaño y SHA-256 del audio.
- `<audio>.beatstars.txt`: URL pública y salto de línea.

Se valida duración, tipo de stream y decodificación antes de publicar. El audio
aparece al final, después de sus archivos asociados. Si hay colisión se elige un
nombre nuevo; el ID permanece en el nombre. El título de metadata debe usarse
como origen al integrar los títulos manuales en la fase 3.

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
  ni convertir otra vez.
- Paquete incompleto: quitar únicamente los componentes de ese paquete cuyo
  contenido coincida con el registro y limpiar la intención.
- Archivos modificados o enlaces simbólicos: detenerse con
  `package_recovery_conflict`, sin borrarlos ni marcar éxito. Se requiere revisar
  los tres archivos y restaurar el paquete o retirar sus restos antes de reintentar.

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
