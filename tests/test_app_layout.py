"""The guide must scroll instead of squeezing cards or clipping primary actions."""
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt5.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea
from core.app_shell import AppShell
from core.home_screen import HomeScreen
from core.guide_panel import GuidePanel, GuideStep
from core.connections_view import ConnectionsView
from ui_theme import APPLICATION_STYLESHEET

APP = QApplication.instance() or QApplication([])


class LayoutTests(unittest.TestCase):
    def show_widget(self, widget, width, height):
        widget.setStyleSheet(APPLICATION_STYLESHEET)
        widget.resize(width, height)
        widget.show()
        for _ in range(3):
            APP.processEvents()
        self.addCleanup(widget.deleteLater)
        self.addCleanup(widget.close)

    def test_home_actions_fit_with_guide_at_minimum_window_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = HomeScreen()
            shell = AppShell(home, {}, settings_path=os.path.join(tmp, 'settings.json'))
            self.show_widget(shell, 900, 620)
            buttons = (home.btn_local, home.btn_cloud, home.btn_connections)
            for button in buttons:
                self.assertTrue(home.rect().contains(button.geometry()))
                self.assertGreaterEqual(button.height(), button.sizeHint().height())
            for first, second in zip(buttons, buttons[1:]):
                self.assertLess(first.geometry().bottom(), second.geometry().top())

    def test_guide_scrolls_instead_of_squeezing_step_buttons(self):
        guide = GuidePanel()
        guide.set_guide('Guide', 'Instructions', [GuideStep('A title that can wrap over two lines',
            'A detailed explanation with enough words to occupy several lines in this narrow guide.',
            action=lambda: None) for _ in range(10)])
        self.show_widget(guide, 310, 450)
        scroll = guide.findChild(QScrollArea)
        self.assertGreater(scroll.verticalScrollBar().maximum(), 0)
        for button in guide.body.findChildren(QPushButton):
            self.assertGreaterEqual(button.height(), button.minimumSizeHint().height())
        for label in guide.body.findChildren(QLabel):
            if label.hasHeightForWidth():
                self.assertGreaterEqual(label.height(), label.heightForWidth(label.width()))

    def test_connections_fit_the_page_beside_guide(self):
        with patch.object(ConnectionsView, 'check_cloud'), patch.object(ConnectionsView, 'refresh'), \
                patch('core.connections_view.ConnectionCard.refresh'):
            view = ConnectionsView()
            self.show_widget(view, 570, 570)
            self.assertEqual(view.cards_page.horizontalScrollBar().maximum(), 0)
            for card in view.cards:
                title = card.findChildren(QLabel)[0]
                self.assertTrue(title.wordWrap())


if __name__ == '__main__':
    unittest.main()
