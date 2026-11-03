# RaveWaveBeatz — preparación del canal

Fecha: 2026-11-03. Canal activo en la automatización de Beats (ver «Estado operativo»).

## Evidencia y límites

Revisión de las diez capturas suministradas por el usuario, sin consultas pagas de vidIQ.
Se distinguen tres canales: RaveWaveBeatz, Olbeats y Avram. No hay capturas que permitan
identificar y evaluar por separado el canal UC9_V3H6Mv2BXbgVIT9O7yDw.
Las cifras siguientes corresponden a las capturas, no a una consulta en vivo.

| Canal | Muestra visible | Lectura útil |
|---|---|---|
| RaveWaveBeatz | Seis videos recientes con 8–32 vistas, marcados «hace 5 m»; HIGH IN AMSTERDAM tiene 32 vistas y fecha 20 de mayo de 2026 en su descripción | Títulos coherentes Makar x Deep House; varios planos repetidos, bandas laterales y algunos subtítulos incrustados |
| Olbeats | 2,64 mil suscriptores; seis recientes: 48–49 vistas a las 3 horas, 1,5 mil a los 4 días, 2,2 mil a los 7 días, 673 a los 10 días, 794 a los 13 días y 1,3 mil a las dos semanas | Escenas cinematográficas variadas y marca pequeña; combina Makar, Morad y Deep House |
| Avram | 12,9 mil suscriptores; recientes de 1,9–3,2 mil vistas a los 6–11 días; populares de 116–483 mil a los 9 meses–2 años | Conviven retratos del artista, escenas nocturnas y colores intensos; títulos centrados en Makar / House / Deep House |

No comparar estas vistas como si las publicaciones tuvieran la misma edad o audiencia.
No hay CTR, impresiones, retención ni historial de cambios. No se puede concluir que
una miniatura causó más vistas. Dos competidores son referencias creativas, una muestra
insuficiente para afirmar una regla general del mercado o estimar demanda de keywords.
La conexión gratuita de vidIQ solo mostró @matiasperree, no el canal objetivo.

## Dirección recomendada

- Identidad principal: Makar, House y Deep House. Escribir **Makar**, como en las capturas.
- Afro House es una variante musical cuando el beat realmente corresponde; no usarlo como
  sinónimo de Deep House ni de Afrobeats. Morad se agrega solo cuando describe el beat.
- Conservar escenas del artista y estética cinematográfica. Elegir un sujeto legible, variar
  escenas entre publicaciones y evitar subtítulos accidentales o palabras enormes del clip.
- Las bandas laterales también aparecen en las referencias: no hay evidencia para atribuirles
  el bajo rendimiento. Si existe un original horizontal de calidad, priorizarlo; evitar
  recortes agresivos que corten caras o deformen la imagen.
- Miniaturas sin título superpuesto por defecto. Evitar varias publicaciones consecutivas de
  la misma moto/pareja. Usar material que el usuario pueda reutilizar; esta revisión no verifica permisos.
- El video usa el beat como audio y el material del artista como fondo, con el audio original
  del clip silenciado. Fragmentos iniciales propuestos: 6–10 segundos, ajustables al material.

## Títulos

Base compatible con toda la selección House:

`(FREE) Makar x House Type Beat - "{name}"`

Para una selección comprobada de Deep House, preferir:

`(FREE) Makar x Deep House Type Beat - "{name}"`

Variantes editoriales, elegidas por sonido y no rotadas indiscriminadamente:

- `(FREE) Makar x Afro House Type Beat - "{name}"`
- `(FREE) Makar x Morad Type Beat - "{name}" | Deep House`
- `(FREE) Makar Type Beat - "{name}" | Melodic House`

Ejemplos usando nombres existentes de las capturas: `(FREE) Makar x Deep House Type Beat - "OZONE"`
y `(FREE) Makar x Deep House Type Beat - "BACCARA"`. Son ejemplos de formato, no nuevas
publicaciones ni una indicación de volver a subir esos beats.
No añadir año, artistas o FREE FOR PROFIT automáticamente. La licencia visible permite
uso gratuito no comercial, no «free for profit».

## Descripción propuesta

La ficha publicada está en `ravewavebeatz.channel.json`. Usa `{name}`, `{url}` y `{style}`
(modo `house_v1`). La versión publicada quita los dos enlaces de wyrebeats.vercel.app (404). El enlace debe ser el del beat de cada publicación:
el enlace corto cpDTrW de HIGH IN AMSTERDAM no se reutiliza para todo el catálogo.

```text
Makar x House Type Beat - "{name}"
💰 Purchase / Download this beat: {url}

Melodic house instrumental produced by RaveWaveBeatz.

⬇️ Free demos: https://wyrebeats.vercel.app/free
🛒 Website: https://wyrebeats.vercel.app/
📸 Instagram: https://instagram.com/wyrebeats

FREE FOR NON-PROFIT USE ONLY.
You may use this beat for non-profit releases on YouTube or SoundCloud.
Required credit: "Prod. RaveWaveBeatz".
If another producer is listed on the beat, credit them too.
A license is required for Spotify, Apple Music and other commercial releases.
Do not register this beat or a song using it with Content ID.

All rights reserved © RaveWaveBeatz.

#MakarTypeBeat #HouseTypeBeat #RaveWaveBeatz
```

Basada en los datos y condiciones del propio canal mostrados en la captura 2. Enlaces
transcritos, no comprobados en vivo. Se omiten las ofertas por cantidad hasta comprobar
que siguen vigentes para los beats seleccionados. Se quita el bloque «Ignore Tags» y
la referencia a 2025; las etiquetas van en su campo de metadata.
Agregar BPM, tonalidad y capítulos únicamente si son datos reales del beat. La plantilla
SEO genérica no sustituye `{bpm}` ni `{key}`: no dejarlos como texto literal.

Etiquetas base propuestas, sin volumen ni puntuaciones inventadas:

`makar type beat, makar beat, makar instrumental, house type beat, deep house type beat,
house instrumental, deep house instrumental, melodic house type beat, club type beat,
free makar type beat, free house type beat, ravewavebeatz`

Para Afro House, sustituir las etiquetas Deep House por `afro house type beat` y
`afro house instrumental`. No añadir Avram, Olbeats o artistas que no describan el audio.
El borrador común usa solo las etiquetas amplias de House; las variantes quedan para
una selección musical comprobada.

## Horario y evaluación

Cuatro publicaciones por semana, pedido del usuario: **martes, jueves, viernes y domingo,
15:00 Argentina (UTC−3)** (slots weekday 1, 3, 4 y 6; 0 = lunes). Cadencia operativa, no un
mejor horario demostrado por Analytics. El worker sube con anticipación (margen de 14 días).
Primera revisión tras ocho publicaciones (dos semanas): comparar vistas a igual edad (7 días),
impresiones, CTR y duración media cuando haya acceso a Studio. Cambiar una variable por vez.

## Estado operativo (2026-11-03)

Ficha publicada: `docs/ravewavebeatz.channel.json` es copia de lo que quedó en la config remota.

- **Identidad:** página pública @RaveWaveBeatz → `UC9_V3H6Mv2BXbgVIT9O7yDw`; el OAuth del usuario
  devolvió el mismo canal (título RaveWaveBeatz). Secretos `BEAT_CHANNEL_ID_RAVEWAVEBEATZ` y
  `BEAT_YT_TOKEN_JSON_RAVEWAVEBEATZ` cargados en `kit-weekly`; slug agregado a `BEAT_CHANNELS`
  conservando ey-mat, lovesickk, matwyresoul y mattwyyre.
- **Catálogo:** no existe tienda RaveWaveBeatz en BeatStars; los videos del canal enlazan a la
  tienda de matwyre (`bsta.rs/FspSKH` → matwyre). Se usa el catálogo compartido (1.147 tracks).
  Filtro: las 8 etiquetas del borrador + `melodic house`, `melodic deep house`, `club house`
  → 68 elegibles. No se agregan `afro` / `afrobeat` (Afrobeats) ni `reggaeton house`.
- **Título:** `seo.title_mode=house_v1` (`core/beat_house_seo.py`): `(FREE) Makar x {style} Type
  Beat - "{name}"`. `{style}` = Afro House con etiqueta afro house; si no, Deep House con
  etiqueta deep house / melodic deep house; si no, House. Son etiquetas del productor, no
  análisis del audio. En el catálogo: 41 Deep House, 21 House, 6 Afro House; 39–55 caracteres.
  Las etiquetas SEO suman las de la variante; máximo 220 caracteres.
- **Descripción:** borrador sin los enlaces `wyrebeats.vercel.app` (`/free` y `/` devolvían 404 el
  2026-11-03); Instagram responde. `{url}` = enlace corto propio de cada beat; comprobados tres
  (`bsta.rs/...` → mismo ID). Licencia no comercial y créditos sin cambios.
- **Fondos:** el original (4K HEVC, 154,6 s, 30 fps, 295,8 MiB) es un lyric video que repite su
  primera mitad, con subtítulos y palabras superpuestas. Se conserva intacto. En
  `contenido/canales/ravewavebeatz/fondos`: 6 fragmentos únicos 1080p H.264 sin audio
  (6,1–10,8 s, 23 MB en total), zoom 88 % alineado arriba para dejar fuera los subtítulos inferiores,
  cortados en cambios de escena y revisados cuadro a cuadro (0,25–0,5 s) sin texto superpuesto.
- **Miniaturas:** 9 de las 14 JPG sin texto incrustado + la escena de calle al sol con el
  subtítulo recortado = 10, ordenadas para alternar escenas (rotación LRU por nombre).
  Excluidas por texto: números 2 («AND»), 5 y 14 (subtítulos) y 12 («I JUST»).
- **Muestra local:** VELVET, 2:17, 6 fondos en loop sin descartes, única pista de audio = beat,
  miniatura sin texto. El FFmpeg 7.1 local informa `avg_frame_rate 6300/209` también con los
  fondos de ey mat, así que solo para esta muestra se relajó el chequeo; el worker usa el FFmpeg de Ubuntu.
- **Actions:** dry-run del canal en verde: planned=8, eligible=2,
  failed/blocked/orphan/unknown/calendar_unavailable=0.

Pendiente de observar: el nombre «GYATT house» (título de catálogo «GYATT house type beat»)
y beats con el mismo nombre que subidas manuales previas del canal (MOOD, NOCHE); el worker
solo conoce su propio historial. No se eligen en las primeras ocho fechas simuladas.
