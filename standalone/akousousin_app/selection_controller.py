# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Resident ownership of read/stop and its optional desktop shortcut session."""
import threading
from . import selection


class Selection:
    def __init__(self, path):
        self.path = path
        self.lock = threading.RLock()
        self.thread = self.shortcuts = None
        self.cancelled = threading.Event()
        self.state = 'Ready to read selected text'
        self.closed = False

    def status(self):
        with self.lock:
            shortcuts = self.shortcuts
            return {'reading': bool(self.thread and self.thread.is_alive()), 'state': self.state,
                    'shortcuts_enabled': bool(shortcuts and shortcuts.enabled),
                    'shortcut_state': shortcuts.status if shortcuts else 'Reading shortcuts are disabled'}

    def toggle(self, clipboard=False):
        with self.lock:
            if self.closed:
                return
            if self.thread and self.thread.is_alive():
                self.stop()
                return
            self.cancelled = threading.Event()
            self.state = 'Reading copied text…' if clipboard else 'Reading selected text…'
            def read():
                try:
                    selection.toggle(self.path, clipboard=clipboard, cancelled=self.cancelled)
                    self.state = 'Reading stopped' if self.cancelled.is_set() else 'Reading finished'
                except InterruptedError:
                    self.state = 'Reading stopped'
                except Exception as error:
                    self.state = str(error)
                    selection.notify(str(error))
            self.thread = threading.Thread(target=read, daemon=True)
            self.thread.start()

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.state = 'Stopping reading…'
        self.cancelled.set()

    def enable(self):
        self.disable()
        from .selection_shortcuts import ReadingShortcuts
        self.shortcuts = ReadingShortcuts(self.toggle, self.stop)
        self.shortcuts.start()

    def disable(self):
        if self.shortcuts:
            self.shortcuts.close()
            self.shortcuts = None
        self.stop()

    def close(self):
        self.closed = True
        self.disable()
        if self.thread:
            self.thread.join(12)
