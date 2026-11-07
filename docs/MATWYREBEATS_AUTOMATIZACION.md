# matwyrebeats: automatización

Autorizada por el usuario el 07/11/2026, después de revisar la propuesta SEO.
Ampliación explícita: usar otros tags compatibles y títulos por género cuando
no haya un artista confirmado. No limitar la selección a los pocos tags de artistas.

## Configuración preparada

- Slug `matwyrebeats`; OAuth verificado: `UCrXlloS9FyZ32yaqV32GZjQ`.
- Lunes, miércoles y viernes a las 18:00 Argentina (horario inicial asumido).
- Búfer existente de 14 días, escalonado 2–4 días, cuota compartida existente.
- 24 imágenes de `images/matwyrebeats/Principal`, verificadas y copiadas sin
  alterar sus bytes a la carpeta propia de Dropbox.
- Imagen completa centrada con bandas negras; sin texto agregado; miniatura automática.
- Configuración y registro activos por CAS y releídos tras validación remota.
- BEAT_CHANNELS incluye matwyrebeats conservando los nueve canales anteriores.

## Catálogo y prevención de repeticiones

Catálogo público propio: 1.151 beats al 07/11/2026. El filtro versionado
`selection_tags: ["matwyre:v1"]` identifica 560 por tags reales de sonido,
instrumento, ánimo o artista. Excluye estilos explícitos ajenos como House,
Afro, Reggaeton, Dancehall, Jersey, Pop, Indie y Rock aunque contengan Sad o Guitar.

Cruce conservador contra nombres de los 500 videos del export del usuario:
308 IDs del catálogo coinciden, de los cuales 156 pertenecen al conjunto elegible.
Es una comparación textual, no identificación acústica ni prueba de duplicación.
Sus IDs se guardan en `excluded_track_ids`: no entran al planificador, render ni subida.
La barrera de revisión remota también detecta cambios en estas exclusiones.
El export omite videos de pocas vistas y los nombres pueden cambiar: el cruce
no garantiza descubrir todos los audios publicados antes de esta automatización.

Quedan 404 elegibles: 273 del núcleo melódico/emocional, 98 de R&B/acústico
y 33 de trap. Reparto por déficit 50/30/20 sobre las familias disponibles,
contando las reservas persistidas para conservar estabilidad entre corridas.
Los títulos describen los tags reales: la familia de planificación no se usa
para inventar que un beat es Trap, acústico o de un artista concreto.
El historial propio del worker conserva las barreras de repetición y reservas.

## Metadatos

Modo `matwyre_v1`, implementado en módulos pequeños de `core/`.
Artistas por tags exactos normalizados, incluidas variantes explícitas con año;
si faltan, género/instrumento/ánimo. No hay inferencia de artistas por semejanza.
Dos artistas en título solo cuando ambos están respaldados.

Nombre real de catálogo, con créditos de productor separados cuando están
indicados explícitamente entre paréntesis. Variante buscable, nombre primero
y detalle musical cuando existe; asignación estable por hash del ID del beat.
No se fabrican frases emocionales diferentes del nombre real ni se republica
el mismo audio para comparar títulos. Títulos limitados a 100 caracteres y
tags acotados con las comillas implícitas de YouTube.

Descripción: compra individual primero, contexto por beat, BPM/tono si constan
en el título fuente, créditos originales, condiciones propias, tienda/contacto,
oferta de EP en CABA y hashtags por beat. Se conserva el texto de uso no comercial
y Content ID de los antecedentes propios; no se copian licencias ajenas.
El enlace usa el short link real de BeatStars o el slug individual original del
catálogo. Si no hay un enlace individual válido, no se llama al uploader.

Snapshots registran versión, familia de presentación, tags fuente y repertorio.
Recolección a partir de días 7/28 de vistas, likes y comentarios mediante Data API;
indica observaciones tardías y campos ausentes. No mide CTR, impresiones, retención,
tiempo de reproducción ni ventas; Analytics sigue siendo una integración pendiente.
No elige automáticamente un ganador con métricas incompletas.

## Validación y estado

- Los 404 snapshots reales fueron generados y revalidados localmente.
- Pruebas específicas de selección, familias, planificación, límites, créditos,
  reproducción de snapshots, exclusiones, enlaces y observaciones de métricas.
- Control general del worker aprobado localmente: 375 pruebas (dos omisiones
  opcionales); comprobaciones específicas repetidas tras pulir nombres/títulos.
- Simulación remota `42396922345`: success; planned=6, eligible=1, uploaded=0,
  failed/blocked/unknown/orphan/calendar_unavailable=0. Sin escrituras de publicación.
- Corrida real `42397167599`: success; planned=6, eligible=1, uploaded=1,
  failed/blocked/unknown/orphan/expired/calendar_unavailable/thumbnail_failed/budget=0.
- Los controles remotos aprobaron 375 pruebas (dos omisiones opcionales).
- Configuración de los otros nueve canales conservada en la preparación.
- Secretos nuevos por slug en GitHub; OAuth usado en memoria sin token local.

Referencia editorial: `docs/MATWYREBEATS_PROPUESTA_SEO.md`.

## Primera programación y funcionamiento continuo

Video `O22BXIPrDSE`: `(FREE) Sad Type Beat - "OLVIDARTE"`, beat `TK12208309`.
Recibo de estado confirmado en Dropbox: uploaded, publication_mode=scheduled,
turno 09/11/2026 a las 18:00 Argentina. Solicitud de inserción privada con
publishAt para esa fecha; no es un piloto privado permanente.
Enlace: https://www.youtube.com/watch?v=O22BXIPrDSE

Sus tags de catálogo son juicewrld, sad y sad beat; el título fuente menciona
Milo J Guitar, pero este modo no convierte menciones del título en tags de artista
o instrumento. El título elegido usa únicamente el clima respaldado por los tags.

Imagen propia image_01.jfif. Descarga posterior del origen de Dropbox con hash
idéntico al snapshot y miniatura reproducida con el mismo compositor; inspección
visual del encuadre completo y bandas aprobada. No se reprodujo el video privado
en YouTube ni se releyeron sus metadatos allí en esta sesión: la confirmación de
programación se apoya en la respuesta exitosa de inserción y el recibo persistido.

Cinco pendientes reservados: 11, 13, 16, 18 y 20/11, todos a las 18:00 Argentina.
No están todos subidos: el escalonado existente los procesará cuando corresponda.
El cron diario de GitHub repone la ventana de 14 días y renderiza/sube sin esta PC.
Las futuras subidas dependen de permisos válidos, acceso a fuentes y cupo normal;
no se cambió ni se exceptuó el límite compartido de intentos.

Verificación final: configuración y registro activos, nueve canales anteriores
idénticos a la copia previa, un solo trabajo subido de matwyrebeats y cinco
pendientes. Código y documentación publicados; `main.py` intacto.
