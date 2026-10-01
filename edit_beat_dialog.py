#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Diálogo para editar el nombre personalizado de un beat.
"""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                            QPushButton, QFormLayout, QFrame, QDoubleSpinBox,
                            QPlainTextEdit, QApplication, QMessageBox)
from PyQt5.QtCore import Qt
import os

from core import library, description, audio_analysis

try:
    import qtawesome as qta
except ImportError:
    qta = None

class EditBeatNameDialog(QDialog):
    """Diálogo para editar el nombre personalizado de un beat."""
    
    def __init__(self, beat_info=None, parent=None):
        super().__init__(parent)
        # Soportar llamada con (parent) cuando se edita desde la lista sin asignar
        if parent is None and beat_info is not None and not isinstance(beat_info, dict):
            parent, beat_info = beat_info, None
        if beat_info is None:
            beat_info = {'audio': '', 'channel': 'Sin asignar', 'group': '', 'custom_name': ''}
        self.beat_info = beat_info
        self.custom_name = self.beat_info.get('custom_name', '')
        self._setup_ui()
    
    def set_beat_info(self, beat_file, custom_name=''):
        """Asigna archivo y nombre (cuando se abre sin beat_info, ej. desde lista de beats)."""
        self.beat_info['audio'] = self.beat_info.get('beat_file') or beat_file
        self.beat_info['beat_file'] = beat_file
        self.beat_info['custom_name'] = custom_name
        self.custom_name = custom_name
        if hasattr(self, '_file_value'):
            self._file_value.setText(beat_file)
        if hasattr(self, 'name_input'):
            self.name_input.setText(custom_name)
            base_name, _ = os.path.splitext(beat_file)
            channel = self.beat_info.get('channel', '')
            group = self.beat_info.get('group', 'Principal')
            self.name_input.setPlaceholderText(f"{base_name}_{channel}_{group}")
        if hasattr(self, 'bpm_input'):
            self._lib_beat = library.find_beat_by_path(beat_file)
            self._fill_metadata()
            self._update_preview()
    
    def get_custom_name(self):
        """Devuelve el nombre personalizado introducido."""
        return getattr(self, 'custom_name', '') or (self.name_input.text().strip() if hasattr(self, 'name_input') else '')
    
    def _setup_ui(self):
        """Configura la interfaz del diálogo con estilo moderno."""
        self.setWindowTitle("Personalizar nombre del video")
        self.setFixedSize(640, 760)
        
        # Aplicar estilos
        self.setStyleSheet("""
            QDialog {
                background-color: #1E1E2E;
            }
            QLabel {
                color: #CDD6F4;
                font-size: 15px;
                margin: 2px;
                padding: 2px;
            }
            QLineEdit {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 8px;
                font-size: 15px;
                min-height: 30px;
                margin: 4px;
            }
            QPushButton {
                background-color: #89B4FA;
                color: #1E1E2E;
                font-weight: bold;
                padding: 10px 18px;
                border: none;
                border-radius: 6px;
                min-width: 120px;
                min-height: 36px;
                font-size: 14px;
                margin: 4px;
            }
            QPushButton:hover {
                background-color: #B4BEFE;
            }
            QPushButton:pressed {
                background-color: #74C7EC;
            }
            QDoubleSpinBox, QPlainTextEdit {
                background-color: #313244;
                color: #CDD6F4;
                border: 1px solid #45475A;
                border-radius: 4px;
                padding: 4px;
                font-size: 14px;
            }
            QFrame {
                background-color: #313244;
                border-radius: 8px;
                padding: 15px;
                margin: 5px;
            }
        """)
        
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Título
        title = QLabel("Personalizar nombre del video")
        title.setStyleSheet("font-size: 18px; color: #89B4FA; font-weight: bold;")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Tarjeta de información
        info_card = QFrame()
        info_card_layout = QFormLayout(info_card)
        
        # Información del beat (soporta 'audio' o 'beat_file')
        original_name = self.beat_info.get('audio') or self.beat_info.get('beat_file', '')
        base_name, _ = os.path.splitext(original_name)
        
        # Nombre del archivo (guardamos referencia por si se llama set_beat_info después)
        file_label = QLabel("Archivo de audio:")
        file_value = QLabel(original_name)
        file_value.setStyleSheet("font-weight: bold;")
        self._file_value = file_value
        info_card_layout.addRow(file_label, file_value)
        
        # Canal
        channel_label = QLabel("Canal:")
        channel_value = QLabel(self.beat_info.get('channel', 'Sin canal asignado'))
        channel_value.setStyleSheet("font-weight: bold;")
        info_card_layout.addRow(channel_label, channel_value)
        
        # Grupo
        group_label = QLabel("Grupo:")
        group_value = QLabel(self.beat_info.get('group', 'Principal'))
        group_value.setStyleSheet("font-weight: bold;")
        info_card_layout.addRow(group_label, group_value)
        
        layout.addWidget(info_card)
        
        # Explicación
        instruct = QLabel("Ingrese un nombre personalizado para el video final:")
        layout.addWidget(instruct)
        
        # Campo de texto para el nombre personalizado
        self.name_input = QLineEdit()
        if self.custom_name:
            self.name_input.setText(self.custom_name)
        else:
            channel = self.beat_info.get('channel', '')
            group = self.beat_info.get('group', 'Principal')
            self.name_input.setPlaceholderText(f"{base_name}_{channel}_{group}")
        
        layout.addWidget(self.name_input)
        
        # Nota
        note = QLabel("(Si lo deja vacío, se usará el formato predeterminado: nombre_beat_canal_grupo)")
        note.setStyleSheet("font-size: 12px; color: #6C7086; font-style: italic;")
        layout.addWidget(note)
        
        self._setup_metadata_ui(layout)
        
        # Botones
        btn_layout = QHBoxLayout()
        
        self.btn_cancel = QPushButton("Cancelar")
        if qta:
            self.btn_cancel.setIcon(qta.icon("fa5s.times", color="#1E1E2E"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)
        
        self.btn_save = QPushButton("Guardar")
        if qta:
            self.btn_save.setIcon(qta.icon("fa5s.save", color="#1E1E2E"))
        self.btn_save.clicked.connect(self._save_name)
        self.btn_save.setDefault(True)
        btn_layout.addWidget(self.btn_save)
        
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)
    
    def _setup_metadata_ui(self, layout):
        """BPM, key, link BeatStars y vista previa de la descripción (requiere beat en la biblioteca)."""
        self._lib_beat = library.find_beat_by_path(
            self.beat_info.get('audio') or self.beat_info.get('beat_file', ''))
        form = QFormLayout()
        self.bpm_input = QDoubleSpinBox()
        self.bpm_input.setRange(0, 300)
        self.bpm_input.setDecimals(1)
        self.bpm_input.setSpecialValueText("—")
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("ej. A minor")
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://www.beatstars.com/...")
        self.btn_analyze = QPushButton("Analizar BPM/key")
        self.btn_analyze.clicked.connect(self._analyze)
        form.addRow("BPM:", self.bpm_input)
        form.addRow("Key:", self.key_input)
        form.addRow("Link BeatStars:", self.url_input)
        layout.addLayout(form)
        layout.addWidget(self.btn_analyze)

        layout.addWidget(QLabel("Plantilla de descripción del canal ({name} {bpm} {key} {beatstars_url} {tags} {socials} {hashtags}):"))
        self.template_input = QPlainTextEdit()
        self.template_input.setFixedHeight(90)
        layout.addWidget(self.template_input)
        self.btn_save_template = QPushButton("Guardar plantilla del canal")
        self.btn_save_template.clicked.connect(self._save_template)
        layout.addWidget(self.btn_save_template)

        layout.addWidget(QLabel("Vista previa:"))
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setFixedHeight(110)
        layout.addWidget(self.preview)

        self._fill_metadata()
        settings = description.get_channel_settings(self._channel())
        self.template_input.setPlainText(settings['template'])
        for w in (self.key_input, self.url_input):
            w.textChanged.connect(self._update_preview)
        self.bpm_input.valueChanged.connect(self._update_preview)
        self.template_input.textChanged.connect(self._update_preview)
        self._update_preview()

    def _fill_metadata(self):
        b = self._lib_beat
        for w in (self.bpm_input, self.key_input, self.url_input, self.btn_analyze):
            w.setEnabled(bool(b))
        if b:
            self.bpm_input.setValue(b.get('bpm') or 0)
            self.key_input.setText(b.get('key') or '')
            self.url_input.setText(b.get('beatstars_url') or '')
        else:
            self.key_input.setPlaceholderText("Importa el beat a la biblioteca para editarlo")

    def _channel(self):
        ch = self.beat_info.get('channel', '')
        return '' if ch == 'Sin asignar' else ch

    def _update_preview(self):
        base, _ = os.path.splitext(self.beat_info.get('audio') or self.beat_info.get('beat_file', ''))
        name = self.name_input.text().strip() or (self._lib_beat or {}).get('nombre') or base
        s = description.get_channel_settings(self._channel())
        self.preview.setPlainText(description.render(
            self.template_input.toPlainText(), name, self.bpm_input.value() or None,
            self.key_input.text().strip(), self.url_input.text().strip(),
            socials=s['socials'], hashtags=s['hashtags']))

    def _analyze(self):
        if not self._lib_beat:
            return
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            bpm, key = audio_analysis.analyze(self._lib_beat['ruta'])
        except ImportError:
            QMessageBox.warning(self, "librosa no instalado", "Instala librosa: pip install librosa")
            return
        except Exception as e:
            QMessageBox.warning(self, "Error de análisis", str(e))
            return
        finally:
            QApplication.restoreOverrideCursor()
        self.bpm_input.setValue(bpm)
        self.key_input.setText(key)

    def _save_template(self):
        channel = self._channel()
        if not channel:
            QMessageBox.information(self, "Sin canal", "Asigna el beat a un canal para guardar su plantilla.")
            return
        description.save_channel_template(channel, self.template_input.toPlainText())

    def _save_name(self):
        """Guarda el nombre personalizado y la metadata en la biblioteca."""
        self.custom_name = self.name_input.text().strip()
        if self._lib_beat:
            bpm = self.bpm_input.value() or None
            key = self.key_input.text().strip() or None
            url = self.url_input.text().strip() or None
            library.update_beat(self._lib_beat['id'], bpm=bpm, key=key, beatstars_url=url)
            self.beat_info.update(bpm=bpm, key=key, beatstars_url=url)
        self.accept()
