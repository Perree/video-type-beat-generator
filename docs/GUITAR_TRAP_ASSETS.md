# Guitar trap — materiales del nuevo canal

Preparación solicitada el 7/11/2026. `guitar-trap` es un identificador provisional;
todavía no identifica un canal de YouTube ni una automatización activa.

Actualización: el usuario identificó Make You Beats,
`UCwo47db3RCos_jTzzr1nsdg`, y pidió publicación diaria. OAuth confirmó ese ID
exacto; credenciales en memoria y GitHub Secrets del slug `guitar-trap`.
Se conserva el slug para no mover los materiales que ya estaban verificados.

## Origen y destino

- Videos originales: `C:\Users\matia\Videos\4K Video Downloader+`.
- Miniaturas originales: `C:\Users\matia\Downloads\Miniaturas`.
- Dropbox: `/Soft Projects/Type Beat Generator/contenido/canales/guitar-trap`.
- Subcarpetas: `fondos` para siete videos y `miniaturas` para 35 imágenes JFIF.
- Se copian originales completos, sin recortar, convertir ni borrar archivos locales.
- Sin emparejamiento fijo entre videos y miniaturas: el usuario no indicó parejas.

## Referencia editorial

Las ocho capturas del usuario muestran principalmente Koena y ejemplos de Volto
y SoulfulWaves. Koena usa `[FREE] Guitar x {artistas} Type Beat - "{name}"`,
miniaturas fotográficas verticales con bandas negras y sin títulos superpuestos.
Las capturas del reproductor también muestran escenas distintas a la miniatura.
No se atribuye el rendimiento observado a esos elementos.

Selección solicitada: Juice WRLD, guitar y trap guitar. El usuario permite ampliar
con etiquetas musicales compatibles; las etiquetas concretas y sus coincidencias
quedan pendientes de contrastar con el catálogo antes de configurar la selección.
No asignar artistas adicionales a todos los beats por esta referencia visual.

## Verificación de la copia

42 archivos copiados y releídos en Dropbox: siete videos y 35 miniaturas,
542.378.546 bytes en total. Tamaño y content hash de cada archivo coinciden con
el original local. Las 35 imágenes pasan la verificación de Pillow; ffprobe
identifica una pista de video y duración positiva en cada uno de los siete videos.
No se realizó una decodificación completa ni un render de prueba.
Inventario detallado local en `tokens/guitar_trap_assets.json` (fuera de Git).

## Trabajo pendiente

Esta fase prepara los materiales en Dropbox. Quedan pendientes el nombre/handle
del canal, selección definitiva del catálogo, configuración de títulos y tags,
calendario, emparejamiento/rotación audiovisual y un render de prueba.
No activa publicaciones ni modifica los canales existentes.

## Automatización preparada

- Configuración en `docs/guitar-trap.channel.json`, copiada y releída en Dropbox.
- Frecuencia solicitada: diaria. Horario inicial adoptado: 18:00 Buenos Aires;
  escalonado habitual de subidas de 2–4 días y búfer de 14 días.
- Modo de selección optativo `guitar-trap:v1`: Juice WRLD y artistas de la
  referencia por etiqueta real, guitarras, emo/emo rap/emo trap, pain y melodic trap.
  Sad, emotional o trap solos no incorporan beats; se excluyen mezclas con Afro,
  House, Reggaeton, Dancehall, Jersey, EDM, Techno, Pop, Indie y Rock.
- Catálogo público consultado: 1.151 beats, 611 elegibles; todos sus snapshots
  generados y revalidados. Los demás filtros exactos y modos siguen intactos.
- Títulos `[FREE] {style} Type Beat - "{name}"`; Guitar y artistas solo cuando
  las etiquetas correspondientes existen, sin añadir Hurricane Wisdom/Nino Paid
  a un beat que únicamente tenga Juice WRLD. Nombre real, BPM/key disponibles,
  coproductores del título y condiciones propias de MatWyre en la descripción.
- Enlace individual corto cuando existe; fallback a la URL real del catálogo
  únicamente si su ID coincide con el beat. Nunca reconstruye un slug ficticio.
- Montaje 1080p/30 FPS con fragmentos de 3–6 s; audio de los videos fuente
  descartado. Rotación independiente de las 35 miniaturas, foto completa con
  bandas negras, sin texto agregado. Se intentan subir como miniaturas propias.
- Primera muestra completa de 204,0163 s validada. Una captura mostró créditos
  incrustados en el video fuente; se añadió el margen optativo de 15 s al inicio
  y al final, solo configurado para este canal. No garantiza eliminar textos que
  estén en el centro de un videoclip. Fuentes demasiado cortas se omiten.
- Las siete fuentes suman más de 512 MiB: el límite existente puede omitir una
  fuente por montaje; no se elevó ese límite ni el cupo diario de subidas.

La preparación remota permanece pausada hasta terminar las comprobaciones.
