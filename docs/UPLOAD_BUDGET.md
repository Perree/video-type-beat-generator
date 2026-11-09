# Presupuesto compartido de subidas

Desde esta fase, los entry points `core.beat_worker` y `scripts/run_kit_weekly.py`
usan quince **intentos** diarios compartidos entre todas sus automatizaciones de
Beats y Loops. No cambian los slots ni la frecuencia pública de ningún canal.
El contador está en `datos/automatizacion/upload_budget.json`, en el mismo
Dropbox visible para todos los workers. Es un límite propio, no la cuota de Google.
Si se usan proyectos distintos, este contador sigue siendo un límite total más
conservador. Las subidas manuales externas a estos entry points no se contabilizan.

Cada `videos.insert`, incluido el fallback privado de kits, reserva antes de
subir por CAS de Dropbox. Fallos y resultados ambiguos no devuelven el intento.
Los reintentos de la escritura de una misma reserva no duplican el cargo. Un
archivo ausente, corrupto o inaccesible impide subir; nunca se reinicia solo.
El día compartido usa `America/Los_Angeles` (medianoche del Pacífico, con DST).
Beats conserva adicionalmente su historial/reserva propia de quince intentos por
fecha Buenos Aires y la barrera que impide repetir una subida ambigua.
La UI que consulta ese historial muestra solo Beats, no el saldo global de Loops.

Si YouTube responde `uploadLimitExceeded`, se guarda una pausa de 24 horas para
ese canal y se corta su corrida. Los demás pueden continuar. Los kits que no se
subieron no quedan registrados como usados; los trabajos de Beats conservan su
historial y el rechazo queda sujeto a su recuperación existente de intentos sin
video (no se borra ni se devuelve la cuota). Los slots vencidos siguen las reglas
existentes. No se agrega un cron nuevo ni se garantiza recuperar un slot pasado.

## Activación y recuperación

Antes de desplegar, crear el archivo una sola vez mediante
`core.upload_budget.initialize(DropboxTransport(cliente))`. Usa creación exclusiva:
si ya existe no lo sobrescribe. Por seguridad, el día de activación se reserva
completo para cubrir subidas de la versión anterior que no tenían este contador.
Los intentos nuevos se habilitan en la siguiente medianoche del Pacífico.
No iniciar corridas antiguas y nuevas simultáneas. Si se pierde el archivo,
restaurar su revisión desde Dropbox; no recrearlo vacío para recuperar saldo.
El cambio a quince (2026-11-09) acepta la configuración antigua de seis o diez
y conserva íntegro su historial. Un contador guardado con `limit: 10` se acepta
y pasa a `limit: 15` en su próxima escritura, sin borrar días anteriores. No hace falta editar calendarios ni tokens.

Verificación: pruebas offline de contención de workers, respuesta de escritura
perdida, renovación a medianoche, falta/corrupción del estado, fallo sin devolución,
pausa por canal, fallback privado y presupuesto de Loops consumido antes de Beats.
