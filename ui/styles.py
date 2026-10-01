# -*- coding: utf-8 -*-
"""
Hoja de estilos de la interfaz.
"""

# Estilos profesionales
STYLESHEET = """
QMainWindow {
    background-color: #2b2b2b;
    color: white;
}

QLabel {
    color: white;
    font-size: 12px;
    padding: 2px;
}

QPushButton {
    background-color: #404040;
    color: white;
    border: 1px solid #555;
    padding: 8px;
    border-radius: 4px;
    font-size: 12px;
}

QPushButton:hover {
    background-color: #505050;
}

QPushButton:pressed {
    background-color: #606060;
}

QFrame {
    background-color: #353535;
    border: 1px solid #555;
    border-radius: 8px;
    margin: 2px;
}

QListWidget {
    background-color: #404040;
    color: white;
    border: 1px solid #555;
    selection-background-color: #0078D4;
    padding: 4px;
}

QComboBox {
    background-color: #404040;
    color: white;
    border: 1px solid #555;
    padding: 4px;
    border-radius: 4px;
}

QProgressBar {
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    background-color: #404040;
    color: white;
}

QProgressBar::chunk {
    background-color: #3498DB;
}
"""
