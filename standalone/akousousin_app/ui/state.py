# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Settings and live status, shared by every page.

AppState is the only object that reads the controller's status. It polls once
a second in the background and emits a signal only when something changed.
Pages listen to those signals and update themselves.
"""
from dataclasses import dataclass, field
import os
import threading

from PySide6.QtCore import QObject, QTimer, Signal

from .. import download_status, resources, runtime, settings
from ..service import Service


class ChangeWatcher(QObject):
    """Waits in the background for the controller to report a change."""
    changed = Signal()

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.stopping = threading.Event()

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self.stopping.set()

    def _run(self):
        generation = None
        while not self.stopping.is_set():
            try:
                reply = runtime.call(self.path, {'command': 'wait', 'after': generation, 'timeout': 25},
                                     launch=False, timeout=35)
            except (OSError, RuntimeError, ValueError):
                reply = None
            if self.stopping.is_set():
                return
            if not isinstance(reply, dict) or not isinstance(reply.get('generation'), int):
                # No controller to wait on: show that, and look again in a moment.
                self.changed.emit()
                self.stopping.wait(2)
                continue
            if reply['generation'] != generation:
                generation = reply['generation']
                self.changed.emit()


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
        self.repoll = False
        # The panel reads its status when the controller says something changed.
        self.timer = QTimer(self)  # kept for callers that stop it; no longer started
        self.timer.timeout.connect(self.poll)
        self.watcher = None
        if poll and os.name == 'nt':
            self.timer.start(1000)  # Windows keeps asking every second, as before
            QTimer.singleShot(0, self.poll)
        elif poll:
            self.watcher = ChangeWatcher(path, self)
            self.watcher.changed.connect(self.poll)
            self.watcher.start()
            QTimer.singleShot(0, self.poll)

    def stop_polling(self):
        self.timer.stop()
        if self.watcher:
            self.watcher.stop()

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
        if self.tasks.closing:
            return
        if self.polling:
            self.repoll = True  # read again when this one finishes, so the change is not missed
            return
        self.polling = True
        port = self.config['port']

        def read():
            return Status(self.service.health(port),
                          runtime.call(self.path, {'command': 'panel-status'}, launch=False),
                          runtime.call(self.path, {'command': 'stt-status'}, launch=False),
                          download_status.current())

        def again():
            self.polling = False
            if self.repoll:
                self.repoll = False
                QTimer.singleShot(0, self.poll)

        def apply(status):
            again()
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
            again()
            self.status = Status(error=str(error))
            self.status_changed.emit(self.status)

        self.tasks.run(read, apply, failed=failed, background=True)

    @property
    def windows(self):
        return os.name == 'nt'
