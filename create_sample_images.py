#!/usr/bin/env python3
"""
Crear imágenes de ejemplo para probar el thumbnail editor
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_sample_image(text, color, size=(800, 600), filename="sample.jpg"):
    """Crea una imagen de ejemplo con texto."""
    img = Image.new('RGB', size, color=color)
    draw = ImageDraw.Draw(img)
    
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except:
        font = ImageFont.load_default()
    
    # Calcular posición centrada
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    x = (size[0] - text_width) // 2
    y = (size[1] - text_height) // 2
    
    draw.text((x, y), text, font=font, fill='white')
    
    img.save(filename)
    print(f"Creada imagen: {filename}")

def main():
    """Crear imágenes de ejemplo en las carpetas de canales."""
    
    # Imágenes para TrappyBeats - Principal
    principal_path = "images/TrappyBeats/Principal"
    create_sample_image("Type Beat\nBackground 1", (25, 25, 112), filename=f"{principal_path}/background1.jpg")
    create_sample_image("Dark Vibes\nStudio", (139, 0, 139), filename=f"{principal_path}/background2.jpg")
    create_sample_image("Urban Style", (70, 130, 180), filename=f"{principal_path}/background3.jpg")
    
    # Imágenes para TrappyBeats - Dark
    dark_path = "images/TrappyBeats/Dark"
    create_sample_image("Dark Mode\nBeats", (32, 32, 32), filename=f"{dark_path}/dark1.jpg")
    create_sample_image("Night Vibes", (64, 64, 64), filename=f"{dark_path}/dark2.jpg")
    
    # Imágenes para MelodyMaker - Principal
    melody_path = "images/MelodyMaker/Principal"
    create_sample_image("Melodic\nBeats", (255, 20, 147), filename=f"{melody_path}/melody1.jpg")
    create_sample_image("Soft Vibes", (255, 182, 193), filename=f"{melody_path}/melody2.jpg")
    create_sample_image("Piano Type", (186, 85, 211), filename=f"{melody_path}/melody3.jpg")
    
    print("✅ Imágenes de ejemplo creadas exitosamente!")
    print("📁 Estructura creada:")
    print("   images/")
    print("   ├── TrappyBeats/")
    print("   │   ├── Principal/ (3 imágenes)")
    print("   │   └── Dark/ (2 imágenes)")
    print("   └── MelodyMaker/")
    print("       └── Principal/ (3 imágenes)")

if __name__ == "__main__":
    main()