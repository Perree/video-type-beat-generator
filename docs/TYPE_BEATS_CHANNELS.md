# Canales de Beats: conexiones independientes y alternancia visual

Cada slug de BEAT_CHANNELS usa el Environment `type-beats-<slug>`.
El workflow y su verificación administrativa resuelven el mismo nombre.
El script `scripts/beat_secrets_sync.py --channel "<nombre>" --slug <slug>`
carga únicamente la autorización de ese canal en su Environment.
Una lectura fallida o inválida de BEAT_CHANNELS aborta sin reemplazar la lista;
un fallo al cargar secretos no incorpora el canal a esa lista.

## Migración del setup anterior

El setup anterior de Beats usaba `kit-weekly`. Antes de ejecutar el workflow
actualizado, preparar también el canal existente en `type-beats-<slug>`.
No eliminar ni modificar los secretos de `kit-weekly`: Loopkits los conserva.
No activar producción hasta verificar los nuevos Environments.

En cada Environment de Beats configurar:

- BEAT_CHANNEL_ID: nombre/ID interno en la configuración.
- BEAT_YT_TOKEN_JSON: token del canal correspondiente.
- BEAT_DROPBOX_APP_KEY y BEAT_DROPBOX_REFRESH_TOKEN: la misma app autorizada
  para todos los canales, conservando el estado compartido bajo /type-beats/.
- BEAT_TELEGRAM_TOKEN y BEAT_TELEGRAM_CHAT_ID: notificaciones.
- BEAT_NOTION_TOKEN y BEAT_NOTION_PAGE_ID: opcionales.

Los valores Dropbox/Telegram del setup anterior pueden reutilizarse, copiándolos
con los nombres BEAT_* a cada Environment; no reemplazar los secretos KIT_*.
Cada Environment debe permitir exclusivamente la rama master.
La lista BEAT_CHANNELS debe incluir los slugs actuales y los nuevos.
La conexión local por sí sola no carga los secretos en GitHub.

## Alternancia

El panel de Beats ofrece `Alternar imagen y video` (`visual.mode=alternate`).
El orden de los slots semanales define una secuencia continua entre semanas,
independiente del orden de ejecución y del catálogo. Los slots vacíos siguen
contando: la alternancia corresponde al calendario, no al número de uploads exitosos.
El modo se congela por job antes de renderizar; reintentos y respuestas CAS perdidas
conservan esa elección. Cambiar horarios afecta únicamente jobs sin modo congelado.
No modifica los modos image/video existentes.

`visual.plain_image=true` usa imágenes simples sin el título superpuesto.
La miniatura puede ser automática o un archivo local/Dropbox. En la nube, usar Dropbox.
En video con miniatura automática y una carpeta de imágenes del género, las imágenes
rotan como miniaturas. Un archivo personalizado permite elegir una miniatura específica.

## Preparación de mattwyyre

Alta local pausada: martes, jueves y sábados a las 10:00 Buenos Aires.
Perfil compartido matwyre; análisis público de 1.138 tracks y 132 coincidencias únicas
con los tags solicitados y variantes cercanas. No agrega house, pop o R&B al filtro:
un track puede tener esos tags adicionales y seguir siendo elegible si tiene reggaeton,
latin, afrobeat u otro tag permitido. La selección exige coincidencia de tags completos.

La configuración y los informes están bajo config/ y tokens/, excluidos de Git.
La simulación de 14 días es local con estado vacío y activación temporal en memoria;
no reserva publicaciones ni consume cuota real.

Pendiente: recursos visuales en Dropbox, elección de miniatura, ID real de YouTube
(confirmado al autorizar), conexión OAuth, nuevos Environments, publicación de config
por CAS conservando el estado vigente, dry-run y piloto antes de activar producción.
El alta no escribe en Dropbox ni cambia Actions remoto.
