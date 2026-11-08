# IslaBeats — automatización cada dos días

Destino: https://www.youtube.com/channel/UCPDszmzMcBNuR2h1ReIRupg
Perfil: `docs/islabeatz.channel.json`. Slug propio: `islabeatz`.

- Base copiada de la configuración activa de WyreLatinBeatz el 8/11/2026.
- Cada dos días a las 15:00 Argentina, misma ancla del 8/11 y escalonado de 2–4 días.
- Mismos filtros latinos y descripción comercial de MatWyre. Marca del canal en tags: IslaBeats.
- Referencias aportadas: capturas de IslaBeats y DysmoBeats (`@dysmoprod`).
  Imágenes centradas con negro lateral, sin texto; artistas primero, nombre entre comillas
  y cierre `| Género Type Beat` (con emoción cuando corresponde).
- Se usa el modo optativo `latin_dysmo_v1`: artistas, género y emoción salen de los tags
  reales del catálogo de descarga; conserva el nombre real de cada beat. No fuerza
  Bad Bunny x Mora a todos los títulos. Sin artistas etiquetados, usa el género.
- Los bloques TAGS (IGNORE), contactos y marcas SOLD de DysmoBeats no se copian.
  Las cifras de vistas en las capturas no prueban el efecto de los metadatos.

## Imágenes y validación

17 JFIF de `images/islabaetz/Principal`, con coincidencias visuales en las capturas.
Copiadas sin modificar a
`/Soft Projects/Type Beat Generator/contenido/canales/islabeatz/fondos`.
Cada archivo se descargó de vuelta y se comparó byte por byte; manifiesto privado
con tamaños y SHA-256 en `tokens/islabeatz_assets.json`.

Modo `image`, ajuste `contain`: imagen completa, centrada y sin deformación.
Las bandas dependen de la proporción del original. Miniatura automática de YouTube,
sin carpeta de portadas. Las 17 composiciones 1920×1080 se generaron correctamente.
Vista previa local de 3 segundos con silencio de prueba, H.264/AAC, validada con
FFprobe e inspección visual en `exported_videos/islabeatz-preview/`.

138 beats elegibles del catálogo de 1.151 disponible; todos sus snapshots SEO
generados y revalidados. Ejemplos reales:

- `(FREE) Bad Bunny Type Beat - "New York" | Latin Trap`
- `(FREE) Bad Bunny Type Beat - "Ser" | Emotional Latin Trap`
- `(FREE) Bad Bunny Type Beat - "Emboscada" | Emotional Reggaeton`

17 pruebas y 18 subtests específicos aprobados; control general del worker: 398 pruebas OK (dos omitidas). Simulación contra Dropbox y catálogo
público: planned=7, eligible=1, uploaded=0; failed/orphan/unknown/blocked/budget/
thumbnail_failed/expired/calendar_unavailable=0.

Configuración y registro remotos guardados y activados con control de revisión y
lectura posterior; los otros trece perfiles preservados. No se modificó `main.py`
y se reutilizan la selección y el render existentes. El modo de títulos propio se describe abajo.

## Conexión y activación

OAuth completado y verificado: IslaBeats, `UCPDszmzMcBNuR2h1ReIRupg`.
Credenciales propias guardadas en el entorno kit-weekly; token solo en memoria y
GitHub Secrets. BEAT_CHANNELS ampliado a catorce conservando los trece anteriores.
Configuración y registro activos, releídos. Horario: cada dos días, 15:00 Argentina.

Primera corrida real: https://github.com/Perree/video-type-beat-generator/actions/runs/42494221965
Completada con éxito: planned=7, eligible=2, uploaded=2;
failed/orphan/unknown/blocked/budget/expired/calendar_unavailable/thumbnail_failed=0.
398 pruebas aprobadas también en el servidor, incluidas las pruebas con FFmpeg real.
Recibos de estado Dropbox releídos: ambos con `publication_mode=scheduled` y fondos propios distintos.

- 8/11/2026, 15:00 Argentina: Es tan fina, `gH_XRs4cRxQ`.
  `(FREE) Feid x Tainy Type Beat - "Es tan fina" | Reggaeton`.
- 10/11/2026, 15:00 Argentina: VERTE DE NUEVO, `FkYJK_CIeZI`.
  `(FREE) Reggaeton Type Beat - "VERTE DE NUEVO"` (sin artistas en los tags originales).
- Cinco reservas pendientes: 12, 14, 16, 18 y 20/11 a las 15:00,
  sujetas al escalonado y cupo compartido normales.

Límite de verificación: solicitudes de subida y recibos del worker comprobados;
no se reprodujeron los videos de YouTube ni se releyó su estado por Data API después
de la subida. La simulación anterior no reservó turnos.

La primera autorización se trabó en el receptor local; se reinició el flujo con
un receptor concurrente temporal. No se guardaron tokens locales ni se cambió el
código de OAuth de la aplicación durante este trabajo.

## Ajuste a la competencia (2026-11-08)

Pedido posterior: títulos y tags muy parecidos a las capturas de DysmoBeats.
Modo nuevo `core/beat_latin_dysmo_seo.py`, optativo solo para IslaBeats.
Los modos anteriores siguen validando los snapshots históricos.

Formato con artistas: `(FREE) Bad Bunny x Mora Type Beat - "Nombre" | Sad Dancehall Type Beat`.
La pareja y el estilo son un ejemplo condicionado a esos tags originales; con un
solo artista se muestra uno, y sin artistas se usa el género sin inventarlos.
El nombre del beat sigue siendo el propio; no se toman títulos de canciones ajenas.

Tags siguiendo las búsquedas visibles en la referencia: `mora type beat`,
`type beat mora`, `beat mora`, `bad bunny x mora type beat`, `mora x bad bunny type beat`,
y variantes con género/emoción, siempre condicionadas a las etiquetas del beat.
Máximo 40 tags y 450 caracteres con margen para las comillas de las frases.
Sin marcas de competidores ni SOLD; no se añaden artistas por la imagen del video.
No se interpreta el bloque TAGS (IGNORE) de la captura como etiquetas verificadas de Studio.

138 snapshots reales generados y revalidados; 21 pruebas y siete subtests específicos
aprobados; 402 pruebas del worker OK (dos omisiones opcionales). Código publicado:
`db6c182`. Configuración activa actualizada por CAS y releída; registro compatible.
Calendario, selección, imágenes y otros trece canales conservados.

Comprobación remota en simulación: corrida `42497347567`, completada con éxito.
402 pruebas remotas OK; planned/eligible/uploaded/failed/orphan/unknown/blocked/
expired/calendar_unavailable/thumbnail_failed=0. No había nuevos turnos elegibles;
los 138 snapshots del nuevo modo se comprobaron localmente con el catálogo real.
Los dos videos existentes fueron editados y comprobados mediante lectura posterior
de YouTube: corrida de solo lectura `42498318065`, verified=2, failed=0,
differences=[]. También aprobó las 405 pruebas del worker con FFmpeg real.
La lectura inicial tras la edición del segundo video no coincidió inmediatamente;
la lectura posterior desde el servidor confirmó ambos cambios.

- `gH_XRs4cRxQ`: `(FREE) Feid x Tainy Type Beat - "Es tan fina" | Reggaeton Type Beat`, 21 tags.
- `FkYJK_CIeZI`: `(FREE) Reggaeton Type Beat - "VERTE DE NUEVO"`, nueve tags.

Estado de YouTube completo y descripciones comparados con el respaldo anterior:
idénticos; conservan 8/11 y 10/11 a las 15:00 Argentina. Se sincronizaron solamente
los dos snapshots SEO del estado, conservando el resto exactamente por CAS y lectura
posterior. Snapshots anteriores y comprobantes fuera de Git, en tokens/islabeatz_dysmo_*.
El permiso de edición se usó solo en memoria y no reemplazó el token de subida.

Se añadió comprobación reutilizable de solo lectura en `core/beat_metadata_verify.py`
y la opción manual `verify_metadata` del workflow, publicada en `55e7c36`. Verifica
propietario, título, tags sin depender de su orden y fecha futura. No planifica,
reserva, sube ni modifica videos, estado o configuración.
