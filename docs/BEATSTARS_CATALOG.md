# Catálogo público Type Beats — Fase 1 completada

Uso independiente de la UI actual, con biblioteca y configuración existentes sin cambios.
En la configuración local, definir `beat_automation.beatstars_profile_url` como
`https://www.beatstars.com/PROFILE/tracks` (también admite la URL del perfil sin `/tracks`).
No necesita credenciales. El valor vacío del ejemplo requiere configurar el perfil explícitamente.

```python
import json
from core.beat_catalog import BeatCatalog
from core.beat_sync import sync_configured

with open("config/app_config.json", encoding="utf-8") as f:
    config = json.load(f)
catalog = BeatCatalog("library/beat_catalog.db")  # crear library/ antes si no existe
result = sync_configured(config, catalog)
print(result)  # solo contadores y versiones
```

`BeatStarsSource.scan(url)` obtiene el perfil y todas sus páginas públicas por queries
GraphQL fijas mediante POST de solo lectura. No usa mutations, cookies, OAuth, login,
proxies del entorno ni redirecciones. No pide ni descarga audio, imágenes, URLs firmadas
o datos personales del perfil. El formato fue comprobado contra el JavaScript público y
consultas anónimas de BeatStars el 2026-10-12; es un endpoint público del sitio, sin contrato
de API garantizado. Cambios de formato, bloqueos o respuestas parciales generan un error.

Cada track conserva ID `TK…`, título, URL de página, tags y duración en segundos
(null si no está publicada). `preview_ref` conserva proveedor, ID estable, ID v2 y URL
de página: permite consultar el preview actualizado en una fase posterior, sin persistir
URLs temporales ni descargarlas durante el escaneo. Esa resolución no se implementa aquí.

El catálogo SQLite separado tiene `schema_version=1` (`PRAGMA user_version`) y una
versión de contenido por ID estable de perfil `MR…`. Inserta los nuevos, actualiza
metadatos, reactiva los que reaparecen y marca inactivos los ausentes. Conserva
`first_seen`, `last_seen`, `changed_version` y las revisiones de cambios de las últimas
20 versiones. Una corrida sin cambios actualiza `last_seen` sin crear una versión.
Cambiar de perfil mantiene ambos catálogos aislados; cambiar su username conserva la
identidad por member ID. `tracks(member_id, include_inactive=True)` incluye los inactivos.

Solo se aplica un snapshot cuando sus páginas, propietarios, IDs y cantidad total son
consistentes. Los límites o errores abortan sin aplicar bajas ni modificaciones; el commit
local es transaccional. Un cambio de orden que genere duplicados durante el escaneo
también aborta y puede reintentarse. No detecta cambios remotos que mantengan el total y
no generen duplicados entre páginas: la API no ofrece aquí un snapshot transaccional remoto.

Límites predeterminados: 10 s por operación de socket, 120 s por escaneo, 2 MB por respuesta,
50 tracks por página, 100 páginas, 5000 tracks por escaneo; catálogo limitado a 20000 IDs
conservados en total. El plazo se comprueba entre lecturas y llamadas (una lectura en curso
puede consumir hasta su timeout). `Limits` permite valores menores y limita los máximos.
Si un catálogo supera esos límites, falla sin aplicar un resultado truncado.

Hosts de perfil permitidos: `beatstars.com`, `www.beatstars.com`; único destino de red:
`https://core.prod.beatstars.net/graphql`. Se rechazan HTTP, credenciales en URL, puertos
no estándar, fragments, query strings de perfil y hosts parecidos. Los errores de servicio
son `BeatError` con códigos fijos; no muestran cuerpos, URLs, credenciales ni rutas locales.

Pruebas sin red (solo librería estándar):

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -p 'test_beat_*.py' -v
```

Los fixtures son sintéticos, basados en el formato público observado. El transporte falso
permite probar paginación, cambios de título/slug, bajas, reactivación, errores y límites.
Las pruebas HTTP usan respuestas en memoria; no requieren BeatStars ni audios.

Cierre validado el 2026-10-12: 22 tests sin red aprobados, dos hallazgos de Bugbot
corregidos y revisión de seguridad sin vulnerabilidades confirmadas. Prueba real del
perfil configurado: 1138 tracks sincronizados; segunda corrida con 1138 sin cambios,
sin nuevas versiones ni descargas de audio. Configuración y catálogo locales no versionados.
