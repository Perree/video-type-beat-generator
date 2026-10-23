# Carpeta única en Dropbox

Desde 2026-10-23 todo lo de la app vive en **`/Soft Projects/Type Beat Generator/`** (antes estaba suelto en
la raíz de Dropbox). Las rutas salen de `core/dropbox_layout.py`; la raíz se puede cambiar con
`TYPEBEAT_DROPBOX_ROOT`.

```
/Soft Projects/Type Beat Generator/
├─ datos/                      lo que usa el programa (no hace falta tocarlo a mano)
│  ├─ automatizacion/          canales.json, ajustes.json          (antes /automatizacion)
│  ├─ beats/                   config.json, state.json             (antes /type-beats)
│  └─ loop_kits/               config, kits, channels.json, <canal>/config.json   (antes /loop_kits/_automation)
│     └─ estado/               state.json, <canal>/state.json      (antes /loop_kits_state)
├─ contenido/                  lo que agrega el usuario
│  ├─ canales/<canal>/         fondos/, miniaturas/, logo.png      (ey mat: antes /AudioVisual Stuff/Type Beats - STUFF/ey mat y «ey mat thumbnails»)
│  ├─ entrada/<canal>/         beats para generar en tanda (modo local)
│  └─ loop_kits/referencias/   referencias de portadas             (antes /loop_kits/_referencias)
└─ _archivo/                   copias viejas (código de febrero 2026)
```

- Las rutas viejas que quedaron **guardadas adentro** de los JSON (config, estado, historial de imágenes) se
  traducen solas al leer (`dropbox_layout.translate`); al volver a guardarse quedan con la ruta nueva. El estado
  guarda rutas en minúsculas y se mantienen en minúsculas.
- No se movió: la librería de productos (`/Music Production Stuff/…/B_PRODUCTOS_TIENDA (WYRESOUNDS)`), de donde
  salen los loops, ni el resto de `/AudioVisual Stuff`.
- Modo local: la app usa `<Dropbox en la PC>/Soft Projects/Type Beat Generator/contenido` si esa PC lo tiene
  sincronizado con la app de Dropbox; si no, sigue con `<Dropbox>/TypeBeat Local`.
