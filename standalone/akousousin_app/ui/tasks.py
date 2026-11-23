# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 John Goodman
"""Run blocking work off the GUI thread.

Workers never touch widgets. Each result returns to the GUI thread through a
queued signal, and nothing is delivered once the panel starts closing, so a
late worker cannot reach a widget that Qt has already destroyed.
"""
import threading

from PySide6.QtCore import QObject, Qt, Signal, Slot


class Tasks(QObject):
    finished = Signal(object, object, object, object, object)  # key, done, value, error, failed
    busy_changed = Signal(str, bool)
    failed = Signal(object)    # errors with no handler of their own
    idle = Signal()            # no foreground work remains

    def __init__(self, parent=None):
        super().__init__(parent)
        self.closing = False
        self.active = set()        # foreground keys
        self.threads = set()
        self.lock = threading.Lock()
        self.finished.connect(self._deliver, Qt.QueuedConnection)

    def busy(self, key=None):
        return bool(self.active) if key is None else key in self.active

    def run(self, work, done=None, *, failed=None, key=None, background=False):
        """Start ``work()``; return False if closing or ``key`` is already running."""
        if self.closing:
            return False
        if not background:
            key = key or 'task'
            if key in self.active:
                return False
            self.active.add(key)
            self.busy_changed.emit(key, True)

        def target():
            try:
                value, error = work(), None
            except Exception as exc:  # delivered to the GUI thread
                value, error = None, exc
            with self.lock:
                self.threads.discard(threading.current_thread())
                if not self.closing:
                    self.finished.emit(None if background else key, done, value, error, failed)

        thread = threading.Thread(target=target, daemon=True, name='akousousin-ui-' + (key or 'poll'))
        with self.lock:
            self.threads.add(thread)
        thread.start()
        return True

    @Slot(object, object, object, object, object)
    def _deliver(self, key, done, value, error, failed):
        if self.closing:
            return
        if key is not None:
            self.active.discard(key)
            self.busy_changed.emit(key, False)
        try:
            if error is not None:
                (failed or self.failed.emit)(error)
            elif done is not None:
                done(value)
        except Exception as exc:
            self.failed.emit(exc)
        if key is not None and not self.active:
            self.idle.emit()

    def shutdown(self, timeout=2.0):
        """Stop delivering results and give running work a moment to finish."""
        with self.lock:
            self.closing = True
            threads = list(self.threads)
        for thread in threads:
            thread.join(timeout / max(1, len(threads)))
