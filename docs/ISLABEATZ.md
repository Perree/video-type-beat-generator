# IslaBeats — automatización cada dos días

Destino: https://www.youtube.com/channel/UCPDszmzMcBNuR2h1ReIRupg
Perfil: `docs/islabeatz.channel.json`. Slug propio: `islabeatz`.

- Base copiada de la configuración activa de WyreLatinBeatz el 8/11/2026.
- Cada dos días a las 15:00 Argentina, misma ancla del 8/11 y escalonado de 2–4 días.
- Mismos filtros latinos y descripción comercial de MatWyre. Marca del canal en tags: IslaBeats.
- Referencias aportadas: capturas de IslaBeats y DysmoBeats (`@dysmoprod`).
  Imágenes centradas con negro lateral, sin texto; artistas primero, nombre entre comillas
  y contexto musical al final del título cuando corresponde.
- Se usa el modo existente `latin_v2`: artistas, género y emoción salen de los tags
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
ni fue necesario añadir código: se reutilizan selección, SEO y render existentes.

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
