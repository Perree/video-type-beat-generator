# -*- coding: utf-8 -*-
"""Guía lateral tipo checklist: pasos que se tildan solos y botón «Llevarme ahí».

Cada pantalla le da sus pasos con ``set_guide``. Mientras la guía está visible se revisa sola
cada poco tiempo, así el usuario ve que avanzó sin tener que tocar nada.
"""
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget, QLayout, QSizePolicy)
import ui_theme as theme

DONE, TODO, INFO = 'done', 'todo', 'info'

_ICON = {DONE: ('✔', theme.color('success')), TODO: ('○', theme.color('text_muted')),
         INFO: ('•', theme.color('accent_hover'))}


class GuideStep:
    """Paso de la guía.

    ``done``: función que devuelve True/False (se tilda sola), o None para un paso informativo.
    ``action``: función que lleva al lugar del paso (botón «Llevarme ahí»), opcional.
    """

    def __init__(self, text, hint='', done=None, action=None, action_text='Llevarme ahí'):
        self.text, self.hint, self.done, self.action, self.action_text = text, hint, done, action, action_text

    def state(self):
        if self.done is None:
            return INFO
        try:
            return DONE if self.done() else TODO
        except Exception:  # noqa: BLE001 - la guía nunca debe romper la ventana
            return TODO


class GuideRow(QFrame):
    """QScrollArea needs an explicit minimum after wrapped labels get their width."""
    def resizeEvent(self, event):
        super().resizeEvent(event)
        layout = self.layout()
        if layout is None:
            return
        margins = layout.contentsMargins()
        width = max(1, self.contentsRect().width() - margins.left() - margins.right())
        for label in self.findChildren(QLabel):
            if label.hasHeightForWidth():
                label.setMinimumHeight(label.heightForWidth(width))


class GuidePanel(QFrame):
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('guide')
        self.setMinimumWidth(300)
        self.setMaximumWidth(360)
        self.steps = []
        layout = QVBoxLayout(self)
        top = QHBoxLayout()
        self.title = theme.subtitle(QLabel())
        self.title.setWordWrap(True)
        top.addWidget(self.title, 1)
        close = theme.flat(QPushButton('✕'))
        close.setToolTip('Cerrar la guía (se vuelve a abrir con «? Guía»)')
        close.setFixedWidth(36)
        close.clicked.connect(self._close)
        top.addWidget(close)
        layout.addLayout(top)
        self.intro = theme.muted(QLabel())
        layout.addWidget(self.intro)
        self.progress = QLabel()
        layout.addWidget(self.progress)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setSizeConstraint(QLayout.SetMinimumSize)
        self.body_layout.setAlignment(Qt.AlignTop)
        scroll.setWidget(self.body)
        layout.addWidget(scroll, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(800)
        self.timer.timeout.connect(self.refresh)

    def set_guide(self, title, intro, steps):
        self.title.setText(title)
        self.intro.setText(intro)
        self.steps = list(steps)
        self._signature = None
        self.refresh()

    def states(self):
        return [step.state() for step in self.steps]

    def refresh(self):
        states = self.states()
        if states == getattr(self, '_signature', None):
            return  # nada cambió: no se redibuja (evita parpadeo)
        self._signature = states
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            if item.widget():
                item.widget().hide()  # si no, la tarjeta vieja se ve encima de la nueva hasta borrarse
                item.widget().deleteLater()
        current = next((i for i, s in enumerate(states) if s == TODO), None)
        for index, (step, state) in enumerate(zip(self.steps, states)):
            self.body_layout.addWidget(self._row(index, step, state, index == current))
        checkable = [s for s in states if s != INFO]
        done = sum(s == DONE for s in checkable)
        if checkable:
            text = f'{done} de {len(checkable)} pasos listos'
            if done == len(checkable):
                text += ' — ¡todo listo!'
            self.progress.setText(text)
        self.progress.setVisible(bool(checkable))

    def _row(self, index, step, state, current):
        row = GuideRow()
        row.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        theme.set_role(row, 'step_current' if current else 'step')
        layout = QVBoxLayout(row)
        layout.setSizeConstraint(QLayout.SetMinimumSize)
        icon, color = _ICON[state]
        now = f'  <span style="color:{theme.color("accent_hover")}">← ahora</span>' if current else ''
        head = QLabel(f'<span style="color:{color}">{icon}</span> <b>{index + 1}. {step.text}</b>{now}')
        head.setWordWrap(True)
        head.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        layout.addWidget(head)
        if step.hint:
            hint = QLabel(step.hint)
            hint.setWordWrap(True)
            hint.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
            theme.muted(hint)
            layout.addWidget(hint)
        if step.action:
            button = QPushButton(step.action_text)
            button.clicked.connect(lambda _c=False, s=step: self._run(s))
            layout.addWidget(button, 0, Qt.AlignLeft)
        return row

    def _run(self, step):
        step.action()
        self._signature = None
        self.refresh()

    def showEvent(self, event):
        self.timer.start()
        self.refresh()
        super().showEvent(event)

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _close(self):
        self.hide()
        self.closed.emit()
