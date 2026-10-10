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

`kit_preview.dropbox_root` es la carpeta de la tienda: adentro van las categorías
(`kit_preview.scan_folders`) y, en cada una, una carpeta por kit con sus loops (mp3/wav) en
`LOOPS/` o, si no la tiene, en su raíz. Los archivos con `tag` o `preview` en el nombre se
ignoran y no se recorren las subcarpetas de drum kits, midis, starters, vocals, phrases ni stems.
Imágenes: subcarpeta `images/` del kit (jpg, jpeg, png, webp). Si esa carpeta no existe, se
usan los archivos de `kit_preview.local_images_root/<nombre-del-kit>/` en disco. El detalle
está en [KIT_PREVIEW.md](KIT_PREVIEW.md).
