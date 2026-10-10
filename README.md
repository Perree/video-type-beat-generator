# Type Beat Video Generator

![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-blue.svg)
![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![UI](https://img.shields.io/badge/UI-PyQt5-green.svg)

Desktop app (PyQt5 + FFmpeg) that turns beats and loop kits into YouTube videos: it renders them, uploads them to your channels and can schedule recurring preview videos of loop kits. Documentation is in Spanish.

> **Licencia: source-available, no open source (OSI).** El código es público para que lo leas, lo uses y lo modifiques con fines **no comerciales**. El uso comercial queda reservado al autor. Ver [Licencia](#licencia).

## Qué hace

- **Beats → video.** Genera videos 16:9 (1920x1080, H.264 + AAC) a partir de un audio y una imagen o un video en loop, sin repetir contenido.
- **Canales y grupos.** Organiza beats por canal de YouTube y grupo (género/estilo) con sus propias imágenes, plantillas de título y descripción.
- **Biblioteca local.** Guarda cada beat con BPM, tonalidad y link de la tienda, y recuerda qué se subió a cada canal para avisar si ya existe.
- **Subida a YouTube.** Multicuenta, con descripción por plantilla, miniatura y registro de cada subida.
- **Dropbox.** Importa audios directamente desde carpetas de Dropbox.
- **Loop kits.** Una sección aparte para packs de loops, con previews automáticos ([ver docs/KIT_PREVIEW.md](docs/KIT_PREVIEW.md)).
- **Shorts / clips verticales 9:16.** Recorte vertical con subtítulos (en desarrollo).

## Requisitos

- Windows 10/11 (probado ahí; el código es Python y puede correr en otros sistemas).
- Python 3.10 o superior.
- [FFmpeg](https://ffmpeg.org/download.html) en el `PATH` o copiado en `bin/` (`bin/ffmpeg.exe` y `bin/ffprobe.exe`). **No viene incluido en el repo.**

## Instalación

```bash
git clone https://github.com/Perree/video-type-beat-generator.git
cd video-type-beat-generator

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux / macOS

pip install -r requirements.txt
python main.py
```

En Windows también podés usar `run_app.bat`.

La primera vez la app crea las carpetas que necesita. Copiá `config/app_config.example.json` a `config/app_config.json` y editalo con tus canales.

## Credenciales: traé las tuyas

Este repositorio **no incluye ninguna clave, token ni credencial**. Cada persona usa las suyas:

| Servicio | Qué necesitás | Guía |
|---|---|---|
| YouTube | Un proyecto propio de Google Cloud con YouTube Data API v3 y un cliente OAuth de escritorio (`config/client_secret.json`) | [docs/YOUTUBE_SETUP.md](docs/YOUTUBE_SETUP.md) |
| Dropbox | Una app propia de Dropbox (`config/dropbox_app.json`) | [docs/DROPBOX_SETUP.md](docs/DROPBOX_SETUP.md) |

Estos archivos y la carpeta `tokens/` están en `.gitignore`. **Nunca los subas.**

Importante sobre YouTube: los proyectos de Google Cloud nuevos que no pasaron la auditoría de YouTube API **suben los videos en privado**, y puede que la programación (`publishAt`) sea rechazada. La app lo maneja dejando el video privado para que lo publiques desde YouTube Studio. Detalles en la guía.

## Loop kits: previews automáticos

Elige un pack de Dropbox, arma un video con imagen fija y audio, y lo sube al canal de loop kits en el próximo horario configurado.

```bash
python scripts/run_kit_preview.py --dry-run   # solo muestra qué haría
python scripts/run_kit_preview.py             # corrida completa
```

Guía completa, incluida la programación con el Programador de tareas de Windows: [docs/KIT_PREVIEW.md](docs/KIT_PREVIEW.md).

## Verificación

Los scripts `scripts/smoke_*.py` son pruebas de humo locales, sin red. Por ejemplo:

```bash
python scripts/smoke_kit_schema.py
python scripts/smoke_kit_trim.py
```

## Estructura

```
main.py                 App principal (PyQt5)
core/                   Lógica en módulos chicos: biblioteca, YouTube, Dropbox, kits, clips...
scripts/                Entry points por CLI y pruebas de humo
docs/                   Guías de configuración
config/                 Configuración (solo el .example va al repo)
overlays/               Recursos gráficos
```

## Privacidad y términos

Páginas públicas de la app, necesarias para el consentimiento de Google OAuth:

- [Inicio](https://perree.github.io/video-type-beat-generator/)
- [Política de privacidad](https://perree.github.io/video-type-beat-generator/privacy.html)
- [Condiciones del servicio](https://perree.github.io/video-type-beat-generator/terms.html)

## Contribuir

Los issues son bienvenidos. Si enviás un pull request, aceptás que tu aporte se publique bajo esta misma licencia y que el autor pueda usarlo en versiones comerciales del proyecto.

## Licencia

[PolyForm Noncommercial License 1.0.0](LICENSE). En resumen:

- Podés usarlo, estudiarlo y modificarlo para **fines no comerciales** (personal, educativo, hobby, investigación).
- **No** podés venderlo, ofrecerlo como servicio ni usarlo en un negocio sin permiso del autor.
- El software se ofrece "tal cual", sin garantías.

Para uso comercial, contactá al autor por su [perfil de GitHub](https://github.com/Perree).

Este proyecto no está afiliado a YouTube, Google, Dropbox ni PayHip. Es un resumen informativo, no asesoramiento legal.
