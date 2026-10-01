#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Type Beat Video Generator - Versión Completa
------------------------------------------------
Aplicación para generar automáticamente videos para Type Beats.
Combina beats de audio con imágenes según género y exporta videos en formato MP4.
"""

import sys

from PyQt5.QtWidgets import QApplication, QStyleFactory

from ui.main_window import MainWindow


def main():
    """Función principal."""
    app = QApplication(sys.argv)
    
    # Configurar estilo
    app.setStyle(QStyleFactory.create('Fusion'))
    
    # Crear ventana principal
    window = MainWindow()
    window.show()
    
    # Ejecutar aplicación
    sys.exit(app.exec())


if __name__ == "__main__":
    main()