# Worker semanal de loop kits

> **2026-10-18:** Conexiones ya no escribe `tokens/kit_secrets.json` ni `tokens/dropbox_worker.json`: Dropbox va al llavero de Windows y el resto directo a GitHub Secrets. Ver [CLOUD_CREDENTIALS.md](CLOUD_CREDENTIALS.md).

`scripts/run_kit_weekly.py` corre en GitHub Actions (`.github/workflows/kit-weekly.yml`): domingo 23:00 UTC
(20:00 en Buenos Aires) o a mano con `workflow_dispatch` (inputs `channel` y `dry_run`). Nunca se dispara con
`pull_request`. Con más de un canal, cada uno corre su día: ver "Varios canales" más abajo.

Cada corrida toma el lock de `state.json` (Dropbox), calcula los próximos slots (uno por horario de
`kit_preview.slots`, hasta 3; de fábrica lun/mié/vie 18:00) en `America/Argentina/Buenos_Aires` y, por slot, corre `run_preview` con un kit distinto. Sube en **privado** con la fecha
propuesta como `publishAt`; si YouTube la rechaza queda `private_pending` y el slot propuesto se guarda igual en el
estado, así una segunda corrida de la misma semana no duplica. Al final manda por Telegram un resumen con los links a
YouTube Studio (o una alerta con el paso que falló) y libera el lock en un `finally`.

### Calendario de YouTube

Misma regla que Type Beats: antes de elegir fechas, la corrida **real** lee el canal de YouTube
destino (token `KIT_YT_TOKEN_JSON` del Environment). Un día en Buenos Aires está ocupado si hay un
video publicado (público o no listado) o programado (privado con `publishAt`); un privado sin
`publishAt` no ocupa. Si un slot de cron cae en un día ocupado —por ejemplo un video programado a
mano en Studio— se salta al siguiente día libre del cron; un día libre **anterior** a otro día ya
ocupado sigue valiendo.

Por semana se publican hasta **tres** videos en los próximos slots libres (el tope habitual de
horarios por corrida). El estado en Dropbox (`scheduled_packs`, corridas con el mismo `publish_at`)
sigue evitando duplicar una fecha que el robot ya guardó; **no** es una copia del calendario de
YouTube ni hay que migrarlo ni ampliarlo para esta regla. No se cancelan corridas por colisión con
Studio: solo se elige otro día.

Si la lectura del calendario falla, esa corrida no sube nada, no reescribe el estado por ese motivo
y llega la alerta de Telegram que ya usa el worker. `--dry-run` no llama a YouTube.

Qué kits salen y cómo se arma cada video lo decide `core/kit_week.py`:

- Los kits salen de las categorías de `kit_preview.scan_folders` dentro de `kit_preview.dropbox_root` (obligatorio);
  cómo se reconocen los loops está en [KIT_PREVIEW.md](KIT_PREVIEW.md). El botón "Detectar kits" del panel los suma a la
  tabla sin link, para completarlos; una carpeta duplicada (nombre terminado en ` (1)`) llega desactivada.
- Solo entran los kits de `kits.json` (panel de la app) activos, con link y con carpeta en Dropbox; las carpetas que
  empiezan con `_` y los kits sin loops quedan afuera. Un kit sin imágenes solo entra con `cover_mode: "auto"` (el
  fondo se genera); con `manual` necesita su `images/`. Sin `kits.json` se usan todas las carpetas y el link del canal.
- Sale primero el kit que hace más que no se usa; entre kits parejos manda el orden de `scan_folders` y, dentro de
  cada categoría, el de las carpetas. Cada kit hace hasta `cycle_max_videos` (3) videos y descansa `cycle_rest_days`
  (30); entre dos usos pasan al menos `kit_min_gap_days` (7).
- El audio dura entre `target_min_s` y `target_max_s` (135-195 s) y nunca repite un loop dentro del ciclo del kit. Hacen
  falta `min_loops_per_video` (4) loops sin usar: con menos, el kit se saltea. Con 4 o más que no llegan al mínimo de
  duración sale un video más corto, con aviso. Ese video, o el que deja al kit sin loops para otro, cierra el ciclo y
  el kit descansa. `short_min_s` (0 = sin piso) permite exigir una duración mínima al video corto.
- `{link}` es el link del kit con `utm_source` y `utm_content` propios del video; nombre y referencias usan el género del kit.
- Un kit que no da un video se saltea y se prueba el siguiente. Si no alcanzan los kits, los horarios que sobran quedan
  sin video y el resumen de Telegram lo avisa (no es un fallo). Con 12 kits, 3 videos por semana y 30 días de descanso
  puede haber una semana incompleta cada tanto: se evita con más kits o con `cycle_rest_days: 28`.
- Renombrar la carpeta de un kit en Dropbox lo convierte en un kit nuevo: hay que actualizar `folder` en `kits.json`.

En la PC, sin variables `KIT_*`, el worker usa `tokens/` y `config/` locales; `--cloud-config` lee la config de Dropbox
aunque exista `config/app_config.json` (así corre **Probar sin subir** del panel).

- `--dry-run`: elige kits y slots; no toma el lock, no renderiza, no sube y no escribe en Dropbox. Manda un único aviso.
- Sin `config/app_config.json` (está ignorado por git) la config se lee de Dropbox (`KIT_CONFIG_PATH`, por defecto
  `/loop_kits/_automation/config.json`).
- Secretos (solo como `env` del paso del worker): `KIT_YT_CHANNEL`, `KIT_YT_TOKEN_JSON`,
  `KIT_DROPBOX_REFRESH_TOKEN`, `KIT_DROPBOX_APP_KEY`, `KIT_TELEGRAM_TOKEN`, `KIT_TELEGRAM_CHAT_ID` y, para
  el informe de tendencias (opcional), `KIT_NOTION_TOKEN` y `KIT_NOTION_PAGE_ID`. El
  `client_secret.json` no hace falta en el runner (solo sirve para conectar un canal): si ya cargaste
  `KIT_YT_CLIENT_SECRET_JSON`, borralo.
- El log es público: solo se imprime el paso y el tipo de error, nunca nombres de kits ni mensajes de las librerías.
  En Actions el worker además descarta `stderr`, registra como máscaras los valores sueltos de los secretos JSON y saca
  los secretos del entorno al arrancar, así ffmpeg no los hereda. Smoke: `scripts/smoke_kit_hardening.py`.

Smoke: `py -3 scripts/smoke_kit_weekly.py`.

## Panel de la app

El diálogo *Loop kits > Configuración de automatización* usa las mismas pestañas que Beats:

| Pestaña | Contenido |
|---|---|
| Conexiones | Semáforos (YouTube, Dropbox worker, Telegram, Notion, LLM, imágenes, `gh`). Conectar YouTube, wizard de Dropbox (`scripts/kit_dropbox_auth.py`), guardar Telegram/Notion/LLM/imagen en `tokens/kit_secrets.json` (nunca se muestran los valores), probar Telegram, sincronizar secretos a Actions. |
| Canal | Canal y horarios, carpeta de kits, tabla, géneros/referencias y **Portada** (modo y prompt). |
| SEO y tendencias | Ficha por género (frase, artistas, etiquetas, plantilla). |
| Avanzado | Topes de gasto e IA, recargar, **Publicar solo en Dropbox**, **Probar sin subir**, último estado y log. |

A diferencia de Beats, Loop kits no guarda una copia local del catálogo: **Publicar al robot** (barra inferior)
sube `kits.json` y la config del worker con el mismo CAS que el botón de Avanzado. La barra muestra el
checklist `readiness_kits` y si el canal está listo para piloto (conexiones + informe SEO válido).

La UI solo escribe claves SHARED conocidas (`KIT_TELEGRAM_*`, `KIT_NOTION_*`, `KIT_LLM_API_KEY`, `KIT_IMAGE_API_KEY`). Dropbox worker sigue en `tokens/dropbox_worker.json`. El botón *Sincronizar secretos del canal* corre `py -3 scripts/kit_secrets_sync.py --env kit-weekly-<slug> --channel "<canal>" --no-prompt` (sin shell). Si no hay `gh`, hay que instalar GitHub CLI y hacer `gh auth login` a mano. Smoke del panel: `py -3 scripts/smoke_kit_panel.py`.

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
2. En la pestaña Conexiones, *Sincronizar secretos del canal* (o a mano
   `py -3 scripts/kit_secrets_sync.py --env kit-weekly-<slug> --channel "<canal>" --no-prompt`): crea el Environment
   (limitado a `master`) si no existe y carga los secretos, con los mismos nombres que en el canal por defecto. Los
   compartidos salen de `tokens/kit_secrets.json` (`{"KIT_LLM_API_KEY": "…", …}`, fuera de git), de
   `tokens/dropbox_worker.json`, del entorno o de un prompt sin eco (Enter no toca ese secreto; `--no-prompt` no pide
   nada); el token de YouTube, de `tokens/<canal>.json`. Los valores viajan a `gh` por stdin. Un Environment que ya
   existe no se modifica: solo se cargan secretos.
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

## SEO por género: título, gancho y capítulos (opcional)

Con una ficha en `kit_preview.seo.<genero>` (sección "SEO por género" del panel), el título de los
videos de ese género lo arma `core/kit_seo.py`, sin modelo de lenguaje, con el **nombre real del kit**
(`name` del catálogo). La ficha vive en la config del canal en Dropbox, no en el repo:

```json
"seo": {"<genero>": {"phrase": "…", "artists": ["…"], "tags": ["…"], "title_template": "…", "examples": ["…"]}}
```

- `phrase` (obligatoria) es la frase que la gente busca; `artists` y `tags` admiten hasta 40 entradas de
  80 caracteres. `title_template` usa `{artist}`, `{artists}`, `{phrase}`, `{name}` y `{tags}`; sin ella
  vale `[FREE] {artist} {phrase} - "{name}" | ({tags})`. `examples` son títulos de referencia para vos.
- Reglas del título: la frase termina dentro de los primeros 40 caracteres, 100 como máximo (objetivo 90;
  se recortan etiquetas, nunca el nombre ni la frase), sin `<` ni `>` ni espacios dobles, y sin repetir
  uno de los últimos 20 títulos del canal. Si ningún título las cumple (nombre muy largo, plantilla que
  deja la frase lejos) se usa la plantilla de título del canal y llega un aviso.
- La frase tiene que entrar en esos 40 caracteres junto con lo que va antes: con la plantilla de fábrica
  quedan 33 para artista más frase. Una frase que no entra ni sin artista se rechaza al guardar. Un
  artista demasiado largo no sale de principal: el panel lo avisa al guardar y, si ninguno entra, el
  título sale sin artista con un aviso por Telegram.
- Una ficha sin frase se guarda pero no se usa (ese género sigue con la plantilla del canal).
- **Rotación para medir:** cada video de un kit usa otro artista principal (cuando se agotan vuelve el
  que hace más que no sale) y otra mezcla de 3 o 4 etiquetas; no se repite una variante ya usada por ese
  kit. La variante queda en el estado, en la corrida, junto al `youtube_id`: `seo: {artist, artists,
  tags, phrase, title}`.
- **Descripción:** la plantilla de descripción del canal admite `{hook}` y `{chapters}`. Si el marcador
  no está, no se agrega nada; si está y no hay contenido, se quita sin dejar huecos.
  - `{chapters}`: `0:00 Loop 1`, `0:28 Loop 2`… con la duración exacta de cada tramo. Un loop de menos
    de 10 s comparte capítulo con el siguiente (`Loops 3-4`). Hacen falta al menos 3 capítulos de 10 s
    o más; si no, se omiten y llega un aviso.
  - `{hook}`: 1 o 2 frases en inglés, una sola llamada al modelo de texto de `kit_preview.names`
    (`base_url`, `model`; clave en `KIT_LLM_API_KEY`) con la descripción del kit, el género y las
    palabras de la ficha. Se descarta si trae un link, una frase de autoría ("made by", "used by",
    "feat."), una cifra que no está en la descripción del kit, o si nombra a un artista de la ficha sin
    "inspired by" / "style of" delante o "-style" / "type" detrás. Cuesta `spend.text_cost_usd` (0.01)
    dentro del tope mensual; si el tope no deja (llega un aviso), el modelo falla o no hay modelo
    configurado, el video sale sin gancho, nunca sin título.
  - Sin `{hook}` en la plantilla no se llama al modelo, y sin `{chapters}` no se arman capítulos.
- Las llamadas de `kit_names` también cuentan como gasto de texto dentro del tope mensual (con o sin
  ficha): si el tope no deja, el video sale con el nombre del kit y llega un aviso.
- `names.vary_name` (casilla "Variar también el nombre", apagada de fábrica): reemplaza el nombre real
  por uno de una sola palabra, de marca o lugar, propuesto por `kit_names`. Sin ficha para el género
  nada de esto aplica: título y nombre salen como siempre.
- Una ficha mal formada no corta la corrida: ese género usa la plantilla del canal y llega un aviso.

Smoke: `py -3 scripts/smoke_kit_seo.py`.

### Tendencias semanales (opcional)

Antes de armar los videos el worker puede ajustar la ficha de cada género con un **informe de
tendencias** que una tarea programada de Claude (con vidIQ) deja cada semana en una página de Notion.
Sin los dos secretos de Notion la función no hace nada.

1. La tarea programada corre antes del worker (por ejemplo, el domingo 20:00 UTC; el worker corre a las
   23:00 UTC) y deja la página con **un bloque de código `json`** (el worker toma el último):

   ```json
   {"version": 1, "generated_at": "2026-10-11T20:00:00Z",
    "channel": {"top_videos": [{"title": "…", "views": 123}]},
    "genres": {"<genero>": {"keywords": [
      {"keyword": "emotional guitar loop kit", "monthly_searches": 11700, "competition": 12.3, "growth_pct": 4.0}]}}}
   ```

2. El worker lee la página con `KIT_NOTION_TOKEN` (clave de una integración de Notion **solo con permiso de
   lectura**, compartida únicamente con esa página) y `KIT_NOTION_PAGE_ID` (el id o la URL de la página). Solo
   habla con `api.notion.com`, sin seguir redirecciones. El informe se descarta si no es JSON válido, si su
   `version` no es 1 o si tiene más de `trends.max_age_days` días (10 de fábrica).
3. Una llamada al modelo de texto por género (`kit_preview.names`, clave `KIT_LLM_API_KEY`; cuenta como
   `spend.text_cost_usd` dentro del tope) **elige entre opciones que ya existen**: una de las frases del
   informe que cabe en el título y no repite a un artista, y los subconjuntos de etiquetas y artistas de
   tu ficha (al menos 4 y 2, para que la rotación siga). Lo que invente se descarta, y el resultado se vuelve
   a validar con `kit_seo`. Sin modelo, sin tope de gasto o con una respuesta inválida se usa la frase con
   mejor puntaje de búsquedas y llega un aviso.
4. La ficha de la semana de cada género queda guardada en `seo_trends.json`, junto a la config del canal,
   con su fecha y una huella de la ficha del panel de la que salió. Si la semana siguiente falta el informe
   (la tarea no corrió, Notion no responde, es viejo) se usa esa última ficha buena **siempre que no hayas
   cambiado la ficha del panel** y no tenga más de `trends.max_saved_age_days` días (35, contados por
   género); si no, manda la del panel. En todos esos casos llega un aviso por Telegram. **El panel no se
   modifica nunca**: lo que carga el informe vale una semana. El análisis corre solo si hay un horario libre
   y kits para armar, y solo para los géneros de esos kits (una llamada de texto por género).
5. Las ideas nuevas que sugiera el modelo (`suggestions`) se guardan en `seo_trends.json` solo para que
   las leas; el worker no las usa.

Config opcional en `kit_preview.trends`: `enabled` (true), `max_age_days` (10), `max_saved_age_days` (35),
`timeout` (30). Smoke: `py -3 scripts/smoke_kit_trends.py`.

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
  `refs_per_video` (2), `styles` (`{"<genero>": {"palette": "…", "motifs": ["…"], "colors": ["#e8662a", "#0f4c5c"]}}`)
  y `banned_words`.
  Si falta `art.genre` se usa `names.genre`.
- La clave va en el secret `KIT_IMAGE_API_KEY` (tiene prioridad sobre `key_file`).
- Una referencia no se repite dentro de `ref_cooldown_days`; cada video guarda las suyas en el
  estado (`ref_images`). Si no queda ninguna libre se repite la más antigua, con un warning.
- El prompt describe solo estética (paleta, grano, bokeh, motivos): sin texto en la imagen, sin
  personas y sin el nombre del kit ni el de los archivos. Las referencias se envían achicadas, sin
  metadatos y con nombre genérico.
- Un solo pedido por video, sin reintentos. Si la API rechaza la referencia o falla, ese video sale
  con la imagen manual del pack, llega un aviso por Telegram (uno por corrida) y la corrida sigue.

### Portada sin IA (respaldo)

Si la IA falla (sin saldo, clave vencida, rechazo, tope de gasto) y el kit no tiene imagen propia,
`kit_art.free_background` arma el fondo sin costo y el video sale igual:

1. Una imagen de la carpeta del género, desenfocada y oscurecida: en `template`, uno de `fondos/`
   (desenfoque leve); en `auto`, una referencia (desenfoque fuerte, solo queda el color). Rota con la
   misma regla de `ref_cooldown_days`.
2. Si no hay imágenes o Dropbox falla, un degradado con los colores del género (`styles.<genero>.colors`,
   dos hex; sin ellos, unos fijos derivados del nombre).

El compositor le pone el título encima, como en `auto`.

## Portada por plantilla + fondo (opcional)

Con `"cover_mode": "template"` la API de imágenes devuelve la portada cuadrada **completa**
(`core/kit_template_art.py`): recibe la portada modelo del género, un fondo y el título del video. El
compositor de `core/kit_cover.py` no interviene; solo se arma el cuadro 16:9 con `to_video_frame`.
`manual` y `auto` siguen como estaban.

En Dropbox, dentro de la carpeta de referencias de cada género (`<refs_root>/<genero>`):

- `modelo.png`: la portada modelo (también sirve `.jpg`, `.jfif` o `.webp`).
- `fondos/`: los fondos. Uno no se repite dentro de `ref_cooldown_days` (30); si no queda ninguno libre
  se repite el más antiguo, con un warning. El fondo usado queda en el estado (`ref_images`).

```json
"cover_mode": "template",
"art": {"refs_root": "/…/_referencias", "prompt": "… {titulo} …"},
"spend": {"monthly_cap_usd": 10, "max_images_per_run": 6, "image_cost_usd": 0.25, "verify_cost_usd": 0.01}
```

- Opcionales en `art`: `model` (`gpt-image-1`), `size` (`1024x1024`), `quality` (`high`),
  `input_fidelity` (`high`), `n` (1), `timeout`, `model_name` (`modelo`), `backgrounds_dir` (`fondos`) y
  `verify` (`{"enabled": true, "model": "gpt-4o-mini", "base_url": "…"}`).
- **Prompt:** `art.prompt` con el marcador `{titulo}`, que se reemplaza por el título tal cual llega. Sin
  prompt en la config se usa el de fábrica (`DEFAULT_PROMPT`). Se edita en el panel, que tiene un botón
  para restaurarlo.
- Las dos imágenes se envían como PNG achicado, sin metadatos y con nombre genérico. El nombre del kit no
  entra al prompt; el título del video sí (es lo que hay que escribir).
- **Verificación:** un modelo con visión lee el título de la portada y lo compara sin distinguir
  mayúsculas ni espacios. Si no coincide hay **un solo** reintento; si vuelve a fallar se usa esa imagen y
  llega un aviso por Telegram con la portada para revisarla. Usa la clave de imágenes si va al mismo host
  que la API de imágenes; si `verify.base_url` apunta a otro host (permitido), usa `KIT_LLM_API_KEY`.
- **Errores:** si la API rechaza o falla (moderación, 4xx, 5xx, timeout) no hay reintento: ese video sale
  con la imagen manual del kit (o se saltea si el kit no tiene imágenes) y llega un aviso.
- **Tope de gasto** (`core/kit_spend.py`): antes de cada llamada paga se consulta el gasto estimado del
  mes, guardado en el estado del canal (`spend`), y después se anota. Al llegar a `monthly_cap_usd` o a
  `max_images_per_run` no se genera más: los videos que faltan pasan a manual y llega un aviso (uno por
  corrida). Un fallo dudoso (timeout, 5xx) se cuenta como cobrado; un 4xx no. Si el gasto no se puede
  leer o guardar, tampoco se genera. Con `n` mayor que 1 se cobran `n` imágenes y se usa solo la primera.
- El gasto es una **estimación** con los costos de la config, no la factura: `image_cost_usd` hay que
  ajustarlo a la tarifa vigente. La otra capa del tope es el crédito prepago con la recarga automática
  apagada. En corridas locales con `run_kit_preview.py` (sin estado en la nube) solo cuenta el máximo por
  corrida.
- El panel muestra el gasto estimado del mes en "Ver último estado".

### Descripción por kit

Cada entrada de `kits.json` admite un `description` opcional (1 o 2 líneas, hasta 200 caracteres; columna
"Descripción" del panel). Se manda al modelo de lenguaje como contexto para que el nombre del video se
relacione con el kit. No se imprime ni va a los avisos.

Ver también [CLAUDE_SEO_REPORT.md](CLAUDE_SEO_REPORT.md): estado e import del informe de tendencias desde la pestaña SEO y tendencias del panel.

> **2026-10-23:** `KIT_CHANNELS = "-"` significa «ningún canal» (todos pausados); vacío sigue siendo «el canal por
> defecto, los domingos». La app lo administra desde «Mis canales automatizados» (activo/pausado, día, quitar).
