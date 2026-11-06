# mat produced this one

Canal verificado por OAuth: `UC7q99p1bly7hLMsK53wfV0Q`.
Slug: `mat-produced-this-one`. Secretos propios por slug en `kit-weekly`;
token enviado en memoria directamente a GitHub Secrets, sin guardarlo en disco.

## Configuración

- Tienda compartida: `https://www.beatstars.com/matwyre/tracks`.
- Catálogo real consultado el 6/11/2026: 1.147 beats, 566 elegibles.
- Selección por etiquetas exactas de Juice WRLD, Topoppgen, Fattmack, Duki,
  Khea y Melodic, con las variantes de `mat-produced-this-one.channel.json`.
  Melodic House y Melodic Deep House no coinciden por sí solas.
- Un video diario a las 18:00 Argentina (horario inicial asumido).
- Búfer de 14 días, subidas escalonadas 2–4 días antes y contador compartido
  de diez intentos diarios; los demás canales conservan su configuración.
- 35 imágenes locales de `images/mat produced this one/Principal` verificadas
  con Pillow y copiadas a Dropbox sin modificar sus bytes. Originales intactos.
  Carpeta: `/Soft Projects/Type Beat Generator/contenido/canales/mat-produced-this-one/fondos`.
- Imagen completa en 16:9, bandas negras, sin texto; miniatura automática.

## Metadatos

Modo `melodic_v1`: `(FREE) {style} Type Beat - "{name}"`.
Solo usa los artistas presentes en las etiquetas reales del beat, hasta dos,
o Melodic si no hay artista de la lista. No asigna Fattmack a todos los beats
solo porque figure en las capturas. Descripción con enlace individual de BeatStars,
crédito MatWyre y condiciones de uso de los otros canales adaptadas a esta tienda.
Las capturas de Prod. Anti sirven como referencia visual y de estructura;
sus enlaces, contacto y derechos no se copian a este canal.

## Estado

Preparación guardada inicialmente en pausa en config y registro de Dropbox,
con lectura posterior. OAuth conectado.

Simulación remota `42237868882` exitosa: planned=14, eligible=4, uploaded=0;
failed/blocked/orphan/unknown/calendar_unavailable=0. Control del worker:
351 pruebas, OK (dos omitidas). Se integró el cambio reciente de encuadre
de mattwyyre conservando ambas fases del plan; cinco pruebas de encuadre OK.

El workflow permite `include_paused=true` exclusivamente con `dry_run=true`:
simula una copia activa en memoria, sin habilitar la configuración persistida,
escribir en Dropbox ni subir videos. Pruebas de lectura y rechazo del modo real.

Tras aprobar la simulación, config y registro activados por CAS y releídos;
otros canales conservados. `BEAT_CHANNELS` incluye el slug del nuevo canal.
Corrida real `42238364215` **exitosa**, con dry_run/private_pilot/include_paused=false:
planned=14, eligible=4, uploaded=4; failed/blocked/orphan/unknown/expired/
calendar_unavailable/thumbnail_failed/budget=0. Control remoto de 351 pruebas OK.

Cuatro recibos `scheduled` confirmados en Dropbox, con imágenes distintas por SHA-256:

| Fecha (Argentina, 18:00) | Beat | Video |
| --- | --- | --- |
| 6/11/2026 | NOCHE FRÍA | `JxlB37KZzsA` |
| 7/11/2026 | Desolate Dreamscape | `0hq4Xm7yFpk` |
| 8/11/2026 | Bacon | `rYtigvM_a4A` |
| 9/11/2026 | On The Edge | `B5rh0_LbfGY` |

No son pilotos privados permanentes: se subieron privados con fecha de publicación.
El primer video se publicará hoy a las 18:00. Los diez pendientes restantes siguen
planificados y el cron diario existente mantiene el búfer con las subidas escalonadas.
La hora nominal del cron es 19:00 Argentina; GitHub puede demorar su ejecución.
La publicación de los videos ya programados depende de YouTube y no del horario
de la próxima corrida del worker.

Verificación final: config y registro activos; configuración de los siete canales
anteriores igual a la copia previa. Contador compartido: cuatro intentos nuevos
del 6/11, sin excepciones ni modificaciones del límite. Código y documentación
publicados en master. Automatización activa sin depender de esta PC.
