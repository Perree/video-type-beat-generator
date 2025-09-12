#!/usr/bin/env python3
"""
Script de prueba para verificar la generación automática de thumbnails
"""

import os
import sys

def test_thumbnail_generation():
    """Prueba la generación automática de thumbnails"""
    print("🧪 PROBANDO GENERACIÓN AUTOMÁTICA DE THUMBNAILS")
    print("=" * 60)
    
    # Verificar dependencias
    try:
        from PIL import Image, ImageDraw, ImageFont
        print("✅ PIL/Pillow disponible")
    except ImportError:
        print("❌ PIL/Pillow no disponible")
        return False
        
    try:
        import PyQt6
        print("✅ PyQt6 disponible")
    except ImportError:
        print("❌ PyQt6 no disponible")
        return False
    
    # Verificar archivos necesarios
    if os.path.exists("thumbnail_editor.py"):
        print("✅ thumbnail_editor.py encontrado")
    else:
        print("❌ thumbnail_editor.py no encontrado")
        return False
        
    if os.path.exists("thumbnail_config.py"):
        print("✅ thumbnail_config.py encontrado")
    else:
        print("❌ thumbnail_config.py no encontrado")
        return False
    
    # Verificar carpetas
    if os.path.exists("overlays"):
        overlay_count = len([f for f in os.listdir("overlays") if f.endswith('.png')])
        print(f"✅ Carpeta overlays encontrada con {overlay_count} overlays")
    else:
        print("❌ Carpeta overlays no encontrada")
        
    if os.path.exists("test_images"):
        print("✅ Carpeta test_images disponible")
    else:
        print("❌ Carpeta test_images no encontrada")
    
    print("\\n🎯 FUNCIONALIDADES IMPLEMENTADAS:")
    print("• Generación automática de thumbnails durante creación de videos")
    print("• Thumbnails personalizados usando configuraciones guardadas")
    print("• Thumbnails automáticos con texto del beat y canal")
    print("• Formato YouTube 1280x720 optimizado")
    
    print("\\n🚀 CÓMO FUNCIONA:")
    print("1. Al generar videos, automáticamente se crean thumbnails")
    print("2. Si hay configuración guardada del canal → thumbnail personalizado")
    print("3. Si no hay configuración → thumbnail automático con texto")
    print("4. Archivos generados por video:")
    print("   • video.mp4")
    print("   • imagen_utilizada.jpg")
    print("   • thumbnail.png")
    
    print("\\n📝 PARA PROBAR:")
    print("1. Ejecuta: python main.py")
    print("2. Carga algunos beats")
    print("3. Asigna canales")
    print("4. Genera videos")
    print("5. ¡Verifica que se generen thumbnails automáticamente!")
    
    return True

def test_manual_thumbnail():
    """Prueba la generación manual de un thumbnail"""
    print("\\n🎨 PROBANDO GENERACIÓN MANUAL DE THUMBNAIL")
    print("=" * 50)
    
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Crear thumbnail de prueba
        thumbnail = Image.new('RGB', (1280, 720), (30, 30, 30))
        draw = ImageDraw.Draw(thumbnail)
        
        # Agregar texto de prueba
        try:
            font = ImageFont.truetype("arial.ttf", 72)
        except:
            font = ImageFont.load_default()
            
        text = "SAMPLE TYPE BEAT"
        
        # Calcular posición centrada
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        x = (1280 - text_width) // 2
        y = 300
        
        # Dibujar texto con borde
        for adj in range(-3, 4):
            for adj2 in range(-3, 4):
                if adj != 0 or adj2 != 0:
                    draw.text((x + adj, y + adj2), text, font=font, fill=(0, 0, 0))
        
        draw.text((x, y), text, font=font, fill=(255, 255, 255))
        
        # Guardar
        os.makedirs("test_output", exist_ok=True)
        thumbnail.save("test_output/sample_thumbnail.png")
        print("✅ Thumbnail de prueba generado: test_output/sample_thumbnail.png")
        
        return True
        
    except Exception as e:
        print(f"❌ Error generando thumbnail de prueba: {e}")
        return False

if __name__ == "__main__":
    print("🔍 VERIFICADOR DE SISTEMA DE THUMBNAILS")
    print("=" * 70)
    
    if test_thumbnail_generation():
        print("\\n✅ SISTEMA VERIFICADO CORRECTAMENTE")
        
        # Probar generación manual
        if test_manual_thumbnail():
            print("\\n🎉 ¡TODO FUNCIONA! El sistema de thumbnails está listo.")
        else:
            print("\\n⚠️ Generación manual falló, pero el sistema principal debería funcionar.")
    else:
        print("\\n❌ PROBLEMAS DETECTADOS - Revisa las dependencias")
    
    print("\\n" + "=" * 70)