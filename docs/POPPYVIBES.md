# poppyvibes — Indie / Bedroom / Pop (2026-11-03)

Canal: `poppyvibes`, ID verificado por OAuth y captura
`UCrYqzwzKeGieAUTcRSX_A-Q`, handle actual `@poppyvibes-u7t`.
La captura pública mostraba el handle anterior `@prodmatwyre`: el ID coincide.
Token autorizado en memoria y guardado directamente en GitHub Secrets de
`kit-weekly` (`BEAT_CHANNEL_ID_POPPYVIBES`, `BEAT_YT_TOKEN_JSON_POPPYVIBES`).

## Selección y visuales

Catálogo real de matwyre: 1.147 beats, 21 elegibles por las etiquetas exactas del
canal (`docs/poppyvibes.channel.json`). Búsqueda ampliada por indicación del usuario
a indie, indie pop, indie bedroom, bedroom, bedroom pop, indie rock, pop, guitar pop
y sad pop, incluyendo variantes de escritura presentes en el catálogo. No se usa
coincidencia por fragmento: `asap rocky`, `hyperpop` y `latin pop` no entran solos.
No se inventan etiquetas bedroom para beats que no las tienen.

31 imágenes de `/typebeat local/canales/Trap Indie Type Beats/fondos`, todas
descargadas y verificadas con Pillow, copiadas sin alterar los bytes a
`contenido/canales/poppyvibes/fondos/image_XX.ext`. Originales preservados.
Inspección visual de dos ejemplos: retratos abstractos y estética granulada;
no se afirma una inspección visual individual de las 31 imágenes.
Imagen fija completa con bandas cuando haga falta, sin texto añadido; miniatura
automática del video. Carpeta antigua de miniaturas vacía.

## Títulos y descripción

Referencia: capturas de matti proporcionadas por el usuario, con títulos como
Pop Type Beat + nombre + Indie Rock / Indie Pop x Bedroom Pop / Guitar Pop.
Se adapta la estructura de género + nombre real + subgénero; no se copian sus
nombres ni miniaturas. Las capturas no prueban causalidad entre títulos y vistas.
No se hicieron llamadas pagas a vidIQ ni se obtuvieron puntuaciones predictivas.

`core/beat_indie_seo.py`, modo `indie_v1`: estilo determinado por tags reales y
tres estructuras en orden estable por ID del beat; al repetir se usa otra opción.
Títulos de hasta 100 caracteres. Ejemplos del catálogo real:

- `[FREE] "Bleeding" | Indie Pop x Indie Rock Type Beat`
- `[FREE] Indie Pop x Indie Rock Type Beat - "Waste my time"`
- `[FREE] Indie Pop Type Beat - "Therapy"`
- `[FREE] Guitar Pop Type Beat - "Beyond us"`

Descripción del usuario, sin timestamps ni promoción de álbumes/EP.
License y Free Demo usan `{url}` individual del beat, resuelto a bsta.rs por el
worker. `https://wyrebeats.vercel.app/` y `/free` devolvieron HTTP 404:
web reemplazada por `https://www.beatstars.com/matwyre`.
Condiciones, ofertas, Instagram, hashtags e Ignore Tags del usuario conservados.
No se verificó que las ofertas estén configuradas en el checkout de BeatStars.

## Cronograma y verificaciones

Lunes, jueves y sábado a las **18:00 America/Argentina/Buenos_Aires**, hora elegida
al no haberse indicado una. Subida escalonada de 2–4 días y tope compartido de diez
intentos diarios, igual que los otros canales; calendario existente respetado.
Con 21 beats hay unas siete semanas de material inicial a tres videos semanales;
la rotación actual no repite un beat durante 180 días. Los nuevos beats que
coincidan con los tags entran en las corridas siguientes.

OAuth leído con credenciales en memoria; calendario de los últimos 200 videos
consultado. Simulación local con días ocupados: seis slots libres entre 5 y 16/11.
Los 21 snapshots de SEO pasaron validación completa. Pruebas de modos y plantillas:
51 aprobadas, 39 subtests. Control del worker: 326 pruebas aprobadas (2 omitidas).
Regresión unittest de Beats: 388 pruebas aprobadas (2 omitidas).

Activación y corridas remotas: pendiente de completar en esta fase.
