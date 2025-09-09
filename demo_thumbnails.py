#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Thumbnail Demo - Demostración del Sistema de Miniaturas
------------------------------------------------------
Script para generar miniaturas de demostración usando diferentes templates.
"""

import os
from PIL import Image, ImageDraw
from thumbnail_generator import ThumbnailGenerator, generate_thumbnail

def create_demo_image():
    """Crea una imagen de demostración para probar las miniaturas."""
    demo_folder = "demo_images"
    os.makedirs(demo_folder, exist_ok=True)
    
    # Crear una imagen de ejemplo con gradiente
    img = Image.new('RGB', (1920, 1080), (50, 50, 50))
    draw = ImageDraw.Draw(img)
    
    # Gradiente diagonal
    for y in range(1080):
        for x in range(0, 1920, 10):  # Cada 10 píxeles para eficiencia
            # Color que va de azul a púrpura
            blue = int(100 + (x / 1920) * 155)
            purple = int(50 + (y / 1080) * 100)
            red = int(30 + ((x + y) / 3000) * 120)
            
            for px in range(x, min(x + 10, 1920)):
                draw.point((px, y), (red, blue, purple))
    
    # Agregar algunos elementos decorativos
    # Círculos
    for i in range(5):
        x = 200 + i * 300
        y = 300 + (i % 2) * 400
        radius = 80 + i * 20
        draw.ellipse([
            (x - radius, y - radius), 
            (x + radius, y + radius)
        ], fill=(255, 255, 255, 100), outline=(255, 255, 255, 200), width=3)
    
    # Líneas decorativas
    for i in range(0, 1920, 150):
        draw.line([(i, 0), (i + 100, 1080)], fill=(255, 255, 255, 50), width=2)
    
    demo_path = os.path.join(demo_folder, "demo_beat_image.jpg")
    img.save(demo_path, 'JPEG', quality=95)
    return demo_path

def generate_demo_thumbnails():
    """Genera miniaturas de demostración usando todos los templates."""
    
    print("🎨 Generando miniaturas de demostración...")
    
    # Crear imagen de demo
    demo_image = create_demo_image()
    print(f"✓ Imagen de demo creada: {demo_image}")
    
    # Crear carpeta de salida
    output_folder = "demo_thumbnails"
    os.makedirs(output_folder, exist_ok=True)
    
    generator = ThumbnailGenerator()
    
    # Demo 1: Template centrado con diferentes proporciones de borde
    border_ratios = [0.05, 0.1, 0.15, 0.2]
    for i, ratio in enumerate(border_ratios):
        output_path = os.path.join(output_folder, f"01_centered_border_{int(ratio*100)}percent.jpg")
        success = generate_thumbnail(
            bg_image_path=demo_image,
            output_path=output_path,
            template='centered_image',
            border_ratio=ratio
        )
        if success:
            print(f"✓ Miniatura centrada creada con borde {int(ratio*100)}%")
    
    # Demo 2: Template con overlays
    overlays = [
        "overlays/gradient_overlay.png",
        "overlays/frame_overlay.png", 
        "overlays/text_overlay.png",
        "overlays/trap_overlay.png",
        "overlays/clean_overlay.png"
    ]
    
    texts = [
        "GRADIENT BEATS",
        "FRAMED BEATS",
        "TEXT OVERLAY",
        "TRAP VIBES",
        "CLEAN STYLE"
    ]
    
    for i, (overlay, text) in enumerate(zip(overlays, texts)):
        if os.path.exists(overlay):
            output_path = os.path.join(output_folder, f"02_overlay_{i+1}_{text.lower().replace(' ', '_')}.jpg")
            success = generate_thumbnail(
                bg_image_path=demo_image,
                output_path=output_path,
                template='overlay_template',
                overlay_path=overlay,
                text=text,
                text_color=(255, 255, 255, 255),
                text_size=50,
                text_position="bottom_center"
            )
            if success:
                print(f"✓ Miniatura con overlay creada: {text}")
    
    # Demo 3: Template full cover
    output_path = os.path.join(output_folder, "03_full_cover_normal.jpg")
    success = generate_thumbnail(
        bg_image_path=demo_image,
        output_path=output_path,
        template='full_cover',
        blur_background=False
    )
    if success:
        print("✓ Miniatura full cover creada")
    
    # Demo 4: Full cover con desenfoque
    output_path = os.path.join(output_folder, "04_full_cover_blurred.jpg")
    success = generate_thumbnail(
        bg_image_path=demo_image,
        output_path=output_path,
        template='full_cover',
        blur_background=True
    )
    if success:
        print("✓ Miniatura full cover con desenfoque creada")
    
    # Demo 5: Diferentes posiciones de texto
    text_positions = [
        ("bottom_center", "BOTTOM CENTER"),
        ("top_center", "TOP CENTER"),
        ("center", "CENTER"),
        ("bottom_left", "BOTTOM LEFT"),
        ("top_right", "TOP RIGHT")
    ]
    
    for i, (position, text) in enumerate(text_positions):
        output_path = os.path.join(output_folder, f"05_text_position_{position}.jpg")
        success = generate_thumbnail(
            bg_image_path=demo_image,
            output_path=output_path,
            template='overlay_template',
            overlay_path="overlays/text_overlay.png",
            text=text,
            text_color=(255, 255, 255, 255),
            text_size=40,
            text_position=position
        )
        if success:
            print(f"✓ Miniatura con texto en {position}")
    
    # Demo 6: Diferentes tamaños de texto
    text_sizes = [30, 45, 60, 80, 100]
    for size in text_sizes:
        output_path = os.path.join(output_folder, f"06_text_size_{size}px.jpg")
        success = generate_thumbnail(
            bg_image_path=demo_image,
            output_path=output_path,
            template='overlay_template',
            overlay_path="overlays/gradient_overlay.png",
            text=f"SIZE {size}PX",
            text_color=(255, 255, 255, 255),
            text_size=size,
            text_position="bottom_center"
        )
        if success:
            print(f"✓ Miniatura con texto tamaño {size}px")
    
    print(f"\n✅ Demostración completada!")
    print(f"📁 Las miniaturas de demo están en: {output_folder}")
    print(f"🖼️ Imagen de demo en: demo_images/")
    
    # Crear archivo HTML para ver todas las miniaturas
    create_demo_html(output_folder)

def create_demo_html(output_folder):
    """Crea una página HTML para visualizar todas las miniaturas generadas."""
    
    html_content = """<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Demo - Sistema de Miniaturas</title>
    <style>
        body {
            font-family: 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #1e3c72, #2a5298);
            margin: 0;
            padding: 20px;
            color: white;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            text-align: center;
            color: #fff;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
            margin-bottom: 30px;
        }
        .section {
            margin-bottom: 40px;
            background: rgba(255,255,255,0.1);
            border-radius: 10px;
            padding: 20px;
            backdrop-filter: blur(10px);
        }
        .section h2 {
            color: #00d4ff;
            border-bottom: 2px solid #00d4ff;
            padding-bottom: 10px;
        }
        .gallery {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }
        .thumbnail-item {
            text-align: center;
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 15px;
            transition: transform 0.3s ease;
        }
        .thumbnail-item:hover {
            transform: scale(1.05);
        }
        .thumbnail-item img {
            max-width: 100%;
            height: auto;
            border-radius: 5px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.3);
        }
        .thumbnail-item p {
            margin-top: 10px;
            font-size: 14px;
            color: #ccc;
        }
        .stats {
            background: rgba(0,0,0,0.4);
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎨 Demo - Sistema de Miniaturas para Type Beats</h1>
        
        <div class="stats">
            <h3>📊 Estadísticas de la Demostración</h3>
            <p>• <strong>Templates probados:</strong> 3 (centered_image, overlay_template, full_cover)</p>
            <p>• <strong>Overlays utilizados:</strong> 5 diferentes estilos</p>
            <p>• <strong>Configuraciones de texto:</strong> Múltiples posiciones y tamaños</p>
            <p>• <strong>Resolución de salida:</strong> 1280x720 (16:9 optimizado para YouTube)</p>
        </div>
"""
    
    # Obtener todas las imágenes generadas
    thumbnails = []
    for file in os.listdir(output_folder):
        if file.endswith('.jpg'):
            thumbnails.append(file)
    
    # Agrupar por categoría
    categories = {
        "01": ("🖼️ Template: Imagen Centrada", "Diferentes proporciones de bordes negros"),
        "02": ("🎨 Template: Overlay y Texto", "Diferentes overlays PNG con texto personalizado"),
        "03": ("📷 Template: Cobertura Completa", "Imagen completa sin bordes"),
        "04": ("🌫️ Template: Cobertura con Desenfoque", "Efecto de desenfoque sutil"),
        "05": ("📝 Posiciones de Texto", "Diferentes ubicaciones para el texto"),
        "06": ("🔤 Tamaños de Texto", "Variaciones en el tamaño de fuente")
    }
    
    for prefix, (title, description) in categories.items():
        category_thumbs = [t for t in thumbnails if t.startswith(prefix)]
        if category_thumbs:
            html_content += f"""
        <div class="section">
            <h2>{title}</h2>
            <p>{description}</p>
            <div class="gallery">
"""
            
            for thumb in sorted(category_thumbs):
                name = thumb.replace('.jpg', '').replace('_', ' ').title()
                html_content += f"""
                <div class="thumbnail-item">
                    <img src="{thumb}" alt="{name}">
                    <p>{name}</p>
                </div>
"""
            
            html_content += """
            </div>
        </div>
"""
    
    html_content += """
        <div class="section">
            <h2>🚀 Cómo Usar en el Programa</h2>
            <ol>
                <li><strong>Cargar Beats:</strong> Agrega tus archivos de audio</li>
                <li><strong>Asignar Canales:</strong> Asigna cada beat a un canal específico</li>
                <li><strong>Configurar Miniaturas:</strong> Haz clic en "🖼️ CONFIGURAR MINIATURAS"</li>
                <li><strong>Seleccionar Template:</strong> Elige el estilo que prefieras para cada canal</li>
                <li><strong>Personalizar:</strong> Ajusta overlays, texto, colores y posiciones</li>
                <li><strong>Generar:</strong> Ejecuta la generación de videos y miniaturas</li>
            </ol>
        </div>
        
        <div class="section">
            <h2>💡 Consejos de Uso</h2>
            <ul>
                <li><strong>Template "Imagen Centrada":</strong> Ideal para un look clean y profesional</li>
                <li><strong>Template "Overlay":</strong> Perfecto para branding fuerte y texto destacado</li>
                <li><strong>Template "Cobertura Completa":</strong> Maximiza el impacto visual de la imagen</li>
                <li><strong>Overlays personalizados:</strong> Puedes crear tus propios archivos PNG</li>
                <li><strong>Texto dinámico:</strong> Usa variables como {CHANNEL} y {BEAT}</li>
            </ul>
        </div>
        
        <footer style="text-align: center; margin-top: 40px; padding: 20px; border-top: 1px solid rgba(255,255,255,0.3);">
            <p>Generado por <strong>Type Beat Video Generator</strong> - Sistema de Miniaturas v1.0</p>
        </footer>
    </div>
</body>
</html>"""
    
    html_path = os.path.join(output_folder, "demo_gallery.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    print(f"🌐 Galería HTML creada: {html_path}")
    print("   Abre este archivo en tu navegador para ver todas las miniaturas")

if __name__ == "__main__":
    generate_demo_thumbnails()
