# afrowyre — preparación Afro (2026-11-07)

Destino aportado por el usuario: https://www.youtube.com/@afrowyre.
La identidad OAuth/ID todavía no está verificada. Configuración local revisable:
`docs/afrowyre.channel.json`, en pausa. No se modificó la configuración remota,
el registro de canales ni `BEAT_CHANNELS`; no se hizo push ni se subieron videos.

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

Cada tres días, 14:00 Argentina, como pidió el usuario. Fecha base provisional:
8/11/2026, por ser el primer día siguiente a esta preparación; no implica una
publicación confirmada. Fechas del ciclo: 8, 11, 14, 17, 20… El intervalo no se
reinicia al ejecutar el worker. Confirmar una fecha futura al activar si fuera
necesario. Escalonado de subidas de 2–4 días y cupo compartido conservados.

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
URL larga de los demás modos se conserva. No se verificaron todavía los
enlaces individuales en una publicación real de afrowyre.

## Imágenes y verificación

Inventario local de las carpetas de canales inspeccionado mediante una hoja de
contacto. En `images/mattwyyre/Principal` se encontraron originales coincidentes
con varias capturas propias, como las escenas de piscina y atardecer. Sus 28
archivos se verificaron con Pillow y se copiaron sin transformar a
`images/afrowyre/Principal`. No se afirma haber localizado todas las imágenes
exactas de las capturas. Originales intactos. La copia es local e ignorada por Git;
debe sincronizarse a una carpeta propia de afrowyre en Dropbox antes del worker.

Imagen fija completa, bandas negras por proporción original, sin texto;
miniatura automática. No se reutilizan imágenes de la competencia.

Los 25 snapshots del catálogo real se generaron y revalidaron sin errores.
Control del worker: 352 pruebas OK (dos omitidas), incluidos selección,
snapshots, plantillas, límites de títulos/tags, calendario estable y el caso
integrado de enlace ausente que no consume intentos ni llama al uploader.
La primera ejecución en sandbox falló por permisos de temporales; se repitió
fuera del sandbox y aprobó. La suite usa servicios/credenciales ficticios.

## Próxima fase: conexión, piloto y activación

Pendientes: registrar la configuración en Dropbox con CAS y conservar los demás
canales; sincronizar los fondos; conectar OAuth de afrowyre y verificar ID;
guardar secretos por slug sin imprimir tokens; publicar el código; ejecutar
dry-run remoto y piloto privado; revisar video, miniatura y link real; activar
la cadencia y confirmar la primera fecha. No se considera el canal operativo
por tener esta preparación local completa.
