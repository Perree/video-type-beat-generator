# Plan: automatizar publicación de type beats (biblioteca + BPM/key + YouTube + Dropbox)

## Context
La app (PyQt, `main.py` 2055 líneas) genera videos con FFmpeg pero la publicación y la promoción son manuales.
Objetivo: reducir tiempo de creación → subida. Dolor principal: subir a YouTube y armar la descripción
(link BeatStars, BPM, key). Además: navegar Dropbox, guardar beats con metadata, y saber hace cuánto se subió cada uno.
Restricciones del usuario: varias cuentas de Google distintas; pocos tokens (plan barato de Claude) → fases chicas,
una sesión por fase, prompts cortos y específicos.

Código existente a reutilizar (`main.py`): `VideoGeneratorWorker` (L147, genera el video; recibe `beats_info`),
`ChannelManager` (L410, canales/grupos en `config/app_config.json`), `MainWindow._load_beats_from_files` (L1178),
`_assign_channel_to_beats` (L1433), `_process_finished` (L1905, punto donde enganchar la subida), `EditBeatDialog`
(`edit_beat_dialog.py`, ideal para editar BPM/key/link).

## Reglas de ahorro de tokens (aplican a todas las fases)
- Una fase = una sesión nueva. No arrastrar contexto viejo (`/clear` entre fases).
- No pedir "analiza todo el proyecto": en cada prompt nombrar los archivos y líneas exactos.
- Módulos nuevos chicos en `core/` (no seguir engordando `main.py`); así Claude lee archivos pequeños.
- Pedir primero un plan de 5 líneas y recién después el código; pedir diffs, no reescrituras completas.
- Modelo: **Sonnet** para casi todo; **Haiku** para tareas mecánicas (Fase 0, plantillas, tests simples);
  **Opus** solo si Sonnet falla 2 veces en algo difícil (OAuth/auditoría YouTube).
- Hacer commit al terminar cada fase para poder volver atrás.

## Fase 0 — Limpieza del repo (Haiku, ~baratísima) ✅ COMPLETADA
Sacar `ffmpeg-8.0/` y `bin/ffmpeg.exe` del repo (`git rm --cached` + `.gitignore`), unificar PyQt5/PyQt6 en
`requirements.txt` según lo que `main.py` importa realmente, quitar rutas `C:/Users/...` de `config/app_config.json`
(mover a un archivo no versionado).
Prompt: "En este repo: (1) agrega ffmpeg-8.0/ y bin/ffmpeg.exe a .gitignore y quítalos del índice con git rm --cached;
(2) revisa los imports de main.py y corrige requirements.txt para que diga PyQt5 o PyQt6 según corresponda;
(3) haz que config/app_config.json no se versione con rutas personales (deja un app_config.example.json).
No toques nada más. Muéstrame el plan antes de ejecutar."

## Fase 1 — Biblioteca local + historial (Sonnet) — la base ✅ COMPLETADA
- `core/library.py`: SQLite `library.db`. Tablas `beats` (id, nombre, ruta, hash, bpm, key, beatstars_url, notas, creado)
  y `uploads` (beat_id, canal, grupo, youtube_id, url, título, subido_en, estado).
- Importar beats copiando el audio a `library/` (dedupe por hash).
- Vista "Biblioteca" (nuevo diálogo) con columnas: nombre, BPM, key, "subido hace X" por canal, filtros
  (nunca subido / sin subir al canal X / >6 meses).
- Función `humanize_ago(fecha)` ("hace 3 meses").
- Enganchar en `_load_beats_from_files` y `_process_finished`.
Prompt: "Crea core/library.py con SQLite (tablas beats y uploads, esquema en PLAN). Implementa import_beat(path),
list_beats(filtros), record_upload(...), humanize_ago(). Luego agrega un diálogo library_dialog.py que liste beats y
permita seleccionarlos para el flujo existente de main.py (_load_beats_from_files, línea ~1178). Pregunta antes de
cambiar firmas existentes. Sin tocar la generación de video."

## Fase 2 — BPM/key + link BeatStars + plantilla de descripción (Sonnet; plantillas con Haiku) ✅ COMPLETADA
- `core/audio_analysis.py`: BPM y key con `librosa` (cargar solo ~60 s del audio para rapidez), corrigiendo
  doble/mitad de tempo. Resultado siempre editable.
- Ampliar `edit_beat_dialog.py` con campos BPM, key y link BeatStars (se guardan en la biblioteca).
- `core/description.py`: plantilla por canal (guardada en `app_config.json`) con variables
  `{name} {bpm} {key} {beatstars_url} {tags}` + redes/hashtags del canal.
Prompt: "Crea core/audio_analysis.py: analyze(path)->(bpm,key) con librosa sobre los primeros 60 s. Agrega campos bpm,
key y beatstars_url a edit_beat_dialog.py (pre-rellenados, editables) y guárdalos con core/library.py. Crea
core/description.py que renderiza una plantilla por canal con {name},{bpm},{key},{beatstars_url}. Muestra una vista
previa de la descripción en el diálogo."

## Fase 3 — Subida a YouTube, multi-cuenta (Sonnet; Opus solo si OAuth se complica) ✅ COMPLETADA
(Implementado: `core/youtube.py`, `core/upload_worker.py`, guía en `docs/YOUTUBE_SETUP.md`.
Pendiente del usuario: pasos de Google Cloud y prueba real F3 con un canal de prueba.)
Pasos manuales previos del usuario (documentar en la fase): crear proyecto en Google Cloud, activar YouTube Data API v3,
crear credenciales OAuth "Escritorio", pasar la app a "In production", agregar cada cuenta como usuario de prueba,
(más adelante) pedir auditoría de la API — hasta entonces los videos suben **privados** y se publican a mano en Studio.
- `core/youtube.py`: un token por canal en `tokens/<canal>.json` (no versionado); `connect_channel()`, `upload()`
  con título, descripción, tags, miniatura, `privacyStatus`/`publishAt`.
- Botón "Conectar canal" en `ChannelManager` y checkbox "Subir a YouTube al terminar" en `MainWindow`
  (`_process_finished`, L1905); registrar en `uploads`.
- Aviso si el beat ya fue subido a ese canal (usa Fase 1).
Prompt: "Implementa core/youtube.py con google-api-python-client: connect_channel(nombre) guarda token en
tokens/<nombre>.json, upload(video, título, descripción, tags, thumbnail, privacy). Agrega botón 'Conectar canal'
en ChannelManager (main.py L410) y la subida opcional en _process_finished (L1905), registrando en core/library.py.
Antes de subir, avisa si el beat ya está en ese canal. Verifica en la documentación oficial el costo actual de cuota."

## Fase 4 — Dropbox por API (Sonnet) ✅ COMPLETADA
(Implementado: `core/dropbox_client.py`, `dropbox_browser_dialog.py`, botón "Dropbox..." en la biblioteca, guía en `docs/DROPBOX_SETUP.md`. Pendiente del usuario: crear la app de Dropbox y prueba real F4.)
- `core/dropbox_client.py`: OAuth con PKCE (refresh token), `list_folder`, `download`.
- Diálogo navegador de carpetas Dropbox (solo audio: mp3/wav) con selección múltiple → descarga e importa a la
  biblioteca (Fase 1).
Prompt: "Implementa core/dropbox_client.py (SDK oficial, OAuth PKCE con refresh token) y dropbox_browser_dialog.py:
árbol de carpetas, filtrar mp3/wav, selección múltiple y botón 'Importar a biblioteca' que descarga y llama a
library.import_beat()."

## Fase 5 — Importar historial existente de YouTube (Haiku/Sonnet) ✅ COMPLETADA
`videos.list` por canal para importar títulos/fechas ya publicados a `uploads` y emparejar con beats por nombre;
refrescar vistas (cuota casi nula). Cierra el "hace cuánto" también para videos anteriores a la app.

## Fase 6 — Extras opcionales (según presupuesto de tokens)
Miniaturas automáticas (Pillow), carpeta vigilada (`watchdog`), modo CLI, aceleración GPU `h264_nvenc`,
versión vertical 9:16 para Shorts, partir `main.py` en módulos.

## Verificación por fase
- F0: `git status` limpio y la app abre (`python main.py`).
- F1: importar 2 beats, reabrir la app y ver que persisten; importar el mismo audio dos veces no duplica.
- F2: analizar un beat con BPM/key conocidos y comparar; ver la descripción renderizada con las variables.
- F3: conectar un canal de prueba, subir un video como privado, comprobar el registro en `uploads` y el aviso de duplicado.
- F4: conectar Dropbox, importar un lote y confirmar los archivos en `library/`.
- F5: el "hace cuánto" aparece también en beats anteriores a la app.
