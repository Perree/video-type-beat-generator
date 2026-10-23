# Distribuir publicaciones desde la aplicación

En **Mis canales automatizados → Distribuir publicaciones de Beats…**, o en
**Modo avanzado → Beats → Canal → Distribuir publicaciones…**, se abre una guía
de dos pasos. Usa la configuración cargada desde Dropbox y no necesita consultar
YouTube ni analizar el catálogo.

1. Todos los canales activos empiezan con **Conservar horarios** marcado. Dejar
   «ey mat» fijo conserva exactamente sus días y horas. Los canales pausados no
   participan y no se activan. Destildar solamente los canales a redistribuir.
2. Elegir entre 1 y 7 videos semanales por canal. El botón de recomendaciones
   intenta dos por semana y un canal diario de mayor prioridad si cabe. Si no
   alcanza, recomienda uno por semana; si eso tampoco cabe, explica el conflicto.
   Empates de prioridad se resuelven por ID. No utiliza métricas ni un LLM.
3. El tope de la propuesta se puede bajar de seis para dejar margen. Las reservas
   externas descuentan capacidad para Loop kits, subidas manuales u otras apps:
   por ejemplo, un video lunes y otro jueves de «ey mat» si no está en la tabla.
   No contar dos veces un canal que ya está fijo en la tabla.
4. Revisar la propuesta y aplicar al borrador. Usar **Guardar cambios** para
   publicarlo mediante el guardado existente de Dropbox con control de conflictos.
   Cancelar no aplica la propuesta. Si cambió la configuración mientras estaba
   abierto el diálogo, se rechaza la aplicación y se pide volver a abrirlo.

La distribución equilibra la carga respetando el número solicitado, luego
prefiere separar los días. Genera como máximo una publicación diaria por canal
movible y conserva la primera hora de su calendario anterior (Buenos Aires).
Los calendarios fijos conservan también múltiples horarios por día.
Dos/tres publicaciones semanales usan días fijos; no representan intervalos
exactos de 48/72 horas. El editor de horarios existente permite ajustes manuales.

## Alcance y límites

- El tope y las reservas externas son parámetros de esta propuesta, no ajustes
  persistentes del worker ni una lectura de los calendarios de otros servicios.
  El worker de Beats conserva su presupuesto existente de seis intentos diarios,
  incluidos fallos. Otros workers no comparten automáticamente ese presupuesto.
- La tabla cuenta **publicaciones** semanales; el presupuesto del worker cuenta
  **intentos de subida** en Buenos Aires. Puede subir anticipadamente para cubrir
  su buffer de 14 días. La propuesta no garantiza cubrir ese buffer, tener catálogo
  suficiente ni poder subir todo el contenido ante fallos o capacidad insuficiente.
- No se reprograman/cancelan jobs ya reservados ni videos ya subidos. Cambiar
  horarios afecta a nuevas reservas; durante la transición pueden coexistir
  horarios anteriores con los nuevos. Revisar el estado/simulación del panel.
- No se modifican Loop kits, workflows, credenciales, cuotas del proyecto ni
  contenido remoto al recomendar o aplicar. Guardar cambios es el paso existente
  que publica la configuración. No se habilita producción desde esta guía.

## Cuota y políticas de YouTube (verificado el 23 de octubre de 2026)

Google documenta actualmente un bucket predeterminado de **100 llamadas diarias
a `videos.insert` por proyecto**, una unidad por llamada. No implica que este
proyecto concreto disponga de esa cuota; verificar **Google Cloud → APIs y
servicios → YouTube Data API v3 → Cuotas**. Un proyecto compartido comparte cuota.
La API también documenta `uploadLimitExceeded` para límites de subida del usuario.
La cuota de Google se reinicia a medianoche del Pacífico, mientras que el límite
local existente usa Buenos Aires. No se amplía automáticamente el límite local.

La cuota técnica no es un permiso para producir contenido repetitivo en masa.
La política de spam contempla contenido automatizado similar con cambios mínimos
y redes coordinadas de canales. Cambiar solamente una imagen, título o fecha no
garantiza cumplirla. Usar material propio/autorizado, contenido con valor y
metadatos fieles; no repartir proyectos/cuentas para eludir restricciones.
Esta guía no audita derechos, similitud del contenido ni riesgo de sanciones.
Mantiene las protecciones existentes de identidad OAuth, reservas y resultados
ambiguos del uploader; no realiza nuevas subidas ni asegura ausencia de bloqueos.

Fuentes oficiales:

- [Calculador de cuotas](https://developers.google.com/youtube/data/determine_quota_cost)
- [Referencia de videos.insert y errores](https://developers.google.com/youtube/data/reference/rest/v3/videos/insert)
- [Historial de cambios de cuota](https://developers.google.com/youtube/data/revision_history)
- [Política de spam](https://support.google.com/youtube/answer/2801973)
- [Políticas para desarrolladores](https://developers.google.com/youtube/terms/developer-policies)

Verificación nueva: `python -m unittest tests.test_beat_distribution`.
La regresión del panel, Mis canales, planificación y panel remoto se ejecutó con
`tests/` en `sys.path`, la lectura del llavero sustituida por una respuesta vacía
y el runner de `gh_status.DEFAULT` sustituido por una respuesta sin conexión:
79 pruebas aprobadas. Las 15 pruebas del adaptador Dropbox se ejecutaron por
separado con su propio `MemoryKeyring`: **94 aprobadas en total**. Así las
pruebas no leen el llavero real ni consultan GitHub.
Incluye escenarios de 15 canales, mezcla de 38 videos, reservas externas,
calendarios fijos/pausados, factibilidad de 400 escenarios contra un criterio
independiente de grados bipartitos, cancelación, borrador obsoleto y guardado CAS
en un Dropbox falso. Sin subidas reales ni lectura de la cuota de Google Cloud.
