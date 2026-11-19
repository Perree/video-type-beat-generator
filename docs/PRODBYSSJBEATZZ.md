# prodbySSJBeatzz — canal de type beats melódicos

Canal nuevo inspirado en prodbyDSI (@prodbydsix), con identidad propia (logo SSJ BEATZ).
Ficha borrador: `docs/prodbyssjbeatzz.channel.json` (pausada, sin YouTube conectado,
todavía no cargada en la configuración de Dropbox). Inventario: `docs/prodbyssjbeatzz.assets.json`.

## Referencia del usuario (2026-11-19)

- Capturas del canal prodbyDSI: títulos `[FREE] Polo G Type Beat 2025 "Nombre"` y
  `[FREE] Polo G x YFG Fatso Type Beat "Nombre"`; descripción con link de compra,
  "FREE FOR NON PROFIT ONLY", BPM/key, coproductores, hashtags y bloque de tags.
- Grabación de la intro de DSI: logo blanco sobre negro, entra con desenfoque, pulsa y
  escala ~3–4 s, luego corte a clips de video musical con barras negras laterales.
- Pedidos: títulos siempre con dos artistas; año 2026/2027 alternado y sin 2026 desde 2027;
  artista principal fijo por mes (mes 1 Polo G, mes 2 Lil Tjay) para comparar rendimiento;
  miniaturas con bordes negros y test 7 con logo / 7 sin logo en bucle; no copiar el canal.

## Decisiones de la Fase A

- Cuenta BeatStars `matwyre`; 1 video diario 18:00 Argentina (por defecto, sin objeción).
- Selección por 26 tags: alias de Juice WRLD, Polo G, Iann Dior, The Kid Laroi, Scorey,
  Lil Tjay y Toosii, con y sin "type beat".
- Catálogo del 19/11/2026: 1.151 beats, **583 elegibles**. Por artista en tags: Juice WRLD 527,
  Iann Dior 227, The Kid Laroi 185, Scorey 4, Polo G 3, Lil Tjay 1, Toosii 0. El artista
  principal del título es fijo por mes; el segundo saldrá de los tags (casi siempre
  Juice WRLD, Iann Dior o The Kid Laroi).
- Clips: 8 videos de `Videos\4K Video Downloader+\polog channel` (Polo G y Scorey)
  recodificados a 1080p sin audio y cortados en segmentos de 12 s (sin los primeros y
  últimos 10 s). El montaje toma un fragmento por fuente y hasta 12 fuentes, así que
  muchos segmentos chicos dan más variedad y ~50 MB de descarga por render.
  Un segmento con tramo negro (blackdetect) se descartó: quedan 83.
- Miniaturas: 29 fotos de `Downloads\polo channel` normalizadas a JPG.
- Logo: captura recibida (1672×941, cromado sobre negro) guardada como PNG. Para la
  miniatura se mezclará en modo `screen` para que el negro no tape la foto.

Carpetas Dropbox bajo `/Soft Projects/Type Beat Generator/contenido/canales/prodbyssjbeatzz/`:
`clips/`, `miniaturas/`, `logo/`. Cada archivo se subió sin sobrescribir y se descargó de
vuelta para comparar byte por byte.

## Decisiones de la Fase B

- Intro `core/beat_intro.py`: 3,5 s, logo al 43 % del ancho sobre negro puro (el fondo gris
  texturado del PNG se lleva a negro por niveles), desenfocado → nítido, zoom + pulso y corte.
  Cacheada por canal + hash del logo. El audio del beat suena desde el segundo 0 sobre la intro.
- `video_fit = fixed_bars`: clips recortados al centro a 1232×1080 con franjas negras de 344 px.
- `source_trim_seconds` pasó a 0: los segmentos ya excluyen los primeros/últimos 10 s del video.

## Campos de la ficha que dependen de fases siguientes

| Campo | Fase |
|---|---|
| `visual.intro` (logo animado) y `visual.video_fit = fixed_bars` para video | B ✅ |
| `seo.title_mode = ssj_v1`, `main_rotation`, `test_start`, descripción | C ✅ |
| `visual.thumbnail_logo.cycle = [7, 7]` | D |
| `youtube_channel_id`, `active`, alta en config/registro Dropbox | E |
