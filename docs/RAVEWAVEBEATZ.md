# RaveWaveBeatz — preparación del canal

Fecha: 2026-11-03. Investigación y propuesta preparadas; automatización pendiente de activación.

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

La plantilla operativa está en `ravewavebeatz.channel.draft.json`. Usa únicamente `{name}`
y `{url}`, que el motor SEO actual sustituye. El enlace debe ser el del beat de cada publicación:
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

Dos publicaciones por semana: **martes y viernes, 15:00 Argentina (UTC−3)**.
Es una hipótesis operativa para mantener una cadencia sostenible, no un mejor horario
demostrado por Analytics. Distribuir las subidas con el mecanismo existente de 2–4 días.
Primera revisión tras ocho publicaciones / cuatro semanas desde el inicio real:
comparar vistas a igual edad (7 días), impresiones, CTR y duración media cuando haya
acceso a Studio. Cambiar una variable por vez; la muestra inicial seguirá siendo pequeña.

## Material encontrado y preparación pendiente

- Dropbox, ubicación actual: `/AudioVisual Stuff/Type Beats - STUFF/RAVEBEATZ`.
  Contiene 14 JPG `Beat-Miiniaturas*.jpg` y `VIDEOS/video stock - RAVE BEATZ.mp4`.
  Se inspeccionaron visualmente tres JPG: base, número 7 y número 14; no todos los archivos.
- El video mide 310.149.077 bytes (295,8 MiB). Supera `MAX_VIDEO_BYTES`, 256 MiB:
  no sirve directamente para el worker; necesita una copia comprimida o fragmentos más chicos.
  No se verificaron duración ni contenido completo del video.
- El proyecto conserva otra copia del video y una imagen tropical local. Las miniaturas de
  Dropbox son una referencia más directa para el estilo de las capturas.
- El perfil Manual local de RaveBeatz aún tiene valores genéricos, incluido «Free for Profit»;
  no debe usarse como plantilla final de este canal.
- El registro y la configuración sincronizada de automatización todavía no contienen RaveWaveBeatz.

El JSON adjunto es **un canal pausado para revisar**, no la configuración remota completa.
Apunta a carpetas nuevas propuestas bajo `contenido/canales/ravewavebeatz`; esas carpetas
todavía no fueron creadas ni llenadas. Antes de incorporarlo al worker:

1. Confirmar el ID canónico de @RaveWaveBeatz mediante la autorización de su cuenta de YouTube;
   no asignar el ID del enlace sin identificarlo. Guardar credenciales en el entorno propio.
2. Preparar el video dentro del límite y seleccionar miniaturas distintas en las carpetas propuestas.
3. Comprobar el catálogo de BeatStars: el filtro actual compara etiquetas exactas sin distinguir
   mayúsculas, con OR. No busca por título, no clasifica audio y no exige todas las etiquetas.
4. Incorporar la ficha al registro y a la configuración de Beats, conservando los demás canales.
5. Simular calendario/selección, renderizar una muestra y revisar título, enlace, audio y miniatura.
6. Activar solo al resolver identidad, credenciales y material. Aún no hay videos programados.
