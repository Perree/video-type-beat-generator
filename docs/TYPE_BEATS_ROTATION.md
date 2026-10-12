# Type Beats: ciclos y rendimiento (Fase 7 completada, revisión aplicada)

Cada canal cubre todos los tracks activos una vez por ciclo. Las reservas evitan
duplicados en el buffer; las canceladas liberan el track, conservando el número
del ciclo. Un track nuevo entra en la vuelta vigente. El catálogo vacío o agotado
deja slots sin reservar, sin romper el descanso ni gastar cuota.

Una repetición exige 180 días exactos desde el mayor de la fecha programada y la
fecha de inserción conocida. Una reserva pendiente, fallida o con resultado
ambiguo impide repetir ese beat hasta resolverla, incluso si se canceló una
reserva que ya tuvo un intento de subida: cancelar no demuestra que el insert
falló. La planificación comprueba el
descanso contra el slot; la reserva CAS de upload vuelve a comprobarlo contra el
reloj actual, porque el worker puede insertar videos antes del slot.

## Score y distribución aprobados

Se reutiliza el JSON validado de Fase 5: versión, canal, fuentes, fecha de hasta
14 días, tipos, rangos, tamaño, unicidad y números finitos. No hay consultas a
Analytics nuevas. Las métricas disponibles son por etiqueta, no por video: el
score de cada beat es el promedio de sus etiquetas reales coincidentes.

Para cada métrica se calcula el rango percentil entre las etiquetas del informe:
0 para el mínimo, 100 para el máximo y rango medio para empates. Si todos los
valores son iguales, se asigna 50. Así un outlier de vistas de hasta 10^12 no
domina por su magnitud. Score = 0.50 × rango(vistas) + 0.30 × rango(CTR) +
0.20 × rango(porcentaje visto). El `score` externo del informe sigue sirviendo
solo al SEO de Fase 5, no a esta fórmula.

Los IDs activos se ordenan por score descendente y por ID en empates. Se dividen
en tercios con ancho ceil(N/3): mejores, intermedios y restantes. Después de la
primera vuelta, cada bloque de diez reservas solicita siete mejores, dos
intermedios y uno restante. El orden se mezcla con seed y canal. La cuenta de
reservas no canceladas de ciclos posteriores conserva la posición entre corridas.
Dentro del grupo se elige el score más alto, luego LRU y desempate reproducible.

Si el informe falta, vence, es inválido, o algún track activo no tiene etiquetas
con métricas, se usa LRU para el canal. También se usa LRU cuando el grupo
solicitado se agota. Por eso 70/20/10 es exacto en las solicitudes por bloque;
los resultados pueden desviarse cuando hay restricciones de catálogo/descanso.
LRU prioriza el track sin publicación, luego el de publicación más antigua.
Ningún fallback permite saltar un ciclo o repetir antes de 180 días.

## Imagen y SEO

Se guarda `visual_snapshot` en el job tras render, también para imágenes locales.
La repetición excluye la ruta de imagen previa y la combinación previa de título
y tags SEO. Cambiar solo la descripción no cuenta. Sin otra opción válida se
bloquea el job; no se inventan artistas ni se cambia el título real del beat.
El snapshot SEO sigue siendo inmutable en reintentos.

Cada worker de la matriz reserva solamente el buffer de su canal: así los jobs
de otro canal se seleccionan con el informe y las credenciales de su propio worker.
La cuota global sigue compartida y el planificador puro conserva sus rondas por
prioridad cuando se invoca con varios canales y sus respectivos informes.

El historial Dropbox anterior puede aportar la imagen de una publicación vieja;
si falta, se requiere reconciliarlo. Los montajes de video no tienen una imagen
catalogada persistida: sus repeticiones quedan bloqueadas por esta regla.
Se excluye la ruta anterior y se guarda un hash de píxeles RGB con orientación
corregida: copiar la misma imagen a otro archivo no permite repetirla. Un hash
duplicado bloquea antes del render/upload. Las publicaciones antiguas sin hash
solo permiten verificar la ruta hasta reconciliar su historial.

## Uso reproducible

`core.beat_schedule.plan`, `BeatState.fill_buffer`, `BeatState.dry_run` y
`run_daily` aceptan `seed`. Sin seed conservan los desempates históricos por ID;
los CLI usan 0 por defecto. El worker admite `--seed 42`. El CLI de planificación
admite `--seed 42 --report canal=export.json` (repetible por canal).
Con iguales estado, catálogo, informe, reloj y seed, el resultado es idéntico,
independiente del orden de entrada. No depende del hash aleatorio de Python.

No se modifican Loopkits, Marca Personal ni `main.py`. Revisión local mediante
la skill Bugbot aplicada el 2026-10-12, con cuatro hallazgos corregidos y pruebas
de regresión. La suite de Beats tiene 174 pruebas aprobadas y 2 omitidas; incluye
el flujo completo de una repetición después de 180 días. No se probaron servicios
reales. Fase cerrada por autorización del usuario, sin commit por su instrucción.
