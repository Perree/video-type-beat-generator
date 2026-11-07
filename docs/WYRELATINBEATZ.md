# WyreLatinBeatz — preparación de automatización

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

Pendientes para activar: publicar el código del nuevo modo, OAuth con identidad
coincidente, secretos BEAT_CHANNEL_ID_WYRELATINBEATZ y BEAT_YT_TOKEN_JSON_WYRELATINBEATZ,
alta en BEAT_CHANNELS, piloto audiovisual y activación. No se ha subido ningún
video a YouTube durante esta preparación. El seguimiento de métricas de títulos
de otros modos no se extiende automáticamente a latin_v2.
