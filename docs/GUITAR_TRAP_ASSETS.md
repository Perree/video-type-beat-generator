# Guitar trap — materiales del nuevo canal

Preparación de materiales solicitada el 7/11/2026, inicialmente con el
identificador provisional `guitar-trap`.

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

## Alcance de la primera fase

La primera fase copió los materiales en Dropbox sin activar publicaciones.
La segunda fase, solicitada después por el usuario, conecta y automatiza el canal.

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

## Validación y conexión

- OAuth verificó Make You Beats y su ID exacto antes de guardar secretos propios
  en `kit-weekly`. Token no persistido en archivos ni mostrado en logs.
- Registro y configuración remotos guardados por CAS y releídos, conservando
  los once canales existentes. BEAT_CHANNELS contiene doce slugs en total:
  once anteriores más `guitar-trap`.
- Simulación remota `42430925997`: success; planned=14, eligible=3,
  uploaded=0 y todos los contadores de error en cero.
- 387 pruebas locales aprobadas con los smokes reales de FFmpeg activados,
  sin omisiones. La primera simulación remota aprobó las 386 pruebas anteriores
  al ajuste de margen; el piloto usa el ajuste y su nueva prueba de regresión.
- Muestra corregida completa de 204,0163 s validada, tres frames y miniatura
  inspeccionados. Un frame conserva subtítulos incrustados en el videoclip
  original; no se afirma que el margen elimine todos los textos de las fuentes.
- Configuración/registro activos para ejecutar el piloto privado
  `42431249016`; la prueba queda privada y consume su primer turno.
- Piloto terminado con success: uploaded=1, failed/unknown/orphan=0.
  `TK11808450`, `[FREE] Juice WRLD Type Beat - "I don't have friends"`,
  YouTube `8g2abkDlkV8`; turno 8/11 a las 18:00 consumido como `private_pilot`.
  Miniatura personalizada rechazada (`thumbnail_failed=1`, `thumbnail_rejected`);
  no impidió subir el video. Se solicitó al usuario comprobar la habilitación
  de miniaturas personalizadas; no se da por confirmada la causa del rechazo.
- Corrida normal `42431772121` terminada con success: uploaded=2,
  failed/unknown/orphan/blocked/expired/calendar_unavailable=0.
  Miniaturas rechazadas en ambos videos (`thumbnail_failed=2`).
- `Lovers` (`TK22318974`, `YRndKj7tJNs`) programado para 9/11/2026, 18:00
  Buenos Aires; `Vida de Rock` (`TK20944427`, `_icpxvFht34`) para 10/11, 18:00.
  Son recibos `scheduled`, no videos publicados en el momento de esta sesión.
- Quedan once turnos planificados del 11 al 21/11. La corrida diaria habitual
  mantiene el búfer, sujeta a cupo y procesamiento exitoso; PC apagada permitida.
  El piloto no se convierte automáticamente en público.
- Comprobación final: config y registro activos, tres recibos uploaded (un
  piloto privado y dos scheduled), once planned y lease liberado. 387 pruebas
  remotas aprobadas tanto en el piloto como en la corrida normal.
- Límite de comprobación: se verificaron solicitudes y recibos de la API, pero
  no se reprodujeron los videos de YouTube ni se hizo lectura posterior de
  `status` por API. Las miniaturas personalizadas siguen pendientes de habilitación
  o diagnóstico del canal; permanecen configuradas para próximos intentos.
