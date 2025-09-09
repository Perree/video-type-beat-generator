#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Overlay Creator - Creador de Overlays de Ejemplo
-----------------------------------------------
Script para crear overlays PNG de ejemplo para las miniaturas.
"""

from PIL import Image, ImageDraw, ImageFont
import os

def create_overlay_examples():
    """Crea overlays de ejemplo para demostrar el sistema."""
    
    overlays_folder = "overlays"
    os.makedirs(overlays_folder, exist_ok=True)
    
    # Overlay 1: Gradiente oscuro con bordes
    def create_gradient_overlay():
        overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Gradiente superior
        for y in range(150):
            alpha = int((150 - y) * 180 / 150)
            draw.rectangle([(0, y), (1280, y+1)], fill=(0, 0, 0, alpha))
        
        # Gradiente inferior
        for y in range(150):
            alpha = int(y * 180 / 150)
            draw.rectangle([(0, 720-150+y), (1280, 720-150+y+1)], fill=(0, 0, 0, alpha))
        
        # Bordes laterales sutiles
        for x in range(40):
            alpha = int((40 - x) * 60 / 40)
            draw.rectangle([(x, 0), (x+1, 720)], fill=(0, 0, 0, alpha))
            draw.rectangle([(1280-x-1, 0), (1280-x, 720)], fill=(0, 0, 0, alpha))
        
        overlay.save(os.path.join(overlays_folder, "gradient_overlay.png"))
        print("✓ Creado: gradient_overlay.png")
    
    # Overlay 2: Marco simple con esquinas redondeadas
    def create_frame_overlay():
        overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Marco exterior
        border_width = 8
        draw.rectangle([
            (border_width, border_width), 
            (1280-border_width, 720-border_width)
        ], outline=(255, 255, 255, 200), width=border_width)
        
        # Esquinas decorativas
        corner_size = 30
        # Esquina superior izquierda
        draw.rectangle([
            (0, 0), (corner_size, corner_size)
        ], fill=(255, 255, 255, 150))
        
        # Esquina superior derecha
        draw.rectangle([
            (1280-corner_size, 0), (1280, corner_size)
        ], fill=(255, 255, 255, 150))
        
        # Esquina inferior izquierda
        draw.rectangle([
            (0, 720-corner_size), (corner_size, 720)
        ], fill=(255, 255, 255, 150))
        
        # Esquina inferior derecha
        draw.rectangle([
            (1280-corner_size, 720-corner_size), (1280, 720)
        ], fill=(255, 255, 255, 150))
        
        overlay.save(os.path.join(overlays_folder, "frame_overlay.png"))
        print("✓ Creado: frame_overlay.png")
    
    # Overlay 3: Overlay minimalista para texto
    def create_text_overlay():
        overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Barra inferior para texto
        bar_height = 120
        # Gradiente en la barra
        for y in range(bar_height):
            alpha = int((y / bar_height) * 180)
            draw.rectangle([
                (0, 720-bar_height+y), (1280, 720-bar_height+y+1)
            ], fill=(0, 0, 0, alpha))
        
        # Línea decorativa
        draw.rectangle([
            (0, 720-bar_height), (1280, 720-bar_height+4)
        ], fill=(255, 255, 255, 100))
        
        overlay.save(os.path.join(overlays_folder, "text_overlay.png"))
        print("✓ Creado: text_overlay.png")
    
    # Overlay 4: Overlay para canales de trap
    def create_trap_overlay():
        overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Efecto de viñeteado
        center_x, center_y = 640, 360
        max_distance = ((640**2 + 360**2) ** 0.5) * 0.8
        
        for y in range(720):
            for x in range(0, 1280, 4):  # Samplear cada 4 píxeles para eficiencia
                distance = ((x - center_x)**2 + (y - center_y)**2) ** 0.5
                if distance > max_distance * 0.6:
                    alpha = int((distance - max_distance * 0.6) / (max_distance * 0.4) * 120)
                    alpha = min(120, alpha)
                    for px in range(x, min(x+4, 1280)):
                        draw.point((px, y), fill=(0, 0, 0, alpha))
        
        # Líneas decorativas en las esquinas
        line_color = (255, 0, 100, 150)  # Rosa/magenta
        line_width = 3
        line_length = 80
        
        # Esquinas superiores
        for i in range(line_width):
            draw.line([(0, i), (line_length, i)], fill=line_color)
            draw.line([(i, 0), (i, line_length)], fill=line_color)
            draw.line([(1280-line_length, i), (1280, i)], fill=line_color)
            draw.line([(1280-i-1, 0), (1280-i-1, line_length)], fill=line_color)
        
        overlay.save(os.path.join(overlays_folder, "trap_overlay.png"))
        print("✓ Creado: trap_overlay.png")
    
    # Overlay 5: Overlay clean/minimalista
    def create_clean_overlay():
        overlay = Image.new('RGBA', (1280, 720), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        # Solo una sutil viñeta
        center_x, center_y = 640, 360
        
        for y in range(0, 720, 8):  # Samplear menos para este overlay sutil
            for x in range(0, 1280, 8):
                distance = ((x - center_x)**2 + (y - center_y)**2) ** 0.5
                max_dist = 600
                if distance > max_dist * 0.8:
                    alpha = int((distance - max_dist * 0.8) / (max_dist * 0.2) * 40)
                    alpha = min(40, alpha)
                    # Dibujar un cuadrado de 8x8
                    for dy in range(8):
                        for dx in range(8):
                            if x+dx < 1280 and y+dy < 720:
                                draw.point((x+dx, y+dy), fill=(0, 0, 0, alpha))
        
        overlay.save(os.path.join(overlays_folder, "clean_overlay.png"))
        print("✓ Creado: clean_overlay.png")
    
    # Crear todos los overlays
    create_gradient_overlay()
    create_frame_overlay()
    create_text_overlay()
    create_trap_overlay()
    create_clean_overlay()
    
    print(f"\n✅ Se crearon 5 overlays de ejemplo en la carpeta '{overlays_folder}'")
    print("\nDescripción de los overlays:")
    print("• gradient_overlay.png - Gradientes superior e inferior con bordes laterales")
    print("• frame_overlay.png - Marco blanco con esquinas decorativas")
    print("• text_overlay.png - Barra inferior semitransparente para texto")
    print("• trap_overlay.png - Viñeteado con líneas decorativas rosas")
    print("• clean_overlay.png - Viñeteado sutil y minimalista")

if __name__ == "__main__":
    create_overlay_examples()
