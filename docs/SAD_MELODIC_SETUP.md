# Canal sad melodic — preparación

Destino indicado: https://www.youtube.com/channel/UCE-BtAOt98IH0hTc4ceuYsQ/
Perfil: `docs/sad-melodic.channel.json`. `sad-melodic` es una clave interna provisional.

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

## Pendiente para activar

1. Imágenes recibidas y configuradas (2026-11-08): 30 JFIF de
   `C:\Users\matia\Downloads\fondos`, copiadas sin modificar a
   `/Soft Projects/Type Beat Generator/contenido/canales/sad-melodic/fondos`.
   Copia local de Dropbox verificada por SHA-256; sincronización remota aún no comprobada.
   Las 30 pasan decodificación y composición del render; originales sin modificar.
   Algunas incluyen iconos de redes dentro del original, conservados sin retoque.
2. Incorporar el perfil al registro/configuración remotos con la clave definitiva, preservando
   los demás canales, conectar OAuth y comprobar que pertenece al ID de destino.
3. Verificar las condiciones FREE de los beats seleccionados y revisar un render real.
4. Simular con el catálogo real antes de habilitar `active` y el worker de publicación.

Esta fase prepara código y perfil local en pausa. No descarga beats, no modifica la configuración
remota y no sube videos. No hay programación de publicaciones activa todavía.

Vista previa local: `exported_videos/sad-melodic-preview/preview.mp4` (3 s, audio silencioso
de prueba, H.264 1920×1080); `thumbnail.jpg` usa la misma composición. No es un beat publicado.
Los originales quedan en Downloads y las imágenes no se agregan a Git.
