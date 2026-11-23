# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""The tray icon and its menu, owned by the controller process.

States: ready (still logo lines), listening (green microphone whose glow
breathes) and reading (the logo lines rising and falling). Movement follows
the desktop's animation setting and stops when animations are turned off.
"""
import math
import os
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, QSettings, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .. import settings

GREEN = QColor('#1E7046')
GLOW = QColor('#3FA36E')
CAUTION = QColor('#E3AA26')
BARS = ((4, 10, 14), (8, 7, 17), (12, 4, 20), (16, 7, 17), (20, 10, 14))  # x, top, bottom on a 24 grid


def animation_factor():
    """KDE's animation speed (0 turns animations off); 1 elsewhere."""
    if os.environ.get('AKOUSOUSIN_NO_ANIMATION'):
        return 0.0
    config = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'kdeglobals'
    if config.is_file():
        try:
            return float(QSettings(str(config), QSettings.IniFormat).value('KDE/AnimationDurationFactor', 1.0))
        except (TypeError, ValueError):
            return 1.0
    return 1.0


def _ini(path):
    import configparser
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read(path, encoding='utf-8')
    except (OSError, configparser.Error, UnicodeError):
        pass
    return parser


def panel_tint():
    """Colour for the monochrome logo lines on the desktop's panel, or None for the app palette.

    The bundled Qt does not know the desktop's colour scheme, so its palette
    is always light and the lines came out dark on a dark panel. Follow what
    the panel follows instead: Plasma's style (Breeze Dark is a dark panel
    even with light apps), else the colour scheme's window text; GNOME's top
    bar is always dark.
    """
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    style = _ini(config / 'plasmarc').get('Theme', 'name', fallback='default').casefold()
    if 'dark' in style:
        return QColor('#fcfcfc')
    if 'light' in style:
        return QColor('#232629')
    foreground = _ini(config / 'kdeglobals').get('Colors:Window', 'ForegroundNormal', fallback='')
    try:
        red, green, blue = (int(part) for part in foreground.split(',')[:3])
        return QColor(red, green, blue)
    except ValueError:
        pass
    if 'GNOME' in os.environ.get('XDG_CURRENT_DESKTOP', '').upper():
        return QColor('#ffffff')
    return None


def draw(state, phase=0.0, tint=None, badge=None, progress=None, size=64):
    """Paint one frame. ``phase`` runs 0–1 through one animation cycle."""
    image = QPixmap(size, size)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    scale = size / 24
    tint = QColor(tint or QApplication.palette().windowText().color())
    if state == 'listening':
        glow = QColor(GLOW)
        glow.setAlphaF(.25 + .45 * (.5 - .5 * math.cos(2 * math.pi * phase)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(glow)
        grow = 1 + .12 * (.5 - .5 * math.cos(2 * math.pi * phase))
        radius = 11.5 * scale * min(1.0, .9 * grow)
        painter.drawEllipse(QPointF(size / 2, size / 2), radius, radius)
        painter.setBrush(GREEN)
        painter.drawEllipse(QPointF(size / 2, size / 2), 9 * scale, 9 * scale)
        pen = QPen(QColor('white'), 1.7 * scale, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(QRectF(10.2 * scale, 6.5 * scale, 3.6 * scale, 7.2 * scale), 1.8 * scale, 1.8 * scale)
        arc = QPainterPath()
        arc.moveTo(8 * scale, 11.5 * scale)
        arc.cubicTo(8 * scale, 16.5 * scale, 16 * scale, 16.5 * scale, 16 * scale, 11.5 * scale)
        painter.drawPath(arc)
        painter.drawLine(QPointF(12 * scale, 15.4 * scale), QPointF(12 * scale, 17.6 * scale))
    else:
        pen = QPen(tint, 2.1 * scale, Qt.SolidLine, Qt.RoundCap)
        painter.setPen(pen)
        for index, (x, top, bottom) in enumerate(BARS):
            middle, half = (top + bottom) / 2, (bottom - top) / 2
            if state == 'reading':
                wave = .5 - .5 * math.cos(2 * math.pi * (phase - index * .125))
                half *= 1 - .55 * wave
            painter.drawLine(QPointF(x * scale, (middle - half) * scale), QPointF(x * scale, (middle + half) * scale))
    if progress is not None:
        painter.setPen(QPen(GREEN, 2.4 * scale, Qt.SolidLine, Qt.RoundCap))
        span = -int(max(.03, min(1.0, progress)) * 360 * 16)
        painter.drawArc(QRectF(1.3 * scale, 1.3 * scale, 21.4 * scale, 21.4 * scale), 90 * 16, span)
    if badge:
        painter.setPen(QPen(QColor('white'), 1.2 * scale))
        painter.setBrush(QColor(badge))
        painter.drawEllipse(QPointF(19.5 * scale, 19.5 * scale), 3.8 * scale, 3.8 * scale)
    painter.end()
    return QIcon(image)


class Tray(QObject):
    """The icon, menu and click behaviour. ``submit`` sends controller requests."""
    FPS = 12

    def __init__(self, path, submit, in_use, parent=None):
        super().__init__(parent)
        self.path, self.submit, self.in_use = path, submit, in_use
        self.mode = 'ready'
        self.extras = {}
        self.phase = 0.0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._frame)
        self.menu = QMenu()
        self.header = self.menu.addAction('')
        self.header.setEnabled(False)
        self.menu.addSeparator()
        self.dictate = self.menu.addAction(self.tr('Start dictation'), lambda: self.submit({'command': 'stt-toggle'}))
        self.stop_reading = self.menu.addAction(self.tr('Stop reading'), lambda: self.submit({'command': 'selection-stop'}))
        self.read_selected = self.menu.addAction(self.tr('Read selected text'),
                                                 lambda: self.submit({'command': 'selection-toggle'}))
        self.read_copied = self.menu.addAction(self.tr('Read copied text'),
                                               lambda: self.submit({'command': 'selection-toggle', 'clipboard': True}))
        self.menu.addSeparator()
        self.voices = self.menu.addMenu(self.tr('Default voice'))
        self.voices.aboutToShow.connect(self._voices)
        self.menu.addSeparator()
        self.downloads = self.menu.addAction('')
        self.downloads.setEnabled(False)
        self.update_action = self.menu.addAction('', lambda: self.submit({'command': 'configure', 'page': 'Updates'}))
        self.menu.addAction(self.tr('Open Akousousin'), lambda: self.submit({'command': 'configure'}))
        self.menu.addAction(self.tr('Quit'), self.quit)
        if os.name == 'nt':
            for action in (self.stop_reading, self.read_selected, self.read_copied):
                action.setVisible(False)
        self.icon = None
        self.create()

    def create(self):
        """(Re)create the system tray icon, e.g. when the desktop's tray appears late."""
        if self.icon is not None:
            self.icon.hide()
            self.icon.deleteLater()
        self.icon = QSystemTrayIcon()
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self._paint()
        self.icon.show()

    def quit(self):
        from PySide6.QtWidgets import QMessageBox
        if self.in_use() and QMessageBox.question(None, self.tr('Quit Akousousin?'),
                                                  self.tr('Speech is in use. Quit and stop speaking?')) != QMessageBox.Yes:
            return
        self.submit({'command': 'quit'})

    def _activated(self, reason):
        if reason != QSystemTrayIcon.Trigger:
            return
        try:
            action = settings.load(self.path).get('tray_click', 'dictate')
        except (OSError, ValueError):
            action = 'dictate'
        self.submit({'command': 'configure'} if action == 'open' else {'command': 'stt-toggle'})

    def _voices(self):
        from .lang import language_name
        self.voices.clear()
        config = settings.load(self.path)
        groups = {}
        for key, voice in sorted(config['voices'].items(), key=lambda item: (language_name(item[1]['language']), item[1]['name'])):
            group = groups.get(voice['language'])
            if group is None:
                group = groups[voice['language']] = self.voices.addMenu(language_name(voice['language']))
            action = group.addAction(voice['name'])
            action.setCheckable(True)
            action.setChecked(key == config['voice'])
            action.triggered.connect(lambda checked=False, k=key: self.submit({'command': 'voice', 'voice': k}))
        if not groups:
            self.voices.addAction(self.tr('No voices installed yet')).setEnabled(False)

    def update(self, *, running, dictation, reading, pending, downloads, available, problem, speaking=False):
        """Refresh text, visibility and icon state from the controller's status.

        ``speaking`` is any speech from the voice service, including Windows
        apps through SAPI; ``reading`` is Akousousin's own read-aloud shortcut.
        """
        busy = bool(dictation.get('busy')) or pending
        listening = busy and dictation.get('phase') in ('listening', 'transcribing', 'opening', 'loading')
        aloud = bool(reading.get('reading')) or speaking
        mode = 'listening' if listening else 'reading' if aloud else 'ready'
        if listening:
            header = self.tr('Dictation listening…')
        elif aloud:
            header = self.tr('Reading aloud…')
        elif problem:
            header = self.tr('Akousousin · needs attention')
        else:
            header = self.tr('Akousousin · Ready')
        self.header.setText(header)
        self.dictate.setText(self.tr('Finish dictation') if busy else self.tr('Start dictation'))
        self.stop_reading.setVisible(bool(reading.get('reading')) and os.name != 'nt')
        self.read_selected.setVisible(not reading.get('reading') and os.name != 'nt')
        self.read_copied.setVisible(not reading.get('reading') and os.name != 'nt')
        from ..download_status import caption
        active = [item for item in downloads if item['status'] == 'active']
        self.downloads.setVisible(bool(downloads))
        self.downloads.setText('\n'.join(caption(item) for item in downloads))
        self.update_action.setVisible(bool(available))
        if available:
            self.update_action.setText(self.tr('Update available: %1…').replace('%1', available['version']))
        progress = None
        if active and active[0]['total']:
            progress = active[0]['completed'] / active[0]['total']
        elif active:
            progress = .1
        extras = {'badge': CAUTION if problem or any(item['status'] == 'error' for item in downloads) else None,
                  'progress': progress, 'tint': panel_tint() if os.name != 'nt' else None}
        tooltip = {'listening': self.tr('Akousousin — dictation listening'),
                   'reading': self.tr('Akousousin — reading aloud')}.get(mode, self.tr('Akousousin — ready'))
        if self.icon.toolTip() != tooltip:
            self.icon.setToolTip(tooltip)
        if mode != self.mode or extras != self.extras:
            self.mode, self.extras = mode, extras
            self._paint()
            animate = mode != 'ready' and animation_factor() > 0
            if animate and not self.timer.isActive():
                self.timer.start(int(1000 / self.FPS))
            elif not animate:
                self.timer.stop()
                self.phase = 0.0

    def _frame(self):
        period = (1.6 if self.mode == 'listening' else 2.4) * max(.25, animation_factor())
        self.phase = (self.phase + 1 / (self.FPS * period)) % 1.0
        self._paint()

    def _paint(self):
        self.icon.setIcon(draw(self.mode, self.phase, **self.extras))
