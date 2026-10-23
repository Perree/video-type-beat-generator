#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Type Beat Video Generator
-------------------------
Punto de entrada. La ventana vive en ``core/main_window.py``: Inicio con «Crear videos ahora»
(local), «Mis canales automatizados» (nube), «Conexiones» y el asistente paso a paso.
"""

import os
import sys

from PyQt5.QtWidgets import QApplication, QStyleFactory

from core.main_window import MainWindow

__all__ = ['MainWindow', 'main']


def main():
    """Función principal."""
    # tokens/, config/ e images/ se resuelven relativos al cwd en varios módulos.
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Fusion'))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
