# Revisión de bugs y seguridad — 23 de octubre de 2026

## Alcance

Revisión local de Inicio, creación manual/bulk, Mis canales, asistentes, Conexiones,
configuración/registro, subida compartida a YouTube, planificación y workers de Beats
y Loop kits. Lectura de los workflows y de los límites de transporte/credenciales;
pruebas con servicios falsos y renders locales. No se habilitó producción ni se
hicieron subidas, mensajes, escrituras en Dropbox o cambios de secretos reales.

## Hallazgos corregidos

| Área | Problema | Corrección |
|---|---|---|
| HTTP con claves | `urlopen` seguía redirecciones después de validar solo el host inicial; podía reenviar datos de la solicitud a otro destino. | Transporte común HTTPS sin proxies del entorno ni redirects. Test con un servidor simulado que responde 302: no se hace una segunda petición. |
| Imágenes de IA | La URL de imagen devuelta por el proveedor admitía cualquier destino HTTPS y las respuestas no tenían límite de tamaño. | Hosts permitidos, solicitudes nuevas sin Authorization y límites de 32 MiB para JSON / 24 MiB para imagen. No se permiten puertos distintos de 443, credenciales en URL o fragmentos. |
| YouTube | Un timeout o error al preparar/enviar la miniatura podía ocultar un upload ya exitoso y provocar un reintento del video. | Se devuelve el ID ya obtenido con un aviso de miniatura; se conservan los cierres de streams. |
| Tandas locales | Fallar al mover un audio a `hechos` o al escribir el log abortaba el resto de la tanda. | Se conserva el resumen de videos generados, se registra el aviso en memoria y se continúa. |
| Exportación local | Un error de disco o un `pendientes.csv` abierto en Excel podía cortar la tanda y perder el resumen. | Los errores por beat no bloquean los siguientes; un video ya generado se conserva y se avisa del CSV pendiente. |
| CSV | Títulos/nombres empezando por `=`, `+`, `-` o `@` podían interpretarse como fórmulas. | Se exportan esas celdas como texto; los títulos y archivos de video no se cambian. |
| Windows | Nombres como `CON`, `AUX` o `LPT1` fallaban al crear carpetas o videos. | Los canales rechazan nombres reservados con un error claro; los nombres de archivos se normalizan, incluidos controles invisibles. |
| Configuración | Un tamaño de caché infinito hacía fallar su conversión a bytes. | Se exigen valores finitos y se limita el tamaño al rango del formulario. |
| Presupuesto de IA | Infinitos en configuración o un saldo corrupto podían desactivar topes o tratar un saldo inválido como cero. | Configuración finita; el lector de gasto persistido rechaza saldos negativos/no finitos y bloquea nuevas llamadas pagas. |
| ffprobe | La consulta de duración no tenía timeout y aceptaba valores no finitos. | Timeout de 30 segundos, sin stdin/consola y duración positiva finita. |
| Empaquetado | Faltaba `tzdata` en el escritorio y la suite `--worker-only` incluía una prueba con PyQt que no se instala en Actions. | Dependencia declarada e instalada localmente; selección explícita de pruebas de escritorio. Se verifica el worker con un importador que prohíbe PyQt. |
| Interfaz | Con la guía abierta, Inicio/Conexiones recortaban textos y la guía aplastaba botones. | Acciones de Inicio en vertical, tarjetas de Conexiones en dos columnas, títulos envueltos y altura mínima calculada para la guía con scroll. |

Los smokes HTTP existentes se adaptaron al nuevo punto de sustitución
`kit_http.open_request`; siguen usando respuestas falsas y no realizan llamadas pagas.

## Verificación

- 19 pruebas nuevas entre `tests/test_app_review.py` y `tests/test_app_layout.py`.
- Suite completa del escritorio mediante unittest, con el mismo aislamiento de
  credenciales que `tests/conftest.py`: `MemoryKeyring` y `FakeGhRun` renovados por
  prueba: **468 pruebas, 466 aprobadas y dos checks optativos de FFmpeg omitidos**.
  Esos dos checks se ejecutaron y aprobaron en la corrida del worker indicada abajo.
  Los temporales se colocaron fuera del repositorio en una carpeta escribible.
- Suite de Beats en modo worker, bloqueando importaciones de PyQt y activando
  `BEAT_REAL_FFMPEG_SMOKE=1`: 257 pruebas aprobadas sin omisiones. Incluye los dos
  checks reales de imagen fija/montaje que se omiten en la corrida general por defecto.
- 31 smokes de Loop kits y funciones compartidas aprobados: API hosts, IA,
  gasto/topes, selección, esquema, CAS/estado, varios canales, portada, SEO,
  simulación, render, programación y migración de biblioteca.
- Recorrido automatizado de las cinco pantallas principales con configuración
  temporal y servicios falsos; capturas inspeccionadas. Inicio, creación local y
  Conexiones se volvieron a revisar a 900 × 620 con la guía abierta.
- Sintaxis Python y whitespace revisados. Se verificó que los archivos de tokens
  y configuración privada no estén versionados. La búsqueda de patrones habituales
  de claves Google/GitHub/OpenAI no encontró coincidencias en archivos versionados;
  no se imprimieron valores de credenciales.

Las pruebas nuevas se pueden ejecutar con:

```powershell
python -m unittest discover -s tests -p test_app_review.py
python -m unittest discover -s tests -p test_app_layout.py
python scripts/smoke_beat_hardening.py --worker-only
```

Para la suite completa usar pytest con `tests/conftest.py`, o un runner unittest
que renueve los dobles de credenciales por prueba. El `unittest discover` sin ese
aislamiento no equivale a esta verificación y podría leer conexiones locales.

## Cambios operativos y límites

- Para proveedores de imágenes que devuelven una URL, se aceptan el host de la API,
  `api.openai.com` y `oaidalleapiprodscus.blob.core.windows.net`. Otros CDN se habilitan
  explícitamente con `KIT_IMAGE_DOWNLOAD_HOSTS` (hosts exactos separados por comas)
  en el entorno del proceso. Nunca desde el JSON de Dropbox. Sin habilitación se
  informa el fallo y se conserva el fallback existente a la portada manual.
- Las bases de API ya no admiten query/fragment; las rutas como `/v1` se conservan.
  No se siguen redirecciones aunque apunten al mismo host. Los presupuestos son
  estimaciones existentes por canal; esta revisión no los convierte en un tope
  atómico compartido entre varios canales.
- Si un video se generó pero su audio no pudo moverse a `hechos`, se avisa que hay
  que retirar ese audio de `entrada` antes de repetir la tanda. No se borra el audio.
- Esta revisión no certifica ausencia de vulnerabilidades. No incluye una auditoría
  exhaustiva de CVE/dependencias, secretos históricos de Git, seguridad de las
  cuentas/Environments reales, derechos de contenido ni cumplimiento antispam.
  Las pruebas de red usan dobles; no confirman OAuth ni publicación reales.
