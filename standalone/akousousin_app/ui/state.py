# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Settings and live status, shared by every page.

AppState is the only object that reads the controller's status. It polls once
a second in the background and emits a signal only when something changed.
Pages listen to those signals and update themselves.
"""
from dataclasses import dataclass, field
import os

from PySide6.QtCore import QObject, QTimer, Signal

from .. import download_status, resources, runtime, settings
from ..service import Service


@dataclass
class Status:
    speech: dict = None        # Piper /health, or None when stopped
    panel: dict = None         # activation counter and reading state
    dictation: dict = None     # controller stt-status
    downloads: list = field(default_factory=list)
    error: str = ''

    @property
    def reading(self):
        return (self.panel or {}).get('reading') or {}

    @property
    def speech_ready(self):
        return bool(self.speech and self.speech.get('ready'))


class AppState(QObject):
    settings_changed = Signal(dict)
    status_changed = Signal(object)
    activated = Signal(str)          # the controller asked to show a page ('' for none)
    notice = Signal(str)             # one line for the status area and screen readers
    navigate = Signal(str)           # a page asked to show another page

    def __init__(self, path, tasks, parent=None, poll=True):
        super().__init__(parent)
        self.path = path
        self.tasks = tasks
        self.config = resources.bootstrap(path)
        self.service = Service(path)
        self.status = Status()
        self.last_activation = None
        self.polling = False
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll)
        if poll:
            self.timer.start(1000)
            QTimer.singleShot(0, self.poll)

    # Settings -------------------------------------------------------------
    def save(self, **changes):
        config = settings.load(self.path)
        config.update(changes)
        settings.save(self.path, config)
        self._set_config(config)

    def reload(self):
        self._set_config(settings.load(self.path), force=True)

    def _set_config(self, config, force=False):
        if force or config != self.config:
            self.config = config
            self.settings_changed.emit(config)

    @property
    def voices(self):
        return self.config['voices']

    def default_voice(self):
        return self.config['voices'].get(self.config['voice'])

    def call(self, command, launch=True, **extra):
        """Send one request to the controller (blocking; use from Tasks)."""
        return runtime.call(self.path, dict(command=command, **extra), launch=launch)

    def command(self, command, done=None, *, key=None, background=False, **extra):
        stops = command in ('stt-finish', 'stt-cancel', 'stt-unload', 'selection-stop')
        self.tasks.run(lambda: self.call(command, launch=not stops, **extra), done,
                       key=key or command, background=background or stops)

    # Polling --------------------------------------------------------------
    def poll(self):
        if self.polling or self.tasks.closing:
            return
        self.polling = True
        port = self.config['port']

        def read():
            return Status(self.service.health(port),
                          runtime.call(self.path, {'command': 'panel-status'}, launch=False),
                          runtime.call(self.path, {'command': 'stt-status'}, launch=False),
                          download_status.current())

        def apply(status):
            self.polling = False
            if not self.tasks.busy():
                try:
                    self._set_config(settings.load(self.path))
                except (OSError, ValueError):
                    pass
            changed = status != self.status
            self.status = status
            if changed:
                self.status_changed.emit(status)
            panel = status.panel or {}
            activation = panel.get('activation')
            if activation is not None and activation != self.last_activation:
                first = self.last_activation is None
                self.last_activation = activation
                if not first or panel.get('page'):
                    self.activated.emit(panel.get('page') or '')

        def failed(error):
            self.polling = False
            self.status = Status(error=str(error))
            self.status_changed.emit(self.status)

        self.tasks.run(read, apply, failed=failed, background=True)

    @property
    def windows(self):
        return os.name == 'nt'
