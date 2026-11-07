# afrowyre — automatización Afro (2026-11-07)

Canal conectado y verificado por OAuth y consulta del handle: **AfroWyre**,
`@afrowyre`, `UCakkqBMHo6tRnihgqpJg_Sg`.
Configuración y registro activos en Dropbox; copia en `docs/afrowyre.channel.json`.
Secretos `BEAT_CHANNEL_ID_AFROWYRE` y `BEAT_YT_TOKEN_JSON_AFROWYRE` en `kit-weekly`.
`BEAT_CHANNELS` incluye afrowyre y conserva los ocho canales anteriores.
Token de OAuth solo en memoria durante la conexión y directamente a GitHub Secrets.

## Selección y calendario

Catálogo público de MatWyre consultado en vivo: 1.151 beats, 25 elegibles.
`selection_tags: ["afro*"]` es un marcador explícito para la familia afro:
afro, afrobeat(s), afroswing, afrohouse, afropop, afrodrill, afrofusion,
afrotrap y afrornb, incluidos tags compuestos como Afro Guitar o Guitar Afro.
Se normalizan mayúsculas, acentos y separadores. Los filtros exactos anteriores
conservan su comportamiento; `afro` sin asterisco sigue siendo coincidencia exacta.
No se admiten beats solo por tener R&B, guitarra o el nombre de un artista.
La familia también se aplica a las verificaciones previas a subir y al control
de cambios de selección durante una corrida. Se descarga el preview del beat
seleccionado por el planificador, siguiendo el flujo habitual, sin descarga masiva.

Cada tres días, 14:00 Argentina, como pidió el usuario. Ancla persistente:
8/11/2026 a las 14:00. El piloto privado consumió ese primer turno y permanece
privado, sin publicación automática. Los siguientes cuatro turnos están
reservados para 11, 14, 17 y 20/11 a las 14:00, todavía pendientes de subida.
El intervalo no se reinicia al ejecutar el worker. Escalonado de subidas de
2–4 días y cupo compartido conservados; el cron normal de Actions corre a las
19:00 de Argentina y mantiene el búfer de 14 días. Las fechas públicas quedan
sujetas a subida exitosa y disponibilidad de cupo.

## Referencias y adaptación

Evidencia: las capturas aportadas de Anyvibe, E+F, Brizy Beatz, Zane98 y trave,
y las capturas propias. Se aplicó la guía de Packaging Studio, sin llamadas
pagas a vidIQ ni puntuaciones inventadas. No se atribuye el número de vistas
a un título, imagen o descripción; no se consultaron sus analíticas privadas.

Anyvibe combina afro y artista; E+F y trave concretan Afro R&B; Brizy usa
Afroswing; Zane98 muestra que también existe un título general de Afrobeat.
Adaptación: estilo y, cuando conste en los tags, artista, seguidos por el nombre
real del beat. Sin añadir años antiguos, artistas fijos ni largas listas de
palabras ajenas al beat. El modo `afro_v1` conserva una estructura clara:

- `(FREE) Afrobeat Type Beat - "Touches"`
- `(FREE) Afrobeat x Rema Type Beat - "La vida"`
- `(FREE) Afro House Type Beat - "Fuga"`

Afro R&B y Afro Guitar se activan con etiquetas correspondientes; en la muestra
actual no se inventan para beats genéricos. Artistas reconocidos inicialmente:
Burna Boy, Wizkid, Rema, Tems, Omah Lay y Tayc, exclusivamente por tag exacto.
La variación responde al beat, sin cambios aleatorios de género entre corridas.
Al repetir un beat, se conserva la estructura y se rota el orden de tags.

La descripción abre con el título seleccionado y la compra. Conserva los
contactos, Instagram y términos aportados por el usuario. BPM y tonalidad solo
se muestran si existen en el título original; nunca se publican los ejemplos
105/C# de la captura como valores predeterminados. Hashtags por estilo real;
sin Burna Boy fijo en todos los beats.

El enlace individual se resuelve con ShareLinks al publicar. `afro_v1` exige
un `https://bsta.rs/...` válido, sin parámetros: si falta, se detiene ese intento
antes de reservar cuota y antes de llamar a YouTube, con motivo legible.
Nunca se reutiliza el enlace de Ocean Therapy para otro beat. El fallback a
URL larga de los demás modos se conserva. Para el piloto se resolvió
`https://bsta.rs/iDfeG7` y se comprobó HTTP 200 con redirección al track
`19637168` (MUJERES). El worker completó la subida con el enlace obligatorio;
el snapshot conserva `{url}` deliberadamente hasta el momento de publicar.

## Imágenes y verificación

Inventario local de las carpetas de canales inspeccionado mediante una hoja de
contacto. En `images/mattwyyre/Principal` se encontraron originales coincidentes
con varias capturas propias, como las escenas de piscina y atardecer. Sus 28
archivos se verificaron con Pillow y se copiaron sin transformar a
`images/afrowyre/Principal`. No se afirma haber localizado todas las imágenes
exactas de las capturas. Originales intactos. La copia local está ignorada por Git.
Los 28 archivos se sincronizaron sin transformar a la carpeta propia
`/Soft Projects/Type Beat Generator/contenido/canales/afrowyre/fondos`;
tamaño y content hash de Dropbox verificados uno por uno.

Imagen fija completa, bandas negras por proporción original, sin texto;
miniatura automática. No se reutilizan imágenes de la competencia.

Los 25 snapshots del catálogo real se generaron y revalidaron sin errores.
Control del worker: 352 pruebas OK (dos omitidas), incluidos selección,
snapshots, plantillas, límites de títulos/tags, calendario estable y el caso
integrado de enlace ausente que no consume intentos ni llama al uploader.
La primera ejecución en sandbox falló por permisos de temporales; se repitió
fuera del sandbox y aprobó. La suite usa servicios/credenciales ficticios.

## Conexión, piloto y activación completados

Se integró `origin/master` (incluidas las automatizaciones Melodic y los tests de
títulos R&B) conservando sus cambios. Resolución conjunta de los tres conflictos
en plan, registro de modos y compilación de plantillas. 366 pruebas worker OK,
dos omitidas, tanto localmente como en las dos corridas remotas. Código publicado
con el merge `6124830`; la prueba Afro de seis casos también aprueba con la copia
de configuración activa.

Configuración y registro guardados por CAS y releídos; los demás canales
conservados. No se cambió el estado de publicaciones previas. La preparación se
hizo en pausa; la simulación usó `include_paused` sin escribir reservas reales.
OAuth verificó la misma identidad mediante `channels.list(mine=True)` y
`channels.list(forHandle='@afrowyre')`. El lanzador operativo usa el interruptor
documentado `TBVG_REAL_CREDENTIALS=1`, porque las dependencias de Google pueden
cargar unittest y activar los dobles de la protección automática del proyecto.

- Dry-run remoto: [42393131030](https://github.com/Perree/video-type-beat-generator/actions/runs/42393131030),
  success; planned=5, eligible=1, failed/blocked/orphan/unknown=0, uploaded=0.
- Piloto: [42393378694](https://github.com/Perree/video-type-beat-generator/actions/runs/42393378694),
  success; planned=5, eligible=1, uploaded=1;
  failed/blocked/orphan/unknown/calendar_unavailable/thumbnail_failed=0.
- Video: [MUJERES](https://www.youtube.com/watch?v=IRXRIqpRRC4), track `TK19637168`,
  título `(FREE) Afrobeat Type Beat - "MUJERES"`.
- Subida enviada con privacidad `private`, sin `publishAt`; recibo de Dropbox
  confirmado con modo `private_pilot`. Un intento normal consumido del cupo
  compartido, sin excepciones ni cambios en el límite.
- Fondo reservado `#jacuzzi #pool #spa #winter_.jfif`, 177.473 bytes. Se comprobó
  el digest de píxeles del snapshot contra el original local y se inspeccionó
  una reproducción del frame con el mismo compositor: 1920×1080, imagen completa,
  barras negras, sin texto. Esto no es una inspección de la reproducción de YouTube.
- Activación final: registro `activo=true` y config `active=true`, releídos;
  28 imágenes y cuatro pendientes verificados. Calendario y demás canales intactos.

Computer Use no tenía permiso para acceder a Edge, por lo que no se inspeccionó
la reproducción ni los metadatos en Studio. No se hizo lectura posterior del
status del video mediante la API: la evidencia de privacidad es la solicitud
del uploader y el recibo `private_pilot`. El enlace del piloto permite al usuario
hacer la revisión audiovisual en su cuenta. La subida, el recibo, el enlace corto,
la imagen reservada y el cronograma sí quedaron comprobados técnicamente.
