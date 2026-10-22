# Credenciales solo-nube

Desde 2026-10-18 la app de escritorio **no guarda credenciales en archivos**. En cada PC se conectan
solo dos cosas; todo lo demás va directo a GitHub Secrets del Environment `kit-weekly` (y a cada
`kit-weekly-<slug>`) y nunca toca el disco.

| Qué | Dónde vive | Cómo se conecta |
|---|---|---|
| Dropbox (app «App folder» del worker) | Llavero de Windows, servicio `video-type-beat-generator` (`dropbox_app_key`, `dropbox_refresh_token`) | Conexiones → «Esta PC» → Autorizar Dropbox (PKCE) |
| GitHub | Sesión de `gh auth login` | En una terminal: `gh auth login` |
| `client_secret.json` de Google (OAuth «Escritorio») | Llavero (`youtube_client_secret`); fallback de solo lectura `%APPDATA%\TypeBeat\client_secret.json` | Conexiones → «Importar client_secret.json…» (el archivo original no se toca) |
| Token de YouTube por canal | `BEAT_YT_TOKEN_JSON_<SLUG>` / `KIT_YT_TOKEN_JSON` | «Conectar YouTube y subir a GitHub»: OAuth en memoria y `gh secret set` por stdin |
| Telegram, Notion, claves LLM e imágenes | `KIT_*` / `BEAT_NOTION_*` | Se escriben una vez desde Conexiones; la UI muestra «cargado ✓ (fecha)» |

- Código: `core/cloud_login.py` (llavero, Dropbox, client_secret), `core/gh_status.py` (lectura de
  `gh secret list --json name,updatedAt` y `gh variable get` con caché en memoria de 60 s; escritura
  por stdin), `core/automation_status.py` (semáforos y checklists), `core/cloud_login_box.py` (UI).
- Ningún valor viaja como argumento de `gh`, se imprime, se loguea ni aparece en un mensaje de error.
- Los compartidos de kits se escriben en `kit-weekly` y en cada `kit-weekly-<slug>` que exista. Como
  GitHub no devuelve valores, un Environment nuevo no se puede completar copiando desde otro: después
  de crearlo, volvé a guardar Telegram/Notion/claves en Conexiones. Si no se pueden listar los
  Environments, no se guarda nada.
- **Dropbox del worker ≠ Dropbox de esta PC.** El token del llavero nunca se copia a GitHub. Para el
  worker: «Autorizar Dropbox» → pegar un código nuevo → «Subir al worker (GitHub)»; va a todos los
  Environments de kits y no pasa por el llavero. Cada token se revoca por separado.
- **A qué canal va cada secreto.** Beats: `BEAT_*_<SLUG>` solo se escribe si el slug es el del registro
  para ese canal y no lo usa otro canal (config o registro). Kits: `kit-weekly` solo acepta al canal
  por defecto (`legacy_default` del registro, o `kit_preview.channel` del config guardado); el worker
  no controla el dueño de ese Environment. YouTube: después del OAuth la app muestra la cuenta
  autorizada y pide confirmar antes de subir; si el canal tiene `youtube_channel_id` y no coincide,
  no sube nada.
- Todas las llamadas a `gh` van con `--repo Perree/video-type-beat-generator`
  (`beat_actions.TRUSTED_REPOSITORY`), sin depender de los remotos de la carpeta.
- El llavero se rechaza si el backend guarda en un archivo (`keyrings.alt`, `Plaintext*`) o no guarda
  (`fail`, `null`). «Desconectar» comprueba que la entrada ya no esté. El logger
  `google_auth_oauthlib.flow` queda en WARNING: su INFO incluye `GET /?code=…`.
- `local_transport` (Beats) y `kit_cloud.client()` en el escritorio leen solo del llavero; Beats cae a
  `BEAT_DROPBOX_*` del entorno. El runner (`kit_cloud.bootstrap_credentials`) no cambió.
- `scripts/beat_secrets_sync.py` y `scripts/kit_secrets_sync.py` conservan su CLI. Sin
  `--yt-token-file` autorizan YouTube por OAuth en memoria; Dropbox sale del entorno o del prompt
  (nunca del llavero) y ya no leen `tokens/` por defecto (`--shared-file` sigue funcionando si se
  pasa explícitamente). `kit_secrets_sync --default-channel <canal>` protege `kit-weekly`.
- El llavero (Credential Manager) admite unos 1280 caracteres por entrada; se valida antes de guardar.

## Archivos de `tokens/` y `config/` que quedan obsoletos

La app ya no los lee ni los escribe. **No se borraron**: podés borrarlos vos cuando confirmes que
Conexiones muestra todo en verde.

| Archivo | Reemplazo |
|---|---|
| `tokens/dropbox_worker.json` (si existe) | Llavero (`dropbox_*`) |
| `tokens/dropbox.json` | Llavero (Dropbox del panel de kits también usa el llavero) |
| `tokens/<canal>.json` (`ey mat.json`, `mattwyyre.json`, `WyreSounds.json`) | Secretos `BEAT_YT_TOKEN_JSON_<SLUG>` / `KIT_YT_TOKEN_JSON` |
| `tokens/beat_secrets.json`, `tokens/kit_secrets.json` (si existen) | Secretos `BEAT_NOTION_*` / `KIT_*` |
| `config/client_secret.json` | Llavero (`youtube_client_secret`), después de importarlo |
| `config/dropbox_app.json` | El app key se guarda en el llavero junto con el refresh token |

Siguen usándose: `tokens/seo_reports/` (informes SEO locales) y los scripts sueltos `tokens/*.py`
(de una sola vez, fuera del alcance de esta fase). `scripts/kit_dropbox_auth.py` y
`youtube.connect_channel` todavía escriben archivos si se los llama a mano; la app ya no los usa.

## Validación

```bash
py -3 scripts/smoke_cloud_credentials.py
```
Simula `gh` y el llavero; falla si se crea o abre un archivo en `tokens/` o `config/`, si un secreto
viaja como argumento o aparece en la salida, en los logs o en un mensaje de excepción.
