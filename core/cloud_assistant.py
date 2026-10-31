# -*- coding: utf-8 -*-
"""Camino «Automatizar un canal en la nube» del asistente, con luces de estado reales.

Cada paso muestra qué está listo (el mismo checklist de la pestaña) y un botón que lleva al
lugar exacto de la pantalla de nube; allí aparece un aviso «Volver al asistente». La conexión
de esta PC (Dropbox y GitHub) se hace dentro del asistente con el mismo recuadro de Conexiones.
"""
from PyQt5.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QPushButton, QRadioButton, QVBoxLayout, QWidget

from core.cloud_login_box import CloudLoginBox
from core.cloud_page import BEATS, KITS, REQUIRED, TAB_CHANNEL, TAB_CONNECTIONS
from core.wizard import WizardPage

LABELS = {
    'pc_dropbox': 'Dropbox conectado en esta PC',
    'gh': 'GitHub conectado (gh auth login)',
    'slug': 'Canal elegido y con nombre para el robot',
    'env': 'Canal elegido y preparado en GitHub',
    'youtube': 'YouTube del canal conectado',
    'dropbox': 'Dropbox del robot (worker) cargado',
    'telegram': 'Telegram para avisos (token y chat)',
}


def lights(state, ids):
    rows = []
    for key in ids:
        ok = state.get(key)
        color, mark = ('#2ecc71', '●') if ok else ('#c0392b', '●')
        rows.append(f'<span style="color:{color}; font-size:16px">{mark}</span> {LABELS.get(key, key)}'
                    f'{"" if ok else "  — <i>falta</i>"}')
    return '<br>'.join(rows)


def _page(*widgets):
    box = QWidget()
    layout = QVBoxLayout(box)
    for widget in widgets:
        if isinstance(widget, QHBoxLayout):
            layout.addLayout(widget)
        else:
            layout.addWidget(widget)
    layout.addStretch(1)
    return box


def _buttons(*pairs):
    row = QHBoxLayout()
    for text, slot in pairs:
        button = QPushButton(text)
        button.clicked.connect(slot)
        row.addWidget(button)
    row.addStretch()
    return row


def cloud_pages(assistant, cloud):
    """Pasos del camino de nube. ``cloud``: la ``CloudPage`` (estado real y navegación)."""

    def go(tab, text):
        cloud.open_tab(tab)
        cloud.show_banner(text)
        assistant.cloud_requested.emit()

    # Paso 1: qué automatizar
    beats = QRadioButton('🎵  Beats — publica type beats todos los días')
    kits = QRadioButton('📦  Loop kits — publica kits una vez por semana')
    group = QButtonGroup(assistant)
    group.addButton(beats)
    group.addButton(kits)
    (kits if cloud.kind() == KITS else beats).setChecked(True)
    page1 = _page(beats, kits)

    def choose():
        cloud.set_kind(KITS if kits.isChecked() else BEATS)

    # Paso 2: esta PC (el mismo recuadro de Conexiones, acá adentro)
    login = CloudLoginBox()
    pc_state = QLabel()
    pc_help = QLabel('<b>Dropbox:</b> pegá el app key → «Autorizar Dropbox» (se abre el navegador) → pegá el código '
                     '→ «Guardar en esta PC».<br><b>GitHub:</b> instalá GitHub CLI (cli.github.com), abrí una terminal, '
                     'corré <code>gh auth login</code> y después tocá «Revisar».')
    pc_help.setWordWrap(True)
    page2 = _page(login, pc_help, pc_state)
    pc_ids = ('pc_dropbox', 'gh')

    def refresh_pc():
        pc_state.setText(lights(cloud.readiness(), pc_ids))

    # Paso 3: canal
    channel_state = QLabel()
    channel_help = QLabel()
    channel_help.setWordWrap(True)
    page3 = _page(channel_help, channel_state, _buttons(
        ('Abrir «Canal» para elegirlo', lambda: go(TAB_CHANNEL, 'Elegí o creá el canal y guardá. Después volvé.')),
        ('Asistente de alta de Loop kits', lambda: cloud.loop_kit_panel.btn_wizard.click())))

    def channel_id():
        return 'env' if cloud.kind() == KITS else 'slug'

    def enter_channel():
        if cloud.kind() == KITS:
            channel_help.setText('Elegí arriba de la pestaña Loop kits el canal (o creá uno con «Asistente de alta»). '
                                 'El robot lo reconoce por su nombre.')
        else:
            channel_help.setText('En «Canal» elegí (o agregá) la automatización del canal: canal de YouTube, fondos y '
                                 'horario. Guardá con «Publicar al robot» al final; acá alcanza con que esté elegida.')

    def refresh_channel():
        channel_state.setText(lights(cloud.readiness(), (channel_id(),)))

    # Paso 4: credenciales del robot
    creds_state = QLabel()
    creds_help = QLabel('El robot necesita sus propias credenciales en GitHub (nunca quedan en esta PC):<br>'
                        '• <b>YouTube</b>: «Conectar YouTube» abre el navegador; elegí la cuenta del canal.<br>'
                        '• <b>Dropbox del robot</b>: en el paso anterior, «Subir al robot (GitHub)» con un código nuevo.'
                        '<br>• <b>Telegram</b> (solo Loop kits): en Conexiones.')
    creds_help.setWordWrap(True)

    def connect_youtube():
        cloud.panel().connect_youtube_button.click()

    page4 = _page(creds_help, creds_state, _buttons(
        ('Conectar YouTube', connect_youtube),
        ('Abrir Conexiones', lambda: go(TAB_CONNECTIONS, 'Completá lo que falta en Conexiones y volvé.'))))

    def cred_ids():
        return [i for i in ('youtube', 'dropbox', 'telegram') if i in REQUIRED[cloud.kind()]]

    def refresh_creds():
        creds_state.setText(lights(cloud.readiness(), cred_ids()))

    # Paso 5: publicar
    final = QLabel('Todo listo para que el robot trabaje solo. Falta el último clic: en la pestaña, revisá el horario '
                   'y apretá <b>«Publicar al robot»</b> (abajo). Desde ahí publica aunque la PC esté apagada.')
    final.setWordWrap(True)
    page5 = _page(final, _buttons(('Ir a «Publicar al robot»',
                                   lambda: go(TAB_CHANNEL, 'Revisá el horario y apretá «Publicar al robot» (abajo).'))))

    def missing_text(ids):
        state = cloud.readiness()
        return ', '.join(LABELS.get(i, i) for i in ids if not state.get(i))

    return [
        WizardPage('¿Qué querés automatizar?', 'Se puede automatizar uno y después el otro.', page1, on_next=choose),
        WizardPage('Conectá esta PC', 'Se hace una sola vez por computadora.', page2, refresh=refresh_pc,
                   ready=lambda: all(cloud.readiness().get(i) for i in pc_ids),
                   blocker=lambda: f'falta: {missing_text(pc_ids)}.'),
        WizardPage('Elegí el canal', '', page3, on_enter=enter_channel, refresh=refresh_channel,
                   ready=lambda: bool(cloud.readiness().get(channel_id())),
                   blocker=lambda: 'elegí el canal (botón de abajo) y volvé.'),
        WizardPage('Credenciales del robot', 'Una vez por canal.', page4, refresh=refresh_creds,
                   ready=lambda: all(cloud.readiness().get(i) for i in cred_ids()),
                   blocker=lambda: f'falta: {missing_text(cred_ids())}.'),
        WizardPage('¡Último paso!', '', page5, next_text='Terminar', can_back=True),
    ], login
