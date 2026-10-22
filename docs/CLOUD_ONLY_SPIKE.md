# Spike: escritorio solo contra Dropbox + GitHub Secrets

Fecha: 2026-10-18. Tarea **solo de lectura**: no se cambió código, config, Dropbox ni GitHub.
Evidencia con `ruta:línea` del árbol de trabajo actual (rama `master`, con cambios sin commitear).
Comandos `gh` que se corrieron: `auth status`, `variable get/list`, `secret list` (solo nombres), `api .../environments` y `run list/view`.
De `tokens/` solo se miraron nombres y tamaños de archivo, nunca contenidos.

**Veredicto: es viable.** Los dos workers ya son autosuficientes con sus documentos de Dropbox. Lo que ata
el escritorio a `config/app_config.json` es: (a) el catálogo de canales y su tipo (`channels{}`), (b) las
plantillas de título/descripción, (c) la validación de rutas de media locales y (d) el estado de conexiones,
que se lee de `tokens/*.json`. Hay tres bloqueantes de diseño, que se explican en §7 y §8:
1. En Beats, el **nombre** del canal no se puede cambiar libremente. Es la clave `id` en config/state y
   también es el valor del secreto `BEAT_CHANNEL_ID_<SLUG>`.
2. En Loops, el nombre tampoco se puede cambiar. `kit_channel.check_owner` exige que `slug(nombre) == slug`.
3. Las expresiones regulares de slug de Beats y de Kits son distintas.

---

## 1. Quién lee o escribe `config/app_config.json`

| Lugar | L/E | Campos |
|---|---|---|
| `core/channel_manager_dialog.py:23,58-88` | L+E | `channels{nombre:{groups, section, title_template, description_template}}`. Al guardar mezcla `DEFAULT_CONFIG` (`:24-39`) y llama a `ensure_channel_sections` (`:66,81`). |
| `core/channel_manager_dialog.py:215-230,286-291` | E | `title_template`, `description_template`, y `section=self.default_section` (que depende de la pestaña activa, `main.py:47-48,57`) al crear un canal. |
| `core/description.py:6,32-50` | L+E | `channels[c].description_template`, `socials`, `hashtags`. `save_channel_template` no tiene llamadores; `render_for_channel` solo se usa dentro del módulo (`:80`). |
| `core/beat_settings.py:19-24` `read_app` | L | El documento entero. |
| `core/beat_settings.py:27-32` `settings` | L | `beat_automation` (lo migra) y `channels[id]`, que pasa a `apply_channel_templates`. |
| `core/beat_settings.py:58-79` `validate` | L | `channels` filtrado por `section=beats` (`:61`) para validar `beat_automation.channels[].id` (`:63-64`). Además valida carpetas locales (§3). |
| `core/beat_settings.py:82-97` `save` | E | Reemplaza solo `beat_automation` (escritura atómica). |
| `core/beat_panel.py:29,46-49,191-196,218,224,235` | L+E | Igual que `beat_settings`. El combo de canales sale de `channels` con `section=beats`. |
| `core/beat_remote_form.py:45-54` | L | Lee `app` para validar la config remota. **Una config de Dropbox no carga si sus canales no existen en el `app_config` local.** |
| `core/beat_sync.py:6-9` | L | `beat_automation.beatstars_profile_url` (entrada de la Fase 1). |
| `scripts/render_type_beat.py:24-33` | L | Opcional `--config`; si no se pasa, usa Dropbox. |
| `scripts/run_kit_preview.py:30-57,111` | L | `channels` con `section=loop_kits` y sus plantillas; `kit_preview`. |
| `scripts/run_kit_weekly.py:324,341-349` | L | Solo si existe el archivo local, no se pasó `--cloud-config` y el canal es el default. Si no, usa Dropbox. |
| `scripts/analyze_kits.py:21,69` | L | `kit_preview`. |
| `loop_kit_panel.py:646-653` `_local_config` | L | `channels` (section y plantillas), para `kit_channel_setup.loop_kit_channels/minimal_config` (`:656,666,674`). |
| `core/kit_week.py:25-93`, `core/kit_catalog.py:36-38` | L (dict) | `kit_preview.*`. En el worker el dict viene de Dropbox. |
| `main.py:16,57` | — | Le pasa `CONFIG_FILE` a `ChannelManager`. |
| `tokens/*.py` (scripts sueltos de mattwyyre: `configure_…`, `set_…_active`, `assign_…_assets`, `align_…_templates`, `publish_paused_…`, `verify_…`) | L, y E en algunos | Usan `beat_settings.read_app('config/app_config.json')`. Son scripts de una sola vez, guardados en `tokens/`. |

### `apply_channel_templates` (`core/beat_templates.py:7-35`)
- Solo actúa si `use_channel_templates is True` (`:8-12`) en el canal de `beat_automation`.
- Lee del canal guardado (`app.channels[id]`): `title_template` (obligatorio, no vacío), `description_template`
  (str), y opcionalmente `socials` y `hashtags` (`:15-23`).
- Reemplaza `{beatstars_url}`→`{url}`, `{channel}`→`id`, `{socials}`, `{hashtags}`, `{tags}`. Después de eso solo
  admite `{name}` y `{url}` (`:28-29`). El resultado queda en `channel.seo.title_template` y `seo.description` (`:31-34`).
- **Se ejecuta en el escritorio** dentro de `settings`/`validate` (`beat_settings.py:30,65`). El `seo` ya compilado
  se publica en `/type-beats/config.json`. El worker nunca vuelve a ejecutar esta función.

### `core/channel_templates.py`
- Solo tiene helpers: `DEFAULT_TITLE_TEMPLATE`, `get_title_template(cfg)` (lee `cfg.title_template`, `:14-16`) y
  `render_title` (`{name}`, `{channel}`, `{group}`).
- Lo usan `channel_manager_dialog.py:233` (vista previa) y `kit_publish.py:109-110`. En Kits, `templates` es el
  dict `channels[nombre]` del config de Dropbox del worker.

### Claves muertas
`last_*`, `name_template`, `overlay_*`, `cta_*`, `vertical_*` y `groups` ya no las usa nadie, salvo
`DEFAULT_CONFIG` y `tests/test_beat_panel.py`. Venían de la UI vieja, que está borrada en el árbol actual.
No hace falta migrarlas.

---

## 2. ¿Los workers necesitan `app_config`?

**Beats: no. `/type-beats/config.json` es autosuficiente.**
- Entrada: `scripts/run_beat_daily.py:6` → `core/beat_worker.main`.
- Solo usa variables de entorno `BEAT_*` (`beat_worker.py:32-43`) y `cloud.read('config')` (`:61-64`, `beat_daily.py:47-50`).
  No aparece `app_config` en `beat_worker.py`, `beat_daily.py` ni `beat_cloud.py`.
- Las rutas están fijas: `/type-beats/{config,state}.json` (`beat_cloud.py:153-157`).
- Las plantillas viajan ya compiladas en `channels[].seo` (ver §1).
- Consecuencia: si se cambia una plantilla en «Canales», el worker no se entera hasta que alguien vuelva a
  apretar «Publicar» en Beats.

**Kits en Actions: no. El config de Dropbox del canal es autosuficiente.**
- `run_kit_weekly.py:341-347`: en Actions no hay archivo local, así que lee
  `CONFIG_DROPBOX_PATH` (`/loop_kits/_automation/config.json`) o `paths.config`.
- Ese documento tiene **la misma forma que `app_config`**: `{channels:{nombre:{section:'loop_kits', title_template, description_template, tags, socials, hashtags, link}}, kit_preview:{…}}`.
  Esto lo confirman `kit_channel_setup.minimal_config` (`:53-74`) y `resolve_channel` (`run_kit_preview.py:41-57`).
- El dry-run del escritorio ya fuerza `--cloud-config` (`loop_kit_panel.py:871`).
- Lo que todavía depende del archivo local: la rama local de `run_kit_weekly.py:341` y `run_kit_preview.py`
  (que solo lee local, `:255-260`).
- Hueco actual: las plantillas de un canal de Kits se copian del `app_config` local **solo al crear** la
  automatización (`kit_channel_setup.py:63-66`). Si después se editan en «Canales», el cambio queda solo en el
  archivo local y nunca llega al worker.

---

## 3. Media local y su equivalente en Dropbox

| Opción | Dónde | Valores | En la nube |
|---|---|---|---|
| `visual.video_source` | `beat_visual.py:16,23` | `local` \| `dropbox`. **El default es `local`.** | `dropbox` con `videos_folder` = ruta Dropbox (validada por `dropbox_path`, `:38-39`). Catálogo en `DropboxAssets.list_videos` (`:65`). |
| `visual.thumbnail_source` | `beat_visual.py:18,24,111-123` | `auto` \| `local` \| `dropbox` | `dropbox` + `thumbnail_path` Dropbox, o `auto`. |
| `images_folder` | `beat_settings.py:54-55,76-78`; `beat_visual.py:96-107` | Carpeta local (tiene prioridad sobre Dropbox si el género no está en `dropbox_images`) | `dropbox_images{genero: carpeta}` (`beat_settings.py:39-48`, `beat_visual.py:94-95`). |
| `validate` | `beat_settings.py:68-78` | Hace `Path.is_dir()` / `is_file()` sobre rutas locales | En modo nube: **rechazar** `local` y `images_folder` no vacío. Las rutas Dropbox ya se validan con `dropbox_path`. |
| Kits: imágenes `source:'local'` | `kit_source.py:111-126`, `kit_week.py:100-103`, `run_kit_preview.py:60-64` | Solo si se pasa `local_images_root` | **Código muerto.** Ningún llamador pasa `local_images_root` a `list_packs` (`kit_source.py:176`). |
| Kits: `art.refs_root` | `kit_settings.py:220-232`, `kit_art.py:149-158` | Ya es una ruta Dropbox (`/…`) | Ya está en la nube. |

Hoy los dos canales de Beats del `app_config` local usan `video_source=dropbox`, `thumbnail_source=auto`,
`images_folder` vacío y 1 entrada en `dropbox_images`. **Ninguno depende de media local.**
Recomendación: en el modo solo-nube, `validate` tiene que exigir `video_source='dropbox'` y
`thumbnail_source in ('auto','dropbox')`, y rechazar `images_folder`. Además conviene que el schema escriba
`video_source:'dropbox'` de forma explícita, porque el default `local` (`beat_visual.py:16`) es una trampa.
El botón `browse_images` (`beat_panel.py:209-212`) se puede quitar.

---

## 4. `core/automation_status.py` → `gh`

Lo que lee hoy (solo devuelve códigos; nunca devuelve valores):

| Función | Fuente local | Comprueba |
|---|---|---|
| `youtube_token_status` (`:67-78`) | `tokens/<canal>.json` | Que tenga `refresh_token` |
| `dropbox_worker_status` (`:81-86`) | `tokens/dropbox_worker.json` | `refresh_token` + `app_key` |
| `beat_notion_status` / `read_beat_notion` (`:89-103`) | `tokens/beat_secrets.json` | `BEAT_NOTION_TOKEN`, `BEAT_NOTION_PAGE_ID` (con formato) |
| `kit_*_status` / `read_kit_secrets` (`:143-255`) | `tokens/kit_secrets.json` o el entorno | `KIT_SHARED_KEYS` (`:28-32`) |
| `gh_available` (`:129-131`) | `PATH` | Que exista `gh` (no la sesión) |
| `readiness_kits` / `readiness_beats` (`:266-308`) | Todo lo anterior | Checklist de la UI |

**En esta PC no existen** `tokens/dropbox_worker.json`, `tokens/beat_secrets.json` ni `tokens/kit_secrets.json`,
y no hay variables `BEAT_*`/`KIT_*` en el entorno. Por eso el semáforo de Dropbox da `missing` en las dos secciones,
aunque los secretos están cargados en GitHub. También `beat_panel_cloud.local_transport` (`:12-38`) cae a
`BEAT_DROPBOX_*` y falla, mientras que Kits cae a `tokens/dropbox.json` (`kit_cloud.py:115-120`).
**Esto ya pasa hoy.**

Reemplazo propuesto (`core/gh_status.py`, nuevo y chico):
```text
gh auth status                                      → ok/missing de la sesión (no solo del binario)
gh secret list --env <env> --json name,updatedAt    → set de nombres + fecha
gh variable get BEAT_CHANNELS                       → JSON array (beat_actions.matrix lo valida)
gh variable get KIT_CHANNELS                        → "slug[=dia],…" (kit_channel.parse_schedule); si no existe, exit≠0 y significa "solo default"
gh api repos/{owner}/{repo}/environments --jq '.environments[].name'
```
Semáforo por canal = los nombres esperados por (tipo, slug) (§7) ⊆ `secret list`. La fecha `updatedAt` se puede
mostrar como «actualizado hace N días».
Lo que se pierde: no se puede validar el contenido (que exista `refresh_token`, el formato del page ID), porque
GitHub no devuelve valores. La validación de contenido tiene que hacerse **al subir** el secreto (ya pasa en
`save_kit_keys`, `:178-213`, y en los sync scripts), no al leer el estado.
`youtube_token_status` local deja de tener sentido si el token pasa al llavero (§8).
Todas las llamadas con `subprocess.run([...], capture_output=True)` sin shell, como en `beat_secrets_sync.py:44`.

---

## 5. `keyring`

```
py -3 -c "import keyring; print(keyring.get_keyring())"
→ ModuleNotFoundError: No module named 'keyring'   (Python 3.14.3; tampoco está en .venv)
```
No está instalado ni en `requirements.txt`. Al instalarlo, en Windows el backend por defecto es
`keyring.backends.Windows.WinVaultKeyring` (Credential Manager, ligado al usuario de Windows).
Límite a tener en cuenta: el blob de Credential Manager es de 2560 bytes, que con UTF-16 son unos 1280 caracteres.
Tamaños actuales (solo `wc -c`): `client_secret.json` 402 B, tokens de YouTube 786–794 B, `dropbox.json` 85 B.
**Todo entra.** Hay que validarlo de nuevo antes de guardar, porque un token con más scopes crece.

---

## 6. Dry-run

Hoy:
- **Kits:** `loop_kit_panel.py:856-872` lanza con `QProcess` el comando
  `run_kit_weekly.py --dry-run --cloud-config [--automation <slug>]` **en la PC**, con credenciales locales
  (`_local_credentials`, `run_kit_weekly.py:289-296`). Si sale con 0, marca el flag `dryrun` del asistente.
- **Beats:** no hay dry-run local. El asistente pide un checkbox manual del tipo «Corrí el dry-run en Actions»
  (`channel_wizard.py:189-193`).

Propuesta (documentada, **no se disparó**):
```text
gh workflow run type-beats-daily.yml -f channel=<slug> -f dry_run=true
gh workflow run kit-weekly.yml       -f channel=<slug|default> -f dry_run=true
gh run list --workflow <wf>.yml --event workflow_dispatch --limit 1 --json databaseId,status,conclusion,createdAt
gh run view <id> --json status,conclusion,jobs --jq '.jobs[]|{name,conclusion}'
gh run view <id> --log    # opcional; el log ya está sanitizado (beat_worker imprime solo el JSON de summary, :82)
```
Notas:
- `type-beats-daily.yml:93`: con `dry_run=true`, `DRY_RUN` es true sin importar `private_pilot`.
  Si `channel` va vacío, corre **todos** los canales. `beat_actions.credential_matrix` falla si el slug no está en `BEAT_CHANNELS`.
- `kit-weekly.yml:13-18,42`: `channel` acepta un slug de `KIT_CHANNELS` o `default`. `kit_channel.matrix`
  falla si no está (`kit_channel.py:161-164`). Hoy `KIT_CHANNELS` no existe, así que solo `default` es válido.
- `gh workflow run` no devuelve el id del run. Hay que tomar el más reciente con `--event workflow_dispatch`
  y `createdAt` ≥ la hora del disparo, o polear `run list` cada 10–15 s.
- El nombre del job ya identifica el canal: `daily (ey-mat, BEAT_CHANNEL_ID_EY_MAT, BEAT_YT_TOKEN_JSON_EY_MAT)`
  (verificado con `gh run view 39080839719`). En Kits el job `weekly` sale `skipped` cuando no le toca a ningún
  canal (run 39083812724).
- Ventaja: se prueba exactamente el entorno real (secretos, Environment restringido a `master`). El dry-run
  local de Kits se puede retirar.

---

## 7. Tipo de canal: derivación e inventario

### Dónde se decide el tipo hoy
| Lugar | Regla |
|---|---|
| `core/sections.py:16-32` `channel_section` | Si falta `section` o no es válida → **beats**. `personal` pasa tal cual. |
| `core/sections.py:74-93` `ensure_channel_sections` | **Escribe** `section=beats` en cada canal sin sección cuando `ChannelManager` carga o guarda (`channel_manager_dialog.py:66,81`). |
| `core/channel_manager_dialog.py:286-291` | Un canal nuevo toma la sección de la pestaña activa (`main.py:47-48`). |
| `core/beat_settings.py:61` / `beat_panel.py:49,196` | `channel_names_for_section(…, beats)`, con el default beats. |
| `core/kit_settings.py:295-296` `form_from_config` | Exige `section == 'loop_kits'` **explícito**, sin default. Es asimétrico respecto de `sections.py`. |
| `core/kit_channel_setup.py:13,47-48,62` | Mismo criterio explícito; el config nuevo lleva `section:'loop_kits'`. |
| `scripts/run_kit_preview.py:43-57` | `filter_channels_by_section(…, loop_kits)`, que sale de `sections.py`. |
| `main.py:47-48,57` | La pestaña activa define la sección por defecto del diálogo. |

### Tabla de derivación contra el código y GitHub
| Tipo | Documento | Environment | Secretos del canal | Lista | Workflow | Verificado |
|---|---|---|---|---|---|---|
| beats | Entrada en `/type-beats/config.json` `channels[]` con **`id` = nombre** y **`actions_slug` = slug** (`bind_channel`, `beat_actions.py:43-46`) | `kit-weekly` fijo (`beat_actions.py:10-15`, `type-beats-daily.yml:55`) | `BEAT_CHANNEL_ID_<SLUG>` y `BEAT_YT_TOKEN_JSON_<SLUG>`, con `SLUG = slug.upper().replace('-','_')` (`beat_actions.py:18-22`). **El valor de `BEAT_CHANNEL_ID_*` es el nombre (id), no el slug** (`beat_secrets_sync.py:29-32`, `beat_worker.py:38`). | `BEAT_CHANNELS` = array JSON (`beat_actions.py:49-55`) | `type-beats-daily.yml` | ✔ |
| loops | `kit_channel.paths(slug)` → `/loop_kits/_automation/<slug>/config.json`, `…/<slug>/kits.json`, `/loop_kits_state/<slug>/state.json` (`kit_channel.py:69-79`). El doc tiene `channels{nombre}` y `kit_preview.channel=nombre`. | `kit-weekly-<slug>` (`kit_channel.py:90-92`, `kit-weekly.yml:56`) | `KIT_YT_CHANNEL` (valor = nombre) y `KIT_YT_TOKEN_JSON`, **más los compartidos duplicados en cada env**: `KIT_DROPBOX_*`, `KIT_TELEGRAM_*`, `KIT_LLM_API_KEY`, `KIT_IMAGE_API_KEY`, `KIT_NOTION_*` (`kit-weekly.yml:86-96`, `kit_secrets_sync.py:31,149-150`) | `KIT_CHANNELS` = `slug[=dia]` separado por comas, **no JSON** (`kit_channel.py:137-151`) | `kit-weekly.yml` | ✔ (con agregados) |
| loops `legacy_default` | Rutas por defecto (`kit_channel.py:22-24,61-66`) | `kit-weekly` | Los mismos `KIT_*`, en `kit-weekly` (compartido con Beats) | En `KIT_CHANNELS` aparece como **`default`**, no como su slug. Sin la variable, corre solo los domingos (`FIRST_WEEKDAY=6`). | `kit-weekly.yml` | ✔ |

Correcciones a la tabla del plan:
1. **El nombre no es libre.**
   - Beats: `id` (= nombre) es la clave en config, en `state.jobs[].channel` (`beat_schedule.py:76`) y en
     el valor del secreto `BEAT_CHANNEL_ID_<SLUG>`, y además da nombre al archivo del token.
   - Loops: `check_owner` exige `slug(nombre) == slug` (`kit_channel.py:95-105`).
   - Propuesta: separar `nombre` (visible y editable) de `clave` (el id de hoy, **inmutable**). Para los canales
     nuevos, `clave = slug`.
2. **Las regex de slug no coinciden.** Beats usa `[a-z][a-z0-9-]{0,39}` (`beat_actions.py:52`), que permite
   `--` y un guion al final. Kits usa `[a-z0-9]+(?:-[a-z0-9]+)*`, de hasta 40 caracteres (`kit_channel.py:25-26`),
   que permite empezar con un dígito. Regla común propuesta: `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`, de largo ≤ 40,
   con `default` como palabra reservada.
3. Unicidad entre tipos: no hay choque de environments, porque Beats no crea `kit-weekly-*`. Pero un slug repetido
   confundiría el registro y el semáforo, así que la unicidad global se mantiene como regla del registro.

### Inventario actual (GitHub y `app_config` local, solo nombres)
- Environments: `github-pages` y `kit-weekly`. `kit-weekly` está restringido a la rama `master`
  (`custom_branch_policies:true`). **No hay ningún `kit-weekly-<slug>`.**
- Variables: `BEAT_CHANNELS=["ey-mat","mattwyyre"]`, `BEAT_LIVE_ENABLED=true`. **`KIT_CHANNELS` no existe.**
- Secretos de `kit-weekly`: `BEAT_CHANNEL_ID`, `BEAT_YT_TOKEN_JSON`, `BEAT_CHANNEL_ID_EY_MAT`,
  `BEAT_YT_TOKEN_JSON_EY_MAT`, `BEAT_CHANNEL_ID_MATTWYYRE`, `BEAT_YT_TOKEN_JSON_MATTWYYRE`, `KIT_DROPBOX_APP_KEY`,
  `KIT_DROPBOX_REFRESH_TOKEN`, `KIT_IMAGE_API_KEY`, `KIT_LLM_API_KEY`, `KIT_NOTION_PAGE_ID`, `KIT_NOTION_TOKEN`,
  `KIT_TELEGRAM_CHAT_ID`, `KIT_TELEGRAM_TOKEN`, `KIT_YT_CHANNEL`, `KIT_YT_TOKEN_JSON`. A nivel repo no hay ninguno.
- `app_config.channels` local: `ey mat`, `WyreSounds` y `mattwyyre`, **todos con `section=beats`**.
  `beat_automation.channels`: `ey mat` (slug `ey-mat`, active=true) y `mattwyyre` (slug `mattwyyre`, active=false,
  `use_channel_templates=true`).
- `tokens/` (solo nombres): `ey mat.json`, `mattwyyre.json`, `WyreSounds.json`, `dropbox.json`, más unos 35
  scripts y snapshots de mattwyyre que **no son tokens**.

| slug | tipo | nombre/clave | legacy_default | Estado |
|---|---|---|---|---|
| `ey-mat` | beats | `ey mat` | — | Completo (config local, lista y 2 secretos). El run 39080839719 terminó bien. |
| `mattwyyre` | beats | `mattwyyre` | — | Completo. Localmente `active=false`; hay que comparar con la copia remota, que es la que vale. |
| `wyresounds` (propuesto) | loops | `WyreSounds` | **sí** | Probable canal por defecto de Kits: existe su token local, hay `KIT_YT_*` en `kit-weekly` y el workflow corre. **No se verificó** el valor de `kit_preview.channel` en Dropbox (§Pendiente). |

### Inconsistencias que ya existen hoy
1. **Secretos huérfanos:** `BEAT_CHANNEL_ID` y `BEAT_YT_TOKEN_JSON` sin sufijo (del 2026-10-13). El workflow solo
   usa `secrets[matrix.*_secret]` (`type-beats-daily.yml:85-86`). Se pueden borrar una vez confirmado.
2. **Secretos que faltan:** el workflow pasa `BEAT_NOTION_TOKEN`/`BEAT_NOTION_PAGE_ID` (`:89-90`), pero no existen
   en `kit-weekly`. Por eso el informe SEO de Beats está apagado sin aviso (`beat_worker.py:42`).
3. **Tipo mal registrado:** `WyreSounds` figura con `section=beats` en local, aunque por los indicios es el
   canal Loops por defecto. Ningún canal local tiene `loop_kits`, así que `run_kit_preview.py` local falla y
   `ask_new_automation` (`loop_kit_panel.py:656`) solo ofrece canales del config remoto. El tipo vive en dos
   lugares que no coinciden.
4. `ensure_channel_sections` reclasifica en silencio como beats cualquier canal sin sección.
5. `KIT_CHANNELS` no existe y no hay `kit-weekly-<slug>`. Cualquier entrada del registro
   `/loop_kits/_automation/channels.json` (`kit_channel_setup.py:14,25-40`) no correría y no tendría secretos.
   Falta leer ese registro para confirmarlo.
6. Las plantillas de Kits no se propagan después del alta (§2). Las de Beats quedan desactualizadas hasta el
   próximo «Publicar».
7. El semáforo local de Dropbox da `missing` en las dos secciones porque falta `tokens/dropbox_worker.json` (§4),
   y el panel Beats no puede leer Dropbox sin `BEAT_DROPBOX_*`.
8. **Ya existe un registro parcial:** `/loop_kits/_automation/channels.json` `{channels:[{name,slug}]}`, que es
   solo de Kits y no incluye el default. `canales.json` lo reemplaza. Durante la transición hay que mantenerlo o
   migrarlo.

**Pendiente (no se hizo porque requería leer credenciales de `tokens/`):** leer de Dropbox `/type-beats/config.json`
(`channels[].{id,actions_slug,active}`), `/loop_kits/_automation/config.json` (las claves de `channels` y
`kit_preview.channel`) y `/loop_kits/_automation/channels.json`, para cerrar las filas 2 y 3 del inventario.

---

## 8. Esquemas propuestos

### `/automatizacion/canales.json`
```json
{
  "schema_version": 1,
  "namespace": "automatizacion",
  "canales": [
    {
      "slug": "ey-mat",
      "tipo": "beats",
      "clave": "ey mat",
      "nombre": "ey mat",
      "activo": true,
      "legacy_default": false,
      "plantillas": {
        "title_template": "[Type] {name} | Free for Profit",
        "description_template": "{name} Type Beat | {bpm} BPM | {key}\n\n🎧 {beatstars_url}\n\n{socials}\n\nTags: {tags}\n{hashtags}",
        "socials": "",
        "hashtags": "",
        "tags": [],
        "link": ""
      },
      "creado": "2026-10-13T04:27:38Z"
    }
  ]
}
```
Reglas:
- `slug` cumple `^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$`, ≤ 40, ≠ `default`, y es único en todo el archivo.
- `tipo` ∈ {`beats`, `loops`}.
- `slug`, `tipo` y `clave` son inmutables.
- `clave` es el id de hoy (`beat_automation.channels[].id` y `channels{}` de Kits). Para canales nuevos,
  `clave = slug`.
- `legacy_default: true` solo se permite con `tipo=loops`, y como máximo en un canal.
- `activo` es la intención del usuario. El flag efectivo de Beats sigue en `/type-beats/config.json` `channels[].active`,
  y el escritorio lo proyecta al guardar.
- `plantillas`: en Beats se compilan con `apply_channel_templates` y se proyectan a `seo`. En Loops se copian a
  `channels[clave]` del config del canal. **La fuente de verdad es `canales.json`; los documentos de los workers
  son proyecciones** que se escriben en el mismo «Guardar», con CAS.
- Escritura con CAS por `rev`, como `kit_cloud.write_json`.
- Tamaño: menos de 100 canales, igual que el tope de `beat_actions.matrix`.

### `/automatizacion/ajustes.json`
```json
{
  "schema_version": 1,
  "namespace": "automatizacion",
  "beatstars": { "profile_url": "https://www.beatstars.com/<usuario>" },
  "gasto_kits_default": { "monthly_cap_usd": 10.0, "max_images_per_run": 6 },
  "horarios_default": {
    "beats": [{ "weekday": 0, "hour": 18, "minute": 0 }],
    "loops": [{ "weekday": 0, "hour": 18, "minute": 0 }, { "weekday": 2, "hour": 18, "minute": 0 }, { "weekday": 4, "hour": 18, "minute": 0 }]
  },
  "zona_horaria": "America/Argentina/Buenos_Aires",
  "github": { "repo": "Perree/video-type-beat-generator", "rama": "master" }
}
```
- Los defaults salen de `kit_spend.DEFAULTS` (`kit_spend.py:15-21`), con topes `MAX_MONTHLY_CAP=1000` y
  `MAX_IMAGES_PER_RUN=50` (`kit_settings.py:31-32`). Los horarios salen de `kit_publish.DEFAULT_SLOTS`
  (`:16-20`) y del slot que crea `beat_panel.add_channel` (`:200-201`). El repo sale de
  `beat_actions.TRUSTED_REPOSITORY` (`:9`).
- **Los workers no leen `ajustes.json`.** Todo lo que necesitan se sigue proyectando:
  - `beatstars.profile_url` → `/type-beats/config.json` `beatstars_profile_url`, que ya es global (`beat_daily.py:59`).
  - El tope de gasto es **por canal** en `kit_preview.spend`. `ajustes.json` solo aporta el valor inicial
    para canales nuevos.
- No se guardan secretos en ningún documento de `/automatizacion`.

---

## 9. Recomendaciones

1. **`config/client_secret.json` → llavero (`keyring`, WinVaultKeyring).** Mide 402 B, así que entra.
   - Es un secreto de la app OAuth «Escritorio», y solo lo usa el escritorio para el flujo de conexión
     (`youtube.py:15`). Los workers no lo necesitan, porque el token JSON ya trae `client_id`/`client_secret`.
   - Guardarlo en Dropbox lo expone a cualquier credencial de Dropbox, incluido el refresh token del worker que
     está en GitHub. Eso amplía el radio de daño sin ganar nada.
   - Fallback: un archivo en `%APPDATA%\TypeBeat\` con ACL del usuario, nunca dentro del repo.
   - Usar el mismo llavero para el token de YouTube recién emitido: se sube con `gh secret set` por stdin y no
     hace falta que persista en disco.
   - Agregar `keyring` a `requirements.txt` (no hace falta en `requirements-worker.txt`).
2. **`core/kit_store.py` / `library.db`: ya no hacen falta en el escritorio.**
   - El worker usa `CloudStore`/`kit_state` (`run_kit_weekly.py:165`, `kit_week.py:282`, `kit_state.py:2-4`).
   - `kit_store` solo queda como default de `kit_publish.record_run` (`kit_publish.py:12,221`) y en
     `run_kit_preview.py` (`:22`).
   - `library.py` sigue cargado solo por `upload_worker.py` (que importan los diálogos por `ConnectChannelWorker`),
     `history_import`, `dropbox_client.import_files` (sin llamadores vivos) y `sections.section_library_kind`
     (sin llamadores).
   - Propuesta: mover `ConnectChannelWorker` a un módulo propio, que `kit_publish` exija `store` explícito,
     retirar `run_kit_preview.py` (lo reemplaza el dry-run en Actions) y después borrar `kit_store`, `library.py`,
     `shorts_store`, `history_import` y `library.db`. **No hace falta migración SQL**, porque el estado vivo ya
     está en Dropbox.
3. **Orden sugerido de fases** (una por sesión, según CLAUDE.md):
   1. `canales.json` + `ajustes.json`, con el lector y escritor en `core/` y el import inicial desde
      `app_config` + `/type-beats/config.json` + registro de Kits. En esta fase se corrige `WyreSounds`
      (loops, legacy_default).
   2. `beat_settings.validate` y `beat_remote_form` validan contra `canales.json`; se rechaza media local.
   3. `ChannelManager` escribe en `canales.json` y proyecta plantillas a los dos documentos de los workers
      (esto cierra la inconsistencia 6).
   4. `gh_status` reemplaza `automation_status` para la lectura; `keyring` reemplaza `tokens/`.
   5. Dry-run por `gh workflow run`; se quitan la rama local de `run_kit_weekly.py:341` y `run_kit_preview.py`.
   6. Limpieza: secretos huérfanos (con confirmación), `library.db`/`kit_store`, `tokens/*.py`.
