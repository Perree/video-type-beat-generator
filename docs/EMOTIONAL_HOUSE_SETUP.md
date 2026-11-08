# Canal emocional house — preparación

Fase local preparada el 8/11/2026. Canal indicado después: **afterbeachbeats**,
`UCqSN_dCTnhNcRcMmW3qc3JQ` (nombre contrastado en el HTML público de YouTube).
Esto no comprueba acceso OAuth ni titularidad. Perfil:
`docs/emotional-house.channel.json`. Copiado y releído en la configuración
de Dropbox y en el registro, pausado, con nombre visible afterbeachbeats.
Los otros catorce perfiles se conservaron iguales. No se activaron subidas.

## Referencia del usuario

Cuatro capturas de Klein Beats (@KleinBeats). Se observan títulos con
`[FREE] {géneros} Type Beat - "{nombre}" | {tipo de instrumental}`,
cruces Deep House/Jersey Club/Reggaeton, House/Club y Tech House/Techno.
Los fondos muestran retratos, calle y fiestas nocturnas, rojos y azules,
imagen centrada sobre negro y un contorno lateral de color. Las duraciones
visibles rondan 2:35–3:34. Son observaciones de las capturas, no un análisis
del audio ni una comparación de rendimiento ajustada por antigüedad.

La descripción visible reúne título, compra del beat sin tag, tienda, contacto,
condiciones de uso, palabras de búsqueda, capítulos y hashtags. Los tags internos
no son visibles. Las palabras al pie de la descripción no prueban cuáles son
los tags internos. La consulta pública a YouTube no permitió ampliar la evidencia.

Se reutiliza la estructura con nombre real de cada beat, enlace individual,
créditos propios y condiciones existentes de MatWyre. No se copian identidad,
correo, enlaces de Klein, coproductores ni capítulos de otro audio.
Los cruces y tags musicales se generan a partir de etiquetas reales del beat.
Afro House se incluye por pedido del usuario; no se presume presente en todos
los instrumentales de la referencia. No se crean capítulos sin tiempos reales.

## Tres tipos de montaje

Rotación A/B/C por fecha del turno, independiente del beat y sus reintentos:

| Grupo | Material sugerido | Fragmentos |
|---|---|---|
| emocional | azul, mar, ciudad de noche, retratos tranquilos | 4–7 s |
| club | luces rojas, baile, fiesta, detalles urbanos | 2–4 s |
| afro-calido | atardecer, movimiento, luces cálidas | 3–6 s |

Cada grupo tiene su propia carpeta Dropbox bajo
`/Soft Projects/Type Beat Generator/contenido/canales/emotional-house/`.
Las carpetas ya contienen nueve clips del 8/11/2026, tres por grupo, copiados
y descargados de vuelta por API para comparar byte por byte con sus originales.
No se mezclan carpetas
en un mismo montaje. Un grupo vacío detiene su render; no toma material ajeno.

El motor toma un fragmento por fuente, hasta doce fuentes y 512 MiB por montaje,
normaliza a 1920×1080/30 FPS y repite la secuencia hasta la duración del beat.
Los cortes y puntos de entrada varían de forma estable por trabajo; no hay
sincronización automática de cortes al BPM ni transiciones fundidas.
Se descarta el audio de los videos fuente. El encuadre `contain` conserva
el video vertical completo sobre bandas negras, sin recortar caras.

## Overlay solo para este perfil

`visual.film_overlay = film_gate_red_v1` añade un contorno rojo lateral
redondeado con halo y grano temporal suave. Es una aproximación original a
la ventanilla de película visible en las capturas, no el archivo del competidor
ni una identificación comprobada de una cámara o filtro 8 mm.
Las capturas no permiten verificar rayas, parpadeo ni movimiento del overlay.
Se puede ajustar al revisar un clip del video de referencia y los materiales.

Valor por defecto del motor: sin overlay. El perfil nuevo es el único que
activa el efecto; no se cambiaron perfiles de otros canales.
`custom_thumbnail=false`: no se envía miniatura personalizada. El efecto forma
parte del video y estará en los cuadros de los que YouTube genere miniaturas.
El software no controla cuál de esos cuadros elegirá YouTube.

## Calendario y activación pendiente

Frecuencia solicitada: cada dos días. Hora provisional: 18:00 Argentina,
ancla local 10/11/2026, editable antes de activar. No es una fecha prometida:
no hay reservas ni publicaciones creadas. Se conserva el escalonado habitual
de 2–4 días y el cupo compartido existente.

Antes de activar falta completar la conexión propia de YouTube, contrastar
los tags con el catálogo, ajustar hora/ancla y ejecutar simulación del worker.
El ID de destino es el aportado por el usuario. No se reutilizan credenciales
de otro canal ni se habilita el calendario por la identificación pública.

## Validación de esta fase

- Perfil pausado válido para el esquema; calendario de dos días.
- Pruebas de rotación por turno y reintento, rechazo de opciones inválidas,
  SEO por familias y conservación de comportamiento sin overlay.
- Render real FFmpeg con dos fuentes verticales y audio fuente: MP4 de 2,5 s,
  1080p/30 FPS, marco visible, bandas negras y únicamente audio del beat
  (silencio de prueba). Duración y pistas verificadas con ffprobe.
- No se verificaron licencias de los clips ni se realizaron subidas a YouTube.
- Suite oficial `smoke_beat_hardening.py --worker-only`: 419 pruebas aprobadas,
  sin omisiones, con FFmpeg real y las seis pruebas nuevas incluidas.
  Suite amplia de Beats en el entorno del proyecto: 475 aprobadas antes de
  incorporar las seis nuevas al patrón de descubrimiento del worker.

## Materiales recibidos el 8/11/2026

Origen indicado: `C:\Users\matia\Videos\4K Video Downloader+`.
Se seleccionaron exclusivamente nueve MP4 cuya fecha de creación local corresponde
al 8/11/2026; las fechas de modificación coinciden con el mismo día.
Los siete videoclips descargados el 7/11 quedaron excluidos.
Originales conservados; copias locales en `videos/emotional-house/` y remotas
en las carpetas del perfil. Nombres de destino estables `clip-01.mp4` a
`clip-09.mp4`, sin sobrescribir archivos distintos. Total: 15.527.195 bytes.

| Grupo | Clips | Contenido observado |
|---|---|---|
| emocional | 02, 04, 05 | Auto nocturno, montaje VHS urbano y escenas retro |
| club | 06, 07, 09 | Fiesta, club rojo y montaje surrealista rojo |
| afro-calido | 01, 03, 08 | Costa, atardecer, viaje y baile frente al mar |

Clasificación editorial por revisión de tres cuadros de cada archivo; no es
una etiqueta de género musical inherente al video. Todos pasan decodificación
completa con FFmpeg. Duran entre 6,76 y 40,72 s. El 04 es 240×240 y el 09,
234×416: al ampliar se conserva su suavidad, no se presume detalle 1080p real.
Algunos originales ya contienen cortes y estética VHS; se conservan.

Inventario con dimensiones, tamaños, SHA-256 y rutas verificadas:
`docs/emotional-house.assets.json`. Inventario privado con nombres originales
y revisiones de Dropbox en `tokens/emotional_house_assets.json`, fuera de Git.

La prueba con fuentes reales detectó que el contenedor incluye una cola de
audio más larga que el video. `video_info` ahora usa la menor duración entre
contenedor e imagen, cuando el archivo expone esta última, para evitar cortes
truncados y descartes. Una prueba de regresión cubre el caso y duraciones
inválidas. Se aprobaron 16 pruebas de montaje y seis del perfil, con FFmpeg real.

Se renderizaron tres muestras de 24 s con los clips reales y audio silencioso
de prueba: `exported_videos/emotional-house-previews/emocional.mp4`, `club.mp4`
y `afro-calido.mp4`. Las tres incluyen exactamente las tres fuentes de su
grupo, cero descartes, marco/grano, 1080p/30 FPS y duración validada por ffprobe.
El audio se decodificó completo y contiene únicamente el silencio de prueba:
no quedó sonido de los originales. Nueve cuadros finales inspeccionados.
Son muestras visuales, no beats terminados ni videos subidos a YouTube.
El contacto de revisión está en `exported_videos/emotional-house-previews/revision.jpg`.

Se consultó el catálogo público real de MatWyre: 1.151 beats, 73 elegibles por
las etiquetas del perfil. Los 73 snapshots SEO se generaron y revalidaron.
Simulación local del worker con el perfil pausado habilitado solo en memoria:
`planned=6`, `eligible=1`, `uploaded=0`; todos los contadores de error en cero.
No crea reservas reales ni modifica el estado de publicaciones.

Se abrió OAuth para comprobar y conectar el destino. El primer intento confirmó
el ID, pero no guardó secretos: la importación de Google cargó indirectamente
`unittest` y activó la guarda de pruebas de `gh_status`. Se detectó el motivo
y se reabrió la conexión usando el interruptor documentado para operaciones
reales del proyecto. No se desactivó ni modificó esa guarda en el código.
La conexión no se considera completada mientras no exista comprobante de
identidad y guardado exitoso de secretos propios.

## Conexión verificada (8/11/2026)

OAuth completado: afterbeachbeats, `UCqSN_dCTnhNcRcMmW3qc3JQ`, ID comprobado
antes de guardar el token en GitHub Secrets. El token solo transitó por memoria
y stdin; no se escribió en archivos. Secretos propios del slug emotional-house
en kit-weekly. La clave interna del worker es emotional-house; el ID real de
YouTube se valida mediante `youtube_channel_id` en el perfil.
BEAT_CHANNELS ampliado de catorce a quince canales y releído, conservando
las catorce entradas anteriores. Configuración y registro todavía pausados
mientras se valida la simulación remota antes de la activación.
