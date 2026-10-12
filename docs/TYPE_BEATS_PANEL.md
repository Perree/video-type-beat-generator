# Type Beats — Fase 3 completada, revisión aplicada

En la sección **Beats**, el botón **Automatizaciones de Beats** abre un diálogo
independiente. Solo muestra canales pertenecientes a Beats, incluyendo los canales
históricos sin sección explícita. Loopkits y marca personal conservan sus paneles.

Configuración local en `config/app_config.json`, clave `beat_automation`:

- Perfil público HTTPS de BeatStars para el catálogo compartido.
- Una automatización por canal: activa/pausada, prioridad, horarios semanales en
  Buenos Aires, tags y géneros separados por comas, carpeta local de imágenes.
- Cuota global fija de **6 intentos diarios**, incluyendo fallos, y buffer de
  **14 días**, según el contrato de Fase 2. No son límites editables por canal.

Agregar canal crea una automatización pausada con lunes a las 18:00. El formulario
conserva los cambios al cambiar de canal; guardar valida todos los canales y
horarios. La carpeta puede quedar vacía, pero si se indica debe existir. El guardado
relee la configuración y reemplaza únicamente `beat_automation`, mediante archivo
temporal y reemplazo atómico. No escribe configuración en Dropbox.

**Analizar perfil** usa el extractor público de Fase 1 en un `QThread`: muestra
progreso por página y un resumen de tracks, duraciones disponibles y tags frecuentes.
El resultado queda en memoria hasta cambiar de perfil o cerrar el panel; no altera
el catálogo SQLite ni descarga audio. Cancelar descarta el resultado y detiene las
solicitudes siguientes. Una solicitud de red en curso debe terminar o alcanzar su
timeout (10 segundos por operación de socket en el transporte existente). No se
termina el hilo a la fuerza; cerrar o Escape cancela y difiere el cierre hasta que
el hilo termine. Los fallos de red no muestran respuestas ni URLs del servidor.

**Consultar estado de Beats en Dropbox** hace solo una lectura en otro `QThread`,
con las credenciales independientes `BEAT_DROPBOX_*` de Fase 2. Muestra cantidades
por estado, presencia de lock e intentos consumidos hoy. No inicializa documentos,
toma locks ni reserva intentos. Si falla, conserva la última instantánea disponible;
la cancelación interrumpe las esperas de reintento y descarta el resultado de una
operación en curso. Si el documento no existe, lo informa sin crearlo.

**Simular 14 días** usa `beat_schedule.plan`, sobre el borrador del formulario y el
perfil analizado. Por defecto muestra explícitamente un escenario con estado vacío.
La casilla para usar estado remoto exige haberlo consultado; usa esa instantánea,
no un estado en tiempo real. Muestra slots, canal, track ID y ciclo, junto al
presupuesto disponible hoy. La simulación no cambia el estado ni el archivo de
configuración. Fase 2 planifica slots independientemente de la cuota: los intentos
se cuentan al subir. Tags, géneros e imágenes se guardan como metadata, sin agregar
filtros nuevos al algoritmo de Fase 2.

No hay render, subida, worker nuevo ni sincronización de configuración remota.
Fase cerrada el 2026-10-12 con autorización del usuario después de revisar y corregir.

Validación offline:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_beat_*.py' -v
```

Las pruebas del panel verifican persistencia aislada, selección de canales,
validación, simulación sin mutaciones, recepción de metadata con fixtures, UI
responsiva mientras espera una solicitud, cancelación sin resultados tardíos y
cierre diferido. No requieren BeatStars ni Dropbox reales.

## Revisión y cierre

La revisión local de bugs corrigió la carga de tags/géneros inválidos y JSON
ambiguo, la pérdida silenciosa de prioridades fuera del rango de un `QSpinBox`,
el resumen obsoleto tras un análisis fallido, y la construcción de miles de celdas
en el hilo de UI. La tabla usa un modelo de datos que conserva todas las filas
(probado con 33.600 jobs). La prioridad admite los enteros del esquema de Fase 2.

La consulta remota ahora interrumpe sus esperas de Retry-After al cancelar, comprueba
el evento antes de cada reintento y distingue un estado remoto ausente de un estado
vacío existente. Una solicitud de Dropbox en curso aún debe terminar o alcanzar el
timeout del adaptador (30 segundos por operación). No cambia el adaptador de Fase 2.
La revisión de seguridad independiente no encontró vulnerabilidades confirmadas.

Validación final: **67 tests de Beats aprobados** (18 del panel y 49 de Fases 1/2),
`smoke_sections.py`, `smoke_kit_panel.py`, importación de `main.py` y chequeo de
whitespace. NumPy y watchdog, ya declarados por el proyecto, se instalaron únicamente
en `.venv` para desbloquear las verificaciones. No se modificaron requisitos ni
archivos de Loopkits o marca personal. No se hizo una consulta real a BeatStars o
Dropbox durante el cierre: las verificaciones funcionales usan fixtures y dobles.
