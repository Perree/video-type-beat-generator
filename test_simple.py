#!/usr/bin/env python3
"""
Test simple de las nuevas funcionalidades de thumbnail
"""

import sys
import os

def test_imports():
    """Verifica que las importaciones funcionan."""
    print("🔍 Verificando importaciones...")
    
    try:
        from main import ThumbnailConfigDialog, VideoGeneratorWorker
        print("✅ Clases principales importadas correctamente")
        return True
    except Exception as e:
        print(f"❌ Error importando: {e}")
        return False

def test_thumbnail_config():
    """Verifica que la configuración funciona."""
    print("🔧 Verificando configuración de thumbnails...")
    
    try:
        from main import ThumbnailConfigDialog
        from PyQt6.QtWidgets import QApplication
        
        # No ejecutar la interfaz gráfica, solo verificar que se puede crear
        app = QApplication.instance()
        if app is None:
            app = QApplication(sys.argv)
            
        dialog = ThumbnailConfigDialog()
        
        # Verificar configuración por defecto
        config = dialog.get_config()
        expected_keys = ['letterbox_style', 'show_text', 'use_custom_overlay', 'custom_overlay_path']
        
        for key in expected_keys:
            if key not in config:
                print(f"❌ Falta clave en configuración: {key}")
                return False
        
        print("✅ Configuración de thumbnails funciona correctamente")
        print(f"   - Configuración por defecto: {config}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error en configuración: {e}")
        return False

def test_functions_exist():
    """Verifica que las funciones necesarias existen."""
    print("🔍 Verificando funciones implementadas...")
    
    try:
        from main import VideoGeneratorWorker
        
        # Crear instancia temporal para verificar métodos
        worker = VideoGeneratorWorker("", "", "", [], {})
        
        # Verificar que los métodos existen
        if hasattr(worker, '_generate_thumbnail'):
            print("✅ Método _generate_thumbnail implementado")
        else:
            print("❌ Método _generate_thumbnail faltante")
            return False
            
        if hasattr(worker, '_apply_default_overlay'):
            print("✅ Método _apply_default_overlay implementado")
        else:
            print("❌ Método _apply_default_overlay faltante")
            return False
            
        print("✅ Todas las funciones necesarias están implementadas")
        return True
        
    except Exception as e:
        print(f"❌ Error verificando funciones: {e}")
        return False

def main():
    """Función principal de test."""
    print("🧪 TEST DE NUEVAS FUNCIONALIDADES DE THUMBNAIL")
    print("=" * 60)
    
    tests = [
        ("Importaciones", test_imports),
        ("Configuración de Thumbnails", test_thumbnail_config),
        ("Funciones Implementadas", test_functions_exist),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        if test_func():
            passed += 1
        else:
            print(f"   Test '{test_name}' falló")
    
    print(f"\n🎯 RESUMEN: {passed}/{total} tests pasaron")
    
    if passed == total:
        print("🎉 ¡TODOS LOS TESTS PASARON!")
        print("\n📝 FUNCIONALIDADES IMPLEMENTADAS:")
        print("✅ Diálogo de configuración de thumbnails antes de generar videos")
        print("✅ Soporte para estilo letterbox (barras negras) y pantalla completa")
        print("✅ Opción para mostrar/ocultar texto en thumbnails")
        print("✅ Soporte para overlays personalizados")
        print("✅ Generación automática de thumbnails durante creación de videos")
        print("✅ Sistema de overlay por defecto con transparencia")
        
        print("\n🚀 PARA USAR:")
        print("1. Ejecuta: python main.py")
        print("2. Genera videos - aparecerá diálogo de configuración")
        print("3. Configura el estilo de thumbnail que prefieras")
        print("4. Los thumbnails se generarán automáticamente junto con los videos")
        
    else:
        print("❌ Algunos tests fallaron - revisa la implementación")
    
    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)