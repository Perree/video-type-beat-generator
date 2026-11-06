# Lovesickk: referencias de títulos y descripciones

Fecha: 2026-11-06. Fuente: cinco capturas aportadas por el usuario en el chat.
Esta fase registra la investigación; no implementa ni activa la rotación ni la
lectura de métricas y no modifica videos publicados o programados.

## Títulos observados

| Captura | Canal | Título visible | Vistas visibles | Fecha visible |
| --- | --- | --- | --- | --- |
| 1 | Heartbreak | `(FREE) R&B Type Beat - "This Time"` | 915 | 2026-11-05 |
| 2 | frozone 酷冰 | `[free for profit] trap soul + rnb type beat "fair love"` | 10.171 | 2026-08-21 |
| 3 | Bad Habits | `(FREE) R&B Type Beat - "For The Night" \| Smooth Freestyle RnB 2026` | 29.734 | 2026-09-30 |
| 4 | Heartbreak | `(FREE) R&B Type Beat - "Fade Away"` | 250.503 | 2026-09-13 |
| 5 | prodbyajdee | `(FREE) Kehlani x Aaliyah R&B Type Beat - "Slow Down"` | 842 | 2026-11-01 |

Las vistas son una foto del momento, no métricas actuales. Fechas, antigüedad,
tamaño del canal, audio y miniaturas difieren: no permiten atribuir resultados al
título ni ordenar formatos por eficacia. Dos ejemplos son del mismo canal.

## Descripciones observadas

- **Heartbreak / This Time:** enlace de compra/descarga y promoción al principio;
  tono y BPM; uso gratuito no comercial y crédito requerido; párrafo narrativo
  específico del beat, con ambiente emocional, características sonoras y
  referencias de artistas; contacto, tienda y tres hashtags al final.
  La descripción menciona Drake, Brent Faiyaz, Bryson Tiller y PARTYNEXTDOOR aunque
  el título solo lleva R&B. No es necesario poner todos los artistas en el título.
- **frozone / fair love:** información breve: BPM y tono, licencia, crédito,
  condiciones de Content ID/exclusividad, contacto, repetición del título y
  hashtags. La autorización comercial pertenece a ese productor y ese beat;
  no se traslada a los beats de Lovesickk.
- **Bad Habits / For The Night:** enlace primero; BPM y tono; promoción; licencia
  no comercial; contacto; título repetido; hashtags y un bloque extenso de
  keywords/artistas con años anteriores. Registrar el bloque como observación,
  sin adoptarlo como requisito ni asumir que causó las visitas.
- **Heartbreak / Fade Away:** compra/descarga, tono y BPM, licencia/crédito,
  párrafo corto sobre ambiente cálido, nostálgico y nocturno con referencias
  Karri, Kehlani y Bryson Tiller; contacto, tienda y hashtags.
- **prodbyajdee / Slow Down:** enlace a otro video; compra; contactos/tienda;
  licencia no comercial; BPM/tono; título repetido; párrafo largo con artistas,
  estilo, instrumentos y usos vocales; tres hashtags. Sirve como referencia de
  estructura, no como texto para copiar o evidencia del sonido de nuestros beats.

## Cuatro familias propuestas para probar

1. **Género simple (control):** `(FREE) R&B Type Beat - "{name}"`.
2. **Género con detalle:** `(FREE) R&B Type Beat - "{name}" | {detail}`.
   Detalles posibles: Acoustic R&B, Sad R&B, Emotional R&B o Smooth Freestyle RnB;
   solo habilitados por tags o revisión explícita del audio. Año opcional y real.
3. **Cruce de géneros:** `(FREE) {style_a} + {style_b} Type Beat - "{name}"`.
   Ejemplo: Trap Soul + R&B, únicamente si la metadata sostiene ambos estilos.
4. **Artistas:** `(FREE) {artist_a} x {artist_b} R&B Type Beat - "{name}"`.
   Uno o dos artistas presentes en los tags; no asignar Kehlani/Aaliyah por la
   estética de la miniatura o porque aparezcan en estas referencias.

Se conserva `(FREE)` como presentación común para no mezclar cambios de licencia
con la prueba de estructura. Nunca generar `free for profit` desde una plantilla
de referencia: exigir condiciones comerciales explícitas del beat propio.

## Contraste con BeatStars consultado en esta conversación

El catálogo público de matwyre devolvió 1.148 beats; 108 coincidían con la búsqueda
de tags R&B/RnB utilizada. No equivale a 108 beats elegibles para Lovesickk.

| Beat / ID | Tags devueltos | Aplicación posible |
| --- | --- | --- |
| Her eyes / TK17320232 | acoustic rnb, rnb, sad rnb | Familia simple o detalle acústico/triste |
| Couwart / TK20761539 | emotional, rnb, emo rap | Familia simple o detalle emocional |
| Intriga / TK18632859 | partynextdoor, rnb, che ecru | Familia simple o artistas PARTYNEXTDOOR x Che Ecru |
| Nevermind <3 / TK17125660 | soul, rnb, sad rnb | Familia simple o detalle triste; no inferir Trap Soul solo de Soul |

Existe otro Her Eyes, TK22721993 (139 s), con tags emotional/rnb/acoustic guitar.
No confundirlo con TK17320232 (181 s), que coincide aproximadamente con la
duración de la captura del canal. La identificación final debe usar el ID guardado
en el trabajo de publicación.

## Reglas para la siguiente fase de código

- La app ya lee tags públicos y genera un snapshot de SEO por trabajo.
  `core/beat_seo.py` elige la primera opción compatible; enumerar candidatos no
  constituye por sí solo una distribución de pruebas.
- Generar hasta cuatro familias y descartar las incompatibles; asignar variantes
  entre beats comparables sin forzar artistas o instrumentos ausentes.
- Guardar familia, versión, tags de origen y título elegido antes de publicar;
  conservar esa asignación al reintentar una descarga, render o subida.
- Mantener reproducibles los snapshots históricos y respetar los otros canales.
- Descripción propia: enlace real, BPM/tono solo si están disponibles, licencia y
  crédito propios, párrafo breve basado en metadata verificada, contacto propio
  y pocos hashtags pertinentes. No copiar emails, promociones o textos ajenos.
- Seguimiento propuesto a los 7 y 28 días: impresiones y CTR por superficie cuando
  estén disponibles, vistas desde búsqueda, tiempo de reproducción e interacción.
  Dato ausente no es cero. Obtener estas métricas requiere integrar una fuente
  autorizada; aún no está implementado en esta fase.
- No declarar ganador con pocos datos ni confundir comparación entre beats con
  un A/B del mismo video. Las pocas impresiones no demuestran una causa única.

## Estado

- [x] Referencias y descripciones anotadas.
- [x] Cuatro familias definidas para orientar la implementación.
- [x] Implementar selección estable por tags y registro de variante (`rnb_test_v1`).
- [x] Integrar registro de vistas, likes y comentarios con permisos existentes.
- [ ] Integrar impresiones, CTR, tiempo de reproducción y búsqueda de Analytics.
- [ ] Validar con el catálogo del canal y activar la configuración correspondiente.
