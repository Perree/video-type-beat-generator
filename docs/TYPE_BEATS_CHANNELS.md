# Canales de Beats: autorizaciones independientes y servicios existentes

Beats conserva el Environment `kit-weekly`, donde ya están configurados Dropbox y Telegram.
Cada canal usa secretos de YouTube propios, seleccionados por su slug de BEAT_CHANNELS:

- `BEAT_CHANNEL_ID_<SLUG>`: nombre/ID interno del canal.
- `BEAT_YT_TOKEN_JSON_<SLUG>`: autorización OAuth verificada de ese canal.

El sufijo es el slug en mayúsculas, sustituyendo guiones por guiones bajos.
Por ejemplo, ey-mat usa EY_MAT y mattwyyre usa MATTWYYRE.
El workflow solo entrega al proceso los valores del canal de esa fila.
La cuenta OAuth se compara con youtube_channel_id remoto antes de renderizar/subir.

Dropbox y Telegram conservan los secretos KIT_DROPBOX_* y KIT_TELEGRAM_* existentes.
No se modifican módulos, secretos, workflows ni estados de Loopkits o marca personal.
Esta disposición sustituye la propuesta anterior de Environments type-beats-<slug>:
no requiere copiar los valores de servicios compartidos ni volver a configurar el bot.

## Alta y pruebas

`scripts/beat_secrets_sync.py --channel "<nombre>" --slug <slug>` carga solo los dos
secretos de Beats de ese slug en kit-weekly. La lista BEAT_CHANNELS conserva los slugs
existentes y rechaza lecturas fallidas o JSON inválido. No incorpora el canal si falla
la carga de su autorización. Los tokens viajan por stdin y no se imprimen.
El Environment debe permitir exclusivamente la rama master.

workflow_dispatch permite `channel=<slug>` para probar únicamente un canal:
`dry_run=true` simula; `dry_run=false, private_pilot=true` intenta un video privado.
Un channel vacío recorre la lista completa, como el cron diario.
El piloto debe dirigirse únicamente al canal nuevo para no generar otro video en el actual.
Solo habilitar el canal después de verificar destino, recursos, dry-run y piloto.

## Alternancia y miniaturas

El panel ofrece `Alternar imagen y video` (`visual.mode=alternate`).
Los slots definen una secuencia continua entre semanas; los slots vacíos también cuentan.
El modo se congela por job antes del render. Reintentos y respuestas CAS perdidas
conservan la elección. Cambios posteriores del calendario afectan jobs no congelados.
`visual.plain_image=true` conserva la imagen sin título superpuesto.
En modo video, thumbnail_source=auto con una carpeta de imágenes del género usa
esas imágenes como miniaturas rotativas. Un archivo personalizado permite elegir otra.
Beats acepta JPEG, JFIF, PNG y WebP, validando su contenido al decodificar.

## mattwyyre

Canal de YouTube @mattwyyre verificado mediante OAuth y asociado a su ID real.
Martes, jueves y sábados a las 10:00 Buenos Aires, alternando imagen y video.
Selección: 16 tags solicitados y variantes cercanas; análisis público de 1.138 tracks
con 132 coincidencias únicas. House, pop y R&B no se agregaron al filtro; un track
con esos tags adicionales puede entrar si también tiene un tag permitido.

Carpetas asignadas localmente: 28 imágenes y 4 videos compatibles por extensión/tamaño.
La configuración remota incluye el canal pausado, preservando el canal actual y su estado.
Rutas, links, snapshots e informes privados permanecen en config/ y tokens/, fuera de Git.
La conexión OAuth por sí sola no habilita cron: faltan los secretos seleccionados por slug,
publicar el workflow, dry-run y piloto. La activación se registra separadamente.

## Título y descripción modelo del canal

Para mattwyyre, use_channel_templates=true compila title_template y description_template
que se guardan en Gestionar canales. El perfil SEO enviado al worker conserva ese modelo,
rellena {name} con el nombre limpio del beat y usa {beatstars_url} como enlace del track.
La configuración de otros canales queda intacta. Para cambios posteriores, abrir/guardar
Automatizaciones de Beats y publicar la configuración en Dropbox como antes.

Cambiar un modelo no reemplaza automáticamente snapshots SEO ya reservados. Una renovación
explícita, con el canal pausado y sin render activo, archiva las fichas de jobs pendientes
que no tengan intentos. No se eliminan reservas, cuotas ni historial de subidas.
Para videos ya subidos, la edición necesita un scope de YouTube admitido por videos.update;
youtube.upload/youtube.readonly no alcanzan. Editarlos en Studio es una alternativa manual.
