# Type Beats — Fase 5 completada, revisión aplicada

Consumidor independiente de Loopkits. No crea informes, tareas de Claude Code,
publicaciones ni llamadas LLM. Lee un JSON exportado de Notion o un único bloque
de código `json` de una página configurada. No cambia la ficha manual del panel.

## Contrato del productor

Claude Code puede combinar vidIQ y YouTube Analytics para producir este contrato
v1. Las fuentes declaradas son metadata, no una prueba de autenticidad del informe.
`channel_id` debe coincidir exactamente con el ID de la automatización y reserva
de Beats, no con un nombre inferido del texto ni con otro canal de YouTube.

```json
{
  "schema_version": 1,
  "generated_at": "2026-10-12T12:00:00+00:00",
  "channel_id": "beats",
  "sources": ["claude_code", "vidiq", "youtube_analytics"],
  "keywords": [
    {"tag": "trap", "score": 75, "views": 1500, "ctr": 4.5,
     "average_view_percentage": 55}
  ]
}
```

El objeto y cada keyword admiten únicamente esas claves. JSON UTF-8 de hasta
128 KiB, máximo 100 keywords únicos sin distinguir mayúsculas. Tags de hasta
100 caracteres, sin controles, caracteres invisibles, `<>{}` ni espacios externos.
Versión entera 1; no se aceptan booleanos como números, NaN, infinito, claves
duplicadas ni JSON truncado. `score`, CTR y porcentaje visto van de 0 a 100;
`views` es entero de 0 a 10^12. La fecha debe tener zona horaria, no estar en el
futuro y tener como máximo 14 días. Se rechaza el informe entero ante un error.

No incluir instrucciones, URLs, prompts, títulos sugeridos, ejemplos, ni
recomendaciones de texto libre. Un tag con aspecto de instrucción que pase las
reglas de texto nunca se copia del informe: solo puede coincidir con una opción
que ya existe simultáneamente en tags del beat y ficha manual del canal.

## Ficha manual y candidatos

En `beat_automation.channels[]`, la ficha opcional es:

```json
"seo": {
  "tags": ["trap", "drill"],
  "description": "Descripción manual del canal.\nSegunda línea."
}
```

Hasta 40 tags únicos de 100 caracteres; descripción estática de hasta 4000
caracteres, admite saltos LF. No hay expansión de variables. Sin `seo`, se usan
los `tags` existentes del panel y descripción vacía. Configuración manual
inválida produce un error; nunca se reemplaza con contenido del informe.

Se intersectan los tags reales del catálogo con los manuales (igualdad sin
distinguir mayúsculas). Por cada coincidencia se construye
`<tag real> Type Beat | <título real>`, máximo 100 caracteres. Cada opción incluye
ese tag y la descripción manual. `score` solo ordena coincidencias; desempate
alfabético estable. Se elige la primera opción. Sin coincidencias que entren,
se conserva el título real sin tags; si tampoco entra, se rechaza, sin truncarlo
ni inventar otro nombre. No se usa LLM ni se reserva presupuesto de texto.

## Fallback y snapshot

Orden: informe válido → último informe bueno del mismo canal y huella de ficha
manual, de hasta 30 días desde su fecha original → configuración manual.
Una ficha modificada invalida la caché anterior. Fallos de Notion, archivo ausente,
JSON inválido o caché corrupta siguen esta cadena. No se almacena un informe
rechazado ni se rejuvenece la fecha de la caché al usarla. Los errores del
consumidor y lector Notion son códigos fijos, sin contenido o secretos.

`prepare_seo` escribe mediante CAS en `/type-beats/state.json`:

- `jobs[job_id].seo_snapshot`: versión, identidad, fecha de decisión, entrada
  real del beat, ficha manual, scores coincidentes, opciones, selección, origen,
  SHA-256 del informe validado y SHA-256 del snapshot canónico.
- `seo_last_good[channel_id]`: informe validado y huella de ficha manual.
  Sigue siendo entrada no confiable y se revalida antes de usarla.

Las opciones guardan solo título y tags; comparten la descripción de la ficha
manual, que también aparece en la selección final. Esto evita duplicarla hasta
40 veces por trabajo. Los snapshots v1 previos a la revisión, con descripción
en cada opción, siguen siendo válidos si reconstruyen exactamente el mismo SEO.
La caché admite 100 canales; al incorporar otro se reemplaza una entrada
inválida/vencida o, si todas son válidas, el informe más antiguo. El estado sigue
sujeto al límite global de 8 MiB de `BeatCloud`.

El primer snapshot persistido gana, también ante conflictos o respuestas perdidas.
Repetir el trabajo devuelve ese snapshot sin consultar Notion, aunque cambien fecha,
tags o ficha. Puede reproducirse la selección con `candidates` y comprobarse con
`validate_snapshot`; las entradas guardadas bastan sin el informe original.
El hash detecta alteraciones accidentales; no es una firma ni autentica el estado
remoto. Un snapshot inválido bloquea el trabajo en lugar de sustituir su SEO.

## Uso

El CLI existente prepara el snapshot antes del render. Para preparar solamente SEO:

```powershell
python scripts/render_type_beat.py --job-id '<id reservado>' --track track.json --genre trap --seo-report report.json --seo-only
```

`--seo-notion` reemplaza `--seo-report`: requiere `BEAT_NOTION_TOKEN` y
`BEAT_NOTION_PAGE_ID` (UUID, sin URL). Integración de solo lectura con acceso
limitado a la página del informe. Mantener un único bloque `json` no vacío;
varios bloques son ambiguos y disparan fallback. El lector usa host HTTPS fijo,
sin proxies del entorno ni redirects, máximo 10 páginas de 100 bloques y 2 MB
por respuesta, timeout de socket de hasta 15 s y deadline comprobado entre
lecturas de bloques de 64 KiB de 60 s. Solo acepta respuestas `application/json`
y JSON UTF-8. No sigue enlaces, subpáginas ni adjuntos. Un socket en curso
queda limitado por su timeout, no se interrumpe exactamente al deadline.

`--dry-run --seo-only` lee y calcula sin escribir caché ni snapshot. Sin fuente
explícita, se usa caché/manual. `--seo-only` imprime el snapshot para revisión;
el render imprime únicamente origen y huella, sin contenido del informe.
El render conserva el título real en la imagen; el snapshot queda disponible para
la futura publicación. Esta fase no sube videos ni cambia `main.py`.

Pruebas offline: `python -m unittest discover -s tests -p 'test_beat_*.py'`.
Notion real y el informe real de Claude Code no se probaron en esta sesión.

Revisión local aplicada: UTF-8 estricto, deadline durante la lectura del cuerpo,
snapshots compactos con replay compatible, y renovación de caché llena sin
bloquear trabajos. Casos de regresión y CLI `--seo-only`/`--dry-run` offline.
Validación: 129 tests aprobados y 2 omitidos. Cierre autorizado por el usuario
el 2026-10-12; no se hizo commit por instrucción explícita.
