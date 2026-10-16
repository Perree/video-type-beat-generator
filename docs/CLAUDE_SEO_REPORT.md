# Informe de Claude Code → worker (Beats y Loop kits)

Puente operable entre el informe que produce Claude Code (vidIQ + YouTube Analytics) y los
workers. **No cambia la semántica de SEO**: el informe solo reordena opciones que ya existen
(tags de la ficha / frases de kits). Ningún texto libre del informe llega a un título.
Contratos: [TYPE_BEATS_SEO.md](TYPE_BEATS_SEO.md) (`beat_seo_report`) y
[KIT_WEEKLY.md](KIT_WEEKLY.md) (`kit_trends`).

## Dónde vive cada informe

| | Beats | Loop kits |
|---|---|---|
| Clave | `channel_id` = **ID interno** del canal (un solo bloque JSON) | `genres.<género>.keywords` |
| Fuente en producción | Página de Notion (`BEAT_NOTION_*`) | Página de Notion (`KIT_NOTION_*`) |
| Edad máxima | 14 días | `trends.max_age_days` (10) |
| Copia local (fuera de git) | `tokens/seo_reports/beats-<canal>-<hash>.json` | `tokens/seo_reports/kits-<slug>-<hash>.json` |

La copia local sirve para **validar antes de pegar en Notion**; el worker no la lee. `tokens/`
está en `.gitignore`.

## Pestaña "SEO y tendencias"

Cuadro *Informe de Claude Code* en ambos paneles:

- **Estado**: vigente / vencido / inválido / sin informe, edad en días, origen (`copia local`,
  `Notion` si está configurado pero no hay copia, o ninguno) y cantidad de keywords.
- **Importar informe JSON…**: valida con las reglas del worker y solo entonces copia (atómico).
  Un rechazo no pisa la copia anterior.
- **Copiar schema**: deja en el portapapeles un JSON de ejemplo (con tus tags o géneros) para
  pegarlo en el prompt de Claude Code.
- **Sugerencias** (solo lectura): Beats = tags del informe que coinciden con la ficha, aclarando
  que el worker además necesita el tag en el beat y un título de hasta 100 caracteres; Kits =
  top de búsquedas por género. La edad de kits sale de `kit_preview.trends.max_age_days` de la
  config cargada (10 si no está).
- **Recomendaciones de miniaturas** (solo lectura): si el JSON local trae
  `thumbnail_suggestions` (o en kits también `suggestions` informativas), se listan; si no, una
  nota fija de que las miniaturas son manuales. Nada se aplica al render ni a YouTube desde el panel.

## Códigos de error

La UI nunca muestra texto del informe, solo un código fijo: `file`, `size`, `json`, `schema`,
`version`, `channel`, `expired`, `date`, `sources`, `keywords`, `metric`, `text`, `duplicate`.
`expired` incluye fechas futuras. Un informe sin keywords es válido, igual que para el worker.

## Prueba

`py -3 scripts/smoke_seo_report_status.py` (sin red, carpeta temporal).

TODO: la prueba real con Notion y el informe real de Claude Code sigue pendiente.
