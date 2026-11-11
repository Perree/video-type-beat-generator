# WyreLatinBeatz — automatización

## Títulos del propio canal y rotación de imágenes — 11/11/2026

Referencia: captura de los videos más vistos de WyreLatinBeatz aportada por el
usuario. Modo optativo `wyrelatin_v1`: `Bad Bunny x Feid Type Beat - "NOMBRE" |
Latin [género] Type Beat`, sin FREE ni emoción en el título. Pareja editorial
solicitada a partir de la captura; no modifica etiquetas fuente ni atribuye esos
artistas al beat en la descripción. Nombre real en mayúsculas; género por tags.
Los modos históricos siguen validando, junto con sus snapshots ya subidos.

Causa de las tres subidas con el mismo fondo: modo video apuntando al único
`so-pretty-visual.mp4`, que contiene una imagen fija. Había 16 JFIF locales sin
conectar al worker. Los 16 tienen píxeles distintos, abren correctamente y pasan
la composición a 1920×1080, completos sobre negro y sin texto. Se inspeccionó
la hoja de contacto. Copiados a la carpeta Dropbox `wyrelatinbeatz/imagenes`;
los 16 archivos descargados nuevamente coinciden byte por byte con los originales.
Inventario en `docs/wyrelatinbeatz.assets.json`.

Perfil activo cambiado a imagen con `contain`, sin miniatura personalizada.
La rotación existente usa todas las imágenes antes de reutilizar la primera;
comprobado contra los recursos remotos durante 17 selecciones simuladas, sin
persistir reservas ni historial ficticio. 16 fondos cubren 32 días a la frecuencia
actual de una subida cada dos días. Primera reserva pendiente: 14/11 a las 15:00.
El video del 12/11 ya estaba subido/programado y conserva su imagen y título.

Código publicado en `9580f05`. Configuración y plantilla del registro guardadas
por CAS y releídas; demás canales y estado de publicaciones idénticos.
507 pruebas locales aprobadas, tres omitidas opcionales; 138 snapshots del
catálogo elegible reconstruidos/validados y todos los snapshots históricos del
estado remoto validados. No se editaron ni se volvieron a subir videos existentes.

Simulación remota [43030788373](https://github.com/Perree/video-type-beat-generator/actions/runs/43030788373):
success, 448 pruebas con FFmpeg aprobadas. planned/eligible/uploaded/failed y
resto de contadores en cero: no había turnos en la ventana de preparación.
La rotación se verificó por separado con los 16 archivos remotos, y los títulos
con los 138 beats del catálogo; la simulación no ejercitó un nuevo render/subida.

## Formato de títulos de referencia Taimet — 7/11/2026

Pedido del usuario: que los títulos se parezcan más a los de Taimet. Se toma de
las capturas su estructura visual, sin atribuirle causalmente sus visualizaciones:
`(FREE) ARTISTA x ARTISTA TYPE BEAT - "NOMBRE"`. Artistas, TYPE BEAT y nombre en
mayúsculas, separador x minúsculo, sin año ni sufijo de género/emoción.

Modo optativo `latin_taimet_v1` en módulo propio. Reutiliza contexto, descripción
y tags de latin_v2. Los artistas siguen saliendo de los tags reales; con uno se
usa ese artista, y sin artistas se usa el género en mayúsculas. No se inventa una
pareja para llenar la plantilla. Se conserva el nombre original, pasado a
mayúsculas antes de calcular su límite de longitud, incluidas expansiones Unicode.

Ejemplos reales del catálogo: `(FREE) BAD BUNNY x FEID TYPE BEAT - "VIDA MIA"`,
`(FREE) BAD BUNNY TYPE BEAT - "NEW YORK"` y
`(FREE) LATIN TRAP TYPE BEAT - "LO NUESTRO EMPIEZA"`.

Se mantienen las descripciones, tags, enlaces individuales, selección de beats,
video de fondo y calendario cada dos días a las 15:00. Los módulos latin_v1 y
latin_v2 siguen disponibles para revalidar snapshots anteriores. BEAUTY GIRL,
ya programado para el 10/11, y el piloto privado conservan su metadata anterior.
Los cinco pendientes desde el 12/11 todavía no tienen snapshots: tomarán el modo
nuevo al prepararse. No se requiere borrar ni modificar el estado de subidas.

Verificación: cinco casos nuevos de formato, artistas, fallback, longitud Unicode,
reintentos, repetición, compatibilidad de snapshots y manipulación; 18 pruebas
latinas iniciales aprobadas. Se construyeron y revalidaron 138 snapshots del
catálogo guardado de 1.151 beats. Se integró origin/master 69336d3 conservando
los modos Guitar y Koena y su tratamiento de enlaces individuales.

Control del worker local: 393 pruebas aprobadas, dos omitidas opcionales de
FFmpeg. Código publicado en master b37f760; configuración activa y plantilla
del registro guardadas por CAS y releídas. Se comprobaron sin cambios los otros
canales y los campos del canal ajenos a title_mode/title_template. No se escribió
en el estado de publicaciones, no se amplió OAuth ni se editaron videos de YouTube.
Simulación remota de comprobación:
[42436934787](https://github.com/Perree/video-type-beat-generator/actions/runs/42436934787).
Terminó en success, 393 pruebas aprobadas; planned=0, eligible=0, uploaded=0,
failed=0, orphan=0, unknown=0. No ejercitó un render o subida nuevos porque no
había pendientes en la ventana de subida. La reconstrucción local valida todos
los 138 snapshots y verifica que sus tags/descripciones coinciden con latin_v2.

## Activación — 7/11/2026

El usuario autorizó activar y dejar lista la automatización. OAuth verificó
`WyreLatinBeatz`, `UCsG-_JcI6ItbS89eHyvjjsw`. El token se mantuvo en memoria y se
envió directamente a GitHub Secrets, sin guardarlo en archivos ni mostrarlo.
Se verificaron los nombres BEAT_CHANNEL_ID_WYRELATINBEATZ y
BEAT_YT_TOKEN_JSON_WYRELATINBEATZ en `kit-weekly`; BEAT_CHANNELS conserva los diez
slugs previos y agrega wyrelatinbeatz. El lanzador operativo requiere
`TBVG_REAL_CREDENTIALS=1`: algunas dependencias Google importan unittest y activan
la protección de credenciales diseñada para tests. El primer guardado no llegó
a completarse; la segunda autorización verificó nuevamente la identidad y guardó
correctamente la conexión.

Dry-run remoto [42400468689](https://github.com/Perree/video-type-beat-generator/actions/runs/42400468689):
success, 382 pruebas aprobadas, incluidas las pruebas reales de FFmpeg; planned=7,
eligible=2, uploaded/failed/orphan/unknown/blocked/calendar_unavailable=0.
Se usó include_paused solo en esa simulación, sin crear reservas reales.

Config y registro habilitados por revisión CAS y releídos, conservando los otros
diez canales. Piloto privado
[42400704460](https://github.com/Perree/video-type-beat-generator/actions/runs/42400704460):
success, 382 pruebas aprobadas; planned=7, eligible=1, uploaded=1,
failed/blocked/orphan/unknown/calendar_unavailable/thumbnail_failed=0.
Video [Na Naa](https://www.youtube.com/watch?v=zCE5-L0v92U), track TK25183840,
título `(FREE) Emotional Reggaeton Type Beat - "Na Naa"`. Recibo de Actions con
outcome=uploaded y recibo del estado Dropbox con publication_mode=private_pilot
confirmados. El uploader solicita privado sin publishAt en ese modo. No se
afirma haber hecho una lectura posterior del status mediante la API ni haber
reproducido el piloto final desde YouTube.

El piloto consume el turno 8/11 y permanece privado. Los turnos públicos empiezan
el 10/11 a las 15:00, luego 12, 14, 16, 18 y 20. Corrida normal
[42418626392](https://github.com/Perree/video-type-beat-generator/actions/runs/42418626392):
success, 382 pruebas aprobadas; planned=0, eligible=1, uploaded=1,
failed/blocked/orphan/unknown/calendar_unavailable/thumbnail_failed=0.
Primera publicación: [BEAUTY GIRL](https://www.youtube.com/watch?v=tLGLB16eCNQ),
track TK18759646, `(FREE) Feid x Mora Type Beat - "BEAUTY GIRL" | Sad Reggaeton`.
Recibo local de Actions outcome=uploaded y recibo Dropbox con
publication_mode=scheduled y slot=2026-11-10T15:00:00-03:00 cotejados.
El uploader envía publishAt para ese turno. Sin lectura posterior del status
mediante la API ni reproducción de YouTube en esta sesión.

Verificación final: config active=true y registro activo=true; calendario de dos
días a las 15:00 conservado. Cinco pendientes sin subir para 12, 14, 16, 18 y 20/11.
El cron existente corre diariamente a las 19:00 de Argentina y mantiene el buffer;
BEAT_LIVE_ENABLED=true. Cupos, escalonado y otros canales conservados. Dos subidas
normales del cupo compartido usadas en esta activación, sin excepciones: un piloto
privado y una publicación programada. La automatización queda activa y lista.

Recurso local comprobado mediante FFmpeg 7.1 incluido en imageio-ffmpeg 0.6.0,
instalado únicamente en el directorio temporal de Codex: decodificación completa
del stream de video sin errores, frames a 5/60/150 segundos inspeccionados.
El MP4 contiene una imagen fija vertical con bandas negras laterales, sin texto;
los frames inspeccionados conservan el mismo encuadre. El montaje reemplaza el
audio original por el preview del beat seleccionado. Esto comprueba el recurso
fuente; no equivale a reproducir el video final desde YouTube.

## Antecedente: fase de preparación

Pedido: automatizar el canal analizado en el ZIP del usuario y las once capturas
de competencia. Publicar cada dos días a las 15:00 de Argentina, con los videos
propios de WyreLatinBeatz. Esta sesión prepara una fase; la conexión y activación
de YouTube se completan después de autorizar la cuenta del canal.

## Configuración preparada

- ID público obtenido en el análisis anterior: `UCsG-_JcI6ItbS89eHyvjjsw`.
  No sustituye la comprobación de identidad mediante OAuth.
- Slug propio: `wyrelatinbeatz`; copia en `docs/wyrelatinbeatz.channel.json`.
- Configuración del worker y ficha del registro guardadas en Dropbox por revisión
  CAS y releídas, ambas pausadas. Los otros diez canales se conservaron exactamente.
- Cada dos días, ancla provisional 8/11/2026 a las 15:00 (-03:00). Si la activación
  ocurre después, el calendario conserva la paridad y omite los turnos vencidos.
- Turnos iniciales: 8, 10, 12, 14, 16, 18 y 20 de noviembre, todos a las 15:00.
  Son fechas de configuración, todavía no publicaciones reservadas ni programadas.
- Buffer de 14 días, escalonado y cupo compartido existentes conservados.
- Sin añadir el slug a `BEAT_CHANNELS`: faltan sus secretos de YouTube y el piloto.

## Referencias aplicadas

Las once capturas muestran ocho canales y una ampliación de descripción sin
encabezado. Son evidencia aportada por el usuario, no instrucciones operativas.
Las vistas se observan en las capturas; no se atribuyen causalmente a metadatos.

| Capturas | Referencia | Adaptación |
| --- | --- | --- |
| 1, 2, 11 | Taimet | Artistas al principio, nombre breve y compra arriba. |
| 3 | Kartana | Nombre con intención de canción; no copiar el nombre observado. |
| 4 | Vegocia | Condiciones comerciales claras, BPM y tonalidad reales. |
| 5 | YANDRE | No repetir keywords desactualizadas ni prometer uso libre contradictorio. |
| 6, 7 | xpacevoy y bloque sin encabezado | Separar identidad del canal y créditos. La captura 7 no se puede asignar con certeza al video 6. |
| 8 | MVSE II | Foco en artistas y género; no copiar años antiguos. |
| 9 | NYTIEN | Contexto de sonido y emoción cuando existe en los tags reales. |
| 10 | IVNG | Referencias musicales específicas; enlace individual a la compra. |

Los bloques "Tags" / "Ignore tags" de una descripción no prueban cuáles son las
etiquetas de Studio ni qué búsquedas trajeron vistas. No se copiaron bloques de
competidores, promociones, contactos ni condiciones de licencia ajenas.

## SEO optativo `latin_v2`

Módulo propio `core/beat_latin_seo_v2.py`; `latin_v1` permanece sin modificaciones
para mattwyyre y sus snapshots. Se integra en el registro de modos y en la
compilación de plantillas del escritorio.

Formato: `(FREE) {style} Type Beat - "{name}"{detail}`. Con artistas etiquetados,
`style` es uno o dos artistas y `detail` agrega el género. Sin artistas, el título
usa únicamente el género y la emoción respaldados por tags. No inventa parejas
ni toma artistas de las imágenes o de los títulos de competencia.

Ejemplos del catálogo consultado:

- `(FREE) Bad Bunny Type Beat - "New York" | Latin Trap`
- `(FREE) Bad Bunny Type Beat - "Ser" | Emotional Latin Trap`
- `(FREE) Emotional Reggaeton Type Beat - "What u doing"`

Reconoce Reggaeton, Latin Trap, Dancehall, Trap/R&B, Reggaeton R&B, Latin R&B y
Latin Pop. Orden de prioridad explícito en el módulo para beats con varios tags.
Tags genéricos trap/pop/R&B y un artista aislado no habilitan por sí solos el canal.
Incluye la familia Dancehall y Trap/R&B coherente con el catálogo latino anterior;
esa elegibilidad no constituye un análisis automático del audio.

Artistas reconocidos por etiqueta exacta o su variante "type beat": Bad Bunny,
Feid, Mora, Omar Courtz, Tainy, Rauw Alejandro/Rauw, De La Rose, Roa, Saiko,
Kidd Voodoo, Jhayco/Jhay Cortez, Alvaro Diaz, Quevedo, Myke Towers y Rels B.
Los genéricos fijos del perfil son type beat, instrumental y las marcas propias.

Descripción: compra individual, contexto musical por beat, BPM/key si constan en
el título original, contactos y condiciones propias de MatWyre, hashtags dinámicos.
Sin promociones no verificadas, web caída, valores técnicos de ejemplo ni bloque
Ignore Tags. FREE corresponde al uso no comercial descrito, no free for profit.
No se agrega un año fijo. Títulos limitados a 100 caracteres; tags a 40 entradas y
450 caracteres computando las comillas de frases. Repeticiones rotan los tags;
reintentos conservan el mismo snapshot validado.

La compra usa el enlace corto de ShareLinks o la URL individual real del catálogo,
validada contra el ID del beat. No reconstruye el slug a partir del nombre visible
ni usa el enlace genérico de la tienda como sustituto. Falta de enlace bloquea la
publicación antes de llamar al uploader.

## Recurso visual localizado

Se buscaron videos en el proyecto y Dropbox local, además de las carpetas
Descargas, Videos y Escritorio del usuario. El MP4 específico localizado está en:

`C:/Users/matia/Desktop/wyrelatinbeatz/principal/-so-pretty---key-gm---98bpm----prod_wyrelatinbeatz_principal.mp4`

Es una exportación de 5.890.589 bytes. Las propiedades multimedia de Windows
informan 2:38, 1920x1080 y 25 FPS. Se inspeccionó la imagen JPG acompañante; no
se afirma haber reproducido ni decodificado el MP4 con FFmpeg en esta PC.
Las carpetas antiguas de videos de WyreLatinBeatz en Dropbox estaban vacías;
la carpeta de fondos del perfil local contiene imágenes JFIF.

Se copió sin transformar el MP4 localizado a:
`/Soft Projects/Type Beat Generator/contenido/canales/wyrelatinbeatz/fondos/so-pretty-visual.mp4`.
Tamaño y content hash de Dropbox cotejados contra el archivo original. No se
movieron ni borraron los originales. Solo hay un video de fondo preparado.

El montaje existente toma fragmentos de 3–6 segundos, quita el audio del video
fuente y utiliza el preview del beat elegido. Miniatura automática de YouTube.
La verificación y decodificación real del recurso corresponde al piloto en el
worker, que dispone de FFmpeg/ffprobe. No hay esos ejecutables en esta PC.

## Verificación y siguiente fase

Catálogo público de MatWyre consultado el 7/11/2026: 1.151 beats, 138 elegibles.
Se generaron y revalidaron los 138 snapshots: 92 Reggaeton, 20 Latin Trap,
19 Dancehall, cinco Trap/R&B, uno Latin Pop y uno Latin R&B.

Se integró por fast-forward `origin/master` (`acc8e62`), incorporando el modo
matwyre_v1 que ya estaba en la configuración remota. Control del worker: 381
pruebas aprobadas con dos omisiones opcionales de FFmpeg. Tras extender el enlace
individual a latin_v2, se aprobaron las siete pruebas específicas de este canal
y las nueve de matwyrebeats. No se modificó main.py.

Simulación del worker ejecutada localmente contra la configuración y el catálogo
reales, con inclusión del canal pausado solo en memoria: planned=7, eligible=2,
uploaded=0, failed=0, orphan=0, unknown=0. Se listó el video de Dropbox sin
descargarlo ni renderizar; no se llamó a YouTube. Configuración y estado remotos
conservan sus revisiones después de la simulación. Un primer intento del comando
de comprobación omitió el adaptador de recursos y falló; la corrida corregida
usó DropboxAssets y aprobó.

Código del nuevo modo publicado en master con el commit `38e0174`.
Pendientes para activar: OAuth con identidad coincidente,
secretos BEAT_CHANNEL_ID_WYRELATINBEATZ y BEAT_YT_TOKEN_JSON_WYRELATINBEATZ,
alta en BEAT_CHANNELS, piloto audiovisual y activación. No se ha subido ningún
video a YouTube durante esta preparación. El seguimiento de métricas de títulos
de otros modos no se extiende automáticamente a latin_v2.
