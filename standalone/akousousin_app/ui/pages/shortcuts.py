# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Shortcuts: global keys for reading and dictation, and the tray icon."""
import os
import shutil

from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ... import runtime
from .. import theme
from ..lang import keys
from ..widgets import Card, Keys, Rule, SettingRow, button, combo, fill, row, text
from .base import Page


class Shortcut(QWidget):
    """One global shortcut: what it does, its keys and whether it is on."""
    def __init__(self, icon, title, explanation, *controls):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(Rule())
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 14, 0, 14)
        layout.setSpacing(16)
        image = text()
        image.setPixmap(theme.pixmap(icon, 22, theme.current().accent_text))
        layout.addWidget(image, 0)
        words = QVBoxLayout()
        words.setSpacing(3)
        words.addWidget(text(title, 'h3'))
        words.addWidget(text(explanation, 'muted'))
        layout.addLayout(words, 1)
        self.keys = Keys()
        self.state = text('', 'ok', wrap=False)
        layout.addWidget(self.keys)
        layout.addWidget(self.state)
        for control in controls:
            layout.addWidget(control)
        outer.addLayout(layout)
        self.setAccessibleName(title)

    def set(self, found, on, on_text, off_text):
        self.keys.set(found if on else [])
        self.state.setText(on_text if on else off_text)
        self.state.setProperty('role', 'ok' if on else 'muted')
        self.state.style().unpolish(self.state)
        self.state.style().polish(self.state)


class ShortcutsPage(Page):
    key = 'shortcuts'
    icon = 'keys'

    def title(self):
        return self.tr('Shortcuts')

    def subtitle(self):
        return self.tr('Use Akousousin from anywhere with a few keys.')

    def build(self):
        if os.environ.get('FLATPAK_ID'):
            self.add(text(self.tr('Global desktop shortcuts require the native Linux package.'), 'muted'))
            return
        main = Card(self.tr('Global shortcuts'))
        main.add(text(self.tr('These work in every app. Your desktop asks you to approve each one the first time, '
                              'and you can change the keys in your desktop’s settings at any time.'), 'muted'))
        self.reading_on = button(self.tr('Turn on…'), self.enable_reading)
        self.reading_off = button(self.tr('Turn off'), lambda: self.state.command('selection-shortcuts-disable', key='reading'))
        self.change = button(self.tr('Change keys…'), self.change_keys)
        main.add(SettingRow(self.tr('Reading shortcuts'), '', self.reading_on, self.reading_off, self.change, first=True))
        self.selected = Shortcut('voices', self.tr('Read selected text'),
                                 self.tr('Highlight text anywhere and press the keys. Press them again to stop.'))
        self.copied = Shortcut('copy', self.tr('Read copied text'),
                               self.tr('For apps where selecting is not enough, such as some Windows apps: copy with Ctrl+C first.'))
        main.add(self.selected)
        main.add(self.copied)
        self.dictate_on = button(self.tr('Turn on…'), lambda: self.state.command('stt-desktop-enable', key='shortcut'))
        self.dictate_off = button(self.tr('Turn off'), lambda: self.state.command('stt-desktop-disable', key='shortcut'))
        self.dictate = Shortcut('mic', self.tr('Dictate'),
                                self.tr('Types what you say into the app you are using. Hold to talk, or press to start and stop — choose on the Dictation page.'),
                                self.dictate_on, self.dictate_off)
        main.add(self.dictate)
        self.detail = text('', 'small')
        main.add(self.detail)
        self.add(main)

        if 'gnome' in os.environ.get('XDG_CURRENT_DESKTOP', '').lower():
            gnome = Card()
            words = QVBoxLayout()
            words.addWidget(text(self.tr('GNOME: Akousousin Focus extension'), 'h2'))
            words.addWidget(text(self.tr('GNOME needs a small extension so dictation knows which window it is typing into.'), 'muted'))
            layout = row(stretch=False, spacing=20)
            layout.addLayout(words, 1)
            layout.addWidget(button(self.tr('Set up extension…'), self.gnome_extension))
            gnome.add(layout)
            self.add(gnome)

        if not os.environ.get('WAYLAND_DISPLAY') and os.name != 'nt':
            other = Card(self.tr('Other desktops'))
            other.add(text(self.tr('If your desktop does not offer to approve shortcuts, add a desktop action and bind it to keys yourself.'), 'muted'))
            other.add(row(button(self.tr('Add desktop action'), self.desktop_action)))
            self.add(other)

        tray = Card(self.tr('Tray icon'))
        self.tray = combo([('dictate', self.tr('Start or stop dictation')), ('open', self.tr('Open Akousousin'))],
                          self.state.config.get('tray_click', 'dictate'))
        self.tray.activated.connect(lambda _: self.state.save(tray_click=self.tray.currentData()))
        tray.add(SettingRow(self.tr('Click or tap the tray icon to'),
                            self.tr('Right-click, or press and hold on a touch screen, always shows the menu.'), self.tray, first=True))
        self.add(tray)

        if os.name == 'nt':
            main.setEnabled(False)
            self.layout_.insertWidget(2, text(self.tr('Global reading and dictation shortcuts are available on Linux.'), 'muted'))
        self.status_changed(self.state.status)

    def settings_changed(self, config):
        if os.environ.get('FLATPAK_ID'):
            return
        fill(self.tray, [('dictate', self.tr('Start or stop dictation')), ('open', self.tr('Open Akousousin'))],
             config.get('tray_click', 'dictate'))

    def status_changed(self, status):
        if os.environ.get('FLATPAK_ID'):
            return
        reading = status.reading
        on = bool(reading.get('shortcuts_enabled'))
        found = reading.get('keys') or {}
        self.selected.set(keys(found.get('read-selection', '')), on, self.tr('On'), self.tr('Off'))
        self.copied.set(keys(found.get('read-clipboard', '')), on, self.tr('On'), self.tr('Off'))
        self.reading_on.setVisible(not on)
        self.reading_off.setVisible(on)
        desktop = (status.dictation or {}).get('desktop') or {}
        enabled = bool(desktop.get('enabled'))
        self.dictate.set(keys(desktop.get('keys', '')), enabled, self.tr('On'), self.tr('Off'))
        self.dictate_on.setVisible(not enabled)
        self.dictate_off.setVisible(enabled)
        problems = [value for value in (reading.get('shortcut_state', '') if not on else '',
                                        desktop.get('state', '') if not enabled else '')
                    if value and 'disabled' not in value.lower()]
        self.detail.setText('\n'.join(problems))
        self.detail.setVisible(bool(problems))

    def enable_reading(self):
        if self.confirm(self.tr('Turn on reading shortcuts'),
                        self.tr('Setting up may make Akousousin the Speech Dispatcher voice and pause Orca for a moment. Continue?'),
                        self.tr('Turn on')):
            self.state.command('selection-shortcuts-enable', key='reading')

    def change_keys(self):
        desktop = os.environ.get('XDG_CURRENT_DESKTOP', '').lower()
        for program, arguments in ((('systemsettings', ['kcm_keys']) if 'kde' in desktop else ('', [])),
                                   (('gnome-control-center', ['keyboard']) if 'gnome' in desktop else ('', []))):
            if program and shutil.which(program):
                process = QProcess(self)
                environment = runtime.host_environment()
                from PySide6.QtCore import QProcessEnvironment
                system = QProcessEnvironment()
                for name, value in environment.items():
                    system.insert(name, value)
                process.setProcessEnvironment(system)
                process.setProgram(program)
                process.setArguments(arguments)
                if process.startDetached()[0]:
                    return
        self.notice(self.tr('Open your desktop’s keyboard shortcut settings to change these keys.'))

    def gnome_extension(self):
        from ...gnome_focus import install_extension
        self.run(install_extension, self.notice, key='gnome')

    def desktop_action(self):
        from ...selection import install_action
        self.run(lambda: install_action(self.state.path), lambda _: self.notice(self.tr('Desktop action added.')), key='action')
