# -*- coding: utf-8 -*-
"""Hoja de estilos global de la ventana principal (PyQt5)."""

ACCENT_GENERATE = "#27AE60"
ACCENT_GENERATE_HOVER = "#2ECC71"

APPLICATION_STYLESHEET = f"""
QMainWindow {{
    background-color: #2b2b2b;
    color: #f0f0f0;
}}

QLabel {{
    color: #f0f0f0;
    font-size: 13px;
    padding: 2px;
}}

QPushButton {{
    background-color: #404040;
    color: #f0f0f0;
    border: 1px solid #555;
    padding: 8px;
    border-radius: 4px;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: #505050;
}}

QPushButton:pressed {{
    background-color: #606060;
}}

QPushButton#btn_generate_primary {{
    background-color: {ACCENT_GENERATE};
    color: white;
    border: 1px solid #1e8449;
    font-size: 15px;
    font-weight: bold;
    padding: 12px;
}}

QPushButton#btn_generate_primary:hover {{
    background-color: {ACCENT_GENERATE_HOVER};
}}

QPushButton#btn_generate_primary:disabled {{
    background-color: #3d5c4a;
    color: #aaa;
}}

QPushButton#section_nav_active {{
    background-color: #0078D4;
    border: 1px solid #005a9e;
    font-weight: bold;
}}

QFrame {{
    background-color: #353535;
    border: 1px solid #555;
    border-radius: 8px;
    margin: 2px;
}}

QListWidget {{
    background-color: #404040;
    color: #f0f0f0;
    border: 1px solid #555;
    selection-background-color: #0078D4;
    padding: 4px;
    font-size: 13px;
}}

QComboBox {{
    background-color: #404040;
    color: #f0f0f0;
    border: 1px solid #555;
    padding: 6px;
    border-radius: 4px;
    font-size: 13px;
}}

QCheckBox, QRadioButton {{
    color: #ddd;
    font-size: 13px;
}}

QTableWidget {{
    background-color: #404040;
    alternate-background-color: #464646;
    color: #f0f0f0;
    gridline-color: #555;
    border: 1px solid #555;
    selection-background-color: #0078D4;
    font-size: 13px;
}}

QHeaderView::section {{
    background-color: #353535;
    color: #ddd;
    border: none;
    border-right: 1px solid #555;
    padding: 4px;
}}

QPlainTextEdit, QTextEdit {{
    background-color: #404040;
    color: #f0f0f0;
    border: 1px solid #555;
    font-size: 13px;
}}

QGroupBox {{
    font-size: 13px;
    font-weight: bold;
    color: #ddd;
    border: 1px solid #555;
    border-radius: 6px;
    margin-top: 10px;
    padding-top: 8px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}}

QProgressBar {{
    border: 1px solid #555;
    border-radius: 4px;
    text-align: center;
    background-color: #404040;
    color: white;
    font-size: 13px;
}}

QProgressBar::chunk {{
    background-color: #3498DB;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}

QSpinBox {{
    background-color: #404040;
    color: #f0f0f0;
    border: 1px solid #555;
    padding: 4px;
    font-size: 13px;
}}
"""


