# 📋 Guía de Configuraciones de Miniaturas

## 🎨 Templates Disponibles

### 1. `centered_image` - Imagen Centrada
- **Uso**: Para un estilo clean y profesional
- **Parámetros**:
  - `border_ratio`: Proporción de bordes negros (0.1 = 10%)
- **Recomendado para**: Canales minimalistas, beats instrumentales

### 2. `overlay_template` - Con Overlay y Texto
- **Uso**: Para canales con branding fuerte
- **Parámetros**:
  - `overlay_path`: Ruta al archivo PNG de overlay
  - `text`: Texto a mostrar
  - `text_color`: Color RGBA del texto [R, G, B, A]
  - `text_size`: Tamaño de la fuente
  - `text_position`: Posición del texto
- **Recomendado para**: Canales de trap, beats comerciales

### 3. `full_cover` - Imagen Completa
- **Uso**: Para maximizar el impacto visual
- **Parámetros**:
  - `blur_background`: Aplicar desenfoque sutil
- **Recomendado para**: Canales con imágenes muy visuales

## 🖼️ Overlays Incluidos

1. **gradient_overlay.png** - Gradientes sutiles
2. **frame_overlay.png** - Marco decorativo
3. **text_overlay.png** - Barra para texto
4. **trap_overlay.png** - Estilo trap con efectos
5. **clean_overlay.png** - Minimalista

## 📝 Variables de Texto Dinámicas

Puedes usar estas variables en el texto:
- `{CHANNEL}` - Nombre del canal
- `{GROUP}` - Nombre del grupo
- `{BEAT}` - Nombre del beat

Ejemplo: `"BEATS BY {CHANNEL}"` → `"BEATS BY MATTWYYRE"`

## ⚙️ Configuraciones Recomendadas por Género

### Trap/Hip Hop
```json
{
    "template": "overlay_template",
    "config": {
        "overlay_path": "overlays/trap_overlay.png",
        "text": "BEATS BY {CHANNEL}",
        "text_size": 45,
        "text_position": "bottom_center"
    }
}
```

### Instrumentales/Clean
```json
{
    "template": "centered_image",
    "config": {
        "border_ratio": 0.12
    }
}
```

### Comercial/Branding
```json
{
    "template": "overlay_template", 
    "config": {
        "overlay_path": "overlays/frame_overlay.png",
        "text": "{CHANNEL} BEATS",
        "text_size": 55,
        "text_position": "top_center"
    }
}
```
