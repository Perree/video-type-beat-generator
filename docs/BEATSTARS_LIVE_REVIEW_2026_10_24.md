# Revisión de bugs y prueba real de BeatStars — 2026-10-24

Solicitada y autorizada por el usuario después de las tres fases. Consulta pública
sin login y descarga real; sin modificar automatizaciones, preferencias existentes
ni historial habitual. Historial, canal, audio y videos de prueba aislados en
`.test-run.tmp/beatstars-live-20261024/` (ignorado por Git).

## Evidencia del servicio real

- Perfil configurado: `https://www.beatstars.com/matwyre/tracks`.
- Catálogo completo: **1.139 beats**, consulta inicial en 32,37 segundos.
- Descarga mediante el motor de producción: **New York**, `TK18425328`.
  URL: <https://www.beatstars.com/beat/new-york-18425328>.
- M4A/AAC: **4.203.887 bytes**, **161,724082 segundos**. FFprobe y decodificación
  completa con FFmpeg aprobados. SHA-256:
  `df2abf74f26d0f40ec3480d37edd9e99b0cc0d15eef5065668247333c8a7698d`.
- Nueva instancia del diálogo Qt y servicio, otro canal y mismo historial de
  prueba: tag `BAD BUNNY` devuelve **58** candidatos excluyendo el descargado.
  Al incluir descargados devuelve **59** y marca ese ID como ya descargado.
  Una selección anterior se omite al descargar, sin volver a pedir su audio.
- Render manual real del audio completo con fondo sintético y título editado:
  MP4 de **161,723991 segundos**, miniatura **1280 × 720** y TXT con URL correcta
  en la descripción y en el bloque BEATSTARS. Miniatura inspeccionada.
  NVENC no funciona en este equipo; el render usó el fallback existente libx264.
- Movimiento mediante `mark_done` a `hechos`: M4A, JSON y TXT conservan nombre e
  identidad; tamaño, SHA-256 y enlace comprobados después de moverlos.
- Evidencia local: `report.json`, audio en `local/entrada/Prueba/hechos/` y
  video/miniatura/TXT en `videos/2026-10-24/Prueba/Prueba BeatStars - New York/`.

## Bugs reproducidos y corregidos

1. **La limpieza de un temporal ocultaba un fallo fatal del historial.** Si
   `os.replace` fallaba y también fallaba `unlink` del temporal, se propagaba un
   `OSError` en lugar de `HistoryError`. El motor lo trataba como error de un beat
   y continuaba la tanda. Ahora la limpieza es de mejor esfuerzo y conserva el
   error fatal: detiene nuevas descargas y mantiene intacto el historial anterior.
   La prueba de regresión falló antes del cambio y pasó después.
2. **Metadata Unicode válida rechazada al generar.** El esquema permite 500
   caracteres de título y 40 tags de 100 caracteres. Su representación UTF-8
   puede superar los 16 KiB que leía el render aunque la descarga sea válida.
   El límite ahora es 32 KiB, manteniendo lectura acotada y validación del esquema.
   Pruebas con caracteres de cuatro bytes y JSON válido demasiado grande; la
   primera reprodujo el fallo antes de corregirlo.

## Alcance y límites

Regresión amplia iniciada antes de las correcciones: 426 pruebas ejecutadas,
424 aprobadas y 2 omitidas (smokes opcionales de montaje), sin fallos.
Incluyó `test_manual_beatstars*.py`, `test_beat_*.py`, vista local, render manual
y tandas. Tras las correcciones: **111 pruebas aprobadas sin omisiones**, con
motor, diálogo, metadata, flujo integral, vista local, render y bulk; incluye las
tres pruebas nuevas. GitHub y llavero falsos renovados antes de cada prueba.
`git diff --check` aprobado.

Prueba live de un beat y búsquedas del catálogo completo; no garantiza todos los
previews del catálogo ni futuros cambios de BeatStars. Los fallos de publicación,
cancelación, corrupción y archivos parciales se verifican con fixtures. Revisión
propia del diff y regresiones; Bugbot local no disponible, sin revisión independiente.
Sin SQL, commits de medios, push ni publicaciones remotas.
