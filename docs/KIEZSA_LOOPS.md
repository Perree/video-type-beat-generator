# kiezsa loops — preparación (2026-11-03)

Configuración y catálogo propios guardados en Dropbox y releídos. Canal **activo** en
la app, con `activo: true` y `kiezsa-loops=6` en `KIT_CHANNELS`. No se subieron videos
durante la activación.
Enlaces de Rekonise de los cuatro kits elegidos cargados y releídos.
YouTube conectado por OAuth y verificado por nombre y handle `@kiezsa-loops`:
`UCabIT1klRK7dWEobaW4lHhQ`. Token obtenido en memoria y guardado directamente en
GitHub Secrets (`kit-weekly-kiezsa-loops`), sin archivo local de credenciales.
Environment creado y restringido a `master`; secretos de canal y token cargados.
Soporte de `{loop_count}` publicado en `master`. Prueba remota sin subidas
`41755326855` completada correctamente (`preview 1/1: ok`). Registro actualizado por
CAS y releído; cronogramas y registro de los demás canales conservados.
Primera ejecución automática prevista: domingo 8/11/2026 a las 20:00 Argentina;
primera publicación prevista: lunes 9/11/2026 a las 18:00, sujeto al calendario de
YouTube, material, cuota y éxito de la corrida real. El dry-run no prueba el render
ni una subida real.

## Base y cronograma

Base: configuración **default / WyreSounds** real en Dropbox, no la copia incompleta
`wyresounds/config.json`. Conserva su raíz, reglas de recorrido, previews de 135–195 s
(pueden ser más cortos), mínimo 4 loops, cortes por silencio, portada `template`,
referencias, presupuesto y ciclo de 3 videos con descanso de 30 días.

Un video semanal: **lunes 18:00 America/Argentina/Buenos_Aires**, elegido a partir del
primer horario de WyreSounds. Un único slot y `kits_per_week: 1`.
Nombres reales de los kits, sin nombres generados; SEO de artistas desactivado para
respetar `(FREE) Guitar Sample Pack "{name}" ({loop_count} loops)`.
La cantidad corresponde al preview renderizado, no al total de la carpeta.

Descripción del usuario conservada, incluidos términos 50/50 e hashtags 2025.
Etiquetas tomadas de la captura. Link individual sin parámetros de seguimiento;
sin enlace general para evitar que kits nuevos hereden una descarga equivocada.

## Catálogo preparado

| Kit | Loops disponibles en Dropbox |
|---|---:|
| Lucid Dreams | 7 |
| MIDNIGHT | 8 |
| Take Me Back | 6 |
| 999 | 34 |

Incluye los productos de guitarras aunque estuvieran apagados o mal etiquetados en
WyreSounds. Se excluyen House/Reggaeton, copia `(1)`, bundles y demos que repiten
productos. La elección identifica productos de guitarra por la carpeta; no supone
que todos los audios sean pistas de guitarra aislada (algunos incluyen voces).

Por pedido del usuario, Cold Summer, SAUCO y Yourself se quitaron del catálogo de
este canal; sus carpetas y los demás canales no se modificaron.

`payhip_url` es el nombre histórico del campo: admite Rekonise. Los cuatro enlaces
aportados por el usuario son:

- 999: https://rekonise.com/999-w8w7e
- Take Me Back: https://rkns.link/posur
- MIDNIGHT: https://rkns.link/zioit
- Lucid Dreams: https://rkns.link/1sywk

Los cuatro kits quedan elegibles en el canal activo. Inventario verificado con el
lector real de Dropbox. Config y catálogo reproducibles en
`kiezsa-loops.channel.json` y `kiezsa-loops.kits.json`.

## Validación

- Config validada con el formulario del panel y catálogo con `kit_catalog`.
- Escrituras remotas con CAS, lectura posterior y registro anterior preservado.
- Selección inicial sin links: cola vacía. Tras cargar los enlaces: cuatro kits
  elegibles y ninguna autoalta, sin subidas. URLs guardadas literalmente; no se
  verificó el contenido de las páginas ni los archivos que entregan.
- Prueba de integración del título: 4 loops renderizados de una carpeta de 8,
  enlace de Rekonise intacto y plantilla original preservada.
- Smokes de SEO y multicanal aprobados. El smoke semanal general falla por una
  expectativa antigua: espera un solo mensaje de Telegram y ahora recibe también
  el aviso de inicio. No se modificó ese comportamiento en esta fase.
