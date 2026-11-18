# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
import os
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QLineEdit

from . import resources, settings
from .install import Installer
from .qt_widgets import actions, field, group, label, tr


class Integrations:
    def __init__(self, panel, layout):
        self.panel = panel
        self.windows = os.name == 'nt'
        form = group(layout, "Windows speech (SAPI)" if self.windows else "Windows apps through Wine (SAPI)")
        if not self.windows:
            self.prefix = field(form, "Wine prefix", QLineEdit(panel.config['wine_prefix']))
            self.wine = field(form, "Wine executable or AppImage", QLineEdit(panel.config['wine']))
            actions(form, ("Choose prefix…", self.choose_prefix), ("Choose Wine executable…", self.choose_wine))
            self.prefix.textChanged.connect(self.refresh)
            form.addRow(label(tr("Installation registers the speech engine and voices in the selected prefix. When Wine needs the compatibility DLL, Akousousin installs a private sapi.dll, redirects the SAPI registration to it and sets the sapi override to native,builtin.")))
        self.registration = label()
        form.addRow(self.registration)
        actions(form, ("Install or update registration" if self.windows else "Install in this prefix", lambda: self.register(False)),
                ("Remove registration" if self.windows else "Remove from this prefix", lambda: self.register(True)))
        if not self.windows:
            form = group(layout, "Linux apps (Speech Dispatcher)")
            self.dispatcher = label()
            form.addRow(self.dispatcher)
            actions(form, ("Install Speech Dispatcher support", lambda: self.speechd(False)),
                    ("Remove Speech Dispatcher support", lambda: self.speechd(True)))
        self.refresh()

    def choose_prefix(self):
        folder = QFileDialog.getExistingDirectory(self.panel, tr("Choose an initialised Wine prefix"), self.prefix.text())
        if folder:
            self.prefix.setText(folder)

    def choose_wine(self):
        file, _ = QFileDialog.getOpenFileName(self.panel, tr("Choose Wine executable"), self.wine.text())
        if file:
            self.wine.setText(file)

    def refresh(self, *_):
        if self.windows:
            directory = Path(os.environ['PROGRAMFILES']) / 'Akousousin'
        else:
            from .speech_dispatcher import dispatcher_paths
            _, launcher, _ = dispatcher_paths()
            self.dispatcher.setText(tr("Installed") if launcher.exists() else tr("Not installed"))
            if not self.prefix.text():
                self.registration.setText(tr("Choose a prefix to inspect its registration."))
                return
            directory = Path(self.prefix.text()).expanduser() / 'drive_c/Program Files/Akousousin'
        self.registration.setText(tr("Registration found") if (directory / 'install-state.json').is_file()
                                 else tr("No registration found"))

    def register(self, remove):
        prefix = None
        if not self.windows and self.prefix.text():
            prefix = str(Path(self.prefix.text()).expanduser().resolve())
        wine = None if self.windows else self.wine.text() or None
        try:
            installer = Installer(resources.root(), prefix, wine)
        except (OSError, ValueError) as error:
            self.panel.error(error)
            return
        target = prefix or tr("Windows")
        prompt = tr("Restore the previous speech registration in {target}?") if remove else tr("Close applications using speech, then apply the SAPI registration to {target}?")
        if not self.panel.confirm(tr("Speech registration"), prompt.format(target=target), tr("Continue")):
            return
        def apply():
            if remove:
                installer.uninstall()
                config = settings.load(self.panel.path)
                config['registrations'] = [r for r in config.get('registrations', []) if r['prefix'] != (prefix or '')]
                settings.save(self.panel.path, config)
            else:
                installer.install(settings.load(self.panel.path), self.panel.path)
                settings.register(self.panel.path, prefix, wine)
        self.panel.save(wine_prefix=prefix or '', wine=wine or '')
        def complete(_):
            self.refresh()
            message = tr("Restored registration in {target}.") if remove else tr("Registered voices in {target}. Restart applications that cache their voices.")
            if not remove and installer.state.get('compatibility'):
                message += ' ' + tr("Private sapi.dll and native,builtin override applied.")
            self.panel.notice(message.format(target=target))
        self.panel.run(apply, complete)

    def speechd(self, remove):
        from .speech_dispatcher import configure
        if self.panel.confirm(tr("Speech Dispatcher"), tr("This restarts your user Speech Dispatcher and can interrupt Orca. Continue?"), tr("Continue")):
            self.panel.run(lambda: configure(self.panel.path, remove=remove), lambda _: self.panel.reload())
