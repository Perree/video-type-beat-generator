# wavybeatz — automatización diaria

Destino indicado: https://www.youtube.com/channel/UCE-BtAOt98IH0hTc4ceuYsQ/
Perfil: `docs/sad-melodic.channel.json`. `sad-melodic` es la clave interna del canal wavybeatz.

- Todos los días a las 20:00 de Argentina (UTC-3); calendario del worker en Buenos Aires.
- Selección OR por tags exactos, ignorando mayúsculas y espacios externos:
  `juice wrld`, `iann dior`, `the kid laroi`, `sad beat`.
  Un beat necesita al menos uno, no los cuatro. El catálogo existente sigue siendo la fuente.
- Título según los artistas realmente etiquetados (hasta dos en el título);
  prefijo Sad solo con `sad beat`. Si solo tiene ese tag: `(FREE) Sad Type Beat - "Nombre"`.
- Imagen fija centrada en 1920×1080, con franjas negras constantes de 344 px por lado
  (`image_fit=fixed_bars`). Área central de 1232×1080, sin texto añadido ni deformación;
  se recorta desde el centro cuando la proporción de la imagen lo requiere.
  No requiere carpeta de miniaturas: `custom_thumbnail=false` deja a YouTube usar un cuadro
  del video, idéntico al fondo fijo. El render también produce JPG de la misma composición.
- Descripción en inglés, enlace individual resuelto por el pipeline, BPM/tono cuando constan
  en el título y hashtags de los tags reales. No se inventan mail, tienda ni coproductores.
  La plantilla limita FREE al uso no comercial y remite a las condiciones de cada beat.

## Activación (2026-11-08)

1. Imágenes recibidas y configuradas (2026-11-08): 30 JFIF de
   `C:\Users\matia\Downloads\fondos`, copiadas sin modificar a
   `/Soft Projects/Type Beat Generator/contenido/canales/sad-melodic/fondos`.
   Carga directa verificada en Dropbox: 30 archivos `image_01.jfif` a `image_30.jfif`,
   descargados de vuelta y comparados byte por byte con los originales.
   Las 30 pasan decodificación y composición del render; originales sin modificar.
   Algunas incluyen iconos de redes dentro del original, conservados sin retoque.
2. Perfil incorporado al registro/configuración remotos. OAuth verificado: wavybeatz,
   `UCE-BtAOt98IH0hTc4ceuYsQ`. Credenciales propias del slug en el entorno kit-weekly.
3. Catálogo real revisado: 1.151 beats, 549 coinciden con el filtro; 549 snapshots SEO válidos.
   Vista previa FFmpeg revisada. La plantilla remite a las condiciones individuales de licencia.
4. CLI real en simulación: planned=14, eligible=4; failed/unknown/orphan/expired/blocked=0.
   Perfil y registro activados; slug agregado a BEAT_CHANNELS preservando los otros doce.

Publicación habilitada para todos los días a las 20:00 Argentina. El worker se ejecuta diariamente
a las 19:00 Argentina y sube por anticipado según el escalonado de 2 a 4 días; el límite compartido
con los demás canales sigue vigente. Primera corrida real: `42492174737` (resultado abajo).
Respaldos y reportes privados en `tokens/sad_melodic_*`, fuera de Git.

### Resultado de la primera corrida

- GitHub Actions: https://github.com/Perree/video-type-beat-generator/actions/runs/42492174737
  completada con éxito; 398 pruebas en el worker.
- planned=14, eligible=4, uploaded=4; failed/unknown/orphan/expired/blocked/budget/
  calendar_unavailable/thumbnail_failed=0.
- Programados a las 20:00 Argentina: 08/11 `ZFZhrroc2jc`, 09/11 `QOUQziC3YzQ`,
  10/11 `IBhEfNGIks8`, 11/11 `Quk0nAgYtz0` (2026).
- Las diez reservas restantes del búfer esperan su ventana normal de subida anticipada.

Vista previa local: `exported_videos/sad-melodic-preview/preview.mp4` (3 s, audio silencioso
de prueba, H.264 1920×1080); `thumbnail.jpg` usa la misma composición. No es un beat publicado.
Los originales quedan en Downloads y las imágenes no se agregan a Git.
