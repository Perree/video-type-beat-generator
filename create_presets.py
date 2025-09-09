#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thumbnail Presets - Configuraciones Predeterminadas
--------------------------------------------------
Script para crear configuraciones predeterminadas para diferentes tipos de canales.
"""

import json
import os
from thumbnail_generator import ThumbnailGenerator

def create_default_presets():
    """Crea configuraciones predeterminadas para diferentes tipos de canales."""
    
    # Configuraciones por tipo de canal
    presets = {
        # Canal de Trap - Estilo más agresivo
        "mattwyyre": {
            "template": "overlay_template",
            "config": {
                "overlay_path": "overlays/trap_overlay.png",
                "text": "BEATS BY MATTWYYRE",
                "text_color": [255, 255, 255, 255],
                "text_size": 45,
                "text_position": "bottom_center",
                "border_ratio": 0.08
            }
        },
        
        # Canal alternativo - Estilo clean
        "wyrelatinbeatz": {
            "template": "centered_image", 
            "config": {
                "border_ratio": 0.12
            }
        },
        
        # Ejemplo de canal con overlay gradiente
        "trapbeats": {
            "template": "overlay_template",
            "config": {
                "overlay_path": "overlays/gradient_overlay.png",
                "text": "TRAP BEATS 2024",
                "text_color": [255, 255, 255, 255],
                "text_size": 50,
                "text_position": "bottom_center"
            }
        },
        
        # Ejemplo de canal con marco
        "prodbeats": {
            "template": "overlay_template",
            "config": {
                "overlay_path": "overlays/frame_overlay.png",
                "text": "PROD. BEATS",
                "text_color": [255, 255, 255, 255],
                "text_size": 55,
                "text_position": "top_center"
            }
        },
        
        # Ejemplo de canal minimalista
        "cleanbeats": {
            "template": "overlay_template",
            "config": {
                "overlay_path": "overlays/clean_overlay.png",
                "text": "",  # Sin texto para estilo clean
                "border_ratio": 0.15
            }
        },
        
        # Ejemplo usando template full cover
        "hypebeats": {
            "template": "full_cover",
            "config": {
                "blur_background": False
            }
        }
    }
    
    # Guardar configuraciones usando el sistema del generador
    generator = ThumbnailGenerator()
    
    config_folder = "config"
    os.makedirs(config_folder, exist_ok=True)
    
    for channel, config in presets.items():
        generator.set_channel_config(
            channel, 
            config["template"], 
            **config["config"]
        )
        print(f"✓ Configuración guardada para canal: {channel}")
    
    # Crear archivo de documentación
    doc_content = """# 📋 Guía de Configuraciones de Miniaturas

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
"""
    
    with open(os.path.join(config_folder, "thumbnail_guide.md"), "w", encoding="utf-8") as f:
        f.write(doc_content)
    
    print(f"\n✅ Configuraciones predeterminadas creadas para {len(presets)} canales")
    print("✅ Guía de configuración creada en config/thumbnail_guide.md")
    print("\n📋 Canales configurados:")
    for channel in presets.keys():
        print(f"  • {channel}")

if __name__ == "__main__":
    create_default_presets()
