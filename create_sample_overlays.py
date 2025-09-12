#!/usr/bin/env python3
"""
Script para crear overlays de ejemplo para el editor de thumbnails
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_sample_overlays():
    """Crea overlays de ejemplo en la carpeta overlays/"""
    
    # Crear carpeta si no existe
    os.makedirs("overlays", exist_ok=True)
    
    # 1. Overlay de texto "TYPE BEAT"
    img = Image.new('RGBA', (400, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Texto con borde
    try:
        font = ImageFont.truetype("arial.ttf", 48)
    except:
        font = ImageFont.load_default()
    
    text = "TYPE BEAT"
    # Borde negro
    for adj in range(-2, 3):
        for adj2 in range(-2, 3):
            draw.text((20+adj, 20+adj2), text, font=font, fill=(0, 0, 0, 255))
    # Texto principal en amarillo
    draw.text((20, 20), text, font=font, fill=(255, 255, 0, 255))
    
    img.save("overlays/type_beat_text.png")
    print("✓ Creado: type_beat_text.png")
    
    # 2. Overlay de esquina decorativa
    img = Image.new('RGBA', (200, 200), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Líneas decorativas en esquina
    for i in range(5):
        width = 5 - i
        color = (255, 215, 0, 200 - i*30)  # Dorado con degradé
        draw.rectangle([10+i*5, 10+i*5, 190-i*5, 30+i*5], outline=color, width=width)
        draw.rectangle([10+i*5, 10+i*5, 30+i*5, 190-i*5], outline=color, width=width)
    
    img.save("overlays/corner_decoration.png")
    print("✓ Creado: corner_decoration.png")
    
    # 3. Overlay de nota musical
    img = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Nota musical simple
    # Cabeza de la nota
    draw.ellipse([30, 60, 60, 80], fill=(255, 255, 255, 255))
    # Línea de la nota
    draw.rectangle([58, 20, 63, 70], fill=(255, 255, 255, 255))
    # Bandera
    draw.polygon([(63, 20), (63, 35), (85, 25), (85, 40), (63, 50)], fill=(255, 255, 255, 255))
    
    img.save("overlays/music_note.png")
    print("✓ Creado: music_note.png")
    
    # 4. Overlay de fuego/flame
    img = Image.new('RGBA', (80, 120), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Llama estilizada
    points = [(40, 100), (20, 80), (15, 60), (25, 40), (35, 45), 
              (40, 25), (45, 35), (55, 30), (65, 50), (60, 70), (40, 100)]
    
    # Gradiente de colores para la llama
    colors = [(255, 0, 0, 200), (255, 100, 0, 180), (255, 200, 0, 160)]
    
    for i, color in enumerate(colors):
        offset = i * 3
        offset_points = [(x + offset//2, y + offset) for x, y in points]
        draw.polygon(offset_points, fill=color)
    
    img.save("overlays/flame.png")
    print("✓ Creado: flame.png")
    
    # 5. Overlay de rayo/lightning
    img = Image.new('RGBA', (60, 100), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Rayo
    lightning_points = [(30, 10), (35, 10), (20, 40), (25, 40), 
                       (15, 70), (40, 45), (35, 45), (45, 20), (30, 10)]
    
    # Borde azul eléctrico
    for adj in range(-2, 3):
        for adj2 in range(-2, 3):
            if adj != 0 or adj2 != 0:
                offset_points = [(x + adj, y + adj2) for x, y in lightning_points]
                draw.polygon(offset_points, fill=(0, 100, 255, 150))
    
    # Rayo principal en blanco
    draw.polygon(lightning_points, fill=(255, 255, 255, 255))
    
    img.save("overlays/lightning.png")
    print("✓ Creado: lightning.png")
    
    # 6. Overlay de estrella
    img = Image.new('RGBA', (80, 80), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Estrella de 5 puntas
    import math
    center = (40, 40)
    outer_radius = 30
    inner_radius = 15
    
    star_points = []
    for i in range(10):
        angle = math.pi * i / 5
        if i % 2 == 0:
            radius = outer_radius
        else:
            radius = inner_radius
        x = center[0] + radius * math.cos(angle - math.pi/2)
        y = center[1] + radius * math.sin(angle - math.pi/2)
        star_points.append((x, y))
    
    # Borde dorado
    for adj in range(-2, 3):
        for adj2 in range(-2, 3):
            if adj != 0 or adj2 != 0:
                offset_points = [(x + adj, y + adj2) for x, y in star_points]
                draw.polygon(offset_points, fill=(200, 150, 0, 200))
    
    # Estrella principal
    draw.polygon(star_points, fill=(255, 215, 0, 255))
    
    img.save("overlays/star.png")
    print("✓ Creado: star.png")
    
    print("\n🎉 ¡Todos los overlays de ejemplo han sido creados!")
    print("Puedes encontrarlos en la carpeta 'overlays/'")
    print("\nCómo usar el editor:")
    print("1. Ejecuta el editor: python thumbnail_editor.py")
    print("2. Arrastra los overlays desde la librería al canvas")
    print("3. Usa los controles de la derecha para ajustar propiedades")
    print("4. Guarda tu thumbnail cuando esté listo")

if __name__ == "__main__":
    create_sample_overlays()