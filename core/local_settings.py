# -*- coding: utf-8 -*-
"""Configuración del modo local (⚙): lo que casi nunca se toca, fuera de la pantalla principal."""
import os

from PyQt5.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox, QFormLayout, QHBoxLayout,
                             QLabel, QMessageBox, QPushButton, QVBoxLayout)

from core import channel_profile as cp
from core import stock_cache


class LocalSettingsDialog(QDialog):
    def __init__(self, view):
        """``view``: la ``LocalView`` (sus acciones cambian carpetas y canales)."""
        super().__init__(view)
        self.view = view
        self.setWindowTitle('Configuración — Crear videos')
        self.setMinimumWidth(620)
        self.setStyleSheet('QDialog { background-color: #2b2b2b; }')
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.root_label = QLabel()
        self.root_label.setWordWrap(True)
        form.addRow('Carpeta de canales:', self._row(self.root_label, ('Cambiar', view.pick_root),
                                                     ('Abrir', lambda: view.open_folder(view.local_root))))
        self.output_label = QLabel()
        self.output_label.setWordWrap(True)
        form.addRow('Carpeta de videos:', self._row(self.output_label, ('Cambiar', view.pick_output),
                                                    ('Abrir', lambda: view.open_folder(view.output_root))))
        self.inbox_label = QLabel()
        self.inbox_label.setWordWrap(True)
        form.addRow('Carpeta de entrada:', self._row(
            self.inbox_label, ('Abrir', lambda: view.local_root and view.open_folder(
                os.path.join(view.local_root, cp.INPUT_DIR)))))
        cache_row = QHBoxLayout()
        self.cache_gb = QDoubleSpinBox()
        self.cache_gb.setRange(0.5, 200)
        self.cache_gb.setSuffix(' GB')
        self.cache_gb.setValue(float(view.settings.get('cache_max_gb', stock_cache.DEFAULT_MAX_GB)))
        self.cache_gb.setToolTip('Espacio máximo para los videos stock ya preparados (aceleran los videos).')
        cache_row.addWidget(self.cache_gb)
        self.cache_label = QLabel()
        cache_row.addWidget(self.cache_label, 1)
        clear = QPushButton('Vaciar caché')
        clear.clicked.connect(self._clear_cache)
        cache_row.addWidget(clear)
        form.addRow('Caché de video stock:', cache_row)
        layout.addLayout(form)

        channels = QHBoxLayout()
        for text, action in (('Nuevo canal', view.new_channel),
                             ('Importar canales anteriores', view.import_legacy)):
            button = QPushButton(text)
            button.clicked.connect(lambda _c=False, a=action: (a(), self.refresh()))
            channels.addWidget(button)
        channels.addStretch()
        layout.addLayout(channels)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText('Cerrar')
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh()

    def _row(self, label, *actions):
        row = QHBoxLayout()
        row.addWidget(label, 1)
        for text, action in actions:
            button = QPushButton(text)
            button.clicked.connect(lambda _c=False, a=action: (a(), self.refresh()))
            row.addWidget(button)
        return row

    def refresh(self):
        view = self.view
        self.root_label.setText(view.local_root or 'Sin elegir')
        self.output_label.setText(view.output_root)
        self.inbox_label.setText(os.path.join(view.local_root, cp.INPUT_DIR, '<canal>') if view.local_root
                                 else '—')
        size = stock_cache.StockCache().size() / 1024 ** 3
        self.cache_label.setText(f'en uso: {size:.1f} GB')

    def _clear_cache(self):
        if QMessageBox.question(self, 'Vaciar caché', 'Se borran los videos stock ya preparados. '
                                'Se vuelven a preparar solos la próxima vez (tarda un poco más). ¿Seguir?',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) == QMessageBox.Yes:
            stock_cache.StockCache().clear()
            self.refresh()

    def done(self, result):
        self.view.settings['cache_max_gb'] = self.cache_gb.value()
        self.view.save_settings()
        super().done(result)
