# Lovesickk: pruebas de títulos por beat

## Funcionamiento

Modo optativo `rnb_test_v1`, exclusivo del perfil SEO de Lovesickk. Lee los tags
que ya obtiene el catálogo de BeatStars y ofrece como máximo cuatro familias:

- `simple`: `(FREE) R&B Type Beat - "Nombre"` (Soul si solo hay tags Soul).
- `detail`: título simple más Acoustic, Guitar, Piano, Sad, Emotional, Smooth
  o Dark, cuando exista el tag correspondiente.
- `crossover`: Soul + R&B, Trap Soul + R&B, Drill + R&B o Trap + R&B,
  únicamente cuando los tags respalden la combinación. Soul no implica Trap Soul.
- `artists`: uno o dos artistas identificados por tags exactos. Diccionario:
  PARTYNEXTDOOR, Che Ecru, Drake, Brent Faiyaz, Bryson Tiller, Kehlani, Aaliyah,
  Karri, SZA, Summer Walker y Aftertheparty. No se asignan por miniatura o nombre.

La asignación usa SHA-256 de versión + ID del beat entre sus familias compatibles.
Es reproducible, no garantiza cupos iguales y no cambia al descargar o reintentar.
La reserva guarda `seo_snapshot.experiment` con versión, familia, método y tags
de origen; título, descripción y tags quedan protegidos por el hash existente.
No se pasan campos del experimento a la llamada de subida de YouTube.

Los snapshots anteriores siguen siendo válidos. Publicaciones y programaciones
ya realizadas conservan sus títulos. Los próximos trabajos todavía sin snapshot
usan el nuevo perfil. No se cambia el calendario, audio, imágenes ni otros canales.

La descripción mantiene enlace, promoción, licencia y contacto propios del canal.
Agrega un párrafo breve basado en los tags y BPM/tono solo si constan en el título
de origen. No inventa valores ni usa licencias o contactos de las referencias.

## Medición

Después de una corrida real, el worker recoge vistas, likes y comentarios de los
videos públicos de este experimento a partir de los días 7 y 28. La referencia de
edad es la fecha de publicación que devuelve YouTube, no la fecha de subida privada.
Se verifica canal y título actual antes de guardar los contadores.

Los registros quedan en `jobs[job_id].title_metrics['7'/'28']` del estado de Dropbox.
Cada muestra incluye momento de observación, edad real, familia y título. Las
muestras tomadas con un día o más de demora llevan `late: true`: son acumulados
observados tarde, no una reconstrucción histórica del día 7/28.

Contadores omitidos por YouTube permanecen en `null`. Impresiones, CTR, tiempo de
reproducción y vistas desde búsqueda quedan en `null`: falta integrar YouTube
Analytics con permisos adecuados para obtenerlos. No se amplían los permisos
actuales ni se presenta el experimento como una prueba de impresiones.

La lectura es por lotes de hasta 50 IDs y la escritura usa CAS. Los reintentos no
sobrescriben muestras ya guardadas. Una falla de medición no bloquea publicaciones;
el resumen del worker indica `title_metrics_unavailable`. Dry-run no recoge ni
escribe métricas. Otros modos SEO no participan.

No se elige un ganador automáticamente. Comparar la misma ventana, separar
muestras tardías y estratificar por tags/familias disponibles; los beats distintos
y la distinta disponibilidad de familias impiden interpretar esto como un A/B
controlado del mismo video.

## Validación local

- Siete pruebas específicas: compatibilidad, límites, manipulación de snapshot,
  asignación, reintento CAS/respuesta perdida, datos ausentes, privacidad,
  identidad, cambios externos de título y ventanas de medición.
- Control del worker: 359 pruebas, aprobado con dos omisiones opcionales.
- Catálogo público: 1.148 beats, 90 elegibles para el canal, todos los snapshots
  reconstruidos y validados. Asignación: 34 simple, 28 detalle, 13 cruce y 15 artistas.

Referencias originales: `docs/LOVESICKK_SEO_REFERENCIAS.md`.

## Activación verificada el 2026-11-06

- Código publicado en master (`6cfdc8c`); perfil y plantillas de Lovesickk escritos
  por CAS y releídos. Otros canales y el estado de trabajos quedaron intactos.
- Simulación remota [42265734697](https://github.com/Perree/video-type-beat-generator/actions/runs/42265734697)
  exitosa sobre ese commit; control remoto de 359 pruebas aprobado. El worker
  devolvió eligible=0, planned=0, failed=0 y uploaded=0. Verifica carga/configuración,
  pero no un nuevo render, una subida real ni una captura real de métricas.
- Próximos pendientes revisados localmente: Away (12/11, detalle acústico), Noir
  (14/11, simple), Happier (17/11, simple), Nothing of You (19/11, detalle guitarra).
  Publicaciones previstas a las 18:00 Argentina, sujetas al procesamiento normal.
  La asignación es por ID; los primeros cuatro no cubren necesariamente las cuatro
  familias. En todo el catálogo sí están representadas las cuatro.
- Videos ya subidos, incluidos los programados para 7/11 y 10/11, conservan títulos.
- API de contadores: [videos.list](https://developers.google.com/youtube/v3/docs/videos/list).
