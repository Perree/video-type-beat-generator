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
