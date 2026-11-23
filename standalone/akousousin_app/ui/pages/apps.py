# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Apps: where Akousousin's voices are available — Wine prefixes and Speech Dispatcher."""
import os
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLineEdit, QListWidget,
                               QListWidgetItem, QVBoxLayout,
                               QWidget)

from ... import resources, settings
from ..widgets import Card, Rule, SettingRow, StatusLine, button, labelled, row, text
from .base import Page


def prefix_folder(prefix):
    return Path(prefix).expanduser() / 'drive_c/Program Files/Akousousin'


def browse(parent, title, start, folders=False):
    """A file or folder picker that shows hidden folders, where Wine prefixes usually are."""
    from PySide6.QtCore import QDir
    picker = QFileDialog(parent, title, start)
    picker.setOption(QFileDialog.DontUseNativeDialog)  # a native picker would ignore the hidden-files filter
    picker.setFileMode(QFileDialog.Directory if folders else QFileDialog.ExistingFile)
    if folders:
        picker.setOption(QFileDialog.ShowDirsOnly)
    picker.setFilter(picker.filter() | QDir.Hidden)
    if picker.exec() == QFileDialog.Accepted and picker.selectedFiles():
        return picker.selectedFiles()[0]
    return ''


class PrefixRow(QWidget):
    def __init__(self, page, entry):
        super().__init__()
        self.page, self.entry = page, entry
        prefix = entry.get('prefix') or ''
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(Rule())
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 14, 0, 14)
        layout.setSpacing(16)
        words = QVBoxLayout()
        words.setSpacing(3)
        name = page.prefix_name(prefix)
        words.addWidget(text(name, 'h3'))
        if prefix:
            path = text(prefix, 'small', select=True)
            path.setStyleSheet('font-family: monospace')
            words.addWidget(path)
            words.addWidget(text(entry.get('wine') or self.tr('System Wine'), 'small'))
        layout.addLayout(words, 1)
        registered = page.registered(prefix)
        status = StatusLine()
        status.set(self.tr('Voices registered') if registered else self.tr('Not registered'), 'ok' if registered else 'caution')
        layout.addWidget(status)
        if registered:
            layout.addWidget(button(self.tr('Update'), lambda: page.register(prefix, entry.get('wine'), False)))
            layout.addWidget(button(self.tr('Remove…'), lambda: page.register(prefix, entry.get('wine'), True)))
        else:
            layout.addWidget(button(self.tr('Register voices'), lambda: page.register(prefix, entry.get('wine'), False), kind='primary'))
        outer.addLayout(layout)
        self.setAccessibleName(name)


class AppsPage(Page):
    key = 'apps'
    icon = 'apps'

    def title(self):
        return self.tr('Apps')

    def subtitle(self):
        return self.tr('Where Akousousin’s voices are available.')

    def build(self):
        windows = self.state.windows
        wine = Card()
        words = QVBoxLayout()
        words.setSpacing(4)
        words.addWidget(text(self.tr('Windows speech (SAPI)') if windows else self.tr('Windows apps through Wine'), 'h2'))
        words.addWidget(text(self.tr('Apps such as Logos use Akousousin voices through SAPI, the Windows speech system.')
                             + ('' if windows else ' ' + self.tr('Wine’s own files are left unchanged.')), 'muted'))
        top = row(stretch=False, spacing=20)
        top.addLayout(words, 1)
        if not windows:
            top.addWidget(button(self.tr('Add a Wine prefix…'), self.add_prefix, kind='primary'))
        wine.add(top)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(0)
        wine.add(self.rows)
        wine.add(text(self.tr('Restart a Windows app after registering so it sees new voices.'), 'small'))
        self.add(wine)

        if not windows:
            speechd = Card(self.tr('Linux apps and screen readers'))
            self.dispatcher_status = StatusLine()
            self.dispatcher_on = button(self.tr('Turn on…'), lambda: self.speechd(False))
            self.dispatcher_off = button(self.tr('Turn off…'), lambda: self.speechd(True))
            speechd.add(SettingRow(self.tr('Speech Dispatcher'),
                                   self.tr('Lets Orca, Firefox and other Linux apps speak with Akousousin voices. '
                                           'Changing this restarts Speech Dispatcher, so Orca pauses for a moment.'),
                                   self.dispatcher_status, self.dispatcher_on, self.dispatcher_off, first=True))
            self.add(speechd)
        self.settings_changed(self.state.config)

    # Display ------------------------------------------------------------------
    def prefix_name(self, prefix):
        if not prefix:
            return self.tr('This Windows computer')
        lowered = prefix.lower()
        if 'faithlife' in lowered or 'logos' in lowered:
            return self.tr('Logos Bible Software')
        return Path(prefix).name or prefix

    def registered(self, prefix):
        if self.state.windows:
            return (Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Akousousin/install-state.json').is_file()
        return (prefix_folder(prefix) / 'install-state.json').is_file() if prefix else False

    def settings_changed(self, config):
        while self.rows.count():
            item = self.rows.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        entries = list(config.get('registrations', []))
        legacy = config.get('wine_prefix') or ''
        if legacy and not any(entry.get('prefix') == legacy for entry in entries):
            entries.append({'prefix': legacy, 'wine': config.get('wine', '')})
        if self.state.windows and not entries:
            entries = [{'prefix': '', 'wine': ''}]
        for entry in entries:
            self.rows.addWidget(PrefixRow(self, entry))
        if not entries:
            self.rows.addWidget(text(self.tr('No Wine prefixes yet. Add the prefix your Windows app is installed in.'), 'muted'))
        if not self.state.windows:
            from ...speech_dispatcher import dispatcher_paths
            on = dispatcher_paths()[1].exists()
            self.dispatcher_status.set(self.tr('On') if on else self.tr('Off'), 'ok' if on else 'off')
            self.dispatcher_on.setVisible(not on)
            self.dispatcher_off.setVisible(on)
            warning = config.get('speechd_setup_warning')
            if warning:
                self.notice(warning)

    # Actions ------------------------------------------------------------------
    def add_prefix(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr('Add a Wine prefix'))
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(14)
        layout.addWidget(text(self.tr('Add a Wine prefix'), 'h2'))
        prefix = QLineEdit()
        prefix.setPlaceholderText('~/.wine')
        wine = QLineEdit()
        wine.setPlaceholderText(self.tr('Leave empty to use the system Wine'))

        # Most prefixes can be found, so offer them before any browsing.
        from ... import wine_prefixes
        registered = {str(Path(entry.get('prefix', '')).expanduser()) for entry in self.state.config.get('registrations', [])}
        found = [path for path in wine_prefixes.find() if str(path) not in registered]
        if found:
            choices = QListWidget()
            choices.setObjectName('choices')
            choices.setAccessibleName(self.tr('Wine prefixes found on this computer'))
            for path in found:
                item = QListWidgetItem(self.prefix_name(str(path)) + ' — ' + wine_prefixes.display(path))
                item.setData(Qt.UserRole, str(path))
                choices.addItem(item)
            choices.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            choices.setTextElideMode(Qt.ElideMiddle)
            choices.ensurePolished()
            rows = min(5, len(found))
            choices.setFixedHeight(rows * max(32, choices.sizeHintForRow(0)) + 2 * choices.frameWidth() + 12)
            choices.currentItemChanged.connect(lambda item, _old: item and prefix.setText(item.data(Qt.UserRole)))
            layout.addLayout(labelled(self.tr('Found on this computer'), choices,
                                      self.tr('Choose one, or pick another folder below.')))
            choices.setCurrentRow(0)

        def choose_prefix():
            folder = browse(dialog, self.tr('Choose a Wine prefix'), prefix.text() or str(Path.home()), folders=True)
            if folder:
                prefix.setText(folder)

        def choose_wine():
            file = browse(dialog, self.tr('Choose the Wine program'), wine.text() or str(Path.home()))
            if file:
                wine.setText(file)

        box = labelled(self.tr('Prefix folder'), prefix, self.tr('The folder that contains drive_c.'))
        box.addLayout(row(button(self.tr('Choose…'), choose_prefix)))
        layout.addLayout(box)
        box = labelled(self.tr('Wine program'), wine, self.tr('For example the Wine AppImage your app uses.'))
        box.addLayout(row(button(self.tr('Choose…'), choose_wine)))
        layout.addLayout(box)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(self.tr('Register voices'))
        buttons.button(QDialogButtonBox.Ok).setProperty('kind', 'primary')
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setMinimumWidth(520)
        if dialog.exec() == QDialog.Accepted and prefix.text().strip():
            self.register(prefix.text().strip(), wine.text().strip() or None, False, confirmed=True)

    def register(self, prefix, wine, remove, confirmed=False):
        from ...install import Installer
        prefix = str(Path(prefix).expanduser().resolve()) if prefix else None
        try:
            installer = Installer(resources.root(), prefix, wine or None)
        except (OSError, ValueError) as problem:
            self.error(problem)
            return
        target = self.prefix_name(prefix or '')
        if remove:
            if not self.confirm(self.tr('Remove from %1').replace('%1', target),
                                self.tr('Restore the speech settings %1 had before Akousousin was added?').replace('%1', target),
                                self.tr('Remove')):
                return
        elif not confirmed and not self.confirm(self.tr('Register voices'),
                                                self.tr('Close apps that are speaking, then register Akousousin voices in %1?').replace('%1', target),
                                                self.tr('Register')):
            return
        path = self.state.path

        def apply():
            if remove:
                installer.uninstall()
                config = settings.load(path)
                config['registrations'] = [r for r in config.get('registrations', []) if r['prefix'] != (prefix or '')]
                settings.save(path, config)
            else:
                installer.install(settings.load(path), path)
                settings.register(path, prefix, wine)
            return installer.state.get('compatibility')

        def done(compatibility):
            self.state.reload()
            if remove:
                self.notice(self.tr('Removed from %1.').replace('%1', target))
            else:
                self.notice(self.tr('Voices registered in %1. Restart apps that were open.').replace('%1', target)
                            + (' ' + self.tr('A private speech component was added for this Wine version.') if compatibility else ''))

        self.run(apply, done, key='register', busy=self.tr('Working on %1…').replace('%1', target))

    def speechd(self, remove):
        from ...speech_dispatcher import configure
        if self.confirm(self.tr('Speech Dispatcher'),
                        self.tr('This restarts Speech Dispatcher, so Orca pauses for a moment. Continue?'),
                        self.tr('Turn off') if remove else self.tr('Turn on')):
            self.run(lambda: configure(self.state.path, remove=remove), lambda _: self.state.reload(), key='speechd')
