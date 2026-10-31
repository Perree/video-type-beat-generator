# -*- coding: utf-8 -*-
"""Tema visual de la app: colores, tipografía y espaciado en un solo lugar.

Para ajustar el aspecto, cambiá los valores de ``COLORS``, ``FONT`` y ``SPACE``.
Las pantallas no escriben colores sueltos: usan los roles de este módulo:

- Botones: ``primary(b)`` (una acción principal por pantalla), ``flat(b)`` (discreto),
  ``danger(b)`` (borrar o quitar). Sin rol = botón secundario.
- Textos: ``title(l)``, ``subtitle(l)``, ``muted(l)`` (ayuda corta, gris), ``tone(l, 'error')``.
- Bloques: ``section('Título')`` (tarjeta con título), ``Collapsible`` (lo poco usado, plegado).
"""
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import (QFormLayout, QGroupBox, QHBoxLayout, QSizePolicy, QToolButton,
                             QVBoxLayout, QWidget)

# --- Tokens -------------------------------------------------------------------------------

COLORS = {
    'bg': '#1B1C1F',             # fondo de la ventana
    'surface': '#232529',        # tarjetas y secciones
    'surface_alt': '#2C2F34',    # campos, botones secundarios
    'surface_hover': '#353940',
    'border': '#363940',
    'border_strong': '#4A4E56',
    'text': '#ECEDEF',
    'text_muted': '#A3A7AE',
    'text_disabled': '#6B6F77',
    'accent': '#2F6FEB',         # el único color de acento
    'accent_hover': '#4A82F0',
    'accent_pressed': '#2559C4',
    'accent_disabled': '#283650',
    'on_accent': '#FFFFFF',
    'success': '#3FB97A',
    'warning': '#E0A43A',
    'danger': '#EF6461',
}

FONT_FAMILY = 'Segoe UI'
FONT = {'body': 14, 'subtitle': 16, 'title': 20, 'display': 26}
SPACE = {'xs': 4, 's': 8, 'm': 12, 'l': 16, 'xl': 24, 'xxl': 32}
RADIUS = 8

# Compatibilidad con pantallas que todavía no pasaron al tema nuevo.
ACCENT_GENERATE = COLORS['accent']
ACCENT_GENERATE_HOVER = COLORS['accent_hover']


_ICONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'assets', 'ui').replace('\\', '/')


def _icon(name):
    return f'{_ICONS}/{name}.svg'


def color(name):
    """Color del tema por nombre (para textos enriquecidos: ``<span style="color:…">``)."""
    return COLORS[name]


# --- Hoja de estilos ------------------------------------------------------------------------

def build_stylesheet(c=COLORS, f=FONT, s=SPACE, r=RADIUS):
    return f"""
QWidget {{
    font-family: "{FONT_FAMILY}";
    font-size: {f['body']}px;
    font-weight: 400;
    color: {c['text']};
}}
QMainWindow, QDialog {{ background-color: {c['bg']}; }}

QLabel {{ background: transparent; border: none; padding: 0; }}
QLabel:disabled {{ color: {c['text_disabled']}; }}
QLabel[role="display"] {{ font-size: {f['display']}px; font-weight: 600; }}
QLabel[role="title"] {{ font-size: {f['title']}px; font-weight: 600; }}
QLabel[role="subtitle"] {{ font-size: {f['subtitle']}px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {c['text_muted']}; }}
QLabel[role="success"] {{ color: {c['success']}; }}
QLabel[role="warning"] {{ color: {c['warning']}; }}
QLabel[role="error"] {{ color: {c['danger']}; }}

QFrame[role="card"] {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: {r + 2}px;
}}

/* Secciones: título arriba, contenido en una tarjeta. */
QGroupBox {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: {r + 2}px;
    margin-top: {s['xl'] + s['s']}px;
    padding: {s['l']}px {s['l']}px {s['m']}px {s['l']}px;
    font-size: {f['subtitle']}px;
    font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 2px;
    padding: 0 0 {s['s']}px 0;
    color: {c['text']};
}}

/* Botones */
QPushButton, QToolButton {{
    background-color: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    border-radius: {r}px;
    padding: {s['s']}px {s['l']}px;
}}
QPushButton:hover, QToolButton:hover {{ background-color: {c['surface_hover']}; }}
QPushButton:pressed, QToolButton:pressed {{ background-color: {c['border_strong']}; }}
QPushButton:checked {{ border-color: {c['accent']}; }}
QPushButton:disabled, QToolButton:disabled {{
    color: {c['text_disabled']};
    background-color: {c['surface']};
    border-color: {c['border']};
}}
QPushButton[role="primary"], QPushButton#btn_generate_primary {{
    background-color: {c['accent']};
    color: {c['on_accent']};
    border: 1px solid {c['accent']};
    font-size: {f['subtitle']}px;
    font-weight: 600;
    padding: {s['m'] - 2}px {s['xl']}px;
}}
QPushButton[role="primary"]:hover, QPushButton#btn_generate_primary:hover {{
    background-color: {c['accent_hover']};
    border-color: {c['accent_hover']};
}}
QPushButton[role="primary"]:pressed {{ background-color: {c['accent_pressed']}; }}
QPushButton[role="primary"]:disabled, QPushButton#btn_generate_primary:disabled {{
    background-color: {c['accent_disabled']};
    border-color: {c['accent_disabled']};
    color: {c['text_muted']};
}}
QPushButton[role="flat"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {c['text_muted']};
    padding: {s['s'] - 2}px {s['m']}px;
}}
QPushButton[role="flat"]:hover {{ background-color: {c['surface_alt']}; color: {c['text']}; }}
QPushButton[role="flat"]:disabled {{ color: {c['text_disabled']}; background: transparent; }}
QPushButton[role="danger"] {{
    background-color: transparent;
    border: 1px solid transparent;
    color: {c['danger']};
    padding: {s['s'] - 2}px {s['m']}px;
}}
QPushButton[role="danger"]:hover {{ background-color: #3A2427; }}
QPushButton[role="danger"]:disabled {{ color: {c['text_disabled']}; background: transparent; }}
QPushButton#section_nav_active {{ border-color: {c['accent']}; font-weight: 600; }}
QToolButton[role="disclosure"] {{
    background: transparent;
    border: none;
    color: {c['text_muted']};
    font-weight: 600;
    padding: {s['s']}px 0;
}}
QToolButton[role="disclosure"]:hover {{ color: {c['text']}; }}

/* Campos */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit, QComboBox {{
    background-color: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    border-radius: {r - 2}px;
    padding: {s['s'] - 2}px {s['s']}px;
    selection-background-color: {c['accent']};
    selection-color: {c['on_accent']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QTimeEdit:focus, QDateEdit:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled, QSpinBox:disabled,
QDoubleSpinBox:disabled, QTimeEdit:disabled, QComboBox:disabled {{
    color: {c['text_disabled']};
    background-color: {c['surface']};
    border-color: {c['border']};
}}
QComboBox {{ padding-right: 26px; }}
QComboBox::drop-down {{ border: none; width: 26px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({_icon('chevron-down')}); width: 12px; height: 12px; }}
QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit {{ padding-right: 22px; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QTimeEdit::up-button, QDateEdit::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button, QTimeEdit::down-button, QDateEdit::down-button {{
    border: none; background: transparent; width: 20px;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QTimeEdit::up-arrow, QDateEdit::up-arrow {{
    image: url({_icon('chevron-up')}); width: 10px; height: 10px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QTimeEdit::down-arrow, QDateEdit::down-arrow {{
    image: url({_icon('chevron-down')}); width: 10px; height: 10px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['surface_alt']};
    border: 1px solid {c['border_strong']};
    selection-background-color: {c['accent']};
    selection-color: {c['on_accent']};
    outline: 0;
}}
QCheckBox, QRadioButton {{ background: transparent; spacing: {s['s']}px; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {c['text_disabled']}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px; height: 16px;
    background-color: {c['surface_alt']};
    border: 1px solid {c['border_strong']};
}}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {c['accent']}; }}
QCheckBox::indicator:checked {{
    background-color: {c['accent']}; border-color: {c['accent']}; image: url({_icon('check')});
}}
QRadioButton::indicator:checked {{
    border: 1px solid {c['accent']};
    background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
        stop:0 {c['on_accent']}, stop:0.35 {c['on_accent']}, stop:0.45 {c['accent']}, stop:1 {c['accent']});
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background-color: {c['surface']}; border-color: {c['border']};
}}
QCheckBox::indicator:checked:disabled {{ background-color: {c['accent_disabled']}; }}

/* Listas y tablas */
QListWidget, QListView, QTableWidget, QTableView, QTreeView {{
    background-color: {c['surface_alt']};
    alternate-background-color: {c['surface_hover']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: {r}px;
    gridline-color: {c['border']};
    selection-background-color: {c['accent']};
    selection-color: {c['on_accent']};
    outline: 0;
}}
QListWidget::item, QListView::item {{ padding: {s['s'] - 2}px {s['s']}px; }}
QHeaderView::section {{
    background-color: {c['surface']};
    color: {c['text_muted']};
    border: none;
    border-bottom: 1px solid {c['border']};
    padding: {s['s'] - 2}px {s['s']}px;
    font-weight: 600;
}}
QTableCornerButton::section {{ background-color: {c['surface']}; border: none; }}

/* Pestañas */
QTabWidget::pane {{ border: none; border-top: 1px solid {c['border']}; top: -1px; }}
QTabBar {{ background: transparent; }}
QTabBar::tab {{
    background: transparent;
    color: {c['text_muted']};
    border: none;
    border-bottom: 2px solid transparent;
    padding: {s['s']}px {s['l']}px;
    margin-right: {s['xs']}px;
}}
QTabBar::tab:hover {{ color: {c['text']}; }}
QTabBar::tab:selected {{ color: {c['text']}; border-bottom: 2px solid {c['accent']}; }}

/* Varios */
QScrollArea {{ background: transparent; border: none; }}
QProgressBar {{
    background-color: {c['surface_alt']};
    border: none;
    border-radius: {r - 2}px;
    min-height: 10px;
    text-align: center;
    color: {c['text']};
}}
QProgressBar::chunk {{ background-color: {c['accent']}; border-radius: {r - 2}px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
    background: {c['border_strong']};
    border-radius: 3px;
    min-height: 30px;
    min-width: 30px;
}}
QScrollBar::handle:hover {{ background: {c['text_disabled']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QToolTip {{
    background-color: {c['surface_alt']};
    color: {c['text']};
    border: 1px solid {c['border_strong']};
    padding: {s['s'] - 2}px;
}}
QMenu {{
    background-color: {c['surface_alt']};
    border: 1px solid {c['border_strong']};
    padding: {s['xs']}px;
}}
QMenu::item {{ padding: {s['s'] - 2}px {s['l']}px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {c['accent']}; color: {c['on_accent']}; }}
"""


APPLICATION_STYLESHEET = build_stylesheet()


def palette(c=COLORS):
    """Paleta oscura para lo que Qt dibuja sin hoja de estilos (casillas, menús nativos)."""
    pal = QPalette()
    for role, key in ((QPalette.Window, 'bg'), (QPalette.WindowText, 'text'), (QPalette.Base, 'surface_alt'),
                      (QPalette.AlternateBase, 'surface_hover'), (QPalette.Text, 'text'),
                      (QPalette.Button, 'surface_alt'), (QPalette.ButtonText, 'text'),
                      (QPalette.ToolTipBase, 'surface_alt'), (QPalette.ToolTipText, 'text'),
                      (QPalette.Highlight, 'accent'), (QPalette.HighlightedText, 'on_accent'),
                      (QPalette.PlaceholderText, 'text_disabled'), (QPalette.Link, 'accent_hover')):
        pal.setColor(role, QColor(c[key]))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(c['text_disabled']))
    return pal


def apply_theme(app):
    """Aplica fuente, paleta y hoja de estilos a toda la app (también a los diálogos)."""
    app.setFont(QFont(FONT_FAMILY, 10))
    app.setPalette(palette())
    app.setStyleSheet(APPLICATION_STYLESHEET)


# --- Roles ----------------------------------------------------------------------------------

def set_role(widget, role):
    widget.setProperty('role', role)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    return widget


def primary(button):
    return set_role(button, 'primary')


def flat(button):
    return set_role(button, 'flat')


def danger(button):
    return set_role(button, 'danger')


def title(label):
    return set_role(label, 'title')


def subtitle(label):
    return set_role(label, 'subtitle')


def muted(label, wrap=True):
    label.setWordWrap(wrap)
    return set_role(label, 'muted')


def tone(label, kind):
    """Color de un texto de estado: ``'success'``, ``'warning'``, ``'error'``, ``'muted'`` o ``None``."""
    return set_role(label, kind)


# --- Bloques --------------------------------------------------------------------------------

def form_layout(parent=None):
    """Formulario con etiquetas a la izquierda y espaciado del tema."""
    form = QFormLayout(parent) if parent is not None else QFormLayout()
    form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    form.setHorizontalSpacing(SPACE['l'])
    form.setVerticalSpacing(SPACE['m'])
    return form


def section(heading, form=False):
    """Tarjeta con título. Devuelve ``(caja, layout)``; ``form=True`` da un ``QFormLayout``."""
    box = QGroupBox(heading)
    layout = form_layout(box) if form else QVBoxLayout(box)
    if not form:
        layout.setSpacing(SPACE['m'])
    return box, layout


def button_row(*buttons, align='left'):
    """Fila de botones de tamaño natural (no se estiran a todo el ancho)."""
    row = QHBoxLayout()
    row.setSpacing(SPACE['s'])
    if align == 'right':
        row.addStretch(1)
    for button in buttons:
        if button is None:
            row.addStretch(1)
        else:
            row.addWidget(button)
    if align == 'left':
        row.addStretch(1)
    return row


class Collapsible(QWidget):
    """Sección plegable para lo poco usado. Arranca cerrada; ``body`` es su layout."""

    def __init__(self, text, expanded=False, parent=None):
        super().__init__(parent)
        self._text = text
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACE['s'])
        self.toggle = QToolButton()
        set_role(self.toggle, 'disclosure')
        self.toggle.setCheckable(True)
        self.toggle.setCursor(Qt.PointingHandCursor)
        self.toggle.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.toggle.toggled.connect(self.set_expanded)
        outer.addWidget(self.toggle)
        self.content = QWidget()
        self.body = QVBoxLayout(self.content)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(SPACE['m'])
        outer.addWidget(self.content)
        self.set_expanded(expanded)

    def set_expanded(self, on):
        if self.toggle.isChecked() != on:
            self.toggle.setChecked(on)
            return
        self.toggle.setText(('▾  ' if on else '▸  ') + self._text)
        self.content.setVisible(on)

    def is_expanded(self):
        return self.toggle.isChecked()
