# Worker semanal de loop kits

`scripts/run_kit_weekly.py` corre en GitHub Actions (`.github/workflows/kit-weekly.yml`): domingo 23:00 UTC
(20:00 en Buenos Aires) o a mano con `workflow_dispatch` (inputs `channel` y `dry_run`). Nunca se dispara con
`pull_request`. Con más de un canal, cada uno corre su día: ver "Varios canales" más abajo.

Cada corrida toma el lock de `state.json` (Dropbox), calcula los próximos 3 slots lun/mié/vie 18:00 en
`America/Argentina/Buenos_Aires` y, por slot, corre `run_preview` con un kit distinto. Sube en **privado** con la fecha
propuesta como `publishAt`; si YouTube la rechaza queda `private_pending` y el slot propuesto se guarda igual en el
estado, así una segunda corrida de la misma semana no duplica. Al final manda por Telegram un resumen con los links a
YouTube Studio (o una alerta con el paso que falló) y libera el lock en un `finally`.

Qué kits salen y cómo se arma cada video lo decide `core/kit_week.py`:

- Solo entran los kits de `kits.json` (panel de la app) activos, con link y con carpeta en Dropbox; las carpetas que
  empiezan con `_` y los kits sin audio o sin imágenes quedan afuera. Sin `kits.json` se usan todas las carpetas y el
  link del canal. `kit_preview.dropbox_root` es obligatorio.
- Sale primero el kit que hace más que no se usa. Cada kit hace hasta `cycle_max_videos` (3) videos y descansa
  `cycle_rest_days` (30); entre dos usos pasan al menos `kit_min_gap_days` (7).
- El audio dura entre `target_min_s` y `target_max_s` (135-195 s) y no repite tramos dentro del ciclo del kit.
- `{link}` es el link del kit con `utm_source` y `utm_content` propios del video; nombre y referencias usan el género del kit.
- Un kit que no da un video se saltea y se prueba el siguiente. Si no alcanzan los kits, los horarios que sobran quedan
  sin video y el resumen de Telegram lo avisa (no es un fallo). Con 12 kits, 3 videos por semana y 30 días de descanso
  puede haber una semana incompleta cada tanto: se evita con más kits o con `cycle_rest_days: 28`.
- Renombrar la carpeta de un kit en Dropbox lo convierte en un kit nuevo: hay que actualizar `folder` en `kits.json`.

En la PC, sin variables `KIT_*`, el worker usa `tokens/` y `config/` locales; `--cloud-config` lee la config de Dropbox
aunque exista `config/app_config.json` (así corre el "Probar dry-run" del panel).

- `--dry-run`: elige kits y slots; no toma el lock, no renderiza, no sube y no escribe en Dropbox. Manda un único aviso.
- Sin `config/app_config.json` (está ignorado por git) la config se lee de Dropbox (`KIT_CONFIG_PATH`, por defecto
  `/loop_kits/_automation/config.json`).
- Secretos (solo como `env` del paso del worker): `KIT_YT_CHANNEL`, `KIT_YT_TOKEN_JSON`,
  `KIT_DROPBOX_REFRESH_TOKEN`, `KIT_DROPBOX_APP_KEY`, `KIT_TELEGRAM_TOKEN`, `KIT_TELEGRAM_CHAT_ID`. El
  `client_secret.json` no hace falta en el runner (solo sirve para conectar un canal): si ya cargaste
  `KIT_YT_CLIENT_SECRET_JSON`, borralo.
- El log es público: solo se imprime el paso y el tipo de error, nunca nombres de kits ni mensajes de las librerías.
  En Actions el worker además descarta `stderr`, registra como máscaras los valores sueltos de los secretos JSON y saca
  los secretos del entorno al arrancar, así ffmpeg no los hereda. Smoke: `scripts/smoke_kit_hardening.py`.

Smoke: `py -3 scripts/smoke_kit_weekly.py`.

## Varios canales

Cada canal de loop kits tiene su automatización: config, catálogo, estado y lock propios en Dropbox, y su
Environment en GitHub. Un kit puede estar en el catálogo de varios canales; su ciclo, descanso, nombres y
referencias se cuentan por canal. `core/kit_channel.py` deriva todo del slug del canal (minúsculas, sin tildes,
`a-z0-9` y guiones), así una corrida solo conoce las rutas de su canal:

| | Canal por defecto (el primero) | Otro canal |
|---|---|---|
| Config | `/loop_kits/_automation/config.json` (`KIT_CONFIG_PATH`) | `…/_automation/<slug>/config.json` |
| Catálogo | `/loop_kits/_automation/kits.json` (`KIT_CATALOG_PATH`) | `…/_automation/<slug>/kits.json` |
| Estado | `/loop_kits_state/state.json` (`KIT_STATE_PATH`) | `…/loop_kits_state/<slug>/state.json` |
| Environment | `kit-weekly` | `kit-weekly-<slug>` |

El canal por defecto no cambia nada de lo que ya tenía. Para sumar un canal:

1. En la app, *Loop kits > Configuración de automatización > Crear automatización…* y elegir el canal. Guarda en
   Dropbox su config mínima (carpeta de kits y géneros del canal por defecto, horarios de fábrica y las plantillas
   del canal) y lo deja elegido en el selector de arriba. Marca de la portada, `names`, `art` y demás opcionales no
   se copian: se agregan a mano en la config de ese canal. Después se cargan sus kits y se guarda.
2. `py -3 scripts/kit_secrets_sync.py --env kit-weekly-<slug> --channel "<canal>"`: crea el Environment (limitado
   a `master`) si no existe y carga los secretos, con los mismos nombres que en el canal por defecto. Los compartidos
   salen de `tokens/kit_secrets.json` (`{"KIT_LLM_API_KEY": "…", …}`, fuera de git), de `tokens/dropbox_worker.json`,
   del entorno o de un prompt sin eco (Enter no toca ese secreto); el token de YouTube, de `tokens/<canal>.json`.
   Los valores viajan a `gh` por stdin. Un Environment que ya existe no se modifica: solo se cargan secretos.
3. Sumar el canal a la variable del repo `KIT_CHANNELS` (es una variable, no un secreto):
   `gh variable set KIT_CHANNELS --body "default,<slug>"`.

`KIT_CHANNELS` es una lista `slug[=dia]` separada por comas. Sin día, un canal por día en el orden de la lista
empezando por el domingo (`default,a,b` = domingo, lunes, martes). El día se fija con `0`-`6` (lunes = 0) o
`lun`..`dom`: `default,a=jue`. Sin la variable corre solo el canal por defecto, los domingos, como siempre.
El workflow se dispara todos los días a las 23:00 UTC; el job `plan` (sin secretos ni Environment) arma la lista de
canales del día y el job `weekly` corre uno por canal, cada uno con su Environment y su `concurrency`. En
`workflow_dispatch` se elige el canal por su slug (`default` para el primero) y `dry_run`.

- El worker corta si la config o el token de YouTube del Environment no son del canal que le tocó
  (`kit_channel.check_owner`).
- Telegram usa un solo chat: cada resumen y cada alerta empieza con `[nombre del canal]`.
- El slug del canal se ve en el nombre del Environment y del job, que son públicos. El nombre real del canal no
  aparece en el log.
- En la PC: `py -3 scripts/run_kit_weekly.py --dry-run --cloud-config --automation <slug>`.

Smoke: `py -3 scripts/smoke_kit_multichannel.py`.

## Environment de GitHub (hay que configurarlo una vez)

El job usa el Environment `kit-weekly` y solo corre en `master`. GitHub crea el Environment vacío en la primera
corrida; hasta que lo configures no agrega ninguna protección. En *Settings > Environments > kit-weekly*:

1. *Deployment branches and tags*: "Selected branches" → `master`. Así una corrida manual desde otra rama no recibe
   los secretos aunque esa rama cambie el workflow.
2. Cargar ahí los secretos `KIT_*` y borrarlos de *Settings > Secrets and variables > Actions* (los de repositorio los
   ve cualquier workflow de cualquier rama).
3. Opcional: *Required reviewers* con tu usuario, si querés aprobar cada corrida a mano.

## Dropbox solo para los kits (opcional, recomendado)

El token de la app general ve todo tu Dropbox. Para que el del runner vea solo los kits:

1. En https://www.dropbox.com/developers/apps crear otra app: *Scoped access* → **App folder**. En *Permissions*
   marcar `files.metadata.read`, `files.content.read` y `files.content.write`.
2. Mover la carpeta de los kits (con `_automation` y las referencias) y la del estado dentro de
   `Apps/<nombre de la app>/`. Para esta app esa carpeta es la raíz: las rutas de la config no cambian.
3. `py -3 scripts/kit_dropbox_auth.py --app-key <app key>`: guarda `tokens/dropbox_worker.json` (fuera de git).
   Desde ahí el panel y el worker local usan esa app; Beats sigue con la general.
4. En GitHub, poner en `KIT_DROPBOX_REFRESH_TOKEN` y `KIT_DROPBOX_APP_KEY` los dos valores de ese archivo.
5. `scripts/run_kit_preview.py` y `scripts/analyze_kits.py` siguen usando la app general: en
   `config/app_config.json` su `dropbox_root` pasa a ser `/Apps/<nombre de la app>/...`.
6. Revocar el token viejo del runner no hace falta si era el de la PC; alcanza con que ya no esté en GitHub.

## Claves de API y dependencias

La config puede venir de Dropbox, así que no decide a dónde va una clave ni de qué archivo sale
(`core/kit_llm.py`, smoke `scripts/smoke_kit_api_hosts.py`):

- `base_url` del LLM y de la API de imágenes tiene que ser https y apuntar a un host permitido. De fábrica solo
  `api.openai.com`; para otro proveedor, cargar su host en la variable del repo `KIT_API_HOSTS` (separados por coma;
  es una variable, no un secreto) o en esa variable de entorno en la PC. Con un host no permitido no se manda nada:
  el video sale con el nombre del pack o con la imagen manual.
- En Actions (con variables `KIT_*` de credenciales) `key_file` no se lee: las claves van solo en `KIT_LLM_API_KEY` y
  `KIT_IMAGE_API_KEY`.

`requirements-worker.txt` lleva versiones exactas y hashes y el workflow instala con `--require-hashes`. Las
dependencias directas están en `requirements-worker.in`; para actualizar, regenerar y revisar el diff:

```bash
uv pip compile requirements-worker.in --generate-hashes --python-version 3.12 --python-platform x86_64-unknown-linux-gnu --no-header -o requirements-worker.txt
```

(y volver a poner las dos líneas de comentario del principio).

## Portada del video (opcional)

Si `kit_preview.cover` existe en `config/app_config.json`, cada video usa una portada generada
(`core/kit_cover.py`) en lugar de la imagen del pack, y esa misma imagen se sube como miniatura.
Sin la clave, o con `"enabled": false`, no cambia nada.

```json
"cover": {
  "template": {"brand": {"text": "TU MARCA"}},
  "frame": {}
}
```

`template` se mezcla sobre `DEFAULT_TEMPLATE` (tamaño, colores, textos, posiciones y desgaste);
solo hay que indicar lo que cambia. La marca va en la config, no en el código.

## Nombre del video por LLM (opcional)

Con `kit_preview.names` en la config, cada video recibe un nombre corto de 1 o 2 palabras
(`core/kit_names.py`) que reemplaza al del pack en título, descripción y portada, y el link del
canal lleva `utm_source` y `utm_content` propios del video.

```json
"names": {"genre": "soul", "base_url": "https://…/v1", "model": "…", "key_file": "ruta/fuera/del/repo"}
```

En Actions la clave va en el secret `KIT_LLM_API_KEY` (tiene prioridad sobre `key_file`). Si el LLM
falla, el video sale con el nombre del pack. Sin `names`, no cambia nada.

## Fondo de portada con IA (opcional)

Con `"cover_mode": "auto"` en `kit_preview`, el fondo de cada portada lo genera `core/kit_art.py` a
partir de 1 o 2 imágenes de la carpeta de referencias del género (`<refs_root>/<genero>`, el género
en minúsculas y con guiones bajos). Sin la clave, o con `"manual"`, se usa la imagen del pack como
hasta ahora.

```json
"cover_mode": "auto",
"art": {"refs_root": "/…/_referencias", "genre": "…", "model": "gpt-image-1", "size": "1024x1024"}
```

- Opcionales en `art`: `base_url` (https), `quality`, `key_file`, `ref_cooldown_days` (30),
  `refs_per_video` (2), `styles` (`{"<genero>": {"palette": "…", "motifs": ["…"]}}`) y `banned_words`.
  Si falta `art.genre` se usa `names.genre`.
- La clave va en el secret `KIT_IMAGE_API_KEY` (tiene prioridad sobre `key_file`).
- Una referencia no se repite dentro de `ref_cooldown_days`; cada video guarda las suyas en el
  estado (`ref_images`). Si no queda ninguna libre se repite la más antigua, con un warning.
- El prompt describe solo estética (paleta, grano, bokeh, motivos): sin texto en la imagen, sin
  personas y sin el nombre del kit ni el de los archivos. Las referencias se envían achicadas, sin
  metadatos y con nombre genérico.
- Un solo pedido por video, sin reintentos. Si la API rechaza la referencia o falla, ese video sale
  con la imagen manual del pack, llega un aviso por Telegram y la corrida sigue.
