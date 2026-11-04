# Kiezah — House / Club (2026-11-03)

## Configuración

Canal verificado por OAuth y consulta pública de `@Kiezahhouse`: Kiezah,
`UCcgj7ZzsuADHGg4qcyYe2Kw`. Credenciales enviadas directamente a GitHub Secrets
de `kit-weekly`, por slug `kiezah`; no se guardó el token en disco.

Catálogo público de matwyre: 1.147 beats, 70 elegibles mediante etiquetas exactas.
House, Afro House, Club Banger, Deep House, Melodic House y EDM, con variantes
presentes como melodic deep house, latin house, emotional house y reggaeton house.
No entra un beat solo por Makar, afrobeat, dancehall o jersey club. Los tres beats
con tag EDM ya entran por otras etiquetas. No se clasifica el audio.
Historial por canal existente: compartir beats con RaveWaveBeatz está permitido.

27 JPG/JFIF de `/typebeat local/canales/house beats by matwyre/fondos` verificados
con Pillow y copiados byte por byte a `contenido/canales/kiezah/fondos`.
Originales intactos; dos ejemplos inspeccionados visualmente. Imagen fija completa
en 16:9 con bandas negras, sin texto superpuesto; miniatura automática del video.

## Cadencia y títulos

Pedido del usuario: cada dos días, sin días fijos. `interval_schedule` guarda
`days=2` y una fecha base estable `2026-11-05T15:00:00-03:00`.
Hora asumida: 15:00 Argentina. Próximas fechas base: 5, 7, 9, 11, 13, 15 y 17/11.
La fecha base no se reinicia con cada corrida. Una fecha ocupada en YouTube se
omite sin mover la cadencia restante; fallos no provocan publicaciones de recuperación.
La preparación/subida anticipada mantiene el escalonado de 2–4 días y cupo compartido.
Horario editable en Mis canales → Cambiar. El editor avanzado conserva el intervalo.
Los demás canales conservan sus días semanales.

Referencia: capturas del usuario de su canal y Klein Beats (el nombre visible,
aunque en el audio se mencionó Claim Beats). Se adapta género + nombre real +
instrumental, sin copiar nombres, imágenes o atribuir causalidad a las vistas.
La búsqueda web no devolvió resultados útiles del canal; la referencia son las capturas.
Sin llamadas pagas a vidIQ ni puntuaciones de rendimiento inventadas.

Modo `club_v1`, separado del `house_v1` de RaveWaveBeatz: estilos por etiquetas
reales, incluyendo Melodic House y Club Banger, sin artista objetivo Makar.
Tres estructuras estables por ID, con alternativa al repetir dentro del mismo canal.
Ejemplos de snapshots del catálogo:

- `[FREE] House Instrumental - "Real one"`
- `[FREE] Deep House Type Beat - "Young Blood"`
- `[FREE] Afro House Instrumental - "Fuga"`

Descripción basada en la aportada: crédito MatWyre, coproductores, uso no comercial,
licencia para distribución comercial y prohibición Content ID. Sin listas de keywords
ajenos. Enlace individual `{url}` resuelto por el worker; tienda BeatStars.
Comprobación HTTP: `wyrebeats.vercel.app/` y `/free` devuelven 404, tienda 200.
Free Demo / Beat Preview apunta a la ficha del beat; no se afirma que exista un
archivo demo descargable para todos los beats.

## Verificación y estado operativo

70 snapshots completos validados, títulos hasta 100 caracteres, etiquetas acotadas.
Simulación: siete fechas cada dos días, sin mutar el estado de producción.
Regresión Beats: 397 pruebas OK, dos omitidas. Control del worker: 335 OK, dos omitidas.
Incluye intervalos, reinicios, meses/años, zona horaria, fechas ocupadas, replanificación,
historial por canal y compatibilidad de los modos SEO anteriores.
Pruebas del editor: 43 OK, y 24 de guardado en nube OK; 16 repetidas tras ajustar
el test a la ficha activa. Sin errores pendientes.

Registro y config remotos activados por CAS y releídos; otros seis canales
conservados. `kiezah` agregado a `BEAT_CHANNELS`, secretos por slug comprobados.
Se esperó el cierre de las corridas anteriores antes de cargar el calendario nuevo:
el worker anterior no admite una lista semanal vacía.

Prueba remota `41760970327`, intento 2: success, dry-run, planned=7, eligible=1,
failed/blocked/orphan/unknown/expired/calendar_unavailable=0, uploaded=0.
335 pruebas del worker aprobadas (dos omitidas). El intento 1 y una lectura local
previa fallaron por `remote_schema_error` de BeatStars; otro sondeo dio
`request_failed`. El reintento completo leyó el catálogo en vivo correctamente.
Simulación local con catálogo de la primera lectura y Dropbox real: planned=7,
eligible=1, failed=0. Las simulaciones no crean reservas ni suben videos.

No se hizo una subida real ni se verificó `videos.insert` en esta fase. Automatización
activa para el cron normal del 4/11 a las 19:00 Argentina; primera publicación prevista
5/11 a las 15:00, sujeta a calendario de YouTube, cupo compartido y subida exitosa.
No se alteró el historial ni el calendario de otros canales.


## Prueba privada real autorizada (2026-11-03)

Usuario pidió subir una prueba y autorizó explícitamente una única subida adicional
al agotarse el contador interno (10 reservas heredadas). No se borraron reservas ni
se cambió el límite diario. `PrivatePilotBudget` admite un permiso separado, de un
solo uso, ligado al canal, día Pacific y corrida de GitHub; solo en piloto privado.
Permiso de `41762124991` consumido y releído. Contador normal: límite 10, reservas 10.
Sin permiso, el resto de los canales y pilotos conserva el bloqueo habitual. Un
bloqueo real de YouTube nunca se salta. Tests cubren consumo único, carrera entre
workers, respuesta perdida, canal/día/corrida incorrectos y cooldown de YouTube.

Corrida real `41762124991`: success, private_pilot=true, planned=7, eligible=1,
uploaded=1, failed/orphan/unknown/blocked/calendar_unavailable=0. 340 tests del worker
aprobados (dos omitidos). Beat `TK18104778`, Freedom:
`[FREE] Deep House Type Beat - "Freedom"`. Imagen `kiezah/fondos/image_01.jfif`.
Video: https://www.youtube.com/watch?v=MhnAtBKyNM0
Recibo remoto confirmado como uploaded / private_pilot. La inserción se hizo con
privacyStatus=private y sin publishAt; no se afirma una lectura autenticada posterior
de videos.list. No se reintentó una inserción ni se hicieron otras subidas.

El piloto usa el trabajo del primer slot (5/11 15:00), que queda consumido como prueba
privada; no se publicará automáticamente. Los seis trabajos restantes conservan
7, 9, 11, 13, 15 y 17/11 a las 15:00 Argentina. La próxima publicación automática
prevista pasa al 7/11, sujeta a la subida y al cupo compartido.


## Títulos con estructura habitual y tags por beat (2026-11-03)

Preferencia aclarada por el usuario: conservar la forma de los títulos anteriores,
pero variar los géneros y las etiquetas de YouTube según los tags reales de cada
beat descargado de BeatStars. Esta sección reemplaza el formato `club_v1` para
las publicaciones futuras. `club_v1` permanece intacto para validar el piloto guardado.

Modo actual `club_v2`: `[FREE] {style} Type Beat - "{name}" | {detail}`.
Nombre en mayúsculas como en las capturas. Club Banger o Club abre la combinación
solo si aparece en los tags; Afro/Deep/Melodic/Latin House/EDM dependen del beat.
Con tres géneros, el tercero va después de la barra. Si solo hay uno o dos,
el cierre es el género real + Instrumental. No se alterna a título con nombre primero.
Repeticiones mantienen el marco y pueden rotar el orden de tags.

Ejemplo con tags club banger + afro house + deep house:
`[FREE] Club Banger x Afro House Type Beat - "FREEDOM" | Deep House Type Beat`
Es una demostración de la regla, no los tags atribuidos al beat real Freedom.
Ejemplos reales de la cola:
- `[FREE] Deep House x Latin House Type Beat - "DIVINE" | Latin House Instrumental`
- `[FREE] Club Banger x Melodic Deep House Type Beat - "OASIS" | Melodic Deep House Instrumental`

Tags de YouTube: variantes type beat/instrumental de los géneros presentes, tags
originales relacionados y etiquetas genéricas/marca. No se copia Makar ni artistas
ajenos. Quitado `club instrumental` fijo, para no asignarlo a todos los beats.
Títulos <=100 caracteres, tags <=500 contando comillas implícitas por espacios.

Config y plantillas de registro remotas actualizadas por CAS y releídas. Seis
pendientes todavía sin snapshot SEO: usarán el modo nuevo al prepararse. Estado y
revisión de estado idénticos antes/después: sin alterar historial, reservas, piloto
privado, horarios o los otros canales. No se editó el video ya subido en YouTube.

Verificación: 70 snapshots completos del catálogo real, 44 pruebas SEO específicas
y 343 pruebas del worker aprobadas (dos omitidas). Código publicado, sin corridas
reales ni subidas adicionales en este ajuste.
