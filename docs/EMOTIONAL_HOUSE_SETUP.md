# Canal emocional house — preparación

Fase local preparada el 8/11/2026. Perfil provisional:
`docs/emotional-house.channel.json`. No está conectado ni activado en la nube.
No se modificó ningún canal existente ni se subió ningún video.

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
Las carpetas son destinos propuestos; todavía no se crearon ni se cargaron clips.
Se clasificarán los materiales que indique el usuario. No se mezclan carpetas
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

Antes de activar falta recibir carpetas de clips, identificar el canal nuevo,
verificar su conexión propia y contrastar los tags con el catálogo de beats.
Después: copiar y verificar materiales, ajustar hora/ancla, renderizar una
muestra con los clips reales, ejecutar simulación y conectar el worker.
No hay un YouTube ID ficticio ni credenciales de otro canal en el perfil.

## Validación de esta fase

- Perfil pausado válido para el esquema; calendario de dos días.
- Pruebas de rotación por turno y reintento, rechazo de opciones inválidas,
  SEO por familias y conservación de comportamiento sin overlay.
- Render real FFmpeg con dos fuentes verticales y audio fuente: MP4 de 2,5 s,
  1080p/30 FPS, marco visible, bandas negras y únicamente audio del beat
  (silencio de prueba). Duración y pistas verificadas con ffprobe.
- No se probaron aún los materiales reales, licencias de los clips ni subidas.
- Suite oficial `smoke_beat_hardening.py --worker-only`: 419 pruebas aprobadas,
  sin omisiones, con FFmpeg real y las seis pruebas nuevas incluidas.
  Suite amplia de Beats en el entorno del proyecto: 475 aprobadas antes de
  incorporar las seis nuevas al patrón de descubrimiento del worker.
