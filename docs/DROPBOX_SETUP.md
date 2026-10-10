# Configurar Dropbox (una sola vez)

1. https://www.dropbox.com/developers/apps → **Create app** → *Scoped access* → *Full Dropbox*
   (o *App folder* si preferís limitarlo).
2. Pestaña **Permissions**: activá `files.metadata.read` y `files.content.read` → **Submit**.
3. Pestaña **Settings**: copiá el **App key** (no hace falta el App secret: se usa PKCE).
4. Creá `config/dropbox_app.json` (no se versiona) con: `{"app_key": "TU_APP_KEY"}`
5. `pip install -r requirements.txt`

## Usar
Biblioteca → **Dropbox...** → **Conectar Dropbox** → autorizá en el navegador y pegá el código.
El refresh token queda en `tokens/dropbox.json` (no versionado), así que no se vuelve a pedir.
Navegá con doble clic, seleccioná varios mp3/wav y **Importar a biblioteca**: se descargan y se
copian a `library/` (dedupe por hash). El diálogo de biblioteca sigue mostrando solo audio.

## Loop kits (previews)

`kit_preview.dropbox_root` tiene una subcarpeta por pack. En la **raíz** de esa carpeta van los
loops (mp3/wav). Un archivo de esa misma raíz cuyo nombre contiene `preview` (sin distinguir
mayúsculas) es la pista completa del pack, no un loop. No se recorren `stems/` ni `layers/`.
Imágenes: subcarpeta `images/` del pack (jpg, jpeg, png, webp). Si esa carpeta no existe, se
usan los archivos de `kit_preview.local_images_root/<nombre-del-pack>/` en disco.
