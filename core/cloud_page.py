# -*- coding: utf-8 -*-
"""«Automatizar en la nube»: las pestañas Beats y Loop kits, con su guía."""
from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QWidget

from core.guide_panel import GuideStep


class CloudPage(QWidget):
    def __init__(self, tabs, beat_panel, loop_kit_panel, parent=None):
        super().__init__(parent)
        self.tabs, self.beat_panel, self.loop_kit_panel = tabs, beat_panel, loop_kit_panel
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)

    def _panel(self):
        return self.tabs.currentWidget()

    def _inner_tab(self, index):
        """Abre la subpestaña ``index`` (0 Conexiones, 1 Canal, 2 SEO, 3 Avanzado) del panel actual."""
        inner = self._panel().findChild(QTabWidget)
        if inner is not None and index < inner.count():
            inner.setCurrentIndex(index)

    def guide(self):
        return ('Automatizar en la nube',
                'Un robot en GitHub arma y publica los videos solo. Se configura una vez por canal; '
                'después no hace falta tener la PC prendida.',
                [GuideStep('Elegir qué automatizar',
                           '«Beats» publica type beats todos los días. «Loop kits» publica kits una vez por semana.',
                           action=lambda: self.tabs.setCurrentWidget(self.beat_panel), action_text='Ir a Beats'),
                 GuideStep('Conectar las cuentas',
                           'En la subpestaña «Conexiones»: Dropbox, GitHub (con «gh auth login» en una terminal) '
                           'y YouTube. Las luces verdes indican que está listo.',
                           action=lambda: self._inner_tab(0), action_text='Abrir Conexiones'),
                 GuideStep('Configurar el canal',
                           'En «Canal»: qué canal, qué fondos y a qué hora publicar.',
                           action=lambda: self._inner_tab(1), action_text='Abrir Canal'),
                 GuideStep('Revisar títulos y SEO (opcional)', 'En «SEO y tendencias».',
                           action=lambda: self._inner_tab(2), action_text='Abrir SEO'),
                 GuideStep('Publicar al robot',
                           'Cuando el checklist de abajo esté completo, apretá «Publicar al robot». '
                           'Desde ahí el robot trabaja solo.')])
